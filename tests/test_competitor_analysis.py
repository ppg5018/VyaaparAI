"""
test_competitor_analysis.py — validates competitor_analysis service.

Mocks Claude + Google Places so tests run offline, fast (< 1s), and
deterministic. No API keys required.

Run with:  pytest tests/test_competitor_analysis.py -v
"""
from __future__ import annotations

import json
from unittest.mock import patch, MagicMock

import pytest

from app.services import competitor_analysis as ca


# ─── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def my_business():
    return {
        "name": "Sharma's Kitchen",
        "rating": 4.0,
        "reviews": [
            {"rating": 5, "text": "Great food", "relative_time": "1 week ago"},
            {"rating": 3, "text": "", "relative_time": "2 days ago"},  # empty text
            {"rating": 4, "text": "Decent", "relative_time": "1 month ago"},
        ],
    }


@pytest.fixture
def competitors():
    return [
        {"name": "Top Rival",     "rating": 4.5, "review_count": 800, "place_id": "ChIJ_top"},
        {"name": "Decent Rival",  "rating": 4.2, "review_count": 400, "place_id": "ChIJ_decent"},
        {"name": "Lower Rival",   "rating": 3.5, "review_count": 200, "place_id": "ChIJ_lower"},
        {"name": "No Place ID",   "rating": 4.6, "review_count": 100, "place_id": None},
    ]


@pytest.fixture
def claude_valid_json():
    return json.dumps({
        "themes":        ["Theme A", "Theme B", "Theme C"],
        "opportunities": ["Opp 1",   "Opp 2",   "Opp 3"],
    })


# ─── _parse() — pure function tests ────────────────────────────────────────────


class TestParse:
    def test_valid_response(self, claude_valid_json):
        result = ca._parse(claude_valid_json)
        assert result["themes"] == ["Theme A", "Theme B", "Theme C"]
        assert result["opportunities"] == ["Opp 1", "Opp 2", "Opp 3"]

    def test_strips_markdown_fences(self, claude_valid_json):
        wrapped = f"```json\n{claude_valid_json}\n```"
        result = ca._parse(wrapped)
        assert len(result["themes"]) == 3

    def test_caps_to_three_each(self):
        text = json.dumps({
            "themes":        ["a", "b", "c", "d", "e"],
            "opportunities": ["1", "2", "3", "4"],
        })
        result = ca._parse(text)
        assert len(result["themes"]) == 3
        assert len(result["opportunities"]) == 3
        assert result["themes"] == ["a", "b", "c"]

    def test_missing_themes_key_raises(self):
        with pytest.raises((AssertionError, KeyError)):
            ca._parse(json.dumps({"opportunities": ["x"]}))

    def test_missing_opportunities_key_raises(self):
        with pytest.raises((AssertionError, KeyError)):
            ca._parse(json.dumps({"themes": ["x"]}))

    def test_themes_not_list_raises(self):
        with pytest.raises(AssertionError):
            ca._parse(json.dumps({"themes": "not a list", "opportunities": []}))

    def test_non_string_theme_raises(self):
        with pytest.raises(AssertionError):
            ca._parse(json.dumps({"themes": [1, 2, 3], "opportunities": ["a"]}))

    def test_invalid_json_raises(self):
        with pytest.raises(json.JSONDecodeError):
            ca._parse("this is not json {")


# ─── _build_prompt() — pure function tests ─────────────────────────────────────


class TestBuildPrompt:
    def test_includes_business_name_and_rating(self, my_business):
        prompt = ca._build_prompt(my_business, my_business["reviews"], [])
        assert "Sharma's Kitchen" in prompt
        assert "4.0" in prompt

    def test_filters_empty_review_text(self, my_business):
        prompt = ca._build_prompt(my_business, my_business["reviews"], [])
        # The empty-text review shouldn't appear in the formatted block
        assert prompt.count("5★") == 1
        assert prompt.count("4★") == 1
        # The empty-text 3★ review must be filtered out
        assert "3★:" not in prompt or prompt.count("3★") == 0

    def test_handles_zero_reviews(self):
        biz = {"name": "X", "rating": 4.0, "reviews": []}
        prompt = ca._build_prompt(biz, [], [])
        assert "No reviews with text available" in prompt

    def test_handles_zero_competitors(self, my_business):
        prompt = ca._build_prompt(my_business, my_business["reviews"], [])
        assert "No higher-rated competitors found" in prompt

    def test_includes_competitor_data(self, my_business):
        comps = [{
            "name": "Spice House",
            "rating": 4.5,
            "review_count": 500,
            "reviews": [{"rating": 5, "text": "Amazing biryani", "relative_time": "1d"}],
        }]
        prompt = ca._build_prompt(my_business, my_business["reviews"], comps)
        assert "Spice House" in prompt
        assert "Amazing biryani" in prompt
        assert "4.5" in prompt
        assert "500 reviews" in prompt

    def test_requires_strict_json_output(self, my_business):
        prompt = ca._build_prompt(my_business, my_business["reviews"], [])
        assert "Return ONLY valid JSON" in prompt
        assert "themes" in prompt and "opportunities" in prompt


# ─── _fetch_competitor_reviews() — uses mocked google_places ───────────────────


class TestFetchCompetitorReviews:
    def test_filters_below_my_rating(self, competitors):
        with patch.object(ca.apify_reviews, "get_reviews", return_value=[]), \
             patch.object(ca.google_places, "get_business_details") as mock_details, \
             patch.object(ca.google_places, "parse_reviews", return_value=[]):
            mock_details.return_value = {"raw_reviews": []}
            ca._fetch_competitor_reviews(competitors, my_rating=4.0)
            # Only competitors with rating >= 4.0 AND a place_id should be fetched.
            # Top (4.5), Decent (4.2) qualify. Lower (3.5) below threshold. NoPlaceID skipped.
            called_ids = [c.kwargs.get("place_id") or (c.args[0] if c.args else None)
                          for c in mock_details.call_args_list]
            assert "ChIJ_top" in called_ids
            assert "ChIJ_decent" in called_ids
            assert "ChIJ_lower" not in called_ids

    def test_caps_at_max_competitors_constant(self):
        many = [
            {"name": f"R{i}", "rating": 4.5, "review_count": 100, "place_id": f"ChIJ_{i}"}
            for i in range(10)
        ]
        with patch.object(ca.apify_reviews, "get_reviews", return_value=[]), \
             patch.object(ca.google_places, "get_business_details") as mock_details, \
             patch.object(ca.google_places, "parse_reviews", return_value=[]):
            mock_details.return_value = {"raw_reviews": []}
            result = ca._fetch_competitor_reviews(many, my_rating=4.0)
            assert len(result) <= ca.MAX_COMPETITORS_TO_ANALYZE
            assert mock_details.call_count <= ca.MAX_COMPETITORS_TO_ANALYZE

    def test_skips_competitor_without_place_id(self):
        comps = [{"name": "NoID", "rating": 5.0, "review_count": 100, "place_id": None}]
        with patch.object(ca.apify_reviews, "get_reviews", return_value=[]), \
             patch.object(ca.google_places, "get_business_details") as mock_details:
            result = ca._fetch_competitor_reviews(comps, my_rating=4.0)
            assert result == []
            mock_details.assert_not_called()

    def test_one_failure_doesnt_kill_others(self, competitors):
        def details_side_effect(place_id, *a, **kw):
            if place_id == "ChIJ_top":
                raise RuntimeError("API quota")
            return {"raw_reviews": [{"rating": 5, "text": "ok", "time": 1}]}

        with patch.object(ca.apify_reviews, "get_reviews", return_value=[]), \
             patch.object(ca.google_places, "get_business_details",
                          side_effect=details_side_effect), \
             patch.object(ca.google_places, "parse_reviews",
                          return_value=[{"rating": 5, "text": "ok", "relative_time": "1d"}]):
            result = ca._fetch_competitor_reviews(competitors, my_rating=4.0)
            # Top failed but Decent should still come back.
            names = [c["name"] for c in result]
            assert "Top Rival" not in names
            assert "Decent Rival" in names

    def test_returns_empty_when_no_qualifying_competitors(self):
        comps = [{"name": "Lower", "rating": 3.0, "review_count": 100, "place_id": "ChIJ_x"}]
        with patch.object(ca.apify_reviews, "get_reviews") as mock_apify, \
             patch.object(ca.google_places, "get_business_details") as mock_details:
            result = ca._fetch_competitor_reviews(comps, my_rating=4.0)
            assert result == []
            mock_details.assert_not_called()
            mock_apify.assert_not_called()


# ─── analyze_competitors() — orchestrator integration tests ────────────────────


class TestAnalyzeCompetitors:
    def test_returns_empty_when_no_competitors(self, my_business):
        result = ca.analyze_competitors(my_business, competitors=[])
        assert result == {"themes": [], "opportunities": [], "analyzed_count": 0}

    def test_returns_empty_when_no_higher_rated_competitors(self, my_business):
        # All competitors below my_rating (4.0)
        comps = [
            {"name": "A", "rating": 3.0, "review_count": 100, "place_id": "ChIJ_a"},
            {"name": "B", "rating": 3.5, "review_count": 200, "place_id": "ChIJ_b"},
        ]
        result = ca.analyze_competitors(my_business, comps)
        assert result == {"themes": [], "opportunities": [], "analyzed_count": 0}

    def test_happy_path(self, my_business, competitors, claude_valid_json):
        with patch.object(ca, "_fetch_competitor_reviews") as mock_fetch, \
             patch.object(ca, "_call_claude", return_value=claude_valid_json) as mock_claude:
            mock_fetch.return_value = [{
                "name": "Top Rival", "rating": 4.5, "review_count": 800,
                "reviews": [{"rating": 5, "text": "fab", "relative_time": "1d"}],
            }]
            result = ca.analyze_competitors(my_business, competitors)
            assert result["themes"] == ["Theme A", "Theme B", "Theme C"]
            assert result["opportunities"] == ["Opp 1", "Opp 2", "Opp 3"]
            assert result["analyzed_count"] == 1
            mock_claude.assert_called_once()

    def test_claude_failure_returns_empty_never_raises(self, my_business, competitors):
        with patch.object(ca, "_fetch_competitor_reviews") as mock_fetch, \
             patch.object(ca, "_call_claude", side_effect=RuntimeError("API down")):
            mock_fetch.return_value = [{
                "name": "X", "rating": 4.5, "review_count": 100, "reviews": [],
            }]
            # Should not raise; should return safe empty result
            result = ca.analyze_competitors(my_business, competitors)
            assert result == {"themes": [], "opportunities": [], "analyzed_count": 0}

    def test_malformed_claude_response_returns_empty(self, my_business, competitors):
        with patch.object(ca, "_fetch_competitor_reviews") as mock_fetch, \
             patch.object(ca, "_call_claude", return_value="not json at all"):
            mock_fetch.return_value = [{
                "name": "X", "rating": 4.5, "review_count": 100, "reviews": [],
            }]
            result = ca.analyze_competitors(my_business, competitors)
            assert result["themes"] == []
            assert result["analyzed_count"] == 0

    def test_no_qualifying_competitors_skips_claude_call(self, my_business):
        # All below my_rating — should never call Claude
        low = [{"name": "A", "rating": 3.0, "review_count": 100, "place_id": "ChIJ_a"}]
        with patch.object(ca, "_call_claude") as mock_claude:
            ca.analyze_competitors(my_business, low)
            mock_claude.assert_not_called()
