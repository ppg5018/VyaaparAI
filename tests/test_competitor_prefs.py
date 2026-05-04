"""Validation tests for competitor preference Pydantic models."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.models import CompetitorPrefs, PreferencesRequest


class TestCompetitorPrefsValidation:
    def test_defaults_are_permissive(self):
        prefs = CompetitorPrefs()
        assert prefs.radius_m == 800
        assert prefs.min_reviews == 0
        assert prefs.max_reviews is None
        assert prefs.subcategories == []

    def test_radius_must_be_one_of_allowed(self):
        for r in (500, 800, 1000, 1500, 2000):
            CompetitorPrefs(radius_m=r)
        with pytest.raises(ValidationError):
            CompetitorPrefs(radius_m=600)
        with pytest.raises(ValidationError):
            CompetitorPrefs(radius_m=2500)

    def test_min_reviews_non_negative(self):
        with pytest.raises(ValidationError):
            CompetitorPrefs(min_reviews=-1)

    def test_max_reviews_must_be_positive_when_set(self):
        with pytest.raises(ValidationError):
            CompetitorPrefs(max_reviews=0)

    def test_max_must_be_at_least_min(self):
        with pytest.raises(ValidationError):
            CompetitorPrefs(min_reviews=50, max_reviews=20)
        CompetitorPrefs(min_reviews=50, max_reviews=50)
        CompetitorPrefs(min_reviews=50, max_reviews=100)


class TestPreferencesRequest:
    def test_auto_mode_does_not_require_prefs(self):
        req = PreferencesRequest(mode="auto")
        assert req.mode == "auto"
        assert req.prefs is None

    def test_custom_mode_requires_prefs(self):
        with pytest.raises(ValidationError):
            PreferencesRequest(mode="custom")

    def test_custom_mode_with_prefs(self):
        req = PreferencesRequest(
            mode="custom",
            prefs=CompetitorPrefs(
                radius_m=1000, min_reviews=20, max_reviews=500,
                subcategories=["south_indian"],
            ),
        )
        assert req.prefs.radius_m == 1000

    def test_invalid_mode_rejected(self):
        with pytest.raises(ValidationError):
            PreferencesRequest(mode="something_else")
