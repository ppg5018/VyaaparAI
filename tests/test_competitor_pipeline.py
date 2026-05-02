"""Unit tests for app/services/competitor_pipeline.py.

Google Places, Apify, Cohere, Supabase, and Anthropic calls are all mocked.
Validates the orchestration logic end-to-end without hitting any real API.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services import competitor_pipeline as cp


passed = 0
failed = 0


def check(condition: bool, label: str) -> None:
    global passed, failed
    if condition:
        passed += 1
        print(f"  PASS: {label}")
    else:
        failed += 1
        print(f"  FAIL: {label}")


# ── Hard pre-filter helpers ──────────────────────────────────────────────────


def test_drop_dead_listings():
    print("\n--- _drop_dead_listings ---")
    competitors = [
        {"name": "alive", "review_count": 200},
        {"name": "dead",  "review_count": 2},
        {"name": "edge",  "review_count": 20},  # exactly at the restaurant floor
    ]
    out = cp._drop_dead_listings(competitors, "restaurant")
    names = {c["name"] for c in out}
    check("alive" in names, "high-review competitor kept")
    check("dead" not in names, "very-low-review competitor dropped")
    check("edge" in names, "exactly-at-threshold kept (>=, not >)")


def test_drop_excluded_primary_types():
    print("\n--- _drop_excluded_primary_types ---")
    competitors = [
        {"name": "real restaurant",   "types": ["restaurant", "food"]},
        {"name": "ice cream parlour", "types": ["ice_cream_shop", "restaurant"]},  # excluded
        {"name": "bakery in disguise", "types": ["bakery"]},                         # excluded
        {"name": "no types data",     "types": []},                                 # kept (sparse)
    ]
    out = cp._drop_excluded_primary_types(competitors, "restaurant")
    names = {c["name"] for c in out}
    check("real restaurant" in names, "actual restaurant kept")
    check("ice cream parlour" not in names, "ice_cream_shop primary type dropped")
    check("bakery in disguise" not in names, "bakery primary type dropped")
    check("no types data" in names, "missing types[] does not get punished")


def test_drop_wrong_subcategory_skips_when_general():
    print("\n--- _drop_wrong_subcategory: general → no-op ---")
    candidates = [
        {"place_id": "a", "name": "A"},
        {"place_id": "b", "name": "B"},
    ]
    tags = {"__me__": "general", "a": "footwear", "b": "clothing"}
    out = cp._drop_wrong_subcategory(candidates, tags)
    check(len(out) == 2, "my_tag=general → no candidates filtered")


def test_drop_wrong_subcategory_filters_when_specific():
    print("\n--- _drop_wrong_subcategory: specific tag filters ---")
    candidates = [
        {"place_id": "shoe1", "name": "Adidas"},
        {"place_id": "shoe2", "name": "Bata"},
        {"place_id": "shirt", "name": "Allen Solly"},
    ]
    tags = {"__me__": "footwear", "shoe1": "footwear", "shoe2": "footwear", "shirt": "clothing"}
    out = cp._drop_wrong_subcategory(candidates, tags)
    names = {c["name"] for c in out}
    check("Adidas" in names, "matching tag kept")
    check("Bata" in names, "matching tag kept")
    check("Allen Solly" not in names, "different tag dropped")


# ── Cache hit short-circuits the pipeline ────────────────────────────────────


def test_run_cache_hit_skips_apis():
    print("\n--- run() cache hit short-circuits ---")
    cached_rows = [
        {"place_id": "p1", "name": "Cached1", "rating": 4.5, "review_count": 100,
         "similarity": 0.81, "sub_category": "footwear"},
        {"place_id": "p2", "name": "Cached2", "rating": 4.0, "review_count": 50,
         "similarity": 0.65, "sub_category": "footwear"},
    ]
    cp._read_cache = lambda biz_id: cached_rows  # type: ignore

    google_called = []
    cp.google_places.get_nearby_competitors = lambda **kw: google_called.append(kw) or []  # type: ignore

    out = cp.run(
        business_id="any-uuid",
        my_business={"place_id": "me", "name": "Me", "category": "retail",
                     "lat": 1.0, "lng": 2.0},
        my_reviews=[{"text": "great"}],
    )
    check(len(out) == 2, f"returned 2 cached matches (got {len(out)})")
    check(out[0]["name"] == "Cached1", "first match is the cached top-similarity row")
    check(len(google_called) == 0, "Google Nearby Search NOT called on cache hit")


# ── Empty-candidate path ─────────────────────────────────────────────────────


def test_run_returns_empty_when_no_candidates():
    print("\n--- run() with 0 nearby candidates ---")
    cp._read_cache = lambda biz_id: None  # type: ignore
    cp._write_cache = lambda biz_id, matches: None  # type: ignore
    cp.google_places.get_nearby_competitors = lambda **kw: []  # type: ignore

    out = cp.run(
        business_id="x",
        my_business={"place_id": "me", "name": "Me", "category": "retail",
                     "lat": 1.0, "lng": 2.0},
        my_reviews=[],
    )
    check(out == [], "empty list when Google returns nothing")


# ── Hard filters wipe everyone → empty list ──────────────────────────────────


def test_run_returns_empty_when_hard_filters_wipe_all():
    print("\n--- run() when hard filters drop everyone ---")
    cp._read_cache = lambda biz_id: None  # type: ignore
    cp._write_cache = lambda biz_id, matches: None  # type: ignore
    # All candidates are dead listings (low review count)
    cp.google_places.get_nearby_competitors = lambda **kw: [  # type: ignore
        {"name": "Dead1", "place_id": "d1", "review_count": 1, "rating": 4.0, "types": ["restaurant"]},
        {"name": "Dead2", "place_id": "d2", "review_count": 0, "rating": 5.0, "types": ["restaurant"]},
    ]

    out = cp.run(
        business_id="x",
        my_business={"place_id": "me", "name": "Me", "category": "restaurant",
                     "lat": 1.0, "lng": 2.0},
        my_reviews=[{"text": "good food"}],
    )
    check(out == [], "empty list when all candidates fail review-count floor")


# ── End-to-end happy path with mocked everything ─────────────────────────────


def test_run_happy_path():
    print("\n--- run() happy path (everything mocked) ---")
    cp._read_cache = lambda biz_id: None  # type: ignore

    written = {}
    cp._write_cache = lambda biz_id, matches: written.setdefault(biz_id, matches)  # type: ignore

    cp.google_places.get_nearby_competitors = lambda **kw: [  # type: ignore
        {"name": "Adidas Store", "place_id": "adi", "review_count": 100, "rating": 4.5,
         "types": ["clothing_store", "shoe_store"]},
        {"name": "Allen Solly",  "place_id": "all", "review_count": 80,  "rating": 4.2,
         "types": ["clothing_store"]},
        {"name": "Pharmacy XYZ", "place_id": "phr", "review_count": 50,  "rating": 4.8,
         "types": ["pharmacy"]},     # wrong type for retail
    ]

    # Haiku tags: my_tag = footwear → only Adidas survives sub-category filter.
    cp._tag_subcategories = lambda **kw: {  # type: ignore
        "__me__": "footwear", "adi": "footwear", "all": "clothing", "phr": "general",
    }

    cp.apify_reviews.get_reviews = lambda pid, max_reviews, is_competitor: [  # type: ignore
        {"text": f"review for {pid} number {i}"} for i in range(3)
    ]

    cp.embeddings.upsert_centroid = lambda pid, texts: [1.0, 0.0, 0.0]  # type: ignore
    cp.embeddings.rank_by_similarity = lambda my_centroid, candidates: [  # type: ignore
        {**c, "similarity": 0.85} for c in candidates
    ]

    out = cp.run(
        business_id="happy-uuid",
        my_business={"place_id": "me", "name": "Reebok Store", "category": "retail",
                     "lat": 1.0, "lng": 2.0},
        my_reviews=[{"text": "good shoes"}],
    )
    check(len(out) == 1, f"only Adidas survives all filters (got {len(out)} matches)")
    if out:
        check(out[0]["name"] == "Adidas Store", "Adidas is the surviving match")
        check(out[0]["similarity"] == 0.85, "similarity score attached")
        check(out[0]["sub_category"] == "footwear", "sub_category tag attached")
    check("happy-uuid" in written, "results written to cache")


# ── Below-threshold fallback (keeps top 3 if no one passes 0.55) ─────────────


def test_run_below_threshold_keeps_top_3():
    print("\n--- run() below-threshold fallback ---")
    cp._read_cache = lambda biz_id: None  # type: ignore
    written = {}
    cp._write_cache = lambda biz_id, matches: written.setdefault(biz_id, matches)  # type: ignore

    candidates = [
        {"name": f"C{i}", "place_id": f"p{i}", "review_count": 100, "rating": 4.0,
         "types": ["restaurant"]}
        for i in range(5)
    ]
    cp.google_places.get_nearby_competitors = lambda **kw: candidates  # type: ignore
    cp._tag_subcategories = lambda **kw: {}  # no tags → no sub-category filter
    cp.apify_reviews.get_reviews = lambda pid, max_reviews, is_competitor: [  # type: ignore
        {"text": f"review for {pid}"}
    ]
    cp.embeddings.upsert_centroid = lambda pid, texts: [1.0, 0.0, 0.0]  # type: ignore
    # Force every candidate below the 0.55 threshold
    cp.embeddings.rank_by_similarity = lambda my_centroid, candidates: [  # type: ignore
        {**c, "similarity": 0.30} for c in candidates
    ]

    out = cp.run(
        business_id="below-uuid",
        my_business={"place_id": "me", "name": "Me", "category": "restaurant",
                     "lat": 1.0, "lng": 2.0},
        my_reviews=[{"text": "good food"}],
    )
    check(len(out) == 3, f"top 3 returned even when all below threshold (got {len(out)})")


# ── No own-reviews → skip similarity, return rating-only list ────────────────


def test_run_no_own_reviews_skips_similarity():
    print("\n--- run() with no own-review text ---")
    cp._read_cache = lambda biz_id: None  # type: ignore
    written = {}
    cp._write_cache = lambda biz_id, matches: written.setdefault(biz_id, matches)  # type: ignore

    cp.google_places.get_nearby_competitors = lambda **kw: [  # type: ignore
        {"name": "Comp", "place_id": "p1", "review_count": 100, "rating": 4.0,
         "types": ["restaurant"]}
    ]
    cp._tag_subcategories = lambda **kw: {}  # type: ignore
    cp.embeddings.upsert_centroid = lambda pid, texts: None  # type: ignore  # no centroid

    rank_called = []
    cp.embeddings.rank_by_similarity = lambda my_c, cs: rank_called.append(1) or cs  # type: ignore

    out = cp.run(
        business_id="no-revs-uuid",
        my_business={"place_id": "me", "name": "Me", "category": "restaurant",
                     "lat": 1.0, "lng": 2.0},
        my_reviews=[],   # no own reviews
    )
    check(len(out) == 1, "candidate still returned without similarity")
    check(out[0]["similarity"] == 0.0, "similarity defaults to 0.0")
    check(len(rank_called) == 0, "rank_by_similarity NOT called when no own centroid")


# ── Run ──────────────────────────────────────────────────────────────────────


def main():
    test_drop_dead_listings()
    test_drop_excluded_primary_types()
    test_drop_wrong_subcategory_skips_when_general()
    test_drop_wrong_subcategory_filters_when_specific()
    test_run_cache_hit_skips_apis()
    test_run_returns_empty_when_no_candidates()
    test_run_returns_empty_when_hard_filters_wipe_all()
    test_run_happy_path()
    test_run_below_threshold_keeps_top_3()
    test_run_no_own_reviews_skips_similarity()

    print(f"\n{'=' * 50}")
    print(f"Total: {passed + failed}  |  Passed: {passed}  |  Failed: {failed}")
    print("=" * 50)
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
