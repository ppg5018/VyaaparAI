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

        # 3. Check for duplicate
        existing = (
            supabase.table("businesses").select("id").eq("place_id", resolved_place_id).execute()
        )
        if existing.data:
            existing_id = existing.data[0]["id"]
            logger.warning(
                "[onboard] place_id=%s already exists as business_id=%s",
                resolved_place_id, existing_id,
            )
            raise HTTPException(
                status_code=409,
                detail={"error": "Business already onboarded", "business_id": existing_id},
            )

    # 4. Insert
    effective_place_id = resolved_place_id

    try:
        result = supabase.table("businesses").insert({
            "name": req.name,
            "place_id": effective_place_id,
            "category": req.category,
            "owner_name": req.owner_name,
            "is_active": True,
        }).execute()
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
