import logging

from fastapi import APIRouter, HTTPException

from app.models import OnboardRequest, OnboardResponse
from app.database import supabase
from app.services import google_places

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/onboard", response_model=OnboardResponse, status_code=201)
def onboard_business(req: OnboardRequest) -> OnboardResponse:
    """Register a new business and verify its Google Place ID."""
    # 1. Validate place_id via Google Places
    try:
        biz_details = google_places.get_business_details(req.place_id)
    except ValueError as exc:
        logger.error("[onboard] place_id=%s invalid: %s", req.place_id, exc)
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        logger.error("[onboard] place_id=%s Google API unavailable: %s", req.place_id, exc)
        raise HTTPException(
            status_code=503, detail="Google Places API unavailable — try again later"
        )

    # 2. Check for duplicate
    existing = (
        supabase.table("businesses").select("id").eq("place_id", req.place_id).execute()
    )
    if existing.data:
        existing_id = existing.data[0]["id"]
        logger.warning(
            "[onboard] place_id=%s already exists as business_id=%s",
            req.place_id, existing_id,
        )
        raise HTTPException(
            status_code=409,
            detail={"error": "Business already onboarded", "business_id": existing_id},
        )

    # 3. Insert
    result = supabase.table("businesses").insert({
        "name": req.name,
        "place_id": req.place_id,
        "category": req.category,
        "owner_name": req.owner_name,
        "is_active": True,
    }).execute()
    row = result.data[0]

    logger.info("[onboard] Registered business_id=%s name=%s", row["id"], req.name)
    return OnboardResponse(
        business_id=row["id"],
        name=row["name"],
        place_id=row["place_id"],
        google_verified_name=biz_details["name"],
    )
