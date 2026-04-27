import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException

from app.models import Competitor, CompetitorAnalysis, ReportResponse, Review, SubScores
from app.database import supabase
from app.services import apify_reviews, competitor_analysis, google_places, health_score, insights, pos_pipeline

logger = logging.getLogger(__name__)

router = APIRouter()

CACHE_TTL_HOURS = 24


def _get_fresh_cache(business_id: str) -> ReportResponse | None:
    """Return the latest cached report if it's < CACHE_TTL_HOURS old, else None.

    Reads `report_payload` (full ReportResponse JSONB) from the most recent
    `health_scores` row. Returns None if the column doesn't exist, no row is
    fresh enough, or the payload can't be parsed.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=CACHE_TTL_HOURS)).isoformat()
    try:
        res = (
            supabase.table("health_scores")
            .select("report_payload, created_at")
            .eq("business_id", business_id)
            .gte("created_at", cutoff)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        logger.warning("[generate-report] cache read failed (non-fatal): %s", exc)
        return None

    if not res.data:
        return None

    payload = res.data[0].get("report_payload")
    if not payload:
        return None

    try:
        return ReportResponse(**payload)
    except Exception as exc:
        logger.warning("[generate-report] cached payload invalid (non-fatal): %s", exc)
        return None


@router.post("/generate-report/{business_id}", response_model=ReportResponse)
def generate_report(business_id: str, force: bool = False) -> ReportResponse:
    """Run the full scoring and insights pipeline for a business.

    Args:
        business_id: UUID of the business.
        force: When False (default) and a cached report < 24h old exists,
            return the cached version. When True, always run the full pipeline.
    """
    # 0. Try cache first unless caller forced refresh
    if not force:
        cached = _get_fresh_cache(business_id)
        if cached is not None:
            logger.info("[generate-report] business_id=%s served from cache", business_id)
            return cached

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

        # 2b. Augment with Apify-scraped reviews (bypasses Google's 5-review cap).
        # Falls back to the original 5 reviews if Apify is unavailable / cache empty.
        try:
            apify_revs = apify_reviews.get_reviews(biz["place_id"], max_reviews=50, is_competitor=False)
            if apify_revs:
                google_data["reviews"] = apify_revs
                logger.info(
                    "[generate-report] business_id=%s using %d Apify reviews",
                    business_id, len(apify_revs),
                )
        except Exception as exc:
            logger.warning(
                "[generate-report] business_id=%s Apify augmentation skipped (non-fatal): %s",
                business_id, exc,
            )

    # 3. POS signals — never raises
    signals = pos_pipeline.pos_signals(business_id, days=30)

    # 4. Sub-scores
    dated_reviews = [
        {"published_at": dt}
        for dt in (
            apify_reviews.parse_posted_at(r.get("posted_at"))
            for r in google_data["reviews"]
        )
        if dt is not None
    ]
    r_score = health_score.review_score(
        rating=google_data["rating"],
        total_reviews=google_data["total_reviews"],
        recent_reviews=google_data["reviews"],
        all_reviews_with_dates=dated_reviews or None,
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

    # 6b. Competitor analysis — never raises, returns empty on failure
    comp_analysis = competitor_analysis.analyze_competitors(
        my_business=google_data,
        competitors=google_data.get("competitors", []),
    )

    # 7. Build the response
    MAX_INSIGHT = 400
    MAX_ACTION  = 600
    safe_insights = [i[:MAX_INSIGHT] for i in insights_result["insights"]]
    safe_action   = insights_result["action"][:MAX_ACTION]

    response = ReportResponse(
        business_id=business_id,
        business_name=google_data["name"],
        address=google_data.get("address", "") or "",
        category=biz.get("category", "") or "",
        owner_name=biz.get("owner_name", "") or "",
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
        insights=safe_insights,
        action=safe_action,
        competitor_analysis=CompetitorAnalysis(
            themes=comp_analysis.get("themes", []),
            opportunities=comp_analysis.get("opportunities", []),
            analyzed_count=comp_analysis.get("analyzed_count", 0),
        ),
        generated_at=datetime.now(timezone.utc).isoformat(),
    )

    # 8. Persist to health_scores — including full payload for the cache
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
            "report_payload": response.model_dump(),
        }).execute()
    except Exception as exc:
        logger.warning(
            "[generate-report] business_id=%s DB save failed (non-fatal): %s", business_id, exc
        )

    logger.info(
        "[generate-report] business_id=%s score=%d band=%s (fresh)",
        business_id, score_result["final_score"], score_result["band"],
    )

    return response
