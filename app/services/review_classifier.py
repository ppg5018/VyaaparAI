"""
Claude Haiku review classifier.

Sends up to 50 review texts to Haiku in a single call and gets back:
  - sentiment_score: 1.0–5.0  (Haiku's true read, NOT the star rating)
  - topic: one of the TOPICS set

Why Haiku and not Sonnet: cheap, fast, deterministic for a structured task.
One call classifies all reviews — no per-review API calls.
"""
from __future__ import annotations

import json
import logging
from collections import Counter

import anthropic

from app.config import ANTHROPIC_API_KEY, HAIKU_MODEL, HAIKU_MAX_TOKENS

logger = logging.getLogger(__name__)

TOPICS = {"food_quality", "service", "cleanliness", "price", "ambience", "other"}
MAX_REVIEWS_TO_CLASSIFY = 50
MAX_TEXT_CHARS = 400  # truncate each review before sending to Haiku


def _build_classifier_prompt(reviews: list[dict]) -> str:
    numbered = "\n".join(
        f"{i+1}. [{r.get('rating', '?')}★] {(r.get('text') or '')[:MAX_TEXT_CHARS]}"
        for i, r in enumerate(reviews)
    )
    return f"""You are a review analyst for Indian restaurants and retail businesses.

Classify each review below. For each, return:
- sentiment_score: 1.0–5.0 (your actual read of the text, NOT the star rating — a 4★ review full of complaints should score 2–3)
- topic: the single dominant topic from this list: food_quality, service, cleanliness, price, ambience, other

Reviews:
{numbered}

Return ONLY a valid JSON array with exactly {len(reviews)} objects, one per review, in the same order.
No markdown, no preamble. Each object: {{"sentiment_score": <float>, "topic": "<topic>"}}"""


def _strip_markdown(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
    if text.endswith("```"):
        text = text.rsplit("```", 1)[0]
    return text.strip()


def classify_reviews(reviews: list[dict]) -> list[dict]:
    """Classify up to MAX_REVIEWS_TO_CLASSIFY reviews with Haiku.

    Returns a list of dicts in the same order as `reviews`:
        [{"sentiment_score": float, "topic": str}, ...]

    Falls back to {"sentiment_score": review["rating"], "topic": "other"}
    for any review that can't be classified, so callers always get a full list.
    """
    if not reviews:
        return []

    def _passthrough(r: dict, score: float, topic: str = "other") -> dict:
        return {
            "sentiment_score": score,
            "topic": topic,
            "reviewer_review_count": r.get("reviewer_review_count"),
            "reviewer_is_local_guide": bool(r.get("reviewer_is_local_guide")),
        }

    batch = [r for r in reviews[:MAX_REVIEWS_TO_CLASSIFY] if r.get("text", "").strip()]
    if not batch:
        return [
            _passthrough(r, float(r.get("rating") or 3))
            for r in reviews[:MAX_REVIEWS_TO_CLASSIFY]
        ]

    fallback = [_passthrough(r, float(r.get("rating") or 3)) for r in batch]

    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model=HAIKU_MODEL,
            max_tokens=HAIKU_MAX_TOKENS,
            messages=[{"role": "user", "content": _build_classifier_prompt(batch)}],
        )
        raw = _strip_markdown(msg.content[0].text)
        parsed = json.loads(raw)
    except Exception as exc:
        logger.warning("[review_classifier] Haiku call failed — using star ratings as fallback: %s", exc)
        return fallback

    if not isinstance(parsed, list) or len(parsed) != len(batch):
        logger.warning(
            "[review_classifier] unexpected response length: got %s items for %d reviews",
            len(parsed) if isinstance(parsed, list) else "?", len(batch),
        )
        return fallback

    result = []
    for i, item in enumerate(parsed):
        try:
            score = float(item["sentiment_score"])
            score = max(1.0, min(5.0, score))
            topic = item["topic"] if item.get("topic") in TOPICS else "other"
            entry = {"sentiment_score": score, "topic": topic}
        except (KeyError, TypeError, ValueError):
            entry = fallback[i]
        # Carry the source review's credibility fields so downstream
        # weighting (health_score.review_score) doesn't have to re-align
        # the classifier output back to the input list.
        src = batch[i]
        entry["reviewer_review_count"] = src.get("reviewer_review_count")
        entry["reviewer_is_local_guide"] = bool(src.get("reviewer_is_local_guide"))
        result.append(entry)

    logger.info("[review_classifier] classified %d reviews via Haiku", len(result))
    return result


def dominant_complaint(classified: list[dict], sentiment_threshold: float = 3.0) -> str | None:
    """Return the most common topic among negative reviews (sentiment <= threshold).

    Returns None if there are no negative reviews or classified is empty.
    Topic strings use underscores (e.g. 'food_quality') — format for display at call site.
    """
    negative = [c["topic"] for c in classified if c.get("sentiment_score", 5) <= sentiment_threshold]
    if not negative:
        return None
    most_common, count = Counter(negative).most_common(1)[0]
    logger.debug("[review_classifier] dominant complaint: %s (%d negative mentions)", most_common, count)
    return most_common
