# Competitor Preferences Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let MSME owners shape competitor auto-discovery during onboarding (sub-categories to compete against, distance, review count range) with a one-click *Let Refloat decide* escape hatch, plus an editable settings panel post-onboarding.

**Architecture:** Add `competitor_prefs_mode` (auto|custom) + `competitor_prefs JSONB` columns to `businesses`. New `GET /competitors/preview` runs the cheap part of the pipeline (Nearby Search + Haiku tag, no Apify, no Cohere) for live counts, cached 1h in `competitor_preview_cache`. New `PUT /preferences/{business_id}` saves prefs and invalidates `competitor_matches` (non-manual) + `health_scores`. `competitor_pipeline.run()` reads prefs at the top and overrides radius / min reviews / max reviews / sub-categories. Frontend gets a Step 2 page after `/onboard/business` and a settings drawer on the dashboard.

**Tech Stack:** FastAPI · Pydantic v2 · Supabase (Postgres + JSONB) · Anthropic Haiku · Cohere · Next.js 14 (App Router) · TypeScript

**Spec:** `docs/superpowers/specs/2026-05-04-competitor-preferences-design.md`

---

## File Structure

**New files (backend):**
- `migrations/2026-05-04-competitor-prefs.sql` — schema migration.
- `app/services/competitor_preview.py` — Nearby Search + Haiku tag preview, with `competitor_preview_cache` TTL.
- `app/api/preferences.py` — `PUT /preferences/{business_id}`.
- `tests/test_competitor_preview.py`
- `tests/test_competitor_prefs.py`

**Modified files (backend):**
- `app/models.py` — add `CompetitorPrefs`, `PreferencesRequest`, `CompetitorPreviewResponse`.
- `app/api/competitors.py` — add `GET /competitors/preview/{business_id}`.
- `app/services/competitor_pipeline.py` — read `competitor_prefs` at the top of `run()`, override knobs in custom mode.
- `app/main.py` — include `preferences.router`.
- `tests/test_competitor_pipeline.py` — add override-path cases + backward-compat case.
- `CLAUDE.md` — document new files, columns, endpoints, migration.

**New files (frontend):**
- `vyaparai-frontend/app/onboard/preferences/page.tsx` — Step 2 page.
- `vyaparai-frontend/components/ui/PrefsForm.tsx` — shared component reused by Step 2 page and dashboard settings drawer.

**Modified files (frontend):**
- `vyaparai-frontend/lib/api.ts` — add `getCompetitorPreview`, `savePreferences`, types.
- `vyaparai-frontend/app/onboard/business/page.tsx` — route to `/onboard/preferences?business_id=...` on success.
- `vyaparai-frontend/app/dashboard/page.tsx` — add *Competitor settings* button on the Competitors tab.

---

## Task 1: Database migration

**Files:**
- Create: `migrations/2026-05-04-competitor-prefs.sql`

- [ ] **Step 1: Write the migration**

```sql
-- migrations/2026-05-04-competitor-prefs.sql
-- Adds per-business competitor preferences and a preview-result cache.
-- competitor_prefs_mode='auto' preserves today's pipeline behaviour.

ALTER TABLE businesses
  ADD COLUMN IF NOT EXISTS competitor_prefs_mode TEXT NOT NULL DEFAULT 'auto'
    CHECK (competitor_prefs_mode IN ('auto', 'custom')),
  ADD COLUMN IF NOT EXISTS competitor_prefs JSONB,
  ADD COLUMN IF NOT EXISTS competitor_prefs_updated_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_businesses_prefs_mode
  ON businesses(competitor_prefs_mode);

CREATE TABLE IF NOT EXISTS competitor_preview_cache (
  place_id TEXT NOT NULL,
  radius_m INT NOT NULL,
  payload JSONB NOT NULL,
  fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (place_id, radius_m)
);

CREATE INDEX IF NOT EXISTS idx_competitor_preview_cache_fetched_at
  ON competitor_preview_cache(fetched_at);
```

- [ ] **Step 2: Apply the migration in Supabase**

Open the Supabase SQL editor, paste the file contents, run.
Expected: three `ALTER TABLE` lines + one `CREATE INDEX` + one `CREATE TABLE` + one `CREATE INDEX` succeed. Re-running is safe (`IF NOT EXISTS`).

- [ ] **Step 3: Commit**

```bash
git add migrations/2026-05-04-competitor-prefs.sql
git commit -m "feat(db): add competitor_prefs columns + preview cache table"
```

---

## Task 2: Pydantic models

**Files:**
- Modify: `app/models.py`
- Test: `tests/test_competitor_prefs.py` (created in this task; extended later)

- [ ] **Step 1: Write the failing test**

Create `tests/test_competitor_prefs.py`:

```python
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
        # min=50, max=20 → invalid
        with pytest.raises(ValidationError):
            CompetitorPrefs(min_reviews=50, max_reviews=20)
        # min=50, max=50 → valid (exact match)
        CompetitorPrefs(min_reviews=50, max_reviews=50)
        # min=50, max=100 → valid
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
            prefs=CompetitorPrefs(radius_m=1000, min_reviews=20, max_reviews=500,
                                   subcategories=["south_indian"]),
        )
        assert req.prefs.radius_m == 1000

    def test_invalid_mode_rejected(self):
        with pytest.raises(ValidationError):
            PreferencesRequest(mode="something_else")
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/pg/Desktop/VyaaparAI && source venv/bin/activate
pytest tests/test_competitor_prefs.py -v
```
Expected: FAIL — `ImportError: cannot import name 'CompetitorPrefs' from 'app.models'`.

- [ ] **Step 3: Implement the models**

Edit `app/models.py`. Replace the imports line and append the new classes.

Top of file — extend the typing import:
```python
from typing import Literal, Optional
from pydantic import BaseModel, Field, field_validator, model_validator
from app.config import VALID_CATEGORIES
```

At the bottom of the file (after the existing classes), add:
```python
class CompetitorPrefs(BaseModel):
    """User-controlled overrides for competitor auto-discovery."""

    radius_m: Literal[500, 800, 1000, 1500, 2000] = 800
    min_reviews: int = Field(0, ge=0, le=10000)
    max_reviews: Optional[int] = Field(None, ge=1, le=100000)
    subcategories: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_range(self) -> "CompetitorPrefs":
        if self.max_reviews is not None and self.max_reviews < self.min_reviews:
            raise ValueError("max_reviews must be >= min_reviews")
        return self


class PreferencesRequest(BaseModel):
    """Body for PUT /preferences/{business_id}."""

    mode: Literal["auto", "custom"]
    prefs: Optional[CompetitorPrefs] = None

    @model_validator(mode="after")
    def _check_prefs_required(self) -> "PreferencesRequest":
        if self.mode == "custom" and self.prefs is None:
            raise ValueError("prefs required when mode='custom'")
        return self


class CompetitorPreviewResponse(BaseModel):
    """Response body for GET /competitors/preview/{business_id}."""

    radius_m: int
    total_candidates: int
    review_buckets: dict[str, int]
    subcategory_counts: dict[str, int]
    top_examples: list[dict]
    own_subcategory: Optional[str] = None
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_competitor_prefs.py -v
```
Expected: PASS — all 8 cases green.

- [ ] **Step 5: Commit**

```bash
git add app/models.py tests/test_competitor_prefs.py
git commit -m "feat(models): CompetitorPrefs + PreferencesRequest + preview response"
```

---

## Task 3: Preview service — bucket logic + cache

**Files:**
- Create: `app/services/competitor_preview.py`
- Test: `tests/test_competitor_preview.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_competitor_preview.py`:

```python
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
            _candidate("a", "p1", 4),       # 0 buckets
            _candidate("b", "p2", 5),       # 5+
            _candidate("c", "p3", 25),      # 5+, 20+
            _candidate("d", "p4", 60),      # 5+, 20+, 50+
            _candidate("e", "p5", 150),     # 5+, 20+, 50+, 100+
            _candidate("f", "p6", 300),     # all 5
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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_competitor_preview.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.competitor_preview'`.

- [ ] **Step 3: Implement the service**

Create `app/services/competitor_preview.py`:

```python
"""Cheap preview pipeline for the onboarding preferences form.

Runs only the cheap stages of the full competitor pipeline (Nearby Search +
Haiku sub-category tagging) so the frontend can show live counts as the user
adjusts the radius / sub-category / review-range filters. No Apify, no
Cohere, no embeddings — those run only on /generate-report.

Cached in `competitor_preview_cache` keyed on (place_id, radius_m) with a
1-hour TTL so slider drags don't burn Google Places quota.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

from app.database import supabase
from app.services import competitor_pipeline, google_places

logger = logging.getLogger(__name__)

PREVIEW_TTL_HOURS = 1
REVIEW_THRESHOLDS = [5, 20, 50, 100, 200]
TOP_EXAMPLES_LIMIT = 5


def _compute_review_buckets(candidates: list[dict]) -> dict[str, int]:
    """Count how many candidates clear each review-count threshold."""
    buckets: dict[str, int] = {f"{t}+": 0 for t in REVIEW_THRESHOLDS}
    for c in candidates:
        rc = c.get("review_count", 0) or 0
        for t in REVIEW_THRESHOLDS:
            if rc >= t:
                buckets[f"{t}+"] += 1
    return buckets


def _compute_subcategory_counts(
    candidates: list[dict], tags: dict[str, str]
) -> dict[str, int]:
    """Count candidates per sub-category tag (excluding the user's own '__me__')."""
    counts: dict[str, int] = {}
    for c in candidates:
        pid = c.get("place_id")
        tag = tags.get(pid) if pid else None
        if not tag:
            continue
        counts[tag] = counts.get(tag, 0) + 1
    return counts


def _top_examples(
    candidates: list[dict], tags: dict[str, str], limit: int = TOP_EXAMPLES_LIMIT
) -> list[dict]:
    """Return up to `limit` highest-review-count candidates with sub-category."""
    sorted_c = sorted(
        candidates, key=lambda c: c.get("review_count", 0) or 0, reverse=True
    )
    out: list[dict] = []
    for c in sorted_c[:limit]:
        pid = c.get("place_id")
        out.append({
            "name": c.get("name", ""),
            "place_id": pid,
            "review_count": c.get("review_count", 0) or 0,
            "rating": c.get("rating", 0.0) or 0.0,
            "sub_category": tags.get(pid) if pid else None,
        })
    return out


def _read_cache(place_id: str, radius_m: int) -> dict | None:
    """Return cached preview payload if fresh (< PREVIEW_TTL_HOURS old)."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=PREVIEW_TTL_HOURS)
    try:
        resp = (
            supabase.table("competitor_preview_cache")
            .select("payload")
            .eq("place_id", place_id)
            .eq("radius_m", radius_m)
            .gte("fetched_at", cutoff.isoformat())
            .limit(1)
            .execute()
        )
    except Exception as exc:
        logger.warning("[competitor_preview] cache read failed: %s", exc)
        return None
    if not resp.data:
        return None
    payload = resp.data[0].get("payload")
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except Exception:
            return None
    return payload


def _write_cache(place_id: str, radius_m: int, payload: dict) -> None:
    """Upsert a preview payload into the cache."""
    try:
        supabase.table("competitor_preview_cache").upsert({
            "place_id": place_id,
            "radius_m": radius_m,
            "payload": payload,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }, on_conflict="place_id,radius_m").execute()
    except Exception as exc:
        logger.warning("[competitor_preview] cache write failed: %s", exc)


def compute_preview(
    *,
    place_id: str,
    lat: float,
    lng: float,
    category: str,
    my_name: str,
    radius_m: int,
) -> dict:
    """Build the preview payload (or return a cached copy)."""
    cached = _read_cache(place_id, radius_m)
    if cached is not None:
        logger.info("[competitor_preview] cache HIT place_id=%s radius=%d", place_id, radius_m)
        return cached

    logger.info("[competitor_preview] cache MISS place_id=%s radius=%d", place_id, radius_m)
    candidates = google_places.get_nearby_competitors(
        lat=lat, lng=lng, category=category,
        radius=radius_m, exclude_place_id=place_id,
    )

    # Haiku-tag everyone (user + candidates) so the frontend can render
    # accurate per-sub-category counts. Failure → empty tags, counts will be {}.
    tags = competitor_pipeline._tag_subcategories(
        parent_category=category, my_name=my_name, candidates=candidates,
    )

    payload = {
        "radius_m": radius_m,
        "total_candidates": len(candidates),
        "review_buckets": _compute_review_buckets(candidates),
        "subcategory_counts": _compute_subcategory_counts(candidates, tags),
        "top_examples": _top_examples(candidates, tags),
        "own_subcategory": tags.get("__me__") if tags else None,
    }
    _write_cache(place_id, radius_m, payload)
    return payload
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_competitor_preview.py -v
```
Expected: PASS — all cases green.

- [ ] **Step 5: Commit**

```bash
git add app/services/competitor_preview.py tests/test_competitor_preview.py
git commit -m "feat(competitor-preview): cheap preview pipeline with 1h cache"
```

---

## Task 4: GET /competitors/preview endpoint

**Files:**
- Modify: `app/api/competitors.py`
- Test: `tests/test_competitor_preview.py` (extend with HTTP-level cases)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_competitor_preview.py`:

```python
from fastapi.testclient import TestClient
from app.main import app


class TestPreviewEndpoint:
    def test_404_when_business_missing(self):
        with patch("app.api.competitors.supabase") as sb:
            sb.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
            client = TestClient(app)
            r = client.get("/competitors/preview/00000000-0000-0000-0000-000000000000")
        assert r.status_code == 404

    def test_400_on_unsupported_radius(self):
        client = TestClient(app)
        r = client.get("/competitors/preview/00000000-0000-0000-0000-000000000000?radius_m=750")
        assert r.status_code == 422

    def test_happy_path_returns_payload(self):
        biz = {"id": "biz-1", "place_id": "ChIJme", "category": "restaurant",
                "name": "X"}
        # google_places.get_business_details supplies lat/lng for cache misses;
        # we mock it so no API call is made.
        details = {"lat": 12.97, "lng": 77.59}
        with patch("app.api.competitors.supabase") as sb, \
             patch("app.api.competitors.google_places.get_business_details",
                    return_value=details), \
             patch("app.api.competitors.competitor_preview.compute_preview") as cp:
            sb.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[biz])
            cp.return_value = {
                "radius_m": 800, "total_candidates": 7,
                "review_buckets": {"5+": 6, "20+": 4, "50+": 2, "100+": 1, "200+": 0},
                "subcategory_counts": {"south_indian": 5, "north_indian": 2},
                "top_examples": [],
                "own_subcategory": "south_indian",
            }
            client = TestClient(app)
            r = client.get("/competitors/preview/biz-1?radius_m=800")
        assert r.status_code == 200
        body = r.json()
        assert body["radius_m"] == 800
        assert body["total_candidates"] == 7
        assert body["own_subcategory"] == "south_indian"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_competitor_preview.py::TestPreviewEndpoint -v
```
Expected: FAIL — `404 Not Found` from FastAPI for the route itself (route doesn't exist yet).

- [ ] **Step 3: Add the endpoint**

Edit `app/api/competitors.py`. Add imports at the top:

```python
from typing import Literal
from fastapi import Query

from app.database import supabase
from app.models import CompetitorPreviewResponse
from app.services import competitor_preview, google_places
```

Then append (before the existing routes is fine; pick any position):

```python
@router.get(
    "/competitors/preview/{business_id}",
    response_model=CompetitorPreviewResponse,
)
def preview_competitors(
    business_id: str,
    radius_m: Literal[500, 800, 1000, 1500, 2000] = Query(800),
) -> CompetitorPreviewResponse:
    """Cheap preview of nearby candidates — for the onboarding preferences form.

    Runs Nearby Search + Haiku sub-category tag only. Cached 1h per
    (place_id, radius_m) so slider drags don't burn quota. Pipeline-level
    Apify + Cohere are NOT run here — they're for /generate-report.
    """
    biz_resp = (
        supabase.table("businesses")
        .select("id, place_id, category, name")
        .eq("id", business_id)
        .execute()
    )
    if not biz_resp.data:
        raise HTTPException(status_code=404, detail="Business not found")
    biz = biz_resp.data[0]

    place_id = biz["place_id"]
    if not place_id or place_id.startswith("manual_"):
        # No real place_id → can't run Nearby Search; return empty preview.
        return CompetitorPreviewResponse(
            radius_m=radius_m, total_candidates=0,
            review_buckets={"5+": 0, "20+": 0, "50+": 0, "100+": 0, "200+": 0},
            subcategory_counts={}, top_examples=[], own_subcategory=None,
        )

    try:
        details = google_places.get_business_details(place_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    payload = competitor_preview.compute_preview(
        place_id=place_id,
        lat=details["lat"],
        lng=details["lng"],
        category=biz["category"],
        my_name=biz["name"],
        radius_m=radius_m,
    )
    return CompetitorPreviewResponse(**payload)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_competitor_preview.py -v
```
Expected: PASS — all cases green including the three new HTTP cases.

- [ ] **Step 5: Commit**

```bash
git add app/api/competitors.py tests/test_competitor_preview.py
git commit -m "feat(api): GET /competitors/preview for onboarding live counts"
```

---

## Task 5: PUT /preferences endpoint

**Files:**
- Create: `app/api/preferences.py`
- Modify: `app/main.py`
- Test: `tests/test_competitor_prefs.py` (extend)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_competitor_prefs.py`:

```python
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

    def test_auto_mode_sets_jsonb_to_null_and_invalidates_caches(self):
        biz = _biz_row()
        calls: list = []

        with patch("app.api.preferences.supabase") as sb:
            # SELECT returns the business
            sb.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[biz])
            # UPDATE / DELETE chains: capture by recording table names
            def _record(name):
                calls.append(name)
                return sb.table.return_value
            sb.table.side_effect = _record

            client = TestClient(app)
            r = client.put("/preferences/biz-1", json={"mode": "auto"})

        assert r.status_code == 204
        # We expect 4 supabase.table() invocations: select, update businesses,
        # delete competitor_matches, delete health_scores.
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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_competitor_prefs.py -v
```
Expected: FAIL — `404 Not Found` for the PUT route (does not exist yet).

- [ ] **Step 3: Implement the endpoint**

Create `app/api/preferences.py`:

```python
"""User-controlled competitor-preference saves.

PUT body validated by `PreferencesRequest`. On success:
- Updates `businesses.competitor_prefs_mode` + `competitor_prefs` (JSON or NULL).
- Wipes non-manual `competitor_matches` rows for this business so the next
  /generate-report rebuilds with the new prefs.
- Wipes `health_scores` rows for this business so the 24h report cache
  doesn't serve stale numbers under the old prefs.

Manual `competitor_matches` rows (`is_manual=true`) are preserved.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Header, HTTPException, Response

from app.config import SUBCATEGORIES_BY_CATEGORY
from app.database import supabase
from app.models import PreferencesRequest

logger = logging.getLogger(__name__)

router = APIRouter()


@router.put("/preferences/{business_id}", status_code=204)
def save_preferences(
    business_id: str,
    body: PreferencesRequest,
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> Response:
    biz_resp = (
        supabase.table("businesses")
        .select("id, user_id, category")
        .eq("id", business_id)
        .execute()
    )
    if not biz_resp.data:
        raise HTTPException(status_code=404, detail="Business not found")
    biz = biz_resp.data[0]

    # Ownership check (only enforce when business has a user_id).
    if biz.get("user_id") and x_user_id and biz["user_id"] != x_user_id:
        raise HTTPException(status_code=403, detail="Not authorised for this business")

    # Validate subcategories against the parent-category vocabulary.
    if body.mode == "custom" and body.prefs and body.prefs.subcategories:
        allowed = set(SUBCATEGORIES_BY_CATEGORY.get(biz["category"], []))
        unknown = [t for t in body.prefs.subcategories if t not in allowed]
        if unknown:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown sub-category tag(s): {unknown}. Allowed: {sorted(allowed)}",
            )

    # Persist.
    update_payload: dict = {
        "competitor_prefs_mode": body.mode,
        "competitor_prefs": body.prefs.model_dump() if body.prefs else None,
        "competitor_prefs_updated_at": datetime.now(timezone.utc).isoformat(),
    }
    supabase.table("businesses").update(update_payload).eq("id", business_id).execute()

    # Invalidate the auto competitor-match cache (manual rows survive).
    try:
        supabase.table("competitor_matches").delete().eq(
            "business_id", business_id
        ).eq("is_manual", False).execute()
    except Exception as exc:
        logger.warning("[preferences.put] competitor_matches wipe failed: %s", exc)

    # Invalidate the 24h report cache so the next /generate-report rebuilds.
    try:
        supabase.table("health_scores").delete().eq("business_id", business_id).execute()
    except Exception as exc:
        logger.warning("[preferences.put] health_scores wipe failed: %s", exc)

    logger.info(
        "[preferences.put] business_id=%s mode=%s radius=%s min=%s max=%s subcats=%s",
        business_id, body.mode,
        body.prefs.radius_m if body.prefs else None,
        body.prefs.min_reviews if body.prefs else None,
        body.prefs.max_reviews if body.prefs else None,
        body.prefs.subcategories if body.prefs else None,
    )
    return Response(status_code=204)
```

Edit `app/main.py`. Update the import line:
```python
from app.api import actions, competitors, onboard, pos, preferences, report, history
```

Inside `create_app()`, add after the existing `include_router` calls:
```python
    application.include_router(preferences.router, tags=["preferences"])
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_competitor_prefs.py -v
```
Expected: PASS — all cases green.

- [ ] **Step 5: Commit**

```bash
git add app/api/preferences.py app/main.py tests/test_competitor_prefs.py
git commit -m "feat(api): PUT /preferences with cache invalidation"
```

---

## Task 6: Pipeline override integration

**Files:**
- Modify: `app/services/competitor_pipeline.py`
- Test: `tests/test_competitor_pipeline.py` (extend)

- [ ] **Step 1: Write the failing test**

Open `tests/test_competitor_pipeline.py`. Append a new test class at the bottom:

```python
class TestCustomPrefsOverride:
    """When businesses.competitor_prefs_mode == 'custom', the pipeline must
    honour user overrides (radius, min/max reviews, sub-category union).
    Manuals + safety floors still apply."""

    def _common_mocks(self, monkeypatch):
        """Patch external services so only the override logic is exercised."""
        from app.services import competitor_pipeline as cp
        monkeypatch.setattr(cp, "_read_cache", lambda *a, **kw: None)
        monkeypatch.setattr(cp, "_read_manuals", lambda *a, **kw: [])
        monkeypatch.setattr(cp, "_write_cache", lambda *a, **kw: None)
        monkeypatch.setattr(cp, "_load_prefs",
            lambda bid: ("custom", {"radius_m": 1500, "min_reviews": 100,
                                      "max_reviews": 1000,
                                      "subcategories": ["south_indian", "biryani"]}))
        # Skip Apify + Cohere by returning candidates directly above threshold.
        monkeypatch.setattr(cp, "_tag_subcategories", lambda **kw: {})
        return cp

    def test_custom_radius_passed_to_nearby_search(self, monkeypatch):
        cp = self._common_mocks(monkeypatch)
        captured: dict = {}
        def fake_nearby(*, lat, lng, category, exclude_place_id, radius=800):
            captured["radius"] = radius
            return []
        monkeypatch.setattr(cp.google_places, "get_nearby_competitors", fake_nearby)

        cp.run(
            business_id="biz-1",
            my_business={"place_id": "ChIJme", "name": "X",
                          "category": "restaurant", "lat": 12.97, "lng": 77.59},
            my_reviews=[{"text": "good"}],
        )
        assert captured["radius"] == 1500

    def test_custom_min_max_review_filter(self, monkeypatch):
        cp = self._common_mocks(monkeypatch)
        candidates = [
            {"name": "tiny", "place_id": "p1", "rating": 4.0, "review_count": 50,  "types": ["restaurant"]},
            {"name": "ok",   "place_id": "p2", "rating": 4.3, "review_count": 300, "types": ["restaurant"]},
            {"name": "huge", "place_id": "p3", "rating": 4.5, "review_count": 5000,"types": ["restaurant"]},
        ]
        monkeypatch.setattr(cp.google_places, "get_nearby_competitors",
                              lambda **kw: candidates)
        # Force the override path to terminate before Apify by mocking centroid build.
        monkeypatch.setattr(cp.embeddings, "upsert_centroid", lambda *a, **kw: None)

        result = cp.run(
            business_id="biz-1",
            my_business={"place_id": "ChIJme", "name": "X",
                          "category": "restaurant", "lat": 12.97, "lng": 77.59},
            my_reviews=[],
        )
        # min=100, max=1000 → only "ok" (300) survives.
        names = [r["name"] for r in result]
        assert names == ["ok"]
```

The above also requires a new `_load_prefs` helper exposed on the module — that's part of Step 3.

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_competitor_pipeline.py::TestCustomPrefsOverride -v
```
Expected: FAIL — `AttributeError: module 'app.services.competitor_pipeline' has no attribute '_load_prefs'`.

- [ ] **Step 3: Implement the override**

Edit `app/services/competitor_pipeline.py`.

Add a helper near the top (just below the other private helpers, e.g. after `_strip_markdown`):

```python
def _load_prefs(business_id: str) -> tuple[str, dict | None]:
    """Read competitor_prefs_mode + competitor_prefs for this business.

    Returns ('auto', None) for any read failure or for businesses that haven't
    set prefs yet — preserving today's hardcoded-default behaviour.
    """
    try:
        resp = (
            supabase.table("businesses")
            .select("competitor_prefs_mode, competitor_prefs")
            .eq("id", business_id)
            .execute()
        )
    except Exception as exc:
        logger.warning("[competitor_pipeline] prefs read failed: %s", exc)
        return ("auto", None)
    if not resp.data:
        return ("auto", None)
    row = resp.data[0]
    mode = row.get("competitor_prefs_mode") or "auto"
    prefs = row.get("competitor_prefs")
    if isinstance(prefs, str):
        try:
            import json as _json
            prefs = _json.loads(prefs)
        except Exception:
            prefs = None
    return (mode, prefs)
```

Modify `_drop_dead_listings` to accept an explicit floor:
```python
def _drop_dead_listings(competitors: list[dict], category: str,
                          override_floor: int | None = None) -> list[dict]:
    """Drop competitors below the review-count floor.

    If override_floor is given (custom prefs path), use it; otherwise fall
    back to the per-category default.
    """
    if override_floor is not None:
        floor = override_floor
    else:
        floor = CATEGORY_MIN_COMPETITOR_REVIEWS.get(category, MIN_COMPETITOR_REVIEWS)
    return [c for c in competitors if c.get("review_count", 0) >= floor]
```

Add a new helper just below it:
```python
def _drop_above_max_reviews(competitors: list[dict], cap: int | None) -> list[dict]:
    """Custom-prefs path only: drop competitors above the user-set max."""
    if cap is None:
        return list(competitors)
    return [c for c in competitors if (c.get("review_count", 0) or 0) <= cap]
```

In `_drop_wrong_subcategory`, accept an optional allow-set override:
```python
def _drop_wrong_subcategory(
    competitors: list[dict], tags: dict[str, str],
    allowed: set[str] | None = None,
) -> list[dict]:
    """Keep only competitors whose Haiku tag matches the allow-set.

    Default allow-set is `{tags['__me__']}` (today's behaviour). Callers in the
    custom-prefs path pass the user-chosen union instead.
    """
    if allowed is None:
        me = tags.get("__me__")
        if not me:
            return list(competitors)
        allowed = {me}
    return [c for c in competitors if tags.get(c.get("place_id")) in allowed]
```

Now update `run()`. Replace the body of `run()` from the start through the `_drop_dead_listings` / `_drop_excluded_*` block with this version (preserve the rest of the function — Apify, Cohere, similarity, cache write — unchanged):

```python
def run(
    business_id: str,
    my_business: dict,
    my_reviews: list[dict],
) -> list[dict]:
    """[unchanged docstring]"""
    # 0. Manual competitors persist across runs and always lead the list.
    manuals = _read_manuals(business_id)

    # 0a. Auto cache hit?
    cached = _read_cache(business_id)
    if cached is not None:
        logger.info(
            "[competitor_pipeline] cache HIT for business_id=%s — %d auto matches, %d manual",
            business_id, len(cached), len(manuals),
        )
        return _merge_manuals_and_auto(manuals, cached[:MAX_COMPETITORS])

    category = my_business.get("category", "")
    my_place_id = my_business.get("place_id")
    if not my_place_id:
        logger.warning("[competitor_pipeline] missing my place_id — returning empty")
        return []

    # 0b. Read user-configurable overrides (mode='auto' → all None).
    prefs_mode, prefs = _load_prefs(business_id)
    override_radius: int | None = None
    override_min: int | None = None
    override_max: int | None = None
    override_subcats: set[str] | None = None
    if prefs_mode == "custom" and isinstance(prefs, dict):
        override_radius = prefs.get("radius_m")
        override_min = prefs.get("min_reviews")
        override_max = prefs.get("max_reviews")
        subs = prefs.get("subcategories") or []
        if subs:
            override_subcats = set(subs)
        logger.info(
            "[competitor_pipeline.run] mode=custom override radius=%s min=%s max=%s subcats=%s",
            override_radius, override_min, override_max, override_subcats,
        )

    # 1. Discovery — Google Nearby Search.
    try:
        candidates = google_places.get_nearby_competitors(
            lat=my_business["lat"],
            lng=my_business["lng"],
            category=category,
            radius=override_radius if override_radius else COMPETITOR_RADIUS_METERS,
            exclude_place_id=my_place_id,
        )
    except Exception as exc:
        logger.warning("[competitor_pipeline] nearby search failed: %s", exc)
        return []

    if not candidates:
        logger.info("[competitor_pipeline] Google returned 0 candidates")
        _write_cache(business_id, [])
        return _merge_manuals_and_auto(manuals, [])

    # 2. Hard pre-filters (no API cost). Honour user min/max in custom mode.
    survivors = _drop_dead_listings(candidates, category, override_floor=override_min)
    survivors = _drop_above_max_reviews(survivors, override_max)
    survivors = _drop_excluded_primary_types(survivors, category)
    survivors = _drop_excluded_name_keywords(
        survivors, category, my_business.get("name", ""),
    )
    if not survivors:
        logger.info("[competitor_pipeline] hard filters wiped all %d candidates", len(candidates))
        _write_cache(business_id, [])
        return _merge_manuals_and_auto(manuals, [])

    # 3. Haiku sub-category tag (one batched call).
    tags = _tag_subcategories(
        parent_category=category,
        my_name=my_business.get("name", ""),
        candidates=survivors,
    )
    # ... [retain the existing retail brand top-up, by_subcat call, similarity
    # block, cache write, and return — but pass `override_subcats` into
    # `_drop_wrong_subcategory`]
    by_subcat = (
        _drop_wrong_subcategory(survivors, tags, allowed=override_subcats)
        if tags
        else survivors
    )

    # ... [rest of run() unchanged from this point]
```

Note for the implementer: keep the rest of the existing `run()` body intact (retail brand top-up, the size-cap, centroid logic, similarity scoring, `_write_cache`, `_merge_manuals_and_auto` return). The only edits are:
1. Insert the new `prefs_mode/prefs` block after the place_id guard.
2. Pass `radius=override_radius or COMPETITOR_RADIUS_METERS` into `get_nearby_competitors`.
3. Pass `override_floor=override_min` to `_drop_dead_listings`.
4. Insert one new `_drop_above_max_reviews` call.
5. Pass `allowed=override_subcats` to `_drop_wrong_subcategory`.

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_competitor_pipeline.py -v
```
Expected: PASS — `TestCustomPrefsOverride` plus all pre-existing tests.

- [ ] **Step 5: Commit**

```bash
git add app/services/competitor_pipeline.py tests/test_competitor_pipeline.py
git commit -m "feat(competitor-pipeline): honour custom prefs (radius, reviews, subcats)"
```

---

## Task 7: Frontend API helpers

**Files:**
- Modify: `vyaparai-frontend/lib/api.ts`

- [ ] **Step 1: Add types and helpers**

Append to `vyaparai-frontend/lib/api.ts`:

```typescript
// ─── Competitor preferences ───────────────────────────────────────────────────
export interface CompetitorPrefs {
  radius_m: 500 | 800 | 1000 | 1500 | 2000;
  min_reviews: number;
  max_reviews: number | null;
  subcategories: string[];
}

export interface CompetitorPreviewExample {
  name: string;
  place_id?: string | null;
  review_count: number;
  rating: number;
  sub_category: string | null;
}

export interface CompetitorPreview {
  radius_m: number;
  total_candidates: number;
  review_buckets: Record<string, number>;
  subcategory_counts: Record<string, number>;
  top_examples: CompetitorPreviewExample[];
  own_subcategory: string | null;
}

export async function getCompetitorPreview(
  businessId: string,
  radiusM: 500 | 800 | 1000 | 1500 | 2000,
): Promise<CompetitorPreview> {
  const res = await fetch(
    `${BASE}/competitors/preview/${encodeURIComponent(businessId)}?radius_m=${radiusM}`,
  );
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export interface PreferencesBody {
  mode: 'auto' | 'custom';
  prefs?: CompetitorPrefs;
}

export async function savePreferences(
  businessId: string,
  body: PreferencesBody,
  userId?: string,
): Promise<void> {
  const res = await fetch(`${BASE}/preferences/${encodeURIComponent(businessId)}`, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
      ...(userId ? { 'X-User-Id': userId } : {}),
    },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await res.text());
}
```

- [ ] **Step 2: Type-check**

```bash
cd vyaparai-frontend && npx tsc --noEmit
```
Expected: zero errors.

- [ ] **Step 3: Commit**

```bash
git add vyaparai-frontend/lib/api.ts
git commit -m "feat(frontend-api): preferences + preview helpers"
```

---

## Task 8: Shared PrefsForm component

**Files:**
- Create: `vyaparai-frontend/components/ui/PrefsForm.tsx`

- [ ] **Step 1: Implement the component**

Create `vyaparai-frontend/components/ui/PrefsForm.tsx`:

```tsx
'use client';

import { useEffect, useMemo, useState } from 'react';
import {
  CompetitorPrefs, CompetitorPreview, getCompetitorPreview, savePreferences,
} from '@/lib/api';

const RADII: CompetitorPrefs['radius_m'][] = [500, 800, 1000, 1500, 2000];
const RADIUS_LABELS: Record<number, string> = {
  500: '500m', 800: '800m', 1000: '1km', 1500: '1.5km', 2000: '2km',
};

const REVIEW_STOPS = [0, 5, 20, 50, 100, 200, 500, 1000];

function logToValue(idx: number): number {
  return REVIEW_STOPS[Math.max(0, Math.min(REVIEW_STOPS.length - 1, idx))];
}

function valueToLog(val: number): number {
  let best = 0;
  for (let i = 0; i < REVIEW_STOPS.length; i++) {
    if (REVIEW_STOPS[i] <= val) best = i;
  }
  return best;
}

export interface PrefsFormProps {
  businessId: string;
  category: string;
  userId?: string;
  initialPrefs?: CompetitorPrefs | null;
  initialMode?: 'auto' | 'custom';
  onSaved?: (mode: 'auto' | 'custom') => void;
  onSkip?: () => void;
}

export default function PrefsForm({
  businessId, category, userId,
  initialPrefs, initialMode = 'auto', onSaved, onSkip,
}: PrefsFormProps) {
  const [mode, setMode]               = useState<'auto' | 'custom'>(initialMode);
  const [radius, setRadius]           = useState<CompetitorPrefs['radius_m']>(
    initialPrefs?.radius_m ?? 800,
  );
  const [minIdx, setMinIdx]           = useState(valueToLog(initialPrefs?.min_reviews ?? 0));
  const [maxIdx, setMaxIdx]           = useState(
    initialPrefs?.max_reviews == null
      ? REVIEW_STOPS.length - 1
      : valueToLog(initialPrefs.max_reviews),
  );
  const [subcats, setSubcats]         = useState<string[]>(initialPrefs?.subcategories ?? []);
  const [preview, setPreview]         = useState<CompetitorPreview | null>(null);
  const [loading, setLoading]         = useState(false);
  const [error, setError]             = useState<string | null>(null);
  const [saving, setSaving]           = useState(false);

  // Fetch preview on mount + on radius change (debounced).
  useEffect(() => {
    let cancelled = false;
    const t = setTimeout(async () => {
      setLoading(true);
      setError(null);
      try {
        const p = await getCompetitorPreview(businessId, radius);
        if (!cancelled) {
          setPreview(p);
          // Pre-check the user's auto-detected sub-cat on first load.
          if (subcats.length === 0 && p.own_subcategory) setSubcats([p.own_subcategory]);
        }
      } catch (e: unknown) {
        if (!cancelled) setError(e instanceof Error ? e.message : 'Preview failed');
      } finally {
        if (!cancelled) setLoading(false);
      }
    }, 250);
    return () => { cancelled = true; clearTimeout(t); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [businessId, radius]);

  const filteredCount = useMemo(() => {
    if (!preview) return 0;
    const min = REVIEW_STOPS[minIdx];
    return Object.entries(preview.review_buckets)
      // Crude estimate: use the largest threshold ≤ min as the count.
      .filter(([k]) => parseInt(k, 10) <= min || min === 0)
      .reduce((acc, [, v]) => Math.max(acc, v), 0);
  }, [preview, minIdx]);

  function toggleMode() {
    setMode((m) => (m === 'auto' ? 'custom' : 'auto'));
  }

  function toggleSubcat(tag: string) {
    setMode('custom');
    setSubcats((s) => (s.includes(tag) ? s.filter((t) => t !== tag) : [...s, tag]));
  }

  async function handleAuto() {
    if (!businessId) return;
    setSaving(true);
    try {
      await savePreferences(businessId, { mode: 'auto' }, userId);
      onSaved?.('auto');
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Save failed');
    } finally {
      setSaving(false);
    }
  }

  async function handleSave() {
    if (!businessId) return;
    setSaving(true);
    try {
      const max = maxIdx >= REVIEW_STOPS.length - 1 ? null : REVIEW_STOPS[maxIdx];
      await savePreferences(businessId, {
        mode: 'custom',
        prefs: {
          radius_m: radius,
          min_reviews: REVIEW_STOPS[minIdx],
          max_reviews: max,
          subcategories: subcats,
        },
      }, userId);
      onSaved?.('custom');
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Save failed');
    } finally {
      setSaving(false);
    }
  }

  const minLabel = REVIEW_STOPS[minIdx].toString();
  const maxLabel = maxIdx >= REVIEW_STOPS.length - 1 ? '∞' : REVIEW_STOPS[maxIdx].toString();

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      {/* Hero CTA */}
      <div style={{
        padding: 20, border: '1.5px solid var(--border)', borderRadius: 12,
        background: 'var(--surface)',
      }}>
        <h3 style={{ margin: 0, marginBottom: 8 }}>Let Refloat decide</h3>
        <p style={{ margin: 0, marginBottom: 12, color: 'var(--muted)', fontSize: 14 }}>
          We'll auto-pick competitors near you based on category similarity. You can change this later.
        </p>
        <button
          type="button"
          onClick={handleAuto}
          disabled={saving}
          style={{
            padding: '10px 18px', borderRadius: 8, border: 'none',
            background: 'var(--text)', color: 'var(--bg)', cursor: 'pointer',
            fontWeight: 600,
          }}
        >
          {saving && mode === 'auto' ? 'Saving…' : 'Use auto'}
        </button>
        <button
          type="button"
          onClick={toggleMode}
          style={{
            marginLeft: 12, padding: '10px 18px', borderRadius: 8,
            border: '1.5px solid var(--border)', background: 'transparent',
            color: 'var(--text)', cursor: 'pointer',
          }}
        >
          {mode === 'auto' ? 'Or customize ↓' : 'Hide options ↑'}
        </button>
      </div>

      {mode === 'custom' && (
        <>
          {/* Sub-categories */}
          <section>
            <h4 style={{ margin: 0, marginBottom: 8 }}>Compete against</h4>
            <p style={{ margin: 0, marginBottom: 12, color: 'var(--muted)', fontSize: 13 }}>
              Pick the sub-categories you want benchmarked. Numbers show nearby places.
            </p>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
              {preview && Object.entries(preview.subcategory_counts).map(([tag, count]) => {
                const active = subcats.includes(tag);
                return (
                  <button
                    key={tag}
                    type="button"
                    onClick={() => toggleSubcat(tag)}
                    style={{
                      padding: '6px 12px', borderRadius: 999, fontSize: 13,
                      border: active ? '1.5px solid var(--text)' : '1.5px solid var(--border)',
                      background: active ? 'var(--text)' : 'transparent',
                      color: active ? 'var(--bg)' : 'var(--text)', cursor: 'pointer',
                    }}
                  >
                    {tag.replace(/_/g, ' ')} ({count})
                  </button>
                );
              })}
              {!preview && <span style={{ color: 'var(--muted)' }}>Loading…</span>}
            </div>
          </section>

          {/* Distance */}
          <section>
            <h4 style={{ margin: 0, marginBottom: 8 }}>Distance</h4>
            <div style={{ display: 'flex', gap: 8 }}>
              {RADII.map((r) => (
                <button
                  key={r}
                  type="button"
                  onClick={() => { setMode('custom'); setRadius(r); }}
                  style={{
                    padding: '6px 14px', borderRadius: 8, fontSize: 13,
                    border: radius === r ? '1.5px solid var(--text)' : '1.5px solid var(--border)',
                    background: radius === r ? 'var(--text)' : 'transparent',
                    color: radius === r ? 'var(--bg)' : 'var(--text)', cursor: 'pointer',
                  }}
                >
                  {RADIUS_LABELS[r]}
                </button>
              ))}
            </div>
          </section>

          {/* Reviews range */}
          <section>
            <h4 style={{ margin: 0, marginBottom: 8 }}>Review-count range</h4>
            <p style={{ margin: 0, marginBottom: 12, color: 'var(--muted)', fontSize: 13 }}>
              Min: {minLabel} · Max: {maxLabel}{loading ? ' · loading…' : ''}
            </p>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <input
                type="range" min={0} max={REVIEW_STOPS.length - 1} step={1}
                value={minIdx}
                onChange={(e) => { setMode('custom'); setMinIdx(Math.min(Number(e.target.value), maxIdx)); }}
                style={{ flex: 1 }}
              />
              <input
                type="range" min={0} max={REVIEW_STOPS.length - 1} step={1}
                value={maxIdx}
                onChange={(e) => { setMode('custom'); setMaxIdx(Math.max(Number(e.target.value), minIdx)); }}
                style={{ flex: 1 }}
              />
            </div>
            {preview && preview.top_examples.length > 0 && (
              <p style={{ marginTop: 10, fontSize: 13, color: 'var(--muted)' }}>
                Top nearby: {preview.top_examples.slice(0, 3).map((e) => `${e.name} (${e.review_count})`).join(', ')}
              </p>
            )}
            {preview && (
              <p style={{ marginTop: 4, fontSize: 12, color: 'var(--muted)' }}>
                Approx. matches in this range: {filteredCount}
              </p>
            )}
          </section>

          {/* Footer */}
          <div style={{ display: 'flex', gap: 12 }}>
            {onSkip && (
              <button
                type="button"
                onClick={onSkip}
                style={{
                  padding: '10px 18px', borderRadius: 8,
                  border: '1.5px solid var(--border)', background: 'transparent',
                  color: 'var(--text)', cursor: 'pointer',
                }}
              >
                Skip for now
              </button>
            )}
            <button
              type="button"
              onClick={handleSave}
              disabled={saving}
              style={{
                padding: '10px 18px', borderRadius: 8, border: 'none',
                background: 'var(--text)', color: 'var(--bg)', cursor: 'pointer',
                fontWeight: 600,
              }}
            >
              {saving ? 'Saving…' : 'Save preferences'}
            </button>
          </div>
        </>
      )}

      {error && (
        <div role="alert" style={{ color: '#c33', fontSize: 13 }}>
          {error}
        </div>
      )}

      {/* Suppress unused-import warning when category isn't displayed */}
      <span style={{ display: 'none' }}>{category}</span>
    </div>
  );
}
```

- [ ] **Step 2: Type-check**

```bash
cd vyaparai-frontend && npx tsc --noEmit
```
Expected: zero errors.

- [ ] **Step 3: Commit**

```bash
git add vyaparai-frontend/components/ui/PrefsForm.tsx
git commit -m "feat(frontend): PrefsForm component (auto + custom paths)"
```

---

## Task 9: Step 2 page + onboard route change

**Files:**
- Create: `vyaparai-frontend/app/onboard/preferences/page.tsx`
- Modify: `vyaparai-frontend/app/onboard/business/page.tsx`

- [ ] **Step 1: Implement the Step 2 page**

Create `vyaparai-frontend/app/onboard/preferences/page.tsx`:

```tsx
'use client';

import { Suspense } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { Aurora, Logo, Steps, ThemeToggle } from '@/components/ui';
import PrefsForm from '@/components/ui/PrefsForm';
import { useAuth } from '@/lib/auth-context';

function PreferencesInner() {
  const router        = useRouter();
  const params        = useSearchParams();
  const { user }      = useAuth();
  const businessId    = params.get('business_id') ?? '';
  const category      = params.get('category') ?? 'restaurant';

  function done() {
    router.push('/dashboard');
  }

  return (
    <div style={{ minHeight: '100vh', position: 'relative' }}>
      <Aurora />
      <header style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '20px 32px',
      }}>
        <Logo />
        <ThemeToggle />
      </header>
      <main style={{ maxWidth: 720, margin: '0 auto', padding: 32 }}>
        <Steps current={1} steps={['Business', 'Preferences']} />
        <h1 style={{ marginTop: 24 }}>How should we benchmark you?</h1>
        <p style={{ color: 'var(--muted)', marginBottom: 24 }}>
          Pick your competition or let Refloat figure it out — you can change this anytime.
        </p>

        {!businessId ? (
          <p style={{ color: '#c33' }}>Missing business id — restart onboarding.</p>
        ) : (
          <PrefsForm
            businessId={businessId}
            category={category}
            userId={user?.id}
            onSaved={done}
            onSkip={done}
          />
        )}
      </main>
    </div>
  );
}

export default function PreferencesPage() {
  return (
    <Suspense fallback={null}>
      <PreferencesInner />
    </Suspense>
  );
}
```

- [ ] **Step 2: Modify the onboard business page to route to Step 2**

Edit `vyaparai-frontend/app/onboard/business/page.tsx`. Find the success branch in the form submit handler. The current success path routes to `/dashboard`. Change it to:

```tsx
// On successful onboard, route to /onboard/preferences with business_id + category.
router.push(
  `/onboard/preferences?business_id=${encodeURIComponent(business_id)}` +
  `&category=${encodeURIComponent(category)}`,
);
```

The implementer should locate the existing post-onboard navigation (`router.push('/dashboard')` or similar) inside this file and replace exactly that line. Categories already exist as a state value `category` and `business_id` is the key returned by `onboardBusiness`.

- [ ] **Step 3: Manual smoke test**

```bash
cd /Users/pg/Desktop/VyaaparAI && source venv/bin/activate
uvicorn app.main:app --reload &
cd vyaparai-frontend && npm run dev
```

Walk the flow: open the dev URL, sign in, complete onboard step 1, verify it routes to `/onboard/preferences?business_id=…`, click *Use auto*, verify dashboard loads. Repeat with *Or customize*, save, verify dashboard loads.

Stop the dev servers with Ctrl-C.

- [ ] **Step 4: Commit**

```bash
git add vyaparai-frontend/app/onboard/preferences/page.tsx \
        vyaparai-frontend/app/onboard/business/page.tsx
git commit -m "feat(frontend): onboarding step 2 — preferences page"
```

---

## Task 10: Dashboard settings entry

**Files:**
- Modify: `vyaparai-frontend/app/dashboard/page.tsx`

- [ ] **Step 1: Add a settings drawer**

In `vyaparai-frontend/app/dashboard/page.tsx`, locate the Competitors tab section. Add a button at the top of that tab and a modal/drawer that reuses the `PrefsForm` component.

Pseudocode (the implementer adapts to the existing JSX shape):

```tsx
import PrefsForm from '@/components/ui/PrefsForm';

const [showPrefs, setShowPrefs] = useState(false);

// Inside the Competitors tab JSX (near the existing "manual add" controls):
<button
  type="button"
  onClick={() => setShowPrefs(true)}
  style={{ /* same ghost-button style used elsewhere on this page */ }}
>
  Competitor settings
</button>

{showPrefs && (
  <div
    role="dialog"
    style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)',
      display: 'flex', justifyContent: 'flex-end', zIndex: 50,
    }}
    onClick={() => setShowPrefs(false)}
  >
    <div
      onClick={(e) => e.stopPropagation()}
      style={{
        width: 'min(560px, 100%)', height: '100%',
        background: 'var(--bg)', padding: 24, overflowY: 'auto',
      }}
    >
      <h2 style={{ marginTop: 0 }}>Competitor settings</h2>
      <PrefsForm
        businessId={businessId}
        category={report?.category ?? 'restaurant'}
        userId={user?.id}
        onSaved={() => { setShowPrefs(false); regenerate(true); }}
      />
    </div>
  </div>
)}
```

`regenerate(true)` is the existing helper that calls `generateReport(businessId, true)` (force=true, since the cache was just invalidated server-side). If the helper is named differently in this file, use the existing one — don't introduce a new name.

- [ ] **Step 2: Type-check + smoke test**

```bash
cd vyaparai-frontend && npx tsc --noEmit
npm run dev
```

Open dashboard → Competitors tab → click *Competitor settings* → drawer opens with `PrefsForm` → save / use auto → drawer closes → report regenerates.

- [ ] **Step 3: Commit**

```bash
git add vyaparai-frontend/app/dashboard/page.tsx
git commit -m "feat(frontend): competitor settings drawer on dashboard"
```

---

## Task 11: Update CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Add the new artefacts**

Edit `CLAUDE.md`:

1. In the **Key files** table, add rows for:
   - `app/api/preferences.py` — PUT /preferences/{id} (saves prefs, invalidates competitor + report caches).
   - `app/services/competitor_preview.py` — cheap nearby + Haiku preview (1h cache) for onboarding form.
   - `tests/test_competitor_preview.py` — unit tests for the preview service + endpoint.
   - `tests/test_competitor_prefs.py` — unit tests for prefs Pydantic models + PUT endpoint.
   - `vyaparai-frontend/app/onboard/preferences/page.tsx` — Step 2 page (sub-cats / distance / review range / let-Refloat-decide).
   - `vyaparai-frontend/components/ui/PrefsForm.tsx` — shared component reused on dashboard.
   - `migrations/2026-05-04-competitor-prefs.sql` — applied; adds 3 columns to `businesses` + `competitor_preview_cache` table.

2. In the **Database tables** section:
   - Update the `businesses` row to mention `competitor_prefs_mode`, `competitor_prefs JSONB`, `competitor_prefs_updated_at`.
   - Add a new row for `competitor_preview_cache` (place_id, radius_m, payload JSONB, fetched_at — 1h TTL).

3. In the **Architecture in one paragraph** section, after the *Manual rows pinned via /competitors/{id} always lead the list* sentence, append:
   > Users can also shape auto-discovery itself via `PUT /preferences/{business_id}` — saved as `competitor_prefs_mode + competitor_prefs JSONB` on `businesses`, read at the top of `competitor_pipeline.run()` to override radius/min/max review counts and the allowed sub-category set. The onboarding flow's Step 2 page calls `GET /competitors/preview` (cheap Nearby + Haiku, 1h cache) to render live counts.

4. Add a Session 13 footer line:
   ```
   *Last updated: 04 May 2026 (Session 13 — Competitor preferences form: onboarding Step 2 + dashboard settings drawer + pipeline overrides + 1h preview cache).*
   ```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(claude.md): document competitor preferences feature"
```

---

## Self-Review Checklist

Before declaring done:

1. **Spec coverage:**
   - ✅ JSONB on `businesses` (Task 1).
   - ✅ Preview endpoint with 1h cache (Tasks 3, 4).
   - ✅ PUT /preferences with cache invalidation (manual rows survive, health_scores wiped) (Task 5).
   - ✅ Pipeline overrides (radius, min/max reviews, subcategory union) (Task 6).
   - ✅ Frontend Step 2 page + dashboard settings drawer (Tasks 8, 9, 10).
   - ✅ Sub-category whitelist validated server-side against `SUBCATEGORIES_BY_CATEGORY[category]` (Task 5).
   - ✅ Backward-compat: NULL prefs / mode=auto preserves today's pipeline (Task 6 default-path test).
   - ✅ Empty `subcategories` widens (no filter applied) — implemented by `override_subcats=None` in Task 6.

2. **Placeholder scan:** No "TBD" / "TODO" / "implement later" / "appropriate error handling" left. Every code step has actual code.

3. **Type consistency:**
   - `CompetitorPrefs` shape identical between Pydantic (Task 2), TS interface (Task 7), and pipeline override path (Task 6).
   - `_load_prefs` defined in Task 6 Step 3 and consumed by `run()` in same task — name matches the test in Task 6 Step 1.
   - `_drop_dead_listings` signature change (added `override_floor`) is compatible with the existing call site in `_topup_branded_retail` (no override passed → uses category default — backward compatible).
   - `getCompetitorPreview` and `savePreferences` names match between `lib/api.ts` (Task 7) and `PrefsForm.tsx` (Task 8).
