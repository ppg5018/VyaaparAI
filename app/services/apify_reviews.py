"""
Apify Google Maps Reviews scraper integration with L2 cache.

Bypasses Google's 5-review API ceiling by running the
`compass/google-maps-reviews-scraper` actor on Apify, then caches results
in Supabase tables `external_reviews` + `review_syncs` so we don't hit
Apify on every dashboard load.

Cache TTLs:
  - 7 days for the user's own business reviews
  - 30 days for competitor reviews

Cost (April 2026): ~$0.30 per 1,000 reviews scraped.
Free tier: $5/month credits ≈ 17,000 reviews/month free.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import requests

from app.config import (
    APIFY_REVIEWS_ACTOR,
    APIFY_TOKEN,
    REVIEW_CACHE_TTL_DAYS_COMPETITOR,
    REVIEW_CACHE_TTL_DAYS_OWN,
)
from app.database import supabase

logger = logging.getLogger(__name__)

APIFY_BASE_URL = "https://api.apify.com/v2"
DEFAULT_MAX_REVIEWS = 50
APIFY_TIMEOUT_SECONDS = 120


# ─── Cache helpers ─────────────────────────────────────────────────────────────


def _is_fresh(place_id: str, max_age_days: int) -> bool:
    """Return True if the last sync for this place_id is within max_age_days."""
    try:
        res = (
            supabase.table("review_syncs")
            .select("last_synced_at")
            .eq("place_id", place_id)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        logger.warning("[apify] sync lookup failed for %s: %s", place_id, exc)
        return False

    if not res.data:
        return False

    last_synced = res.data[0]["last_synced_at"]
    if isinstance(last_synced, str):
        # Handle Postgres timestamp (with or without TZ suffix)
        try:
            last_synced_dt = datetime.fromisoformat(last_synced.replace("Z", "+00:00"))
        except ValueError:
            return False
    else:
        last_synced_dt = last_synced

    if last_synced_dt.tzinfo is None:
        last_synced_dt = last_synced_dt.replace(tzinfo=timezone.utc)

    age = datetime.now(timezone.utc) - last_synced_dt
    return age < timedelta(days=max_age_days)


def _load_from_cache(place_id: str, limit: int = 200) -> list[dict]:
    """Return cached reviews for a place_id, newest first, with relative_time computed."""
    try:
        res = (
            supabase.table("external_reviews")
            .select("rating, text, author_name, posted_at, owner_reply, review_id, raw")
            .eq("place_id", place_id)
            .order("posted_at", desc=True)
            .limit(limit)
            .execute()
        )
    except Exception as exc:
        logger.warning("[apify] cache load failed for %s: %s", place_id, exc)
        return []

    rows = res.data or []
    for r in rows:
        r["relative_time"] = _relative_time_from_iso(r.get("posted_at"))
        # Surface reviewer-credibility signals from the raw JSONB blob without
        # requiring a schema migration. Preserve None when absent so weighting
        # falls back to neutral; preserve a truthful 0 to flag fake accounts.
        raw = r.get("raw") or {}
        count = raw.get("reviewerNumberOfReviews")
        if count is None:
            count = raw.get("reviewer_review_count")
        r["reviewer_review_count"] = count
        r["reviewer_is_local_guide"] = bool(
            raw.get("isLocalGuide") or raw.get("reviewer_is_local_guide")
        )
    return rows


def _upsert_reviews(place_id: str, reviews: list[dict]) -> int:
    """Upsert reviews into external_reviews (no duplicates due to UNIQUE constraint)."""
    if not reviews:
        return 0
    rows = []
    for r in reviews:
        rid = r.get("review_id") or r.get("reviewId") or r.get("id")
        if not rid:
            continue
        rows.append({
            "place_id":    place_id,
            "review_id":   str(rid),
            "source":      "google",
            "rating":      r.get("rating") or r.get("stars"),
            "text":        (r.get("text") or "")[:5000],
            "author_name": (r.get("author_name") or r.get("name") or "")[:200],
            "posted_at":   r.get("posted_at") or r.get("publishedAtDate") or r.get("publishAt"),
            "owner_reply": (r.get("owner_reply") or r.get("responseFromOwnerText") or "")[:5000] or None,
            "raw":         r,
        })

    if not rows:
        return 0

    try:
        supabase.table("external_reviews") \
            .upsert(rows, on_conflict="place_id,review_id") \
            .execute()
    except Exception as exc:
        logger.warning("[apify] upsert failed for %s: %s", place_id, exc)
        return 0
    return len(rows)


def _update_sync_marker(place_id: str, total_reviews: int) -> None:
    try:
        supabase.table("review_syncs").upsert({
            "place_id":       place_id,
            "last_synced_at": datetime.now(timezone.utc).isoformat(),
            "total_reviews":  total_reviews,
            "source":         "apify",
        }, on_conflict="place_id").execute()
    except Exception as exc:
        logger.warning("[apify] sync marker update failed for %s: %s", place_id, exc)


# ─── Apify HTTP call ───────────────────────────────────────────────────────────


def parse_posted_at(iso: Optional[str]) -> Optional[datetime]:
    """Parse an ISO 8601 timestamp into a UTC-aware datetime, or None on failure."""
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _relative_time_from_iso(iso: Optional[str]) -> str:
    """Convert an ISO timestamp into a human-readable relative time string."""
    dt = parse_posted_at(iso)
    if dt is None:
        return ""
    delta = datetime.now(timezone.utc) - dt
    days = delta.days
    if days < 1:    return "today"
    if days < 7:    return f"{days} day{'s' if days > 1 else ''} ago"
    if days < 30:   return f"{days // 7} week{'s' if days // 7 > 1 else ''} ago"
    if days < 365:  return f"{days // 30} month{'s' if days // 30 > 1 else ''} ago"
    return f"{days // 365} year{'s' if days // 365 > 1 else ''} ago"


def _normalize_review(item: dict) -> dict:
    """Convert one Apify dataset item into our internal review dict shape."""
    posted_at = item.get("publishedAtDate") or item.get("publishAt")
    return {
        "review_id":     item.get("reviewId") or item.get("id") or item.get("reviewerId"),
        "rating":        item.get("stars") or item.get("rating"),
        "text":          item.get("text") or item.get("textTranslated") or "",
        "author_name":   item.get("name") or item.get("reviewerName") or "",
        "posted_at":     posted_at,
        "owner_reply":   item.get("responseFromOwnerText"),
        "relative_time": _relative_time_from_iso(posted_at),
        # Reviewer-credibility signals — used by review_credibility.weight()
        # to down-weight likely fake/coerced single-review accounts and
        # up-weight Local Guides + power reviewers. Keep None when the
        # actor didn't surface a count so the weighting falls back to neutral.
        "reviewer_review_count":    item.get("reviewerNumberOfReviews"),
        "reviewer_is_local_guide":  bool(item.get("isLocalGuide")),
    }


def _run_apify_actor(place_id: str, max_reviews: int) -> list[dict]:
    """Run the Apify actor synchronously and return a list of normalised reviews."""
    if not APIFY_TOKEN:
        logger.warning("[apify] APIFY_TOKEN not set — skipping scrape")
        return []

    url = (
        f"{APIFY_BASE_URL}/acts/{APIFY_REVIEWS_ACTOR}/run-sync-get-dataset-items"
        f"?token={APIFY_TOKEN}"
    )
    payload = {
        "placeIds":     [place_id],
        "maxReviews":   max_reviews,
        "reviewsSort":  "newest",
        "language":     "en",
        "personalData": False,
    }

    try:
        resp = requests.post(url, json=payload, timeout=APIFY_TIMEOUT_SECONDS)
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.error("[apify] actor call failed for %s: %s", place_id, exc)
        return []

    try:
        items = resp.json()
    except ValueError:
        logger.error("[apify] non-JSON response for %s", place_id)
        return []

    if not isinstance(items, list):
        logger.warning("[apify] expected list, got %s for %s", type(items).__name__, place_id)
        return []

    return [_normalize_review(item) for item in items if item.get("reviewId") or item.get("id")]


# ─── Public API ────────────────────────────────────────────────────────────────


def get_reviews(
    place_id: str,
    max_reviews: int = DEFAULT_MAX_REVIEWS,
    max_age_days: Optional[int] = None,
    is_competitor: bool = False,
    force: bool = False,
) -> list[dict]:
    """Fetch reviews for a place_id. Uses cache when fresh, hits Apify when stale.

    Args:
        place_id: Google Place ID (must start with ChIJ).
        max_reviews: Cap on reviews fetched from Apify on a cache miss.
        max_age_days: Override default TTL. Defaults to 7 (own) or 30 (competitor).
        is_competitor: Use the longer competitor TTL when None.
        force: Skip cache and always hit Apify.

    Returns:
        List of dicts: {rating, text, author_name, posted_at, owner_reply, review_id}.
        Returns whatever's in cache if Apify call fails.
    """
    if not place_id or not place_id.startswith("ChIJ"):
        return []

    ttl_days = max_age_days if max_age_days is not None else (
        REVIEW_CACHE_TTL_DAYS_COMPETITOR if is_competitor else REVIEW_CACHE_TTL_DAYS_OWN
    )

    if not force and _is_fresh(place_id, ttl_days):
        cached = _load_from_cache(place_id, limit=max_reviews)
        logger.info("[apify] cache HIT for %s — %d reviews", place_id, len(cached))
        return cached

    logger.info("[apify] cache MISS for %s — running actor", place_id)
    fresh = _run_apify_actor(place_id, max_reviews)

    if fresh:
        inserted = _upsert_reviews(place_id, fresh)
        _update_sync_marker(place_id, total_reviews=inserted)
        logger.info("[apify] synced %d new reviews for %s", inserted, place_id)
        return _load_from_cache(place_id, limit=max_reviews)

    # Apify failed — fall back to whatever's cached, even if stale
    fallback = _load_from_cache(place_id, limit=max_reviews)
    logger.warning("[apify] actor returned 0 — falling back to %d stale cache rows", len(fallback))
    return fallback
