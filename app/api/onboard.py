import logging
import uuid

from fastapi import APIRouter, HTTPException, Query
from postgrest.exceptions import APIError

from app.models import OnboardRequest, OnboardResponse
from app.database import supabase
from app.services import google_places

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/search-places")
def search_places(q: str = Query(..., min_length=2)) -> dict:
    """Return Google Places autocomplete suggestions for a business name query."""
    suggestions = google_places.autocomplete_places(q)
    return {"suggestions": suggestions}


@router.get("/businesses/by-user/{user_id}")
def get_business_by_user(user_id: str) -> dict:
    """Return the most recently onboarded business for a given Supabase user_id."""
    result = (
        supabase.table("businesses")
        .select("id, name, place_id, category, owner_name")
        .eq("user_id", user_id)
        .eq("is_active", True)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="No business found for this user")
    row = result.data[0]
    return {"business_id": row["id"], **{k: row[k] for k in ("name", "place_id", "category", "owner_name")}}


@router.post("/onboard", response_model=OnboardResponse, status_code=201)
def onboard_business(req: OnboardRequest) -> OnboardResponse:
    """Register a new business and optionally verify its Google Place ID."""
    google_verified_name = req.name

    # 1. Resolve place_id — use provided value, auto-lookup by name, or generate placeholder
    resolved_place_id = req.place_id
    if not resolved_place_id:
        logger.info("[onboard] No place_id provided — searching by name: %s", req.name)
        resolved_place_id = google_places.find_place_by_name(req.name)
        if resolved_place_id:
            logger.info("[onboard] Auto-resolved place_id=%s for '%s'", resolved_place_id, req.name)
        else:
            resolved_place_id = f"manual_{uuid.uuid4().hex}"
            logger.info("[onboard] Name lookup failed — using placeholder %s", resolved_place_id)

    # 2. Fetch and verify via Google Places (skip for manual placeholders)
    if not resolved_place_id.startswith("manual_"):
        try:
            biz_details = google_places.get_business_details(resolved_place_id)
            google_verified_name = biz_details["name"]
        except ValueError as exc:
            logger.error("[onboard] place_id=%s invalid: %s", resolved_place_id, exc)
            raise HTTPException(status_code=400, detail=str(exc))
        except RuntimeError as exc:
            logger.error("[onboard] place_id=%s Google API unavailable: %s", resolved_place_id, exc)
            raise HTTPException(
                status_code=503, detail="Google Places API unavailable — try again later"
            )

        # 3. Check for duplicate. If the existing row is an orphan (no user_id)
        # and the caller supplied one, adopt it instead of 409-ing — this is
        # what real users will hit when the row was created by a pre-auth flow,
        # seed data, or another pipeline. If the existing row already belongs
        # to someone else, refuse so we don't transfer ownership silently.
        existing = (
            supabase.table("businesses").select("id, user_id")
            .eq("place_id", resolved_place_id).execute()
        )
        if existing.data:
            existing_row = existing.data[0]
            existing_id = existing_row["id"]
            existing_uid = existing_row.get("user_id")
            if req.user_id and not existing_uid:
                supabase.table("businesses").update(
                    {"user_id": req.user_id}
                ).eq("id", existing_id).execute()
                logger.info(
                    "[onboard] adopted orphan business_id=%s for user_id=%s",
                    existing_id, req.user_id,
                )
                return OnboardResponse(
                    business_id=existing_id,
                    name=req.name,
                    place_id=resolved_place_id,
                    google_verified_name=google_verified_name,
                )
            logger.warning(
                "[onboard] place_id=%s already exists as business_id=%s (owned=%s)",
                resolved_place_id, existing_id, bool(existing_uid),
            )
            raise HTTPException(
                status_code=409,
                detail={"error": "Business already onboarded", "business_id": existing_id},
            )

    # 4. Insert
    effective_place_id = resolved_place_id

    try:
        insert_payload = {
            "name": req.name,
            "place_id": effective_place_id,
            "category": req.category,
            "owner_name": req.owner_name,
            "is_active": True,
        }
        if req.user_id:
            insert_payload["user_id"] = req.user_id
        result = supabase.table("businesses").insert(insert_payload).execute()
    except APIError as exc:
        logger.error("[onboard] DB insert failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to save business — database error")

    row = result.data[0]

    logger.info("[onboard] Registered business_id=%s name=%s", row["id"], req.name)
    return OnboardResponse(
        business_id=row["id"],
        name=row["name"],
        place_id=row["place_id"],
        google_verified_name=google_verified_name,
    )
