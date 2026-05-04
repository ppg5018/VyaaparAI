"""Cheap preview pipeline for the onboarding preferences form.

Runs only the cheap stages of the full competitor pipeline (Nearby Search +
Haiku sub-category tagging) so the frontend can show live counts as the user
adjusts the radius / sub-category / review-range filters. No Apify, no
Cohere, no embeddings — those run only on /generate-report.

Cached in `competitor_preview_cache` keyed on (place_id, radius_m) with a
1-hour TTL so slider drags don't burn Google Places quota.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

from app.database import supabase
from app.services import competitor_pipeline, google_places

logger = logging.getLogger(__name__)

PREVIEW_TTL_HOURS = 1
REVIEW_THRESHOLDS = [5, 20, 50, 100, 200]
TOP_EXAMPLES_LIMIT = 5


def _compute_review_buckets(candidates: list[dict]) -> dict[str, int]:
    """Count how many candidates clear each review-count threshold."""
    buckets: dict[str, int] = {f"{t}+": 0 for t in REVIEW_THRESHOLDS}
    for c in candidates:
        rc = c.get("review_count", 0) or 0
        for t in REVIEW_THRESHOLDS:
            if rc >= t:
                buckets[f"{t}+"] += 1
    return buckets


def _compute_subcategory_counts(
    candidates: list[dict], tags: dict[str, str]
) -> dict[str, int]:
    """Count candidates per sub-category tag (excluding the user's own '__me__')."""
    counts: dict[str, int] = {}
    for c in candidates:
        pid = c.get("place_id")
        tag = tags.get(pid) if pid else None
        if not tag:
            continue
        counts[tag] = counts.get(tag, 0) + 1
    return counts


def _top_examples(
    candidates: list[dict], tags: dict[str, str], limit: int = TOP_EXAMPLES_LIMIT
) -> list[dict]:
    """Return up to `limit` highest-review-count candidates with sub-category."""
    sorted_c = sorted(
        candidates, key=lambda c: c.get("review_count", 0) or 0, reverse=True
    )
    out: list[dict] = []
    for c in sorted_c[:limit]:
        pid = c.get("place_id")
        out.append({
            "name": c.get("name", ""),
            "place_id": pid,
            "review_count": c.get("review_count", 0) or 0,
            "rating": c.get("rating", 0.0) or 0.0,
            "sub_category": tags.get(pid) if pid else None,
        })
    return out


def _read_cache(place_id: str, radius_m: int) -> dict | None:
    """Return cached preview payload if fresh (< PREVIEW_TTL_HOURS old)."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=PREVIEW_TTL_HOURS)
    try:
        resp = (
            supabase.table("competitor_preview_cache")
            .select("payload")
            .eq("place_id", place_id)
            .eq("radius_m", radius_m)
            .gte("fetched_at", cutoff.isoformat())
            .limit(1)
            .execute()
        )
    except Exception as exc:
        logger.warning("[competitor_preview] cache read failed: %s", exc)
        return None
    if not resp.data:
        return None
    payload = resp.data[0].get("payload")
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except Exception:
            return None
    return payload


def _write_cache(place_id: str, radius_m: int, payload: dict) -> None:
    """Upsert a preview payload into the cache."""
    try:
        supabase.table("competitor_preview_cache").upsert({
            "place_id": place_id,
            "radius_m": radius_m,
            "payload": payload,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }, on_conflict="place_id,radius_m").execute()
    except Exception as exc:
        logger.warning("[competitor_preview] cache write failed: %s", exc)


def compute_preview(
    *,
    place_id: str,
    lat: float,
    lng: float,
    category: str,
    my_name: str,
    radius_m: int,
) -> dict:
    """Build the preview payload (or return a cached copy)."""
    cached = _read_cache(place_id, radius_m)
    if cached is not None:
        logger.info("[competitor_preview] cache HIT place_id=%s radius=%d", place_id, radius_m)
        return cached

    logger.info("[competitor_preview] cache MISS place_id=%s radius=%d", place_id, radius_m)
    candidates = google_places.get_nearby_competitors(
        lat=lat, lng=lng, category=category,
        radius=radius_m, exclude_place_id=place_id,
    )

    tags = competitor_pipeline._tag_subcategories(
        parent_category=category, my_name=my_name, candidates=candidates,
    )

    payload = {
        "radius_m": radius_m,
        "total_candidates": len(candidates),
        "review_buckets": _compute_review_buckets(candidates),
        "subcategory_counts": _compute_subcategory_counts(candidates, tags),
        "top_examples": _top_examples(candidates, tags),
        "own_subcategory": tags.get("__me__") if tags else None,
    }
    _write_cache(place_id, radius_m, payload)
    return payload
