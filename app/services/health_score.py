import math
import logging
from datetime import datetime, timezone

from app.config import (
    REVIEW_WEIGHT,
    COMPETITOR_WEIGHT,
    POS_WEIGHT,
    HEALTHY_THRESHOLD,
    WATCH_THRESHOLD,
    NO_COMPETITORS_NEUTRAL,
    NO_POS_DATA_NEUTRAL,
    REVIEW_HALFLIFE_MONTHS,
)

logger = logging.getLogger(__name__)

_DAYS_PER_MONTH = 30.44


def _weighted_review_count(
    reviews_with_dates: list,
    now: datetime,
    halflife_months: float,
) -> float:
    """Sum decay-weighted review contributions.

    Each review dict must have a ``published_at`` datetime. Reviews missing
    that field or with an unparseable value are skipped. Future-dated reviews
    (clock skew) are clamped to age 0.
    """
    total = 0.0
    for r in reviews_with_dates or []:
        published_at = r.get("published_at") if isinstance(r, dict) else None
        if not isinstance(published_at, datetime):
            continue
        if published_at.tzinfo is None:
            published_at = published_at.replace(tzinfo=timezone.utc)
        months_old = max(0.0, (now - published_at).days / _DAYS_PER_MONTH)
        total += 1.0 / (1.0 + months_old / halflife_months)
    return total


def review_score(
    rating: float,
    total_reviews: int,
    recent_reviews: list,
    all_reviews_with_dates: list | None = None,
    now: datetime | None = None,
) -> int:
    """Compute 0-100 review quality score from Google Places data.

    When ``all_reviews_with_dates`` is supplied, the volume sub-score uses a
    time-decayed weighted count so recent reviews count more than stale ones.
    Otherwise it falls back to the flat ``log10(total_reviews)`` formula so
    callers without timestamped review history are unaffected.
    """
    if not rating:
        return 0

    if recent_reviews is None:
        recent_reviews = []
    if total_reviews is None or total_reviews < 0:
        total_reviews = 0

    # Google ratings are 1–5, not 0–5; normalise within the actual range so a
    # 1-star business scores near 0 quality points rather than ~20%.
    quality_pts = ((rating - 1) / 4.0) * 55

    if all_reviews_with_dates:
        if now is None:
            now = datetime.now(timezone.utc)
        weighted_count = _weighted_review_count(
            all_reviews_with_dates, now, REVIEW_HALFLIFE_MONTHS
        )
        volume_pts = min(25, math.log10(max(weighted_count, 1)) * 10)
    else:
        volume_pts = min(25, math.log10(max(total_reviews, 1)) * 10)

    if not recent_reviews:
        trend_pts = 10
    else:
        recent_avg = sum(r["rating"] for r in recent_reviews) / len(recent_reviews)
        trend_pts = (recent_avg / 5.0) * 20

    total = int(quality_pts + volume_pts + trend_pts)

    logger.debug(
        "review_score: rating=%.1f reviews=%d quality=%.2f volume=%.2f trend=%.2f → %d",
        rating, total_reviews, quality_pts, volume_pts, trend_pts, total,
    )

    return max(0, min(100, total))


def competitor_score(my_rating: float, competitors: list) -> int:
    """Compute 0-100 competitive position score vs nearby businesses."""
    if not my_rating:
        return NO_COMPETITORS_NEUTRAL

    if not competitors:
        return NO_COMPETITORS_NEUTRAL

    competitor_ratings = [c["rating"] for c in competitors if c.get("rating", 0) > 0]

    if not competitor_ratings:
        return NO_COMPETITORS_NEUTRAL

    mean_competitor = sum(competitor_ratings) / len(competitor_ratings)
    raw_score = 60 + (my_rating - mean_competitor) * 30

    result = max(0, min(100, int(raw_score)))

    logger.debug(
        "competitor_score: my=%.1f mean_comp=%.2f raw=%.1f → %d",
        my_rating, mean_competitor, raw_score, result,
    )

    return result


def pos_score(signals: dict) -> int:
    """Compute 0-100 POS health score from revenue trend, inventory, and AOV signals."""
    if not signals:
        return NO_POS_DATA_NEUTRAL

    trend = signals.get("revenue_trend_pct")

    if trend is None:
        logger.debug("pos_score: no revenue_trend_pct — returning neutral %d", NO_POS_DATA_NEUTRAL)
        return NO_POS_DATA_NEUTRAL

    # Revenue trend (0–50)
    if trend >= 10:
        revenue_pts = 50
    elif trend >= 0:
        revenue_pts = 40 + trend
    elif trend >= -10:
        revenue_pts = 40 + (trend * 2)
    elif trend >= -30:
        revenue_pts = 20 + ((trend + 10) * 1)
    else:
        revenue_pts = 0
    revenue_pts = max(0, min(50, revenue_pts))

    # Inventory health (0–30)
    slow_count = len(signals.get("slow_categories", []))
    if slow_count == 0:
        inventory_pts = 30
    elif slow_count == 1:
        inventory_pts = 20
    elif slow_count == 2:
        inventory_pts = 10
    else:
        inventory_pts = 0

    # AOV health (0–20)
    aov = signals.get("aov_direction")
    if aov == "rising":
        aov_pts = 20
    elif aov == "stable":
        aov_pts = 12
    elif aov == "falling":
        aov_pts = 5
    else:
        aov_pts = 12  # None defaults to stable

    total = int(revenue_pts + inventory_pts + aov_pts)
    result = max(0, min(100, total))

    logger.debug(
        "pos_score: trend=%.1f rev=%.1f inv=%d aov=%d → %d",
        trend, revenue_pts, inventory_pts, aov_pts, result,
    )

    return result


def calculate_health_score(review_s: int, competitor_s: int, pos_s: int) -> dict:
    """Compute final weighted health score and band from three sub-scores."""
    final = int(
        review_s * REVIEW_WEIGHT
        + competitor_s * COMPETITOR_WEIGHT
        + pos_s * POS_WEIGHT
    )
    final = max(0, min(100, final))

    if final >= HEALTHY_THRESHOLD:
        band = "healthy"
    elif final >= WATCH_THRESHOLD:
        band = "watch"
    else:
        band = "at_risk"

    logger.info(
        "Health score computed: final=%d review=%d competitor=%d pos=%d band=%s",
        final, review_s, competitor_s, pos_s, band,
    )

    return {
        "final_score": final,
        "review_score": review_s,
        "competitor_score": competitor_s,
        "pos_score": pos_s,
        "band": band,
    }
