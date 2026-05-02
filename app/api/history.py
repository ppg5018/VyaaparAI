import logging
import time
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, HTTPException

from app.models import HistoryResponse, HistoryScore
from app.database import supabase

logger = logging.getLogger(__name__)

router = APIRouter()

MAX_DB_ATTEMPTS = 2


def _execute_with_retry(operation: Callable[[], Any], *, business_id: str, label: str) -> Any:
    """Run a Supabase operation with one retry for transient transport failures."""
    last_exc: Exception | None = None
    for attempt in range(1, MAX_DB_ATTEMPTS + 1):
        try:
            return operation()
        except Exception as exc:
            last_exc = exc
            if attempt < MAX_DB_ATTEMPTS:
                logger.warning(
                    "[history] %s failed for business_id=%s (attempt %d/%d): %s; retrying",
                    label, business_id, attempt, MAX_DB_ATTEMPTS, exc,
                )
                time.sleep(0.2)

    assert last_exc is not None
    raise last_exc


def _empty_history(business_id: str) -> HistoryResponse:
    return HistoryResponse(business_id=business_id, count=0, scores=[])


@router.get("/history/{business_id}", response_model=HistoryResponse)
def get_history(business_id: str, limit: int = 12) -> HistoryResponse:
    """Return the last N health score records for a business, newest first."""
    # 1. Validate business exists
    try:
        biz = _execute_with_retry(
            lambda: supabase.table("businesses").select("id").eq("id", business_id).execute(),
            business_id=business_id,
            label="business lookup",
        )
    except Exception as exc:
        logger.warning(
            "[history] business lookup failed (non-fatal) for business_id=%s: %s",
            business_id, exc,
        )
        return _empty_history(business_id)

    if not biz.data:
        logger.error("[history] business_id=%s not found", business_id)
        raise HTTPException(status_code=404, detail=f"Business {business_id} not found")

    limit = max(1, min(52, limit))

    # 2. Query history, newest first
    try:
        result = _execute_with_retry(
            lambda: (
                supabase.table("health_scores")
                .select("*")
                .eq("business_id", business_id)
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
            ),
            business_id=business_id,
            label="history query",
        )
    except Exception as exc:
        logger.warning(
            "[history] history query failed (non-fatal) for business_id=%s: %s",
            business_id, exc,
        )
        return _empty_history(business_id)

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
        for row in (result.data or [])
    ]

    return HistoryResponse(
        business_id=business_id,
        count=len(scores),
        scores=scores,
    )
