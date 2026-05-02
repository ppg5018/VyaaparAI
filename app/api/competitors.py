"""Manual competitor management.

Lets a user pin their own competitors (via Google Place ID) so they survive
the auto-discovery pipeline's 7-day rebuild and always lead the competitor list.
"""
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services import competitor_pipeline

logger = logging.getLogger(__name__)

router = APIRouter()


class AddCompetitorRequest(BaseModel):
    place_id: str = Field(..., min_length=1)


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
