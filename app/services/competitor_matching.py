"""
Smarter competitor matching: review-count threshold, price-tier filter, and
sub-category tagging via Haiku.

Replaces the old radius+category-only match with a tiered approach that avoids
the "premium business punished by cheap competition" failure mode and the
inverse "cheap kirana benchmarked against high-end supermarkets" mode.

Filters applied (in order):
  1. review_count >= MIN_COMPETITOR_REVIEWS
  2. |price_level - my_price_level| <= PRICE_TIER_TOLERANCE  (None price kept)
  3. sub_category == my_sub_category  (Haiku-tagged in one batch call)

If price+sub-category strips the list below MIN_COMPETITORS_AFTER_FILTER, the
strict pair is dropped and only the review-count filter remains, so the
downstream competitor_score never collapses to the no-competitors neutral.
"""
from __future__ import annotations

import json
import logging

import anthropic

from app.config import (
    ANTHROPIC_API_KEY,
    HAIKU_MODEL,
    HAIKU_MAX_TOKENS,
    MIN_COMPETITOR_REVIEWS,
    PRICE_TIER_TOLERANCE,
    MIN_COMPETITORS_AFTER_FILTER,
    SUBCATEGORIES_BY_CATEGORY,
)

logger = logging.getLogger(__name__)

ME_KEY = "__me__"   # sentinel place_id for the user's own business in the tag map


def filter_by_review_count(
    competitors: list[dict],
    min_reviews: int = MIN_COMPETITOR_REVIEWS,
) -> list[dict]:
    """Drop competitors whose rating is not statistically meaningful."""
    return [c for c in competitors if c.get("review_count", 0) >= min_reviews]


def filter_by_price_tier(
    competitors: list[dict],
    my_price_level: int | None,
    tolerance: int = PRICE_TIER_TOLERANCE,
) -> list[dict]:
    """Keep competitors within ±tolerance price levels of my own.

    Competitors with `price_level=None` are kept — Google Places price data is
    sparse for Indian MSMEs, and excluding them on a missing field would throw
    out half the list. Same for when my own price_level is missing.
    """
    if my_price_level is None:
        return list(competitors)

    kept = []
    for c in competitors:
        cp = c.get("price_level")
        if cp is None:
            kept.append(c)
            continue
        if abs(cp - my_price_level) <= tolerance:
            kept.append(c)
    return kept


def _strip_markdown(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
    if text.endswith("```"):
        text = text.rsplit("```", 1)[0]
    return text.strip()


def _build_tagger_prompt(
    parent_category: str,
    vocab: list[str],
    my_name: str,
    competitors: list[dict],
) -> str:
    lines = [f"1 | {my_name} (this is the user's own business)"]
    for i, c in enumerate(competitors, start=2):
        lines.append(f"{i} | {c.get('name', '')}")
    business_block = "\n".join(lines)
    vocab_str = ", ".join(vocab)

    return f"""You are categorising Indian {parent_category} businesses by sub-category for a competitive analysis.

Each business below should be tagged with the single best sub-category from this list:
{vocab_str}

Use "general" only if the name gives no signal. Many Indian business names are descriptive
(e.g. "Vidyarthi Bhavan" → south_indian; "Truffles" → multicuisine; "Bhagini Idli" → south_indian).

Businesses (format: index | name):
{business_block}

Return ONLY a valid JSON array with exactly {len(competitors) + 1} objects, in the same order as listed above:
[{{"index": 1, "sub_category": "..."}}, ...]
No markdown, no preamble."""


def tag_subcategories(
    parent_category: str,
    my_name: str,
    competitors: list[dict],
) -> dict[str, str]:
    """Haiku tags the user's business + each competitor with one sub-category.

    Returns a dict mapping place_id -> sub_category. The user's own business uses
    the sentinel key ``ME_KEY``. Returns an empty dict on any failure so the
    caller can skip sub-category filtering without crashing.
    """
    vocab = SUBCATEGORIES_BY_CATEGORY.get(parent_category)
    if not vocab or len(vocab) <= 1 or not competitors:
        return {}

    if not my_name:
        return {}

    prompt = _build_tagger_prompt(parent_category, vocab, my_name, competitors)
    valid_tags = set(vocab)

    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model=HAIKU_MODEL,
            max_tokens=HAIKU_MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = _strip_markdown(msg.content[0].text)
        parsed = json.loads(raw)
    except Exception as exc:
        logger.warning("[competitor_matching] Haiku tag call failed — skipping sub-category filter: %s", exc)
        return {}

    if not isinstance(parsed, list) or len(parsed) != len(competitors) + 1:
        logger.warning(
            "[competitor_matching] unexpected tag response length: got %s for %d businesses",
            len(parsed) if isinstance(parsed, list) else "?", len(competitors) + 1,
        )
        return {}

    tags: dict[str, str] = {}
    me_tag_raw = parsed[0].get("sub_category") if isinstance(parsed[0], dict) else None
    tags[ME_KEY] = me_tag_raw if me_tag_raw in valid_tags else "general"

    for c, item in zip(competitors, parsed[1:]):
        pid = c.get("place_id")
        if not pid:
            continue
        tag = item.get("sub_category") if isinstance(item, dict) else None
        tags[pid] = tag if tag in valid_tags else "general"

    logger.info(
        "[competitor_matching] tagged %d businesses (me=%s)",
        len(tags), tags.get(ME_KEY),
    )
    return tags


def filter_by_subcategory(
    competitors: list[dict],
    tags: dict[str, str],
) -> list[dict]:
    """Keep only competitors that share the user's sub-category tag.

    If my tag is missing, "general", or no tags were produced, return the input
    unchanged — the filter has no signal to act on.
    """
    my_tag = tags.get(ME_KEY)
    if not my_tag or my_tag == "general":
        return list(competitors)
    return [c for c in competitors if tags.get(c.get("place_id")) == my_tag]


def filter_competitors(
    my_business: dict,
    competitors: list[dict],
) -> list[dict]:
    """Apply all three filters and return the matched competitor list.

    Cascade:
      - review-count and price-tier are hard signals; always applied. If a
        hard filter wipes the list it's relaxed (rare data-sparsity case).
      - sub-category is Haiku-tagged → soft signal. Dropped only if it strips
        below MIN_COMPETITORS_AFTER_FILTER, so a misclassification doesn't
        collapse competitor_score to the no-competitors neutral.
    """
    if not competitors:
        return []

    by_reviews = filter_by_review_count(competitors)
    if not by_reviews:
        logger.info(
            "[competitor_matching] all %d competitors below %d-review threshold — keeping originals",
            len(competitors), MIN_COMPETITOR_REVIEWS,
        )
        return list(competitors)

    by_price = filter_by_price_tier(by_reviews, my_business.get("price_level"))
    if not by_price:
        logger.info(
            "[competitor_matching] price tier wiped all %d remaining — relaxing price filter",
            len(by_reviews),
        )
        by_price = by_reviews

    tags = tag_subcategories(
        parent_category=my_business.get("category", ""),
        my_name=my_business.get("name", ""),
        competitors=by_price,
    )
    by_subcat = filter_by_subcategory(by_price, tags)

    if len(by_subcat) >= MIN_COMPETITORS_AFTER_FILTER:
        logger.info(
            "[competitor_matching] strict filter: %d → %d competitors",
            len(competitors), len(by_subcat),
        )
        return by_subcat

    logger.info(
        "[competitor_matching] sub-category filter left only %d (< %d) — relaxing to price+review only (%d)",
        len(by_subcat), MIN_COMPETITORS_AFTER_FILTER, len(by_price),
    )
    return by_price
