import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from app.models import Competitor, ReportResponse, Review, SubScores
from app.database import supabase
from app.services import google_places, health_score, insights, pos_pipeline

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/generate-report/{business_id}", response_model=ReportResponse)
def generate_report(business_id: str) -> ReportResponse:
    """Run the full scoring and insights pipeline for a business."""
    # 1. Look up business
    biz_result = supabase.table("businesses").select("*").eq("id", business_id).execute()
    if not biz_result.data:
        logger.error("[generate-report] business_id=%s not found", business_id)
        raise HTTPException(status_code=404, detail=f"Business {business_id} not found")

    biz = biz_result.data[0]

    # 2. Fetch Google data (skip if no real Place ID was provided)
    if biz["place_id"].startswith("manual_"):
        google_data = {
            "name": biz["name"],
            "rating": 0.0,
            "total_reviews": 0,
            "lat": 0.0,
            "lng": 0.0,
            "address": "",
            "business_status": "OPERATIONAL",
            "reviews": [],
            "competitors": [],
        }
    else:
        try:
            google_data = google_places.fetch_all_data(biz["place_id"], biz["category"])
        except Exception as exc:
            logger.error(
                "[generate-report] business_id=%s Google fetch failed: %s", business_id, exc
            )
            raise HTTPException(status_code=502, detail="Failed to fetch Google data")

    # 3. POS signals — never raises
    signals = pos_pipeline.pos_signals(business_id, days=30)

    # 4. Sub-scores
    r_score = health_score.review_score(
        rating=google_data["rating"],
        total_reviews=google_data["total_reviews"],
        recent_reviews=google_data["reviews"],
    )
    c_score = health_score.competitor_score(
        my_rating=google_data["rating"],
        competitors=google_data["competitors"],
    )
    p_score = health_score.pos_score(signals)

    # 5. Final score + band
    score_result = health_score.calculate_health_score(r_score, c_score, p_score)

    # 6. Generate insights via Claude
    try:
        insights_result = insights.generate_insights(
            business_data=google_data,
            scores=score_result,
            pos_signals=signals,
        )
    except RuntimeError as exc:
        logger.error(
            "[generate-report] business_id=%s insight generation failed: %s", business_id, exc
        )
        raise HTTPException(status_code=500, detail="Insight generation failed")

    # 7. Persist to health_scores — truncate text to avoid Cloudflare 400 on large payloads
    MAX_INSIGHT = 400
    MAX_ACTION  = 600
    safe_insights = [i[:MAX_INSIGHT] for i in insights_result["insights"]]
    safe_action   = insights_result["action"][:MAX_ACTION]

    try:
        supabase.table("health_scores").insert({
            "business_id": business_id,
            "final_score": score_result["final_score"],
            "review_score": r_score,
            "competitor_score": c_score,
            "pos_score": p_score,
            "google_rating": google_data["rating"],
            "total_reviews": google_data["total_reviews"],
            "insights": safe_insights,
            "action": safe_action,
        }).execute()
    except Exception as exc:
        logger.warning(
            "[generate-report] business_id=%s DB save failed (non-fatal): %s", business_id, exc
        )

    logger.info(
        "[generate-report] business_id=%s score=%d band=%s",
        business_id, score_result["final_score"], score_result["band"],
    )

    return ReportResponse(
        business_id=business_id,
        business_name=google_data["name"],
        final_score=score_result["final_score"],
        band=score_result["band"],
        sub_scores=SubScores(
            review_score=r_score,
            competitor_score=c_score,
            pos_score=p_score,
        ),
        google_rating=google_data["rating"],
        total_reviews=google_data["total_reviews"],
        reviews=[
            Review(
                rating=r["rating"],
                text=r["text"],
                relative_time=r["relative_time"],
            )
            for r in google_data["reviews"]
        ],
        competitors=[
            Competitor(
                name=c["name"],
                rating=c["rating"],
                review_count=c["review_count"],
            )
            for c in google_data["competitors"]
        ],
        insights=insights_result["insights"],
        action=insights_result["action"],
        generated_at=datetime.now(timezone.utc).isoformat(),
    )
