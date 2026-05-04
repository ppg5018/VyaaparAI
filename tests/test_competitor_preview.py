"""Unit tests for competitor_preview service. All API calls mocked."""
from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest

from app.services import competitor_preview


def _candidate(name: str, place_id: str, review_count: int, types=None) -> dict:
    return {
        "name": name,
        "place_id": place_id,
        "rating": 4.3,
        "review_count": review_count,
        "price_level": None,
        "types": types or ["restaurant"],
    }


class TestComputeReviewBuckets:
    def test_empty_input(self):
        assert competitor_preview._compute_review_buckets([]) == {
            "5+": 0, "20+": 0, "50+": 0, "100+": 0, "200+": 0,
        }

    def test_each_threshold_counted(self):
        candidates = [
            _candidate("a", "p1", 4),
            _candidate("b", "p2", 5),
            _candidate("c", "p3", 25),
            _candidate("d", "p4", 60),
            _candidate("e", "p5", 150),
            _candidate("f", "p6", 300),
        ]
        buckets = competitor_preview._compute_review_buckets(candidates)
        assert buckets == {"5+": 5, "20+": 4, "50+": 3, "100+": 2, "200+": 1}


class TestComputeSubcategoryCounts:
    def test_counts_per_tag_ignoring_me(self):
        candidates = [
            _candidate("a", "p1", 100),
            _candidate("b", "p2", 50),
            _candidate("c", "p3", 30),
        ]
        tags = {
            "__me__": "south_indian",
            "p1": "south_indian",
            "p2": "south_indian",
            "p3": "north_indian",
        }
        counts = competitor_preview._compute_subcategory_counts(candidates, tags)
        assert counts == {"south_indian": 2, "north_indian": 1}

    def test_empty_tags(self):
        assert competitor_preview._compute_subcategory_counts(
            [_candidate("a", "p1", 100)], {}
        ) == {}


class TestTopExamples:
    def test_sorted_by_review_count_desc(self):
        candidates = [
            _candidate("low", "p1", 10),
            _candidate("high", "p2", 500),
            _candidate("mid", "p3", 100),
        ]
        tags = {"p1": "south_indian", "p2": "south_indian", "p3": "south_indian"}
        examples = competitor_preview._top_examples(candidates, tags, limit=2)
        assert [e["name"] for e in examples] == ["high", "mid"]
        assert examples[0]["sub_category"] == "south_indian"


class TestCacheIO:
    def test_read_returns_none_on_miss(self):
        with patch("app.services.competitor_preview.supabase") as sb:
            sb.table.return_value.select.return_value.eq.return_value.eq.return_value.gte.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
            result = competitor_preview._read_cache("ChIJabc", 800)
            assert result is None

    def test_read_returns_payload_on_hit(self):
        payload = {"radius_m": 800, "total_candidates": 12, "review_buckets": {},
                   "subcategory_counts": {}, "top_examples": [], "own_subcategory": "south_indian"}
        with patch("app.services.competitor_preview.supabase") as sb:
            sb.table.return_value.select.return_value.eq.return_value.eq.return_value.gte.return_value.limit.return_value.execute.return_value = MagicMock(
                data=[{"payload": payload}]
            )
            result = competitor_preview._read_cache("ChIJabc", 800)
            assert result == payload

    def test_write_cache_upserts(self):
        with patch("app.services.competitor_preview.supabase") as sb:
            competitor_preview._write_cache("ChIJabc", 800, {"foo": "bar"})
            sb.table.assert_called_with("competitor_preview_cache")


class TestComputePreviewIntegration:
    def test_runs_nearby_search_and_haiku_then_caches(self):
        candidates = [
            _candidate("Janatha Hotel", "ChIJp1", 412),
            _candidate("MTR", "ChIJp2", 380),
            _candidate("Tiny Place", "ChIJp3", 4),
        ]
        tags = {"__me__": "south_indian_breakfast",
                "ChIJp1": "south_indian_breakfast",
                "ChIJp2": "south_indian_breakfast",
                "ChIJp3": "general"}
        with patch("app.services.competitor_preview._read_cache", return_value=None), \
             patch("app.services.competitor_preview._write_cache") as write, \
             patch("app.services.competitor_preview.google_places.get_nearby_competitors",
                   return_value=candidates), \
             patch("app.services.competitor_preview.competitor_pipeline._tag_subcategories",
                   return_value=tags):
            payload = competitor_preview.compute_preview(
                place_id="ChIJme", lat=12.97, lng=77.59,
                category="restaurant", my_name="My Tiffin Centre",
                radius_m=800,
            )

        assert payload["radius_m"] == 800
        assert payload["total_candidates"] == 3
        assert payload["review_buckets"]["5+"] == 2  # Janatha + MTR
        assert payload["own_subcategory"] == "south_indian_breakfast"
        assert payload["subcategory_counts"]["south_indian_breakfast"] == 2
        write.assert_called_once()

    def test_cache_hit_short_circuits(self):
        cached = {"radius_m": 800, "total_candidates": 7, "review_buckets": {},
                  "subcategory_counts": {}, "top_examples": [], "own_subcategory": None}
        with patch("app.services.competitor_preview._read_cache", return_value=cached), \
             patch("app.services.competitor_preview.google_places.get_nearby_competitors") as gp:
            payload = competitor_preview.compute_preview(
                place_id="ChIJme", lat=12.97, lng=77.59,
                category="restaurant", my_name="X", radius_m=800,
            )
        assert payload == cached
        gp.assert_not_called()
