"""
Reviewer-credibility weighting.

Apify's Google Maps actor surfaces two reviewer-profile signals we trust:
  - reviewerNumberOfReviews: how many reviews this person has written
  - isLocalGuide: whether Google has tagged them as a Local Guide

In the Indian context, a one-shot account leaving a single 1★ tirade
(or a single 5★ rave) is far more likely to be coerced/fake than a
200-review Local Guide. We down-weight the former and up-weight the
latter when computing review-derived health signals.

The weight is multiplicative, applied to the review's contribution to
sentiment averages and velocity counting.
"""
from __future__ import annotations


def _safe_int(v) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def credibility_weight(review: dict) -> float:
    """Return a multiplicative weight in [0.5, 1.5] for one review.

    Surfaced fields (set by apify_reviews):
      reviewer_review_count: int | None  — None means unknown
      reviewer_is_local_guide: bool

    Buckets:
      1.5 — power reviewer (Local Guide AND 200+ reviews)
      1.2 — credible (Local Guide OR 200+ reviews, but not both)
      1.0 — neutral / unknown
      0.5 — likely fake/coerced (count present AND < 5 lifetime reviews)

    Absent fields default to neutral 1.0 — we only penalise when we have
    positive evidence of a low review count.
    """
    if not isinstance(review, dict):
        return 1.0

    count_raw = review.get("reviewer_review_count")
    has_count = count_raw is not None
    count = _safe_int(count_raw)
    is_guide = bool(review.get("reviewer_is_local_guide"))

    is_power = count >= 200
    if is_power and is_guide:
        return 1.5
    if is_power or is_guide:
        return 1.2
    if has_count and count < 5:
        return 0.5
    return 1.0
