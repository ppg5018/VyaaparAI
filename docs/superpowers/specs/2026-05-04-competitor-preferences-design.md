# Competitor Preferences — Design Spec

**Date:** 2026-05-04
**Status:** Draft — pending user review
**Owner:** Pratham

## Goal

Let MSME owners shape the auto-discovery side of the competitor pipeline during onboarding (and edit it later from a settings panel) without forcing them to fill anything if they don't want to. Today's pipeline is fully automatic with hardcoded knobs (`COMPETITOR_RADIUS_METERS=800`, `MIN_COMPETITOR_REVIEWS=20`, sub-category pinned to user's own auto-tag). This adds a one-click *Let Refloat decide* path that preserves today's behaviour exactly, plus a customise path that exposes three knobs: distance, review-count range, and sub-categories to compete against.

Out of scope for this spec: price-tier filtering, cross-parent-category competitors, daily-resolution analytics. Manual competitor pinning already exists via `POST /competitors/{business_id}` and is unchanged.

## Non-goals

- No change to the manual-pin flow (`is_manual` rows in `competitor_matches`).
- No change to the health-score formula or the review/POS sub-scores.
- No change to onboarding step 1 (`/onboard/business`).
- No change to the 7-day `competitor_matches` TTL semantics for non-manual rows beyond targeted invalidation on preference save.

## User flow

1. User completes `/onboard/business` (Step 1) → backend creates business row → frontend routes to `/onboard/preferences` (Step 2, new).
2. Page mounts → frontend calls `GET /competitors/preview/{business_id}?radius_m=800` once for default-state guidance numbers.
3. User sees a hero CTA *Let Refloat decide* and a collapsed *Or customize below* link.
   - **Path A — accepts auto:** clicks the CTA → `PUT /preferences/{business_id}` with `{mode:"auto"}` → routes to dashboard. JSONB stays NULL.
   - **Path B — customises:** clicks the link / interacts with any field → form expands, mode switches to `custom`.
4. Customise form has three sections (sub-categories, distance, reviews range). Slider/pill changes re-fetch the preview endpoint debounced 300ms; the cached result inside the 1-hour TTL means most reshuffles are server-cheap.
5. User clicks `Save preferences` → `PUT /preferences/{business_id}` with `{mode:"custom", prefs:{...}}` → backend wipes non-manual `competitor_matches` rows + the latest `health_scores` for this business → frontend routes to dashboard.
6. Same form is reachable post-onboarding from a *Competitor settings* panel on the Competitors tab.

## Architecture

### Database

Migration `migrations/2026-05-04-competitor-prefs.sql`:

```sql
ALTER TABLE businesses
  ADD COLUMN competitor_prefs_mode TEXT NOT NULL DEFAULT 'auto'
    CHECK (competitor_prefs_mode IN ('auto', 'custom')),
  ADD COLUMN competitor_prefs JSONB,
  ADD COLUMN competitor_prefs_updated_at TIMESTAMPTZ;

CREATE INDEX idx_businesses_prefs_mode ON businesses(competitor_prefs_mode);

CREATE TABLE competitor_preview_cache (
  place_id TEXT NOT NULL,
  radius_m INT NOT NULL,
  payload JSONB NOT NULL,
  fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (place_id, radius_m)
);
CREATE INDEX idx_competitor_preview_cache_fetched_at
  ON competitor_preview_cache(fetched_at);
```

Why JSONB on `businesses` rather than a side table: the prefs blob is small, per-business, accessed exactly when the business row is loaded by the pipeline, and never relationally queried. JSONB avoids a join on the hot read path.

Why a separate `competitor_preview_cache`: previews are accessed from the frontend during onboarding (potentially many times per minute as the user drags sliders), but they are cheaper Nearby Search + Haiku tag results — not full pipeline runs. Storing them in `competitor_matches` would mix incomplete (no Apify, no Cohere) and complete results in the same table and break the 7-day TTL semantics.

### Backend

**File: `app/api/preferences.py`** (new) — registers two endpoints under `/preferences`. Wired into `app/main.py` alongside the existing 6 routers.

**File: `app/api/competitors.py`** (extend) — adds `GET /competitors/preview/{business_id}`.

**File: `app/services/competitor_preview.py`** (new) — wraps Nearby Search + Haiku tag, computes review buckets and sub-category counts, reads/writes `competitor_preview_cache` with 1-hour TTL.

**File: `app/services/competitor_pipeline.py`** (modify) — at the top of `run()`, read `competitor_prefs_mode` and `competitor_prefs` from the `businesses` row already in scope. When `mode=='custom'`:

- `radius` parameter to `places_nearby` ← `prefs.radius_m`
- review-count floor in the pre-filter ← `prefs.min_reviews` (instead of `MIN_COMPETITOR_REVIEWS` / `CATEGORY_MIN_COMPETITOR_REVIEWS[category]`)
- new max review-count cap ← `prefs.max_reviews` (None = no cap)
- allowed sub-category set in the sub-category filter ← `set(prefs.subcategories)` (today: `{user_subcat}` only)

`SIMILARITY_FALLBACK_FLOOR` and `MIN_COMPETITORS_AFTER_FILTER` still apply unchanged. Overrides do not bypass safety floors.

**File: `app/models.py`** (extend):

```python
class CompetitorPrefs(BaseModel):
    radius_m: Literal[500, 800, 1000, 1500, 2000] = 800
    min_reviews: int = Field(0, ge=0, le=10000)
    max_reviews: Optional[int] = Field(None, ge=1, le=100000)
    subcategories: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_range(self):
        if self.max_reviews is not None and self.max_reviews < self.min_reviews:
            raise ValueError("max_reviews must be >= min_reviews")
        return self


class PreferencesRequest(BaseModel):
    mode: Literal["auto", "custom"]
    prefs: Optional[CompetitorPrefs] = None

    @model_validator(mode="after")
    def check_prefs_required(self):
        if self.mode == "custom" and self.prefs is None:
            raise ValueError("prefs required when mode='custom'")
        return self


class CompetitorPreviewResponse(BaseModel):
    radius_m: int
    total_candidates: int
    review_buckets: dict[str, int]   # keys: "5+", "20+", "50+", "100+", "200+"
    subcategory_counts: dict[str, int]
    top_examples: list[dict]         # name, review_count, sub_category, place_id
```

Sub-category whitelist validation: `prefs.subcategories` is checked against `SUBCATEGORIES_BY_CATEGORY[business.category]` server-side; unknown tags rejected with 400. Empty list is allowed and means "any sub-category" (we widen, not narrow, by default — the user explicitly opted into custom and chose to leave it open).

### Endpoints

**`GET /competitors/preview/{business_id}`**

Query: `radius_m` (one of 500/800/1000/1500/2000, default 800). Response: `CompetitorPreviewResponse`. Reads `competitor_preview_cache` first; on miss runs Nearby Search (cheap, single page — no need to paginate for a preview), runs the existing `_tag_subcategories` helper for sub-category counts, computes buckets, writes the cache. TTL = 1 hour. Errors: 404 if business not found, 503 if Google Places unavailable (matches existing onboarding pattern).

Why no `subcategories` query parameter: bucket counts and top examples are computed across all sub-categories so the frontend can render counts on each pill simultaneously. Filtering happens client-side from the per-sub-category counts already in the response.

**`PUT /preferences/{business_id}`**

Body: `PreferencesRequest`. Headers: `X-User-Id` for ownership check (matches the existing Supabase auth pattern in `/businesses/by-user/{user_id}` — formal auth middleware is out of scope for this spec). Logic:

1. Load business row. 404 if missing.
2. If `business.user_id` is set and `X-User-Id` does not match → 403.
3. Validate `prefs.subcategories` against `SUBCATEGORIES_BY_CATEGORY[business.category]`. 400 on any unknown tag.
4. Update `businesses` row: set `competitor_prefs_mode`, `competitor_prefs` (NULL when `mode=='auto'`), `competitor_prefs_updated_at = NOW()`.
5. Delete from `competitor_matches WHERE business_id = $1 AND is_manual = false`. Manual pins survive.
6. Delete from `health_scores WHERE business_id = $1`. The next `/generate-report` rebuilds with new prefs without needing `?force=true`.
7. Return `204 No Content`.

Idempotent: same body produces same end state. Retries are safe.

### Frontend

**File: `vyaparai-frontend/app/onboard/preferences/page.tsx`** (new). Reuses `Aurora`, `Field`, `Logo`, `Steps`, `ThemeToggle` from `@/components/ui` and the same `SHARED_INPUT_STYLE` pattern as `app/onboard/business/page.tsx`.

**File: `vyaparai-frontend/lib/api.ts`** (extend) — add `getCompetitorPreview(businessId, radiusM)`, `savePreferences(businessId, body)`.

**File: `vyaparai-frontend/app/onboard/business/page.tsx`** (modify) — on successful onboard, route to `/onboard/preferences?business_id=...` instead of straight to dashboard.

**File: `vyaparai-frontend/app/dashboard/page.tsx`** (modify) — add a *Competitor settings* button on the Competitors tab that opens the same preferences component as a modal/drawer. Reuse the same React component to avoid drift.

Layout (Step 2 page):
- Page header: "How should we benchmark you?" + sub-line "Pick your competition or let Refloat figure it out — you can change this anytime."
- Hero CTA: large primary button *Let Refloat decide*. Below it: text link *Or customize below ↓*.
- Form (collapsed by default; expands when user clicks the link or interacts with any field):
  - **Sub-categories.** Multi-select pills sourced from `subcategory_counts` in the preview response. Pre-check the user's auto-detected sub-cat (read from the preview's `top_examples` for the user's own place_id, or from a separate field added to the preview response — see open questions). Pill label: `"South Indian (23)"` where 23 is the count.
  - **Distance.** 5 stepped pills: `500m  800m  1km  1.5km  2km`. Default 800m. Click changes `radius_m` and triggers preview re-fetch (debounced 300ms).
  - **Reviews range.** Two-thumb slider 0–1000+ (logarithmic stops: 0, 5, 20, 50, 100, 200, 500, 1000+). Live readout below: *"~18 places match — top: Janatha Hotel (412), MTR (380), Brahmin's Coffee Bar (310)"*. Numbers come from the preview response's `review_buckets` for the matching threshold and `top_examples` filtered by the chosen range client-side.
- Footer: `Skip for now` (no PUT, mode stays auto) + `Save preferences` (PUT custom). Both route to dashboard.

Loading and error states: show a skeleton while the preview is in flight; show a soft error toast and fall back to defaults (allowing the user to save without live counts) if the preview endpoint fails.

### Tests

**Backend:**

- `tests/test_competitor_preview.py` (new) — bucket-count logic, sub-category counts, 1-hour cache hit/miss, mocked Google Places + Haiku. ~10 cases.
- `tests/test_competitor_prefs.py` (new) — Pydantic validation (radius enum, min/max range, max>=min, unknown sub-category rejected), PUT cache-invalidation (`competitor_matches` non-manual wiped, manual preserved, `health_scores` wiped), ownership 403, mode=auto sets JSONB to NULL. ~12 cases.
- `tests/test_competitor_pipeline.py` (extend) — three new cases: custom radius is honoured, min/max review filters strip correctly, sub-category widening returns the union; one backward-compat case asserting `mode=auto` produces byte-identical output to today's hardcoded path.

**Frontend:** manual smoke test pre-merge (run dev server, walk the onboarding flow end-to-end, edit prefs from the dashboard, regenerate report, verify the new prefs are reflected in `competitor_matches`). Frontend unit tests are not currently part of the project; not adding them in this spec.

### Observability

Structured log lines:
- `[preferences.put] business_id=… mode=… radius_m=… min/max=… subcats=…` on save.
- `[competitor_pipeline.run] mode=custom override radius=… min=… max=… subcats=…` when overrides apply, so we can correlate pipeline behaviour with user choices.
- `[preferences.preview] cache=hit|miss place_id=… radius_m=… candidates=…` on every preview.

Counter (Supabase row count): periodic `SELECT competitor_prefs_mode, count(*) FROM businesses GROUP BY 1` for the analytics view.

## Build sequence

1. Migration applied (`migrations/2026-05-04-competitor-prefs.sql`).
2. `app/models.py` extended with `CompetitorPrefs`, `PreferencesRequest`, `CompetitorPreviewResponse`.
3. `app/services/competitor_preview.py` written + unit tests.
4. `app/api/preferences.py` written (PUT) + unit tests.
5. `app/api/competitors.py` extended with `GET /competitors/preview/...` + unit tests.
6. `app/services/competitor_pipeline.py` modified to read prefs and override + extended pipeline tests.
7. `app/main.py` registers the new router.
8. Frontend: `lib/api.ts` helpers, `app/onboard/preferences/page.tsx`, route change in `app/onboard/business/page.tsx`, settings entry in `app/dashboard/page.tsx`.
9. Manual end-to-end smoke test.
10. Update `CLAUDE.md` (new files, new endpoints, new columns, new migration).

## Risks & open questions

- **Auto-detected sub-cat exposure.** The preview endpoint needs to return the user's own auto-tagged sub-category so the frontend can pre-check the right pill. Add an `own_subcategory: str | null` field to `CompetitorPreviewResponse`. (Not a blocker — small addition.)
- **Health-scores cache wipe blast radius.** Wiping all `health_scores` rows for a business on every preference save means losing the history view's recent data points. Acceptable because: (a) prefs changes are rare, (b) the history view shows score-over-time for the *same* config — mixing pre/post-pref-change scores would be misleading anyway. Document this trade-off in `CLAUDE.md`.
- **Empty subcategories list semantics.** Spec says empty = "any sub-category". The alternative is empty = invalid. Going with widen-by-default because the user explicitly opted into `custom`; if they wanted today's strict behaviour, they'd hit *Let Refloat decide*.
- **Logarithmic slider on the frontend.** No existing logarithmic-slider primitive in `vyaparai-frontend/components/ui`. Build a simple one inside the preferences page (~50 lines) rather than pulling a dep — same approach as the existing custom Steps component.
- **Preview cache eviction.** No automatic cleanup of `competitor_preview_cache` rows older than 1 hour. Acceptable at MVP scale (small table); add a cron later if it grows.
