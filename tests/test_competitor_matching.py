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
    filter_by_primary_type,
    filter_by_name_keywords,
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


# ── filter_by_primary_type ───────────────────────────────────────────────────

print("\n=== filter_by_primary_type ===")

comps = [
    {"name": "Naturals",   "types": ["ice_cream_shop", "food", "establishment"]},
    {"name": "RestoA",     "types": ["restaurant", "food", "establishment"]},
    {"name": "Empty",      "types": []},
    {"name": "MissingKey"},
    {"name": "Bakery",     "types": ["bakery", "food"]},
]
out = filter_by_primary_type(comps, my_category="restaurant")
check(
    set(n["name"] for n in out) == {"RestoA", "Empty", "MissingKey"},
    "1. Restaurant: drops ice_cream_shop and bakery, keeps restaurant + empty/missing types",
    [n["name"] for n in out],
)

out = filter_by_primary_type([{"name": "Beer Hub", "types": ["bar", "food"]}], my_category="cafe")
check(out == [], "2. Cafe: bar primary type excluded", out)

out = filter_by_primary_type(
    [{"name": "Whatever", "types": ["restaurant"]}, {"name": "Other", "types": ["bakery"]}],
    my_category="manufacturing",
)
check(len(out) == 2, "3. Category not in map (manufacturing) → no exclusions, all pass", len(out))

# Secondary types should NOT trigger exclusion — only primary (first element)
out = filter_by_primary_type(
    [{"name": "PrimaryRestaurant", "types": ["restaurant", "ice_cream_shop", "food"]}],
    my_category="restaurant",
)
check(len(out) == 1, "4. Only primary type matters (ice_cream_shop in 2nd slot is ignored)", len(out))

out = filter_by_primary_type([], my_category="restaurant")
check(out == [], "5. Empty input", out)


# ── filter_by_name_keywords ──────────────────────────────────────────────────

print("\n=== filter_by_name_keywords ===")

cases = [
    ("Naturals Ice Cream",      "restaurant", False, "drops ice cream"),
    ("Monginis Cake Shop",      "restaurant", False, "drops cake"),
    ("CCD - Café Coffee Day",   "restaurant", False, "drops cafe"),
    ("Sharma Sweets",           "restaurant", False, "drops sweets"),
    ("NATURALS ICE CREAM",      "restaurant", False, "case-insensitive"),
    ("Hotel Sharma",            "restaurant", True,  "Indian 'hotel' = restaurant, kept"),
    ("Sharma's Kitchen",        "restaurant", True,  "no keyword match, kept"),
    ("Punjabi Dhaba",           "restaurant", True,  "dhaba = restaurant, kept"),
    ("Apollo Pharmacy",         "cafe",       False, "drops pharmacy keyword"),
    ("MedPlus Chemist",         "retail",     False, "drops chemist for retail"),
]

for i, (name, category, expect_kept, label) in enumerate(cases, start=1):
    out = filter_by_name_keywords([{"name": name}], my_category=category)
    actual_kept = len(out) == 1
    check(actual_kept == expect_kept, f"{i}. '{name}' for '{category}' — {label}", out)

out = filter_by_name_keywords([{"name": "X"}], my_category="manufacturing")
check(len(out) == 1, "11. Category with no blocklist → no filtering", out)

out = filter_by_name_keywords([], my_category="restaurant")
check(out == [], "12. Empty input", out)


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

# Test 3: when my_tag is specific and Haiku says no competitors match, return
# empty rather than fall back. Stops the Bata-vs-Opticians failure mode.
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
    out == [],
    "3. Hard sub-category: my_tag specific + zero matches → empty (caller uses 65 neutral)",
    out,
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

# Test 8: type/name filters drop bakery + ice-cream BEFORE Haiku is called.
# This is the bug the new signals fix: businesses Google lists under "restaurant"
# that are clearly something else.
_tag_calls["count"] = 0
competitor_matching.tag_subcategories = _stub_tags
out = filter_competitors(
    my_business={"name": "Sharma Restaurant", "category": "restaurant", "price_level": 2},
    competitors=[
        {"name": "Naturals Ice Cream", "place_id": "p1", "review_count": 200, "rating": 4.5, "price_level": 2, "types": ["ice_cream_shop", "food"]},
        {"name": "Monginis Cake Shop", "place_id": "p2", "review_count": 200, "rating": 4.4, "price_level": 2, "types": ["bakery", "food"]},
        {"name": "Punjab Grill",       "place_id": "p3", "review_count": 200, "rating": 4.2, "price_level": 2, "types": ["restaurant", "food"]},
        {"name": "Sharma Sweets",      "place_id": "p4", "review_count": 200, "rating": 4.6, "price_level": 2, "types": ["restaurant", "food"]},
        {"name": "Real Restaurant",    "place_id": "p5", "review_count": 200, "rating": 4.0, "price_level": 2, "types": ["restaurant", "food"]},
    ],
)
check(
    set(names(out)) == {"Punjab Grill", "Real Restaurant"},
    "8. Type filter drops Naturals/Monginis; name filter drops Sharma Sweets — only true restaurants kept",
    names(out),
)

# Test 9: type+name filter wipes everyone → return empty (caller handles 65 neutral)
_tag_calls["count"] = 0
out = filter_competitors(
    my_business={"name": "Me", "category": "restaurant", "price_level": 2},
    competitors=[
        {"name": "Naturals Ice Cream",  "place_id": "p1", "review_count": 200, "rating": 4.5, "price_level": 2, "types": ["ice_cream_shop", "food"]},
        {"name": "Monginis Bakery",     "place_id": "p2", "review_count": 200, "rating": 4.4, "price_level": 2, "types": ["bakery", "food"]},
    ],
)
check(out == [], "9. Type+name wipe → empty list (caller falls back to neutral 65)", out)
check(_tag_calls["count"] == 0, "10. Haiku not called when type+name filter wipes the list", _tag_calls["count"])

# Test 11: unknown category → type/name maps absent → fallthrough behaviour
_tag_calls["count"] = 0
out = filter_competitors(
    my_business={"name": "Me", "category": "unknown_category", "price_level": None},
    competitors=[
        {"name": "Naturals Ice Cream", "place_id": "p1", "review_count": 200, "rating": 4.5, "price_level": 2, "types": ["ice_cream_shop"]},
        {"name": "Whatever",           "place_id": "p2", "review_count": 200, "rating": 4.0, "price_level": 2, "types": ["restaurant"]},
    ],
)
check(
    len(out) == 2,
    "11. Unknown category: no type/name exclusions; price=None keeps all; sub-cat vocab missing → no filter",
    len(out),
)

# Test 12: my_tag = "general" → no usable signal → fall back to price+name+type set
def _stub_tags_me_general(parent_category, my_name, competitors):
    _tag_calls["count"] += 1
    tags = {ME_KEY: "general"}
    for c in competitors:
        tags[c["place_id"]] = "south_indian"  # specific but mine isn't
    return tags

competitor_matching.tag_subcategories = _stub_tags_me_general
_tag_calls["count"] = 0
out = filter_competitors(
    my_business={"name": "Me", "category": "restaurant", "price_level": 2},
    competitors=[
        {"name": "X", "place_id": "p1", "review_count": 100, "rating": 4.0, "price_level": 2},
        {"name": "Y", "place_id": "p2", "review_count": 100, "rating": 4.0, "price_level": 2},
    ],
)
check(
    len(out) == 2,
    "12. my_tag='general' → no signal to filter on → keep price+name+type set",
    len(out),
)

# Test 13: Bata-style — footwear store among non-footwear retail neighbours
# (clean test that exercises the sub-category hard signal, not the name blocklist)
def _stub_tags_footwear_alone(parent_category, my_name, competitors):
    _tag_calls["count"] += 1
    tags = {ME_KEY: "footwear"}
    for c in competitors:
        tags[c["place_id"]] = "clothing"   # everyone else is clothing
    return tags

competitor_matching.tag_subcategories = _stub_tags_footwear_alone
_tag_calls["count"] = 0
out = filter_competitors(
    my_business={"name": "Me Footwear", "category": "retail", "price_level": 2},
    competitors=[
        # Names chosen to NOT trigger retail name blocklist (no "optician","samsung" etc.)
        {"name": "Generic Store A", "place_id": "p1", "review_count": 100, "rating": 4.0, "price_level": 2, "types": ["store"]},
        {"name": "Generic Store B", "place_id": "p2", "review_count": 100, "rating": 4.0, "price_level": 2, "types": ["store"]},
        {"name": "Generic Store C", "place_id": "p3", "review_count": 100, "rating": 4.0, "price_level": 2, "types": ["store"]},
    ],
)
check(
    out == [],
    "13. Bata-style: footwear shop, no footwear competitors → empty (vs polluted by clothing/electronics)",
    out,
)

# Test 14: intra-retail name blocklist catches obvious mismatches even when Haiku is unavailable
competitor_matching.tag_subcategories = _stub_tags_empty   # Haiku failed
_tag_calls["count"] = 0
out = filter_competitors(
    my_business={"name": "Bata Store", "category": "retail", "price_level": 2},
    competitors=[
        {"name": "Student Opticians",      "place_id": "p1", "review_count": 66,  "rating": 4.7, "price_level": 2, "types": ["store"]},
        {"name": "PREM RADIOS SAMSUNG",    "place_id": "p2", "review_count": 78,  "rating": 4.4, "price_level": 2, "types": ["electronics_store"]},
        {"name": "Sleepwell Gallery",      "place_id": "p3", "review_count": 418, "rating": 4.3, "price_level": 2, "types": ["furniture_store"]},
        {"name": "Genuine Footwear Shop",  "place_id": "p4", "review_count": 200, "rating": 4.2, "price_level": 2, "types": ["shoe_store"]},
    ],
)
check(
    set(names(out)) == {"Genuine Footwear Shop"},
    "14. Retail name blocklist: optician/samsung/sleepwell stripped even with Haiku off",
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
