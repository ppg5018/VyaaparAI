import math
import logging
from datetime import datetime, timedelta, timezone

from app.config import (
    REVIEW_WEIGHT,
    COMPETITOR_WEIGHT,
    POS_WEIGHT,
    HEALTHY_THRESHOLD,
    WATCH_THRESHOLD,
    NO_COMPETITORS_NEUTRAL,
    NO_POS_DATA_NEUTRAL,
    REVIEW_HALFLIFE_MONTHS,
    REVIEW_VELOCITY_LOOKBACK_MONTHS,
    REVIEW_VELOCITY_FULL_MARKS_RATE,
    CATEGORY_POS_THRESHOLDS,
    DEFAULT_POS_THRESHOLDS,
)
from app.services.review_credibility import credibility_weight

logger = logging.getLogger(__name__)

_DAYS_PER_MONTH = 30.44


def compute_velocity(
    dated_reviews: list,
    now: datetime | None = None,
    weighted: bool = False,
) -> float:
    """Return reviews per month over the last REVIEW_VELOCITY_LOOKBACK_MONTHS.

    dated_reviews: list of dicts with a ``published_at`` datetime field.
    Returns 0.0 if no dated reviews are provided.

    When ``weighted`` is True, each review counts by its credibility weight
    (Local Guides + power reviewers up-weighted, single-review accounts
    down-weighted). Used internally by review_score for scoring; the caller
    in report.py passes weighted=False so the user-facing reviews_per_month
    figure stays a literal count.
    """
    if not dated_reviews:
        return 0.0
    if now is None:
        now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=REVIEW_VELOCITY_LOOKBACK_MONTHS * _DAYS_PER_MONTH)
    total = 0.0
    for r in dated_reviews:
        pub = r.get("published_at") if isinstance(r, dict) else None
        if not isinstance(pub, datetime):
            continue
        if pub.tzinfo is None:
            pub = pub.replace(tzinfo=timezone.utc)
        if pub >= cutoff:
            total += credibility_weight(r) if weighted else 1.0
    return total / REVIEW_VELOCITY_LOOKBACK_MONTHS


def _velocity_pts(velocity: float) -> float:
    """Map reviews/month to 0–25 pts. Full marks at REVIEW_VELOCITY_FULL_MARKS_RATE."""
    return min(25.0, (velocity / REVIEW_VELOCITY_FULL_MARKS_RATE) * 25.0)


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
    classified_reviews: list | None = None,
    now: datetime | None = None,
) -> int:
    """Compute 0-100 review quality score from Google Places data.

    When ``classified_reviews`` is supplied (from review_classifier), the trend
    sub-score uses Claude-rated sentiment instead of star ratings. This catches
    the common Indian review pattern of 4★ with strongly negative text.

    When ``all_reviews_with_dates`` is supplied, the volume sub-score uses a
    time-decayed weighted count so recent reviews count more than stale ones.
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
        # Velocity (reviews/month) is a stronger health signal than raw count.
        # Credibility-weighted internally so single-review fake accounts
        # contribute less and Local Guides contribute more.
        velocity = compute_velocity(all_reviews_with_dates, now, weighted=True)
        volume_pts = _velocity_pts(velocity)
        logger.debug(
            "review_score: weighted velocity=%.2f reviews/month → volume_pts=%.1f",
            velocity, volume_pts,
        )
    else:
        volume_pts = min(25, math.log10(max(total_reviews, 1)) * 10)

    if classified_reviews:
        # Credibility-weighted sentiment average. Each classified entry
        # carries its source review's reviewer profile fields (set by
        # review_classifier.classify_reviews).
        weighted_sum = 0.0
        weight_total = 0.0
        for c in classified_reviews:
            score = c.get("sentiment_score")
            if not score:
                continue
            w = credibility_weight(c)
            weighted_sum += float(score) * w
            weight_total += w
        if weight_total > 0:
            sentiment_avg = weighted_sum / weight_total
            trend_pts = (sentiment_avg / 5.0) * 20
            logger.debug(
                "review_score: weighted Claude sentiment avg=%.2f over %d reviews (weight_total=%.1f)",
                sentiment_avg, len(classified_reviews), weight_total,
            )
        else:
            trend_pts = 10
    elif recent_reviews:
        # Fallback: credibility-weighted star average over up to 50 reviews
        sample = recent_reviews[:50]
        weighted_sum = 0.0
        weight_total = 0.0
        for r in sample:
            w = credibility_weight(r)
            weighted_sum += float(r["rating"]) * w
            weight_total += w
        if weight_total > 0:
            recent_avg = weighted_sum / weight_total
            trend_pts = (recent_avg / 5.0) * 20
        else:
            trend_pts = 10
    else:
        trend_pts = 10

    total = int(quality_pts + volume_pts + trend_pts)

    logger.debug(
        "review_score: rating=%.1f reviews=%d quality=%.2f volume=%.2f trend=%.2f → %d",
        rating, total_reviews, quality_pts, volume_pts, trend_pts, total,
    )

    return max(0, min(100, total))


def competitor_score(my_rating: float, competitors: list) -> int:
    """Compute 0-100 competitive position score vs nearby businesses.

    Pipeline v2: `competitors` is the similarity-filtered list from
    `competitor_pipeline.run()`. Empty list = no relevant competitors found
    (similarity below threshold or hard filters wiped everyone) → neutral 65.

    Score formula unchanged from v1: rating delta × 30, recentered at 60.
    """
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


def _revenue_pts(trend: float, thresholds: dict) -> float:
    """Map a revenue trend % to 0–50 pts using category-specific bands.

    Two linear zones:
      [growth_neutral, growth_full]  → 25–50 pts  (good-to-great range)
      [growth_floor,   growth_neutral] → 0–25 pts  (bad-to-acceptable range)
    """
    gf  = thresholds["growth_full"]
    gn  = thresholds["growth_neutral"]
    gfl = thresholds["growth_floor"]

    if trend >= gf:
        return 50.0
    if trend >= gn:
        span = gf - gn
        return 25.0 + 25.0 * (trend - gn) / span if span else 25.0
    if trend >= gfl:
        span = gn - gfl
        return 25.0 * (trend - gfl) / span if span else 0.0
    return 0.0


def _repeat_pts(repeat_rate_trend: float | None) -> float:
    """Map repeat-customer rate trend (%) to 0–20 pts.

    Trend > 5%: customers returning more often — strong health signal.
    Trend < -15%: sharp churn — early warning of deeper problems.
    No data: neutral 10 pts so absence of the column doesn't penalise.
    """
    if repeat_rate_trend is None:
        return 10.0  # neutral when column not present in POS data
    if repeat_rate_trend > 5:
        return 20.0
    if repeat_rate_trend >= -5:
        return 14.0
    if repeat_rate_trend >= -15:
        return 7.0
    return 2.0  # sharp decline


def _multi_window_revenue_pts(signals: dict, thresholds: dict) -> float | None:
    """Score revenue across 7-vs-28 (acute), 30-vs-30 (current), 90-vs-90 (chronic).

    Returns the worst available 0–50 band score, with one carve-out:
    if the worst window is acute and both the current and chronic windows
    are at-or-above neutral (25 pts midpoint), drop the acute reading as
    week-on-week noise and use min(current, chronic) instead. This stops
    a single bad week — e.g. a closed weekend or post-festival lull —
    from cratering the POS score.

    Returns None when no window is computable (caller falls back to neutral).
    """
    acute = signals.get("revenue_trend_acute_pct")
    current = signals.get("revenue_trend_pct")
    chronic = signals.get("revenue_trend_chronic_pct")

    pts: dict[str, float] = {}
    if acute is not None:
        pts["acute"] = _revenue_pts(acute, thresholds)
    if current is not None:
        pts["current"] = _revenue_pts(current, thresholds)
    if chronic is not None:
        pts["chronic"] = _revenue_pts(chronic, thresholds)

    if not pts:
        return None

    worst_window = min(pts, key=pts.get)
    worst = pts[worst_window]

    # Acute-noise suppression — only when current AND chronic are both healthy
    if worst_window == "acute" and "current" in pts and "chronic" in pts:
        if pts["current"] >= 25.0 and pts["chronic"] >= 25.0:
            suppressed = min(pts["current"], pts["chronic"])
            logger.debug(
                "pos_score: acute=%.1f suppressed (current=%.1f chronic=%.1f both ≥25) → %.1f",
                worst, pts["current"], pts["chronic"], suppressed,
            )
            return suppressed

    logger.debug(
        "pos_score: window pts=%s worst=%s(%.1f)", pts, worst_window, worst,
    )
    return worst


def pos_score(signals: dict, category: str = "") -> int:
    """Compute 0-100 POS health score from revenue trend, inventory, AOV, and repeat rate.

    Weights: revenue (0–40) + inventory (0–25) + AOV (0–15) + repeat rate (0–20) = 100.
    Uses category-specific growth bands so a pharmacy staying flat is not penalised
    the same as a retail store staying flat.
    """
    if not signals:
        return NO_POS_DATA_NEUTRAL

    trend = signals.get("revenue_trend_pct")

    if trend is None:
        logger.debug("pos_score: no revenue_trend_pct — returning neutral %d", NO_POS_DATA_NEUTRAL)
        return NO_POS_DATA_NEUTRAL

    thresholds = CATEGORY_POS_THRESHOLDS.get(category, DEFAULT_POS_THRESHOLDS)

    # Revenue trend (0–40, scaled from the 0–50 band function).
    # Multi-window when acute/chronic are available — falls back cleanly
    # to the single-window 30-vs-30 reading on short uploads.
    multi = _multi_window_revenue_pts(signals, thresholds)
    band_pts = multi if multi is not None else _revenue_pts(trend, thresholds)
    revenue_pts = max(0.0, min(40.0, band_pts * 0.8))

    # Inventory health (0–25)
    slow_count = len(signals.get("slow_categories", []))
    if slow_count == 0:
        inventory_pts = 25
    elif slow_count == 1:
        inventory_pts = 17
    elif slow_count == 2:
        inventory_pts = 8
    else:
        inventory_pts = 0

    # AOV health (0–15)
    aov = signals.get("aov_direction")
    if aov == "rising":
        aov_pts = 15
    elif aov == "stable":
        aov_pts = 9
    elif aov == "falling":
        aov_pts = 4
    else:
        aov_pts = 9  # None defaults to stable

    # Repeat customer rate trend (0–20)
    repeat_pts = _repeat_pts(signals.get("repeat_rate_trend"))

    total = int(revenue_pts + inventory_pts + aov_pts + repeat_pts)
    result = max(0, min(100, total))

    logger.debug(
        "pos_score: category=%s trend=%.1f rev=%.1f inv=%d aov=%d repeat=%.0f → %d",
        category, trend, revenue_pts, inventory_pts, aov_pts, repeat_pts, result,
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
