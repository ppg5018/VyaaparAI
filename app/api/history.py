import logging

from fastapi import APIRouter, HTTPException

from app.models import HistoryResponse, HistoryScore
from app.database import supabase

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/history/{business_id}", response_model=HistoryResponse)
def get_history(business_id: str, limit: int = 12) -> HistoryResponse:
    """Return the last N health score records for a business, newest first."""
    # 1. Validate business exists
    biz = supabase.table("businesses").select("id").eq("id", business_id).execute()
    if not biz.data:
        logger.error("[history] business_id=%s not found", business_id)
        raise HTTPException(status_code=404, detail=f"Business {business_id} not found")

    limit = max(1, min(52, limit))

    # 2. Query history, newest first
    result = (
        supabase.table("health_scores")
        .select("*")
        .eq("business_id", business_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )

    scores = [
        HistoryScore(
            final_score=row["final_score"],
            review_score=row["review_score"],
            competitor_score=row["competitor_score"],
            pos_score=row["pos_score"],
            google_rating=row["google_rating"],
            insights=row["insights"],
            action=row["action"],
            created_at=row["created_at"],
        )
        for row in result.data
    ]

    return HistoryResponse(
        business_id=business_id,
        count=len(scores),
        scores=scores,
    )
