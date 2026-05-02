"""Competitor pipeline v2 — embeddings + similarity-search.

Orchestrates the end-to-end competitor matching flow for a /generate-report
call. Replaces the deterministic 5-signal filter that was deleted in
Session 9.

Pipeline (cheapest-first, like the old one — but now with semantic understanding):

    Google Places Nearby Search (800m)         ← discovery
       └─ ~20 raw candidates
    drop dead listings (review_count < min)    ← cheap, deterministic
       └─ statistically meaningful set
    Haiku sub-category tag (batched)           ← one cheap LLM call
       └─ drop wrong-type (ice cream parlour vs restaurant, etc.)
    Apify-fetch competitor reviews             ← already-cached when warm
       └─ 30 reviews per surviving competitor
    Cohere centroid embeddings                 ← cached on text_hash
       └─ 1 vector per business
    Cosine similarity vs my centroid           ← cheap once vectors exist
       └─ drop below SIMILARITY_THRESHOLD = 0.55
    Upsert competitor_matches with TTL         ← weekly refresh
       └─ ranked list returned to caller

Cache pattern: if `competitor_matches` has fresh rows for this business
(matched_at > now - COMPETITOR_MATCH_TTL_DAYS), we skip the entire
nearby-search + tagging + embedding flow and return the cached list.
"""
from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone

import anthropic

from app.config import (
    ANTHROPIC_API_KEY,
    CATEGORY_EXCLUSION_MAP,
    CATEGORY_MIN_COMPETITOR_REVIEWS,
    COMPETITOR_MATCH_TTL_DAYS,
    COMPETITOR_RADIUS_METERS,
    HAIKU_MAX_TOKENS,
    HAIKU_MODEL,
    MAX_COMPETITORS,
    MIN_COMPETITOR_REVIEWS,
    NAME_EXCLUSION_KEYWORDS,
    RETAIL_BRAND_KEYWORDS,
    SIMILARITY_THRESHOLD,
    SUBCATEGORIES_BY_CATEGORY,
)
from app.database import supabase
from app.services import apify_reviews, embeddings, google_places

logger = logging.getLogger(__name__)


# ── Tagging (Haiku sub-category) ─────────────────────────────────────────────


def _strip_markdown(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
    if text.endswith("```"):
        text = text.rsplit("```", 1)[0]
    return text.strip()


def _tag_subcategories(
    parent_category: str,
    my_name: str,
    candidates: list[dict],
) -> dict[str, str]:
    """Haiku-tag the user's business + each candidate.

    Returns a dict mapping place_id → sub_category. Empty dict on any failure;
    the caller can skip sub-category filtering without crashing.

    The user's business uses sentinel place_id "__me__".
    """
    vocab = SUBCATEGORIES_BY_CATEGORY.get(parent_category) or []
    if len(vocab) <= 1 or not candidates or not my_name:
        return {}

    lines = [f"1 | {my_name} (this is the user's own business)"]
    for i, c in enumerate(candidates, start=2):
        lines.append(f"{i} | {c.get('name', '')}")
    business_block = "\n".join(lines)
    vocab_str = ", ".join(vocab)

    prompt = f"""Categorise these Indian {parent_category} businesses by sub-category.
Pick the single best tag from: {vocab_str}.

Rules:
- A business that primarily sells one thing gets that tag, even if it also sells related items.
  Sportswear brands like Adidas/Nike/Puma sell apparel too — tag them "footwear", not "clothing".
- Eyewear / sunglasses / opticals (Sunglass Hut, Lenskart, Ray-Ban, Vision Express, Foresight Opticals) → "eyewear" if available, else "general". NEVER "footwear" or "clothing".
- Luggage / travel bags (American Tourister, Samsonite, Skybags, Delsey, VIP, Wildcraft) → "luggage" if available, else "general". NEVER "footwear" or "clothing".
- Jewellery (Tanishq, Kalyan, Joyalukkas, CaratLane) → "jewellery" if available, else "general".
- Use "general" only if the name gives no signal at all, or the business clearly doesn't fit any listed tag.

Businesses (index | name):
{business_block}

Return ONLY a JSON array with exactly {len(candidates) + 1} objects, in order:
[{{"index": 1, "sub_category": "..."}}, ...]
No markdown."""

    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model=HAIKU_MODEL,
            max_tokens=HAIKU_MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
        parsed = json.loads(_strip_markdown(msg.content[0].text))
    except Exception as exc:
        logger.warning("[competitor_pipeline] Haiku tagging failed: %s", exc)
        return {}

    if not isinstance(parsed, list) or len(parsed) != len(candidates) + 1:
        logger.warning(
            "[competitor_pipeline] Haiku returned wrong shape (got %s, expected %d)",
            type(parsed).__name__, len(candidates) + 1,
        )
        return {}

    valid = set(vocab)
    tags: dict[str, str] = {}
    me_tag = parsed[0].get("sub_category") if isinstance(parsed[0], dict) else None
    tags["__me__"] = me_tag if me_tag in valid else "general"
    for c, item in zip(candidates, parsed[1:]):
        pid = c.get("place_id")
        if not pid:
            continue
        t = item.get("sub_category") if isinstance(item, dict) else None
        tags[pid] = t if t in valid else "general"

    logger.info("[competitor_pipeline] tagged %d businesses (me=%s)", len(tags), tags.get("__me__"))
    return tags


# ── Cache: competitor_matches table ──────────────────────────────────────────


def _row_to_dict(r: dict) -> dict:
    return {
        "place_id": r["competitor_pid"],
        "name": r["competitor_name"],
        "rating": float(r["rating"]) if r.get("rating") is not None else 0.0,
        "review_count": r.get("review_count") or 0,
        "similarity": float(r["similarity"]),
        "sub_category": r.get("sub_category"),
        "is_manual": bool(r.get("is_manual", False)),
    }


def _read_cache(business_id: str) -> list[dict] | None:
    """Return AUTO-discovered competitor matches if fresh, else None.

    Manual rows are returned by `_read_manuals`; they are deliberately split
    so that having only manual rows in the table does not short-circuit the
    discovery flow.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=COMPETITOR_MATCH_TTL_DAYS)
    try:
        resp = (
            supabase.table("competitor_matches")
            .select("*")
            .eq("business_id", business_id)
            .eq("is_manual", False)
            .gte("matched_at", cutoff.isoformat())
            .order("similarity", desc=True)
            .execute()
        )
    except Exception as exc:
        logger.warning("[competitor_pipeline] cache read failed for %s: %s", business_id, exc)
        return None

    if not resp.data:
        return None
    return [_row_to_dict(r) for r in resp.data]


def _read_manuals(business_id: str) -> list[dict]:
    """Return manual (user-added) competitor rows. No TTL — these never expire."""
    try:
        resp = (
            supabase.table("competitor_matches")
            .select("*")
            .eq("business_id", business_id)
            .eq("is_manual", True)
            .order("matched_at", desc=False)
            .execute()
        )
    except Exception as exc:
        logger.warning("[competitor_pipeline] manual read failed for %s: %s", business_id, exc)
        return []
    return [_row_to_dict(r) for r in (resp.data or [])]


def _merge_manuals_and_auto(manuals: list[dict], auto: list[dict]) -> list[dict]:
    """Manuals first (user explicitly chose them), then auto by similarity desc.
    Dedupe by place_id with manuals winning."""
    seen = {m["place_id"] for m in manuals}
    return manuals + [a for a in auto if a["place_id"] not in seen]


def _write_cache(business_id: str, matches: list[dict]) -> None:
    """Replace the cached AUTO competitor list for this business.

    Only auto rows are wiped/replaced — manual rows persist across rebuilds.
    """
    try:
        supabase.table("competitor_matches").delete().eq("business_id", business_id).eq("is_manual", False).execute()
        if not matches:
            return
        rows = [
            {
                "business_id": business_id,
                "competitor_pid": m["place_id"],
                "competitor_name": m.get("name", "")[:200],
                "rating": m.get("rating"),
                "review_count": m.get("review_count"),
                "similarity": m["similarity"],
                "sub_category": m.get("sub_category"),
                "is_manual": False,
            }
            for m in matches
        ]
        supabase.table("competitor_matches").insert(rows).execute()
    except Exception as exc:
        logger.warning("[competitor_pipeline] cache write failed for %s: %s", business_id, exc)


def add_manual_competitor(business_id: str, place_id: str) -> dict:
    """Fetch Google details for `place_id` and upsert as a manual competitor.

    Manual rows store similarity=1.0 (treated as max-relevance), no sub_category,
    and never expire. Re-adding an existing manual row is a no-op upsert.
    """
    from app.services import google_places  # local import to keep optional

    details = google_places.get_business_details(place_id)
    row = {
        "business_id": business_id,
        "competitor_pid": place_id,
        "competitor_name": (details.get("name") or "")[:200],
        "rating": float(details.get("rating") or 0.0),
        "review_count": int(details.get("total_reviews") or 0),
        "similarity": 1.0,
        "sub_category": None,
        "is_manual": True,
    }
    supabase.table("competitor_matches").upsert(
        row, on_conflict="business_id,competitor_pid"
    ).execute()
    return _row_to_dict({**row, "rating": row["rating"], "review_count": row["review_count"]})


def remove_manual_competitor(business_id: str, place_id: str) -> bool:
    """Delete a manual competitor row. Returns True if a row was removed."""
    try:
        resp = (
            supabase.table("competitor_matches")
            .delete()
            .eq("business_id", business_id)
            .eq("competitor_pid", place_id)
            .eq("is_manual", True)
            .execute()
        )
    except Exception as exc:
        logger.warning("[competitor_pipeline] manual remove failed for %s/%s: %s", business_id, place_id, exc)
        return False
    return bool(resp.data)


# ── Hard pre-filters (cheap, deterministic) ──────────────────────────────────


def _drop_dead_listings(competitors: list[dict], category: str) -> list[dict]:
    """Drop competitors below the category-specific review-count floor."""
    floor = CATEGORY_MIN_COMPETITOR_REVIEWS.get(category, MIN_COMPETITOR_REVIEWS)
    return [c for c in competitors if c.get("review_count", 0) >= floor]


def _drop_excluded_primary_types(competitors: list[dict], category: str) -> list[dict]:
    """Drop competitors whose primary Google `types[0]` is excluded for category."""
    exclusions = CATEGORY_EXCLUSION_MAP.get(category, set())
    if not exclusions:
        return list(competitors)
    return [
        c for c in competitors
        if not (c.get("types") and c["types"][0] in exclusions)
    ]


def _drop_excluded_name_keywords(
    competitors: list[dict],
    category: str,
    my_name: str = "",
) -> list[dict]:
    """Drop competitors whose name contains a category-specific exclusion keyword.

    Catches cross-category leaks (e.g. Sunglass Hut and luggage stores returned
    by a `type=store` nearby search for a footwear retailer) that Google's
    `types` field doesn't flag and Haiku may misclassify.

    Skips any keyword that is also present in the user's own business name —
    if the user is a "VIP Lounge" café, we don't want the keyword "vip" to
    drop legitimate competitors.
    """
    keywords = NAME_EXCLUSION_KEYWORDS.get(category) or []
    if not keywords:
        return list(competitors)
    my_lower = (my_name or "").lower()
    active = [kw for kw in keywords if kw.lower() not in my_lower]
    if not active:
        return list(competitors)
    out = []
    for c in competitors:
        name_lower = (c.get("name") or "").lower()
        if any(kw in name_lower for kw in active):
            continue
        out.append(c)
    return out


def _drop_wrong_subcategory(
    candidates: list[dict],
    tags: dict[str, str],
) -> list[dict]:
    """Keep only candidates that share the user's sub-category tag.

    No-op when my tag is missing or "general" — Haiku didn't give us a usable signal.
    """
    my_tag = tags.get("__me__")
    if not my_tag or my_tag == "general":
        return list(candidates)
    return [c for c in candidates if tags.get(c.get("place_id")) == my_tag]


def _topup_branded_retail(
    sub_category: str,
    my_name: str,
    my_place_id: str,
    lat: float,
    lng: float,
    existing_pids: set[str],
) -> list[dict]:
    """Run one Google Text Search per brand keyword for the user's sub-category
    and return new (deduped, non-self) candidates. All hits inherit `sub_category`
    so the caller can tag them without a second Haiku call.
    """
    brands = RETAIL_BRAND_KEYWORDS.get(sub_category) or []
    if not brands:
        return []
    my_name_lower = (my_name or "").lower()
    queries = [b for b in brands if b.lower() not in my_name_lower]

    def _search(brand: str) -> list[dict]:
        try:
            return google_places.text_search_brand(brand, lat, lng, COMPETITOR_RADIUS_METERS)
        except Exception as exc:
            logger.warning("[competitor_pipeline] brand top-up '%s' failed: %s", brand, exc)
            return []

    seen = set(existing_pids) | {my_place_id}
    found: list[dict] = []
    with ThreadPoolExecutor(max_workers=min(8, len(queries) or 1)) as pool:
        for hits in pool.map(_search, queries):
            for h in hits:
                pid = h.get("place_id")
                if not pid or pid in seen:
                    continue
                seen.add(pid)
                found.append(h)
    logger.info(
        "[competitor_pipeline] brand top-up sub_category=%s tried=%d added=%d",
        sub_category, len(brands), len(found),
    )
    return found


# ── Main entrypoint ──────────────────────────────────────────────────────────


def run(
    business_id: str,
    my_business: dict,
    my_reviews: list[dict],
) -> list[dict]:
    """Run the full competitor pipeline for one business.

    Args:
        business_id: UUID of the user's business in `businesses.id`.
        my_business: dict with keys `place_id`, `name`, `category`, `lat`, `lng`.
        my_reviews: list of review dicts for the user's business
            (typically Apify-augmented). Each must have at least `text`.

    Returns:
        Ranked list of matched competitors (high similarity first), each:
        {
            "place_id": str,
            "name": str,
            "rating": float,
            "review_count": int,
            "similarity": float,        # cosine [0..1]
            "sub_category": str | None,
        }
        Capped at MAX_COMPETITORS. Empty list = no relevant competitors found
        (caller's competitor_score falls back to neutral).
    """
    # 0. Manual competitors persist across runs and always lead the list.
    manuals = _read_manuals(business_id)

    # 0a. Auto cache hit?
    cached = _read_cache(business_id)
    if cached is not None:
        logger.info(
            "[competitor_pipeline] cache HIT for business_id=%s — %d auto matches, %d manual",
            business_id, len(cached), len(manuals),
        )
        return _merge_manuals_and_auto(manuals, cached[:MAX_COMPETITORS])

    category = my_business.get("category", "")
    my_place_id = my_business.get("place_id")
    if not my_place_id:
        logger.warning("[competitor_pipeline] missing my place_id — returning empty")
        return []

    # 1. Discovery — Google Nearby Search (800m).
    try:
        candidates = google_places.get_nearby_competitors(
            lat=my_business["lat"],
            lng=my_business["lng"],
            category=category,
            exclude_place_id=my_place_id,
        )
    except Exception as exc:
        logger.warning("[competitor_pipeline] nearby search failed: %s", exc)
        return []

    if not candidates:
        logger.info("[competitor_pipeline] Google returned 0 candidates")
        _write_cache(business_id, [])
        return _merge_manuals_and_auto(manuals, [])

    # 2. Hard pre-filters (no API cost).
    survivors = _drop_dead_listings(candidates, category)
    survivors = _drop_excluded_primary_types(survivors, category)
    survivors = _drop_excluded_name_keywords(
        survivors, category, my_business.get("name", ""),
    )
    if not survivors:
        logger.info("[competitor_pipeline] hard filters wiped all %d candidates", len(candidates))
        _write_cache(business_id, [])
        return _merge_manuals_and_auto(manuals, [])

    # 3. Haiku sub-category tag (one batched call).
    tags = _tag_subcategories(
        parent_category=category,
        my_name=my_business.get("name", ""),
        candidates=survivors,
    )

    # 3b. Retail brand top-up — text-search for known brand stores in the
    # user's sub-category. Solves the mall-tenant blind spot where
    # places_nearby's prominence-ranked first page doesn't contain
    # in-mall brand stores.
    my_tag = tags.get("__me__") if tags else None
    if (
        category == "retail"
        and my_tag
        and my_tag != "general"
        and my_tag in RETAIL_BRAND_KEYWORDS
    ):
        existing_pids = {c["place_id"] for c in survivors if c.get("place_id")}
        branded = _topup_branded_retail(
            sub_category=my_tag,
            my_name=my_business.get("name", ""),
            my_place_id=my_place_id,
            lat=my_business["lat"],
            lng=my_business["lng"],
            existing_pids=existing_pids,
        )
        # Apply the same review-count floor branded hits would have faced from
        # the nearby pre-filter, then tag them with the user's sub-category.
        branded = _drop_dead_listings(branded, category)
        for b in branded:
            tags[b["place_id"]] = my_tag
        survivors = survivors + branded

    by_subcat = _drop_wrong_subcategory(survivors, tags) if tags else survivors

    # If the sub-category filter wiped everyone, fall back to the pre-tag set —
    # a single Haiku misclassification shouldn't collapse the whole pipeline.
    if not by_subcat and tags:
        logger.info(
            "[competitor_pipeline] sub-category filter wiped all — falling back to pre-tag set (%d)",
            len(survivors),
        )
        by_subcat = survivors

    # 3b. Cap to top-N by rating BEFORE the expensive Apify fetch loop.
    # Without this cap, a fresh business with 20+ candidates and cold Apify
    # cache spends 5–10 minutes inside this function (one ~30s actor run per
    # competitor). Ranking by rating × review_count is a cheap proxy for
    # "competitor worth analysing" — high-similarity matches usually rank well
    # on these too. The cap is 2× MAX_COMPETITORS so the similarity filter
    # still has headroom to drop irrelevant ones.
    if len(by_subcat) > MAX_COMPETITORS * 2:
        by_subcat.sort(
            key=lambda c: (c.get("rating", 0), c.get("review_count", 0)),
            reverse=True,
        )
        by_subcat = by_subcat[:MAX_COMPETITORS * 2]
        logger.info(
            "[competitor_pipeline] capped candidates to top %d by rating before Apify fetch",
            len(by_subcat),
        )

    # 4. Embed the user's own reviews → centroid.
    my_review_texts = [r.get("text", "") for r in my_reviews if r.get("text")]
    my_centroid = embeddings.upsert_centroid(my_place_id, my_review_texts)
    if not my_centroid:
        # No own-reviews to embed → can't do similarity. Return the pre-similarity
        # list so the rating-based score still works.
        logger.info("[competitor_pipeline] no own-review text — skipping similarity")
        capped = by_subcat[:MAX_COMPETITORS]
        for c in capped:
            c["similarity"] = 0.0
            c["sub_category"] = tags.get(c.get("place_id"))
        _write_cache(business_id, capped)
        return _merge_manuals_and_auto(manuals, capped)

    # 5. For each surviving candidate: fetch reviews → embed centroid.
    # Parallelised — Apify is the slowest step in the pipeline (~30s per cold
    # competitor) and is fully I/O-bound, so a thread pool is a near-linear
    # speedup. supabase-py and cohere are both thread-safe HTTP clients.
    def _build_competitor_centroid(pid: str) -> None:
        comp_reviews = apify_reviews.get_reviews(
            pid, max_reviews=30, is_competitor=True,
        )
        comp_texts = [r.get("text", "") for r in comp_reviews if r.get("text")]
        if comp_texts:
            embeddings.upsert_centroid(pid, comp_texts)

    pids_to_fetch = [c["place_id"] for c in by_subcat if c.get("place_id")]
    if pids_to_fetch:
        with ThreadPoolExecutor(max_workers=8) as pool:
            futs = {pool.submit(_build_competitor_centroid, pid): pid for pid in pids_to_fetch}
            for fut in as_completed(futs):
                pid = futs[fut]
                try:
                    fut.result()
                except Exception as exc:
                    logger.warning(
                        "[competitor_pipeline] competitor centroid build failed for %s: %s",
                        pid, exc,
                    )

    # 6. Score by cosine similarity vs my centroid.
    ranked = embeddings.rank_by_similarity(my_centroid, by_subcat)

    # 7. Drop below threshold (these aren't really competitors of *mine*).
    above_threshold = [c for c in ranked if c["similarity"] >= SIMILARITY_THRESHOLD]
    if not above_threshold:
        # All similarity below threshold — could be sparse competitor reviews.
        # Keep the top 3 with their (low) similarity scores so the score has signal.
        logger.info(
            "[competitor_pipeline] no candidate above threshold %.2f — keeping top 3",
            SIMILARITY_THRESHOLD,
        )
        above_threshold = ranked[:3]

    # 8. Attach sub_category tag and cap.
    for c in above_threshold:
        c["sub_category"] = tags.get(c.get("place_id"))
    matches = above_threshold[:MAX_COMPETITORS]

    logger.info(
        "[competitor_pipeline] business_id=%s candidates=%d → survivors=%d → tagged=%d → "
        "matched=%d (similarity range %.3f..%.3f)",
        business_id, len(candidates), len(survivors), len(by_subcat), len(matches),
        matches[-1]["similarity"] if matches else 0.0,
        matches[0]["similarity"] if matches else 0.0,
    )

    # 9. Persist to the relationship cache (auto rows only) and merge manuals.
    _write_cache(business_id, matches)
    return _merge_manuals_and_auto(manuals, matches)


def invalidate_cache(business_id: str) -> None:
    """Force a re-run on the next call by deleting the relationship cache."""
    try:
        supabase.table("competitor_matches").delete().eq("business_id", business_id).execute()
    except Exception as exc:
        logger.warning("[competitor_pipeline] cache invalidation failed for %s: %s", business_id, exc)
