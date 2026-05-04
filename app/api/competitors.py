"""Manual competitor management + onboarding preview.

Lets a user pin their own competitors (via Google Place ID) so they survive
the auto-discovery pipeline's 7-day rebuild and always lead the competitor list.

Also exposes GET /competitors/preview/{business_id} — a cheap variant of the
pipeline (Nearby Search + Haiku tagging only) used by the onboarding
preferences form to show live counts as the user adjusts filters.
"""
import logging

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.database import supabase
from app.models import CompetitorPreviewResponse
from app.services import competitor_pipeline, competitor_preview, google_places

ALLOWED_RADII = (500, 800, 1000, 1500, 2000)

logger = logging.getLogger(__name__)

router = APIRouter()


class AddCompetitorRequest(BaseModel):
    place_id: str = Field(..., min_length=1)


@router.get(
    "/competitors/preview/{business_id}",
    response_model=CompetitorPreviewResponse,
)
def preview_competitors(
    business_id: str,
    radius_m: int = Query(800),
) -> CompetitorPreviewResponse:
    if radius_m not in ALLOWED_RADII:
        raise HTTPException(
            status_code=422,
            detail=f"radius_m must be one of {ALLOWED_RADII}",
        )
    """Cheap preview of nearby candidates — for the onboarding preferences form.

    Runs Nearby Search + Haiku sub-category tag only. Cached 1h per
    (place_id, radius_m) so slider drags don't burn quota. Apify + Cohere
    are NOT run here — those run only on /generate-report.
    """
    biz_resp = (
        supabase.table("businesses")
        .select("id, place_id, category, name")
        .eq("id", business_id)
        .execute()
    )
    if not biz_resp.data:
        raise HTTPException(status_code=404, detail="Business not found")
    biz = biz_resp.data[0]

    place_id = biz["place_id"]
    if not place_id or place_id.startswith("manual_"):
        return CompetitorPreviewResponse(
            radius_m=radius_m, total_candidates=0,
            review_buckets={"5+": 0, "20+": 0, "50+": 0, "100+": 0, "200+": 0},
            subcategory_counts={}, top_examples=[], own_subcategory=None,
        )

    try:
        details = google_places.get_business_details(place_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    payload = competitor_preview.compute_preview(
        place_id=place_id,
        lat=details["lat"],
        lng=details["lng"],
        category=biz["category"],
        my_name=biz["name"],
        radius_m=radius_m,
    )
    return CompetitorPreviewResponse(**payload)


@router.post("/competitors/{business_id}", status_code=201)
def add_competitor(business_id: str, req: AddCompetitorRequest) -> dict:
    """Pin a Google Place ID as a manual competitor for this business.

    Re-adding an existing competitor is a no-op upsert (idempotent).
    """
    try:
        competitor = competitor_pipeline.add_manual_competitor(business_id, req.place_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        logger.exception("[competitors] add failed for %s/%s", business_id, req.place_id)
        raise HTTPException(status_code=500, detail=f"Failed to add competitor: {exc}")
    return {"competitor": competitor}


@router.delete("/competitors/{business_id}/{competitor_pid}", status_code=200)
def remove_competitor(business_id: str, competitor_pid: str) -> dict:
    """Remove a manual competitor. 404 if not found."""
    removed = competitor_pipeline.remove_manual_competitor(business_id, competitor_pid)
    if not removed:
        raise HTTPException(status_code=404, detail="Manual competitor not found")
    return {"removed": True, "place_id": competitor_pid}
