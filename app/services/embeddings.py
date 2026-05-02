"""Cohere embeddings + Supabase pgvector cache.

Two units are persisted in `review_embeddings`:
  - per-review vectors (review_id NOT NULL, is_centroid = false)
  - per-business "centroid" vectors (review_id NULL, is_centroid = true)

The centroid is the embedding of the concatenated review text (capped at
MAX_REVIEWS_PER_COMPETITOR_FOR_EMBEDDING reviews). It's what we compare
businesses on for similarity-based matching.

Caching strategy:
  - Per-review: keyed on (place_id, review_id, text_hash). If text hash
    matches, we never re-embed.
  - Centroid: keyed on (place_id, text_hash of concatenation). Re-embeds
    only when the underlying review set changes.

This module does NOT call Anthropic, Google, or Apify. It only talks to
Cohere and Supabase.
"""
from __future__ import annotations

import hashlib
import logging
from typing import Sequence

import cohere

from app.config import (
    COHERE_API_KEY,
    EMBEDDING_DIM,
    EMBEDDING_INPUT_TYPE_DOC,
    EMBEDDING_INPUT_TYPE_QUERY,
    EMBEDDING_MODEL,
    MAX_REVIEWS_PER_COMPETITOR_FOR_EMBEDDING,
)
from app.database import supabase

logger = logging.getLogger(__name__)

# Cohere `embed-multilingual-v3.0` accepts up to 96 documents per call.
COHERE_MAX_BATCH = 96

# Cohere truncates texts longer than ~512 tokens — pre-trim aggressively to
# avoid wasting tokens on boilerplate (rating stars, dates, etc).
MAX_TEXT_CHARS = 2000


# ── Hashing & text prep ──────────────────────────────────────────────────────


def text_hash(text: str) -> str:
    """Stable SHA-256 hex digest of `text` after normalisation.

    Used as the cache key — identical text never re-embeds. Normalisation
    (lower + collapse whitespace) means trivial formatting changes don't
    invalidate the cache.
    """
    norm = " ".join(text.split()).lower()
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


def _prep_text(text: str | None) -> str:
    if not text:
        return ""
    cleaned = text.strip()[:MAX_TEXT_CHARS]
    return cleaned


def _build_centroid_text(review_texts: Sequence[str]) -> str:
    """Concatenate review texts into a single string for centroid embedding.

    Caps at MAX_REVIEWS_PER_COMPETITOR_FOR_EMBEDDING. Non-empty texts only.
    Joined with ' || ' so Cohere sees clear review boundaries.
    """
    cleaned = [t.strip() for t in review_texts if t and t.strip()]
    capped = cleaned[:MAX_REVIEWS_PER_COMPETITOR_FOR_EMBEDDING]
    return " || ".join(capped)[:MAX_TEXT_CHARS * 4]


# ── Cohere client ────────────────────────────────────────────────────────────


_client: cohere.Client | None = None


def _get_client() -> cohere.Client:
    """Lazy-init the Cohere client. Reused across calls within the same process."""
    global _client
    if _client is None:
        if not COHERE_API_KEY:
            raise RuntimeError(
                "COHERE_API_KEY is not set. Add it to .env before using the "
                "competitor embedding pipeline."
            )
        _client = cohere.Client(api_key=COHERE_API_KEY)
    return _client


def embed_texts(
    texts: list[str],
    input_type: str = EMBEDDING_INPUT_TYPE_DOC,
) -> list[list[float]]:
    """Embed a list of texts. Empty inputs → zero-vector placeholder.

    `input_type` is Cohere's prompt to optimise for storage vs query — pass
    EMBEDDING_INPUT_TYPE_QUERY when comparing a single new text against
    stored vectors at search time.
    """
    if not texts:
        return []

    prepared = [_prep_text(t) for t in texts]

    out: list[list[float]] = [[] for _ in prepared]
    non_empty_idx = [i for i, t in enumerate(prepared) if t]
    non_empty_texts = [prepared[i] for i in non_empty_idx]

    if not non_empty_texts:
        # Cohere can't embed empty strings — return zero vectors.
        return [[0.0] * EMBEDDING_DIM for _ in prepared]

    client = _get_client()
    embeddings: list[list[float]] = []
    for batch_start in range(0, len(non_empty_texts), COHERE_MAX_BATCH):
        batch = non_empty_texts[batch_start:batch_start + COHERE_MAX_BATCH]
        try:
            resp = client.embed(
                texts=batch,
                model=EMBEDDING_MODEL,
                input_type=input_type,
            )
        except Exception as exc:
            logger.error("Cohere embed call failed for %d texts: %s", len(batch), exc)
            raise
        embeddings.extend(resp.embeddings)

    # Stitch the embedded vectors back into the right slots.
    for slot, vec in zip(non_empty_idx, embeddings):
        out[slot] = vec
    # Empty inputs become zero vectors so the caller never sees a None.
    for i, t in enumerate(prepared):
        if not t:
            out[i] = [0.0] * EMBEDDING_DIM

    return out


def embed_one(text: str, input_type: str = EMBEDDING_INPUT_TYPE_DOC) -> list[float]:
    return embed_texts([text], input_type=input_type)[0]


# ── Persistence: upsert / fetch ──────────────────────────────────────────────


def _upsert_row(row: dict) -> None:
    """Insert or update a single review_embeddings row.

    Supabase's `upsert` requires the conflict columns to be a UNIQUE constraint.
    We use (place_id, review_id, is_centroid). NULL review_id is treated as a
    distinct value by Postgres's UNIQUE handling — the partial uniqueness is
    handled by the centroid-shape CHECK constraint.
    """
    try:
        # The pgvector column accepts a Python list — Supabase serialises it.
        supabase.table("review_embeddings").upsert(
            row, on_conflict="place_id,review_id,is_centroid"
        ).execute()
    except Exception as exc:
        logger.warning("Failed to upsert review_embedding (%s): %s", row.get("place_id"), exc)


def upsert_review_embeddings(
    place_id: str,
    reviews: list[dict],
) -> int:
    """Embed and store per-review vectors. Skip reviews whose hash is cached.

    Each review must have keys: review_id (or id), text. Returns the count of
    NEWLY-EMBEDDED reviews (cache hits don't count).
    """
    pairs = []
    hashes = []
    for r in reviews:
        rid = r.get("review_id") or r.get("id")
        text = _prep_text(r.get("text", ""))
        if not rid or not text:
            continue
        h = text_hash(text)
        pairs.append({"review_id": str(rid), "text": text, "hash": h})
        hashes.append(h)

    if not pairs:
        return 0

    # Look up which (review_id, hash) pairs are already cached.
    try:
        existing = (
            supabase.table("review_embeddings")
            .select("review_id, text_hash")
            .eq("place_id", place_id)
            .eq("is_centroid", False)
            .in_("text_hash", list(set(hashes)))
            .execute()
        )
        cached_keys = {(r["review_id"], r["text_hash"]) for r in existing.data}
    except Exception as exc:
        logger.warning("review_embeddings cache lookup failed for %s: %s", place_id, exc)
        cached_keys = set()

    todo = [p for p in pairs if (p["review_id"], p["hash"]) not in cached_keys]
    if not todo:
        return 0

    vectors = embed_texts([p["text"] for p in todo])
    for p, vec in zip(todo, vectors):
        _upsert_row({
            "place_id": place_id,
            "review_id": p["review_id"],
            "is_centroid": False,
            "embedding": vec,
            "text_hash": p["hash"],
        })
    logger.info("Embedded %d new reviews for place_id=%s (cache hit on %d)",
                len(todo), place_id, len(pairs) - len(todo))
    return len(todo)


def upsert_centroid(place_id: str, review_texts: Sequence[str]) -> list[float] | None:
    """Embed concatenated review text as the business's centroid vector.

    Returns the vector. Returns None if there's no review text to embed.
    Cache key: text_hash of the concatenated string.
    """
    centroid_text = _build_centroid_text(review_texts)
    if not centroid_text:
        return None

    h = text_hash(centroid_text)
    try:
        existing = (
            supabase.table("review_embeddings")
            .select("embedding, text_hash")
            .eq("place_id", place_id)
            .eq("is_centroid", True)
            .execute()
        )
    except Exception as exc:
        logger.warning("centroid cache lookup failed for %s: %s", place_id, exc)
        existing = None

    if existing and existing.data:
        row = existing.data[0]
        if row["text_hash"] == h:
            cached = row["embedding"]
            # pgvector returns a string like "[1.2,3.4,...]" — Supabase normally
            # parses this for us, but handle both shapes defensively.
            if isinstance(cached, str):
                cached = _parse_pgvector(cached)
            return cached

    vec = embed_one(centroid_text)
    _upsert_row({
        "place_id": place_id,
        "review_id": None,
        "is_centroid": True,
        "embedding": vec,
        "text_hash": h,
    })
    return vec


def get_centroid(place_id: str) -> list[float] | None:
    """Return the cached centroid vector for `place_id`, or None."""
    try:
        resp = (
            supabase.table("review_embeddings")
            .select("embedding")
            .eq("place_id", place_id)
            .eq("is_centroid", True)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        logger.warning("get_centroid query failed for %s: %s", place_id, exc)
        return None
    if not resp.data:
        return None
    raw = resp.data[0]["embedding"]
    return _parse_pgvector(raw) if isinstance(raw, str) else raw


def _parse_pgvector(s: str) -> list[float]:
    """Parse a pgvector text representation '[1.2, 3.4, ...]' into list[float]."""
    s = s.strip().lstrip("[").rstrip("]")
    if not s:
        return []
    return [float(x) for x in s.split(",")]


# ── Similarity ───────────────────────────────────────────────────────────────


def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    """Plain cosine similarity. Returns 0.0 on degenerate inputs."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    norm_a = 0.0
    norm_b = 0.0
    for x, y in zip(a, b):
        dot += x * y
        norm_a += x * x
        norm_b += y * y
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / ((norm_a ** 0.5) * (norm_b ** 0.5))


def rank_by_similarity(
    my_centroid: Sequence[float],
    candidates: list[dict],
) -> list[dict]:
    """Attach a `similarity` score to each candidate, sorted high→low.

    Each candidate must have a `place_id`. Candidates without a cached centroid
    get similarity=0.0 and end up at the bottom — caller decides whether to
    drop or keep them.
    """
    enriched = []
    for c in candidates:
        pid = c.get("place_id")
        if not pid:
            continue
        their_centroid = get_centroid(pid)
        sim = cosine_similarity(my_centroid, their_centroid) if their_centroid else 0.0
        enriched.append({**c, "similarity": round(sim, 4)})
    enriched.sort(key=lambda x: x["similarity"], reverse=True)
    return enriched
