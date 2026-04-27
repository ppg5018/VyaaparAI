"""
test_competitor_matching.py — unit tests for the tiered competitor filter.

No external API calls: tag_subcategories is monkey-patched in the
filter_competitors tests so this runs offline.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services import competitor_matching
from app.services.competitor_matching import (
    ME_KEY,
    filter_by_review_count,
    filter_by_price_tier,
    filter_by_subcategory,
    filter_competitors,
)

_passed = 0
_total = 0


def check(condition: bool, label: str, actual=None) -> None:
    global _passed, _total
    _total += 1
    if condition:
        _passed += 1
        print(f"  PASS: {label}" + (f"  (actual={actual})" if actual is not None else ""))
    else:
        print(f"  FAIL: {label}  (actual={actual})")


def names(comps):
    return [c["name"] for c in comps]


# ── filter_by_review_count ───────────────────────────────────────────────────

print("\n=== filter_by_review_count ===")

comps = [
    {"name": "A", "review_count": 5},
    {"name": "B", "review_count": 19},
    {"name": "C", "review_count": 20},
    {"name": "D", "review_count": 500},
]
out = filter_by_review_count(comps)
check(names(out) == ["C", "D"], "1. Drops < 20, keeps == 20 and > 20", names(out))

out = filter_by_review_count([{"name": "X"}])  # missing review_count → 0
check(out == [], "2. Missing review_count treated as 0", out)

out = filter_by_review_count([])
check(out == [], "3. Empty input", out)

out = filter_by_review_count([{"name": "Z", "review_count": 100}], min_reviews=200)
check(out == [], "4. Custom threshold respected", out)


# ── filter_by_price_tier ─────────────────────────────────────────────────────

print("\n=== filter_by_price_tier ===")

comps = [
    {"name": "Cheap",   "price_level": 0},
    {"name": "Match",   "price_level": 2},
    {"name": "Match2",  "price_level": 3},
    {"name": "Pricey",  "price_level": 4},
    {"name": "Unknown", "price_level": None},
]
out = filter_by_price_tier(comps, my_price_level=2)
check(
    set(names(out)) == {"Match", "Match2", "Unknown"},
    "1. Keeps within ±1, drops 0 and 4 from price 2, keeps None",
    names(out),
)

out = filter_by_price_tier(comps, my_price_level=None)
check(len(out) == 5, "2. my_price_level=None → keep everyone", len(out))

out = filter_by_price_tier(comps, my_price_level=2, tolerance=2)
check(len(out) == 5, "3. Wider tolerance keeps all in range", len(out))

out = filter_by_price_tier([], my_price_level=2)
check(out == [], "4. Empty input", out)


# ── filter_by_subcategory ────────────────────────────────────────────────────

print("\n=== filter_by_subcategory ===")

comps = [
    {"name": "A", "place_id": "p1"},
    {"name": "B", "place_id": "p2"},
    {"name": "C", "place_id": "p3"},
    {"name": "D", "place_id": "p4"},
]
tags = {
    ME_KEY: "south_indian",
    "p1":   "south_indian",
    "p2":   "north_indian",
    "p3":   "south_indian",
    "p4":   "general",
}
out = filter_by_subcategory(comps, tags)
check(
    set(names(out)) == {"A", "C"},
    "1. Keeps only matching tag, drops different and 'general'",
    names(out),
)

out = filter_by_subcategory(comps, {})  # no tags at all
check(len(out) == 4, "2. No tags → no filtering", len(out))

out = filter_by_subcategory(comps, {ME_KEY: "general"})
check(len(out) == 4, "3. My tag is 'general' → no filtering (no signal)", len(out))

out = filter_by_subcategory(comps, {ME_KEY: "north_indian"})  # competitors untagged
check(out == [], "4. My tag set but competitors untagged → all dropped", out)


# ── filter_competitors (composition) ─────────────────────────────────────────

print("\n=== filter_competitors ===")

# Patch out the Haiku call so these tests run offline.
_tag_calls = {"count": 0}


def _stub_tags(parent_category, my_name, competitors):
    _tag_calls["count"] += 1
    # Mark first three competitors as same sub-category as me, rest as different.
    tags = {ME_KEY: "south_indian"}
    for i, c in enumerate(competitors):
        tags[c["place_id"]] = "south_indian" if i < 3 else "north_indian"
    return tags


def _stub_tags_drop_all(parent_category, my_name, competitors):
    _tag_calls["count"] += 1
    tags = {ME_KEY: "south_indian"}
    for c in competitors:
        tags[c["place_id"]] = "north_indian"
    return tags


def _stub_tags_empty(parent_category, my_name, competitors):
    _tag_calls["count"] += 1
    return {}


_orig_tagger = competitor_matching.tag_subcategories

# Test 1: full strict pipeline reduces a wide list down to same-sub-category survivors.
competitor_matching.tag_subcategories = _stub_tags
_tag_calls["count"] = 0

competitors = [
    # Low review count — gets dropped at filter 1.
    {"name": "TooNew",       "place_id": "p_new",     "review_count": 5,   "rating": 4.6, "price_level": 2},
    # Wrong price tier — gets dropped at filter 2.
    {"name": "PriceyPlace",  "place_id": "p_pricey",  "review_count": 200, "rating": 4.8, "price_level": 4},
    # Same sub-category, in price band — kept.
    {"name": "SoIndianA",    "place_id": "p_a",       "review_count": 200, "rating": 4.3, "price_level": 2},
    {"name": "SoIndianB",    "place_id": "p_b",       "review_count": 80,  "rating": 4.0, "price_level": 1},
    {"name": "SoIndianC",    "place_id": "p_c",       "review_count": 150, "rating": 4.5, "price_level": 3},
    # Different sub-category — gets dropped at filter 3.
    {"name": "NorthIndian",  "place_id": "p_n",       "review_count": 300, "rating": 4.7, "price_level": 2},
]
out = filter_competitors(
    my_business={"name": "Vidyarthi Bhavan", "category": "restaurant", "price_level": 2},
    competitors=competitors,
)
check(
    set(names(out)) == {"SoIndianA", "SoIndianB", "SoIndianC"},
    "1. Strict pipeline keeps only same-sub-category, in-price-band, ≥20-review competitors",
    names(out),
)
check(_tag_calls["count"] == 1, "2. Haiku tagger called exactly once", _tag_calls["count"])

# Test 3: when strict pipeline strips below MIN_COMPETITORS_AFTER_FILTER, fall back.
competitor_matching.tag_subcategories = _stub_tags_drop_all
_tag_calls["count"] = 0

competitors = [
    {"name": "A", "place_id": "p1", "review_count": 100, "rating": 4.0, "price_level": 2},
    {"name": "B", "place_id": "p2", "review_count": 100, "rating": 4.1, "price_level": 2},
    {"name": "C", "place_id": "p3", "review_count": 100, "rating": 4.2, "price_level": 2},
    {"name": "D", "place_id": "p4", "review_count": 100, "rating": 4.3, "price_level": 2},
]
out = filter_competitors(
    my_business={"name": "Me", "category": "restaurant", "price_level": 2},
    competitors=competitors,
)
check(
    len(out) == 4,
    "3. Fallback: strict filter drops everyone → return review-count-filtered set",
    len(out),
)

# Test 4: empty input
out = filter_competitors(
    my_business={"name": "Me", "category": "restaurant", "price_level": 2},
    competitors=[],
)
check(out == [], "4. Empty competitors → empty output", out)

# Test 5: all below review threshold → return originals (so competitor_score still has signal)
_tag_calls["count"] = 0
competitor_matching.tag_subcategories = _stub_tags
out = filter_competitors(
    my_business={"name": "Me", "category": "restaurant", "price_level": 2},
    competitors=[
        {"name": "TinyA", "place_id": "p1", "review_count": 3, "rating": 4.5, "price_level": 2},
        {"name": "TinyB", "place_id": "p2", "review_count": 8, "rating": 4.0, "price_level": 2},
    ],
)
check(
    len(out) == 2,
    "5. All competitors below review threshold → keep originals (no useful signal otherwise)",
    len(out),
)
check(_tag_calls["count"] == 0, "6. Haiku not called when review filter wipes the list", _tag_calls["count"])

# Test 7: empty tags from Haiku failure → sub-category filter is a no-op, price+reviews still applied
competitor_matching.tag_subcategories = _stub_tags_empty
out = filter_competitors(
    my_business={"name": "Me", "category": "restaurant", "price_level": 2},
    competitors=[
        {"name": "Match",   "place_id": "p1", "review_count": 100, "rating": 4.0, "price_level": 2},
        {"name": "Pricey",  "place_id": "p2", "review_count": 100, "rating": 4.0, "price_level": 4},
        {"name": "Cheap",   "place_id": "p3", "review_count": 100, "rating": 4.0, "price_level": 0},
        {"name": "Unknown", "place_id": "p4", "review_count": 100, "rating": 4.0, "price_level": None},
    ],
)
check(
    set(names(out)) == {"Match", "Unknown"},
    "7. Empty tags → only review+price filters survive; None-price kept",
    names(out),
)

# Restore original tagger
competitor_matching.tag_subcategories = _orig_tagger


# ── Summary ──────────────────────────────────────────────────────────────────

print(f"\n{'='*50}")
print(f"Total assertions: {_passed}/{_total} passed")
if _passed == _total:
    print("All assertions passed. competitor_matching.py is ready.")
else:
    print(f"{_total - _passed} assertion(s) failed — fix the functions before proceeding.")
print("="*50)
