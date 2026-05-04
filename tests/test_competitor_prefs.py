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


# ── HTTP-level tests for PUT /preferences/{business_id} ──────────────────────


from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from app.main import app


def _biz_row(*, user_id: str | None = None, category: str = "restaurant") -> dict:
    return {
        "id": "biz-1",
        "user_id": user_id,
        "category": category,
        "name": "Test Cafe",
    }


class TestPreferencesEndpoint:
    def test_404_when_business_missing(self):
        with patch("app.api.preferences.supabase") as sb:
            sb.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
            client = TestClient(app)
            r = client.put("/preferences/biz-x", json={"mode": "auto"})
        assert r.status_code == 404

    def test_403_when_user_id_mismatches(self):
        with patch("app.api.preferences.supabase") as sb:
            sb.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[_biz_row(user_id="real-owner")]
            )
            client = TestClient(app)
            r = client.put(
                "/preferences/biz-1",
                json={"mode": "auto"},
                headers={"X-User-Id": "someone-else"},
            )
        assert r.status_code == 403

    def test_400_on_unknown_subcategory(self):
        with patch("app.api.preferences.supabase") as sb:
            sb.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[_biz_row(category="restaurant")]
            )
            client = TestClient(app)
            r = client.put(
                "/preferences/biz-1",
                json={"mode": "custom", "prefs": {
                    "radius_m": 800, "min_reviews": 0, "max_reviews": None,
                    "subcategories": ["definitely_not_a_real_tag"],
                }},
            )
        assert r.status_code == 400

    def test_auto_mode_invalidates_caches(self):
        biz = _biz_row()
        calls: list = []

        with patch("app.api.preferences.supabase") as sb:
            sb.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[biz])

            def _record(name):
                calls.append(name)
                return sb.table.return_value
            sb.table.side_effect = _record

            client = TestClient(app)
            r = client.put("/preferences/biz-1", json={"mode": "auto"})

        assert r.status_code == 204
        assert calls.count("businesses") >= 2
        assert "competitor_matches" in calls
        assert "health_scores" in calls

    def test_custom_mode_persists_prefs(self):
        biz = _biz_row(category="restaurant")
        with patch("app.api.preferences.supabase") as sb:
            sb.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[biz])
            update_chain = sb.table.return_value.update.return_value.eq.return_value.execute
            update_chain.return_value = MagicMock(data=[{"id": "biz-1"}])
            client = TestClient(app)
            r = client.put("/preferences/biz-1", json={
                "mode": "custom",
                "prefs": {
                    "radius_m": 1000, "min_reviews": 50, "max_reviews": 500,
                    "subcategories": ["south_indian"],
                },
            })
        assert r.status_code == 204
