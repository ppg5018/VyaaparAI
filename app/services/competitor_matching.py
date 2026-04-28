"""
Smarter competitor matching — five-signal relevance filter.

Replaces the old radius+category-only match. Catches:
  - the "premium business punished by cheap competition" failure mode,
  - the inverse "cheap kirana benchmarked against high-end supermarkets",
  - and the "Naturals Ice Cream listed under restaurant in Google's types" mess.

Signals applied in order of cost (cheapest first), so we discard obvious
mismatches before paying for the Haiku call:
  1. review_count >= MIN_COMPETITOR_REVIEWS                        (statistical validity)
  2. competitor's primary Google type not in CATEGORY_EXCLUSION_MAP (deterministic)
  3. competitor's name does not contain a NAME_EXCLUSION_KEYWORDS keyword (deterministic)
  4. |price_level - my_price_level| <= PRICE_TIER_TOLERANCE         (None kept — sparse data)
  5. sub_category == my_sub_category                                (Haiku-tagged batch call)

Hard signals (1-4) excluding everyone is treated as legitimate — the caller's
competitor_score() falls back to NO_COMPETITORS_NEUTRAL = 65 when given an
empty list. Soft signal (5) over-stripping below MIN_COMPETITORS_AFTER_FILTER
is rolled back to the price+name+type set so a Haiku misclassification can't
collapse the score.
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
    CATEGORY_MIN_COMPETITOR_REVIEWS,
    PRICE_TIER_TOLERANCE,
    MIN_COMPETITORS_AFTER_FILTER,
    SUBCATEGORIES_BY_CATEGORY,
    CATEGORY_EXCLUSION_MAP,
    NAME_EXCLUSION_KEYWORDS,
)

logger = logging.getLogger(__name__)

ME_KEY = "__me__"   # sentinel place_id for the user's own business in the tag map


def filter_by_review_count(
    competitors: list[dict],
    min_reviews: int = MIN_COMPETITOR_REVIEWS,
) -> list[dict]:
    """Drop competitors whose rating is not statistically meaningful."""
    return [c for c in competitors if c.get("review_count", 0) >= min_reviews]


def filter_by_primary_type(
    competitors: list[dict],
    my_category: str,
) -> list[dict]:
    """Drop competitors whose primary Google `types` entry is excluded for my_category.

    Each competitor's `types` is the array Google returns from places_nearby —
    the first element is the most specific type. Empty `types` is kept (don't
    punish missing data). Categories without a CATEGORY_EXCLUSION_MAP entry
    receive no filtering.
    """
    exclusions = CATEGORY_EXCLUSION_MAP.get(my_category, set())
    if not exclusions:
        return list(competitors)

    kept = []
    for c in competitors:
        types = c.get("types") or []
        if types and types[0] in exclusions:
            continue
        kept.append(c)
    return kept


def filter_by_name_keywords(
    competitors: list[dict],
    my_category: str,
) -> list[dict]:
    """Drop competitors whose name contains a NAME_EXCLUSION_KEYWORDS keyword.

    Substring match is case-insensitive. Catches the "Monginis Cake Shop" listed
    under restaurant in Google's types — the name betrays it as a bakery.
    Categories without a NAME_EXCLUSION_KEYWORDS entry receive no filtering.
    """
    blocklist = NAME_EXCLUSION_KEYWORDS.get(my_category, [])
    if not blocklist:
        return list(competitors)

    kept = []
    for c in competitors:
        name_lower = (c.get("name") or "").lower()
        if any(kw in name_lower for kw in blocklist):
            continue
        kept.append(c)
    return kept


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


# Per-category tagging examples — specifically chosen to disambiguate brands
# Haiku tends to misclassify across calls (e.g. Adidas sells both shoes and
# apparel; without guidance Haiku flips between footwear and clothing).
_TAGGING_EXAMPLES: dict[str, list[str]] = {
    "restaurant": [
        '"Vidyarthi Bhavan" → south_indian',
        '"Truffles" → multicuisine',
        '"Punjab Grill" → north_indian',
        '"Behrouz Biryani" → biryani',
        '"McDonalds", "Dominos", "KFC" → fast_food',
    ],
    "cafe": [
        '"Starbucks", "Cafe Coffee Day", "Barista" → coffee_shop',
        '"Theobroma", "Monginis" → bakery',
        '"Naturals", "Baskin Robbins" → dessert_parlour',
    ],
    "retail": [
        # Sportswear brands sell shoes AND apparel — always tag as footwear since
        # shoes are their primary identity in India. This is the canonical example
        # of where Haiku flip-flops without guidance.
        '"Nike", "Adidas", "Puma", "Reebok", "Skechers", "ASICS", "New Balance", "FILA" → footwear',
        '"Bata", "Liberty", "Metro Shoes", "Hush Puppies", "Crocs", "Woodland", "Red Tape" → footwear',
        '"Allen Solly", "Van Heusen", "Jockey", "Pantaloons", "Westside", "Max", "Zara", "H&M" → clothing',
        '"Croma", "Reliance Digital", "Vijay Sales", "Samsung", "Sony", "LG" → electronics',
        '"Sleepwell", "Kurlon", "Pepperfry", "Home Centre", "Urban Ladder" → home_goods',
    ],
    "grocery": [
        '"DMart", "Reliance Fresh", "More Megastore", "Big Bazaar" → supermarket',
        '"Local kirana / general store" → kirana',
        '"Organic India", "24 Mantra" → organic',
    ],
    "pharmacy": [
        '"Apollo Pharmacy", "MedPlus", "Wellness Forever", "1mg", "Netmeds" → chain',
        '"Local medical store" → independent',
    ],
    "medical": [
        '"Apollo Clinic", "Practo Clinic" → clinic',
        '"Dr Lal PathLabs", "Thyrocare", "Metropolis" → diagnostic',
    ],
}


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

    examples = _TAGGING_EXAMPLES.get(parent_category, [])
    if examples:
        examples_block = "Examples for this category:\n  " + "\n  ".join(examples)
    else:
        examples_block = "Use the most specific tag that fits the business name."

    return f"""You are categorising Indian {parent_category} businesses by sub-category for a competitive analysis.

Each business below should be tagged with the single best sub-category from this list:
{vocab_str}

{examples_block}

Rules:
- A business that primarily sells one thing (even if it also sells related items)
  gets the primary tag. Sportswear brands like Adidas/Nike sell apparel too, but
  they are footwear stores — tag them "footwear", not "clothing".
- Use "general" only if the name gives NO signal at all (e.g. just a person's name).
- Be consistent: if two names obviously refer to the same kind of business, give
  them the same tag.

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
    """Apply all five signals and return the matched competitor list.

    Order is cheapest-first so we discard obvious mismatches before paying
    for the Haiku call.

    Hard signals — review-count, primary type, name keywords, price-tier —
    are trusted: if they exclude everyone, the empty list is returned and
    the caller's competitor_score() falls back to NO_COMPETITORS_NEUTRAL.
    Exceptions: review-count wiping all → keep originals (a market with no
    20+ review competitors still has signal); price-tier wiping all → relax
    just price (sparse data, not a categorical mismatch).

    Soft signal — Haiku sub-category — over-stripping below
    MIN_COMPETITORS_AFTER_FILTER rolls back to the previous (price+name+type)
    set so a Haiku misclassification can't collapse the score.
    """
    if not competitors:
        return []

    category = my_business.get("category", "")
    min_reviews = CATEGORY_MIN_COMPETITOR_REVIEWS.get(category, MIN_COMPETITOR_REVIEWS)

    by_reviews = filter_by_review_count(competitors, min_reviews)
    if not by_reviews:
        logger.info(
            "[competitor_matching] all %d competitors below %d-review threshold for category=%s — keeping originals",
            len(competitors), min_reviews, category,
        )
        return list(competitors)

    by_type = filter_by_primary_type(by_reviews, category)
    by_name = filter_by_name_keywords(by_type, category)

    if not by_name:
        logger.warning(
            "[competitor_matching] type+name filter excluded all %d competitors for category=%s — caller will use neutral score",
            len(by_reviews), category,
        )
        return []

    price_tier_categories = {"restaurant", "cafe"}
    if category in price_tier_categories:
        by_price = filter_by_price_tier(by_name, my_business.get("price_level"))
    else:
        by_price = by_name

    if not by_price:
        logger.info(
            "[competitor_matching] price tier wiped all %d remaining — relaxing price filter",
            len(by_name),
        )
        by_price = by_name

    tags = tag_subcategories(
        parent_category=category,
        my_name=my_business.get("name", ""),
        competitors=by_price,
    )
    by_subcat = filter_by_subcategory(by_price, tags)
    my_tag = tags.get(ME_KEY)

    # When my own tag is specific (not "general") and Haiku had a clean read,
    # trust the sub-category result even if it's empty. A footwear store with
    # zero nearby footwear competitors should score against an empty list (65
    # neutral) rather than against opticians, mattresses, and electronics
    # stores. The fallback only protects against Haiku failing or my own
    # business landing on "general" — not against legitimate empty matches.
    if my_tag and my_tag != "general":
        logger.info(
            "[competitor_matching] sub-category filter (my_tag=%s): %d → %d competitors",
            my_tag, len(competitors), len(by_subcat),
        )
        return by_subcat

    # my_tag missing or "general" — Haiku gave us no usable signal, fall back.
    logger.info(
        "[competitor_matching] no sub-category signal (my_tag=%s) — keeping price+name+type set (%d competitors)",
        my_tag, len(by_price),
    )
    return by_price
