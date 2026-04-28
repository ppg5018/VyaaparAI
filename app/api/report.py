import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException

from app.models import (
    CategoryRevenue, Competitor, CompetitorAnalysis, PosSignals, ReportResponse,
    Review, SubScores, WeeklyRevenue,
)
from app.database import supabase
from app.services import apify_reviews, competitor_analysis, competitor_matching, google_places, health_score, insights, pos_pipeline, review_classifier
from app.services.health_score import compute_velocity

logger = logging.getLogger(__name__)

router = APIRouter()

CACHE_TTL_HOURS = 24


def _get_fresh_cache(business_id: str) -> ReportResponse | None:
    """Return the latest cached report if it's < CACHE_TTL_HOURS old, else None."""
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

        # 2c. Filter competitors — price tier + type + name + sub-category (Haiku)
        try:
            raw_count = len(google_data["competitors"])
            filtered = competitor_matching.filter_competitors(
                my_business={
                    "name": google_data["name"],
                    "category": biz.get("category", ""),
                    "price_level": google_data.get("price_level"),
                },
                competitors=google_data["competitors"],
            )
            # Cap after filtering so the matcher sees the full Google candidate list
            from app.config import MAX_COMPETITORS
            google_data["competitors"] = filtered[:MAX_COMPETITORS]
            logger.info(
                "[generate-report] business_id=%s competitor filter: %d → %d (capped at %d)",
                business_id, raw_count, len(google_data["competitors"]), MAX_COMPETITORS,
            )
        except Exception as exc:
            logger.warning(
                "[generate-report] business_id=%s competitor filter skipped (non-fatal): %s",
                business_id, exc,
            )

    # 3. POS signals — never raises
    signals = pos_pipeline.pos_signals(business_id, days=30, category=biz.get("category", ""))

    # 4. Classify reviews with Haiku — never raises, falls back to star ratings
    classified = []
    dominant_complaint = None
    if google_data["reviews"]:
        try:
            classified = review_classifier.classify_reviews(google_data["reviews"])
            dominant_complaint = review_classifier.dominant_complaint(classified)
            logger.info(
                "[generate-report] business_id=%s dominant_complaint=%s",
                business_id, dominant_complaint,
            )
        except Exception as exc:
            logger.warning(
                "[generate-report] business_id=%s review classification skipped (non-fatal): %s",
                business_id, exc,
            )

    # 5. Sub-scores
    dated_reviews = [
        {"published_at": dt}
        for dt in (
            apify_reviews.parse_posted_at(r.get("posted_at"))
            for r in google_data["reviews"]
        )
        if dt is not None
    ]
    reviews_per_month = compute_velocity(dated_reviews) if dated_reviews else None
    photo_count = google_data.get("photo_count", 0)

    r_score = health_score.review_score(
        rating=google_data["rating"],
        total_reviews=google_data["total_reviews"],
        recent_reviews=google_data["reviews"],
        all_reviews_with_dates=dated_reviews or None,
        classified_reviews=classified or None,
    )
    c_score = health_score.competitor_score(
        my_rating=google_data["rating"],
        competitors=google_data["competitors"],
    )
    p_score = health_score.pos_score(signals, category=biz.get("category", ""))

    # 6. Final score + band
    score_result = health_score.calculate_health_score(r_score, c_score, p_score)

    # 7. Generate insights via Claude Sonnet (dominant complaint injected into prompt)
    try:
        insights_result = insights.generate_insights(
            business_data=google_data,
            scores=score_result,
            pos_signals=signals,
            dominant_complaint=dominant_complaint,
            reviews_per_month=reviews_per_month,
            photo_count=photo_count,
        )
    except RuntimeError as exc:
        logger.error(
            "[generate-report] business_id=%s insight generation failed: %s", business_id, exc
        )
        raise HTTPException(status_code=500, detail="Insight generation failed")

    # 7b. Competitor analysis — never raises, returns empty on failure
    comp_analysis = competitor_analysis.analyze_competitors(
        my_business=google_data,
        competitors=google_data.get("competitors", []),
    )

    # 7c. Chart data for the dashboard (weekly revenue + revenue-by-category)
    chart = pos_pipeline.chart_data(business_id, weeks=8)

    # 8. Build the response
    MAX_INSIGHT = 400
    MAX_ACTION  = 600
    safe_insights = [i[:MAX_INSIGHT] for i in insights_result["insights"]]
    safe_action   = insights_result["action"][:MAX_ACTION]

    dominant_display = dominant_complaint.replace("_", " ") if dominant_complaint else None

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
        reviews_per_month=reviews_per_month,
        photo_count=photo_count,
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
        dominant_complaint=dominant_display,
        competitor_analysis=CompetitorAnalysis(
            themes=comp_analysis.get("themes", []),
            opportunities=comp_analysis.get("opportunities", []),
            analyzed_count=comp_analysis.get("analyzed_count", 0),
        ),
        pos_signals=PosSignals(
            revenue_trend_pct=signals.get("revenue_trend_pct"),
            slow_categories=signals.get("slow_categories", []),
            top_product=signals.get("top_product"),
            aov_direction=signals.get("aov_direction"),
            repeat_rate_pct=signals.get("repeat_rate_pct"),
            repeat_rate_trend=signals.get("repeat_rate_trend"),
        ),
        weekly_revenue=[WeeklyRevenue(**w) for w in chart.get("weekly_revenue", [])],
        revenue_by_category=[CategoryRevenue(**c) for c in chart.get("revenue_by_category", [])],
        generated_at=datetime.now(timezone.utc).isoformat(),
    )

    # 9. Persist to health_scores — including full payload for the cache
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
        "[generate-report] business_id=%s score=%d band=%s dominant_complaint=%s (fresh)",
        business_id, score_result["final_score"], score_result["band"], dominant_complaint,
    )

    return response
