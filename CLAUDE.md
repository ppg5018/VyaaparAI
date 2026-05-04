# CLAUDE.md — VyaparAI Module 1

This file is Claude Code's memory for this project. Read it at the start of every session.

---

## Project goal

Build a FastAPI backend that generates a 0–100 business health score for Indian MSMEs using Google Places data (reviews + competitors) + synthetic POS sales data, then generates 3 specific insights using the Claude API. MVP only — no UI, no WhatsApp, no scheduler.

## Current phase

MVP — backend deployed to Render via `render.yaml`; Next.js frontend in `vyaparai-frontend/`. Local development still primary.

## Architecture in one paragraph

`app/main.py` is the lean FastAPI factory that registers 7 APIRouters from `app/api/` (onboard, pos, report, history, actions, competitors, preferences) plus a `/health` probe and CORS middleware. All env vars and constants live in `app/config.py`; all services import named constants from there. `app/database.py` holds the single Supabase client. `/onboard` registers a business (with optional Supabase `user_id` linkage). `/upload-pos` ingests a CSV into `pos_records`. `/generate-report` runs the full pipeline: `google_places.fetch_all_data()` → `apify_reviews.get_reviews()` augments with up to 50 scraped reviews (and surfaces reviewer-credibility fields from the cached `raw` JSONB) → `competitor_pipeline.run()` builds the similarity-filtered competitor list (Cohere centroids + Apify review fetch) → `review_classifier.classify_reviews()` Haiku-tags sentiment and carries reviewer credibility forward → `health_score` computes 3 credibility-weighted sub-scores → `pos_pipeline.pos_signals()` computes POS signals across 3 windows (7-vs-28 acute, 30-vs-30 current, 90-vs-90 chronic) → `insights.generate_insights()` calls Claude Sonnet → `competitor_analysis.analyze_competitors()` produces themes/opportunities from cached competitor reviews → result + full payload saved to `health_scores`. The endpoint cache returns the latest payload < 24h old unless `?force=true`. `/competitors/{id}` lets users pin manual competitors that survive auto-discovery rebuilds. Users can also shape auto-discovery itself via `PUT /preferences/{business_id}` — saved as `competitor_prefs_mode + competitor_prefs JSONB` on `businesses`, read at the top of `competitor_pipeline.run()` to override radius/min/max review counts and the allowed sub-category set. The onboarding flow's Step 2 page calls `GET /competitors/preview` (cheap Nearby + Haiku, 1h cache) to render live counts. `/history` returns past scores. `/actions/*` logs user interactions on insights. Auxiliary tables `external_reviews` + `review_syncs` cache Apify reviews; `review_embeddings` + `competitor_matches` back the competitor pipeline; `actions_log` stores user actions.

## Tech stack

- Python 3.11 + FastAPI + Uvicorn
- Supabase (PostgreSQL) via supabase-py
- Google Maps Python client (Places API)
- Anthropic SDK — Sonnet `claude-sonnet-4-20250514` for insights and competitor analysis; Haiku `claude-haiku-4-5-20251001` for review classification and sub-category tagging
- Apify (`compass~google-maps-reviews-scraper`) — bypasses Google's 5-review cap; cached in Supabase
- Cohere `embed-multilingual-v3.0` (1024-dim) — embeds review text for semantic competitor matching; vectors cached in Supabase via `pgvector`
- Pandas + Faker for synthetic POS data
- Frontend: Next.js 14 (App Router) in `vyaparai-frontend/` with Supabase auth (Google Sign-In)

## Key files

| File | Status | Purpose |
|---|---|---|
| `app/main.py` | exists — complete | FastAPI factory — registers 5 APIRouters + /health, CORS, exception handler |
| `app/config.py` | exists — complete | Single source of truth for all env vars and numeric constants |
| `app/database.py` | exists — complete | Singleton Supabase client |
| `app/logging_config.py` | exists — complete | setup_logging() — file + console handlers, suppresses noisy loggers |
| `app/models.py` | exists — complete | All Pydantic v2 models — OnboardRequest, ReportResponse, etc. |
| `app/api/onboard.py` | exists — complete | POST /onboard, GET /search-places, GET /businesses/by-user/{user_id} |
| `app/api/pos.py` | exists — complete | POST /upload-pos/{business_id} router |
| `app/api/report.py` | exists — complete | POST /generate-report/{business_id} — full pipeline + 24h cache |
| `app/api/history.py` | exists — complete | GET /history/{business_id} router |
| `app/api/actions.py` | exists — complete | POST/GET /actions/{business_id}, DELETE /actions/{action_id} |
| `app/services/google_places.py` | exists — complete | Google Places fetch + parse — incl. price_level + photo_count |
| `app/services/apify_reviews.py` | exists — complete | Apify scraper integration with `external_reviews` + `review_syncs` cache (7d own / 30d competitor) |
| `app/services/health_score.py` | exists — complete | Score engine — review (incl. velocity) + competitor + POS (4 signals) |
| `app/services/insights.py` | exists — complete | Claude Sonnet insights — dynamic count 3–6, retry on parse fail |
| `app/api/competitors.py` | exists — complete | POST/DELETE `/competitors/{business_id}` — pin manual competitors that survive auto-discovery rebuilds. Also `GET /competitors/preview/{business_id}?radius_m=` — cheap Nearby+Haiku preview for the onboarding form |
| `app/api/preferences.py` | exists — complete | `PUT /preferences/{business_id}` — saves `competitor_prefs_mode` + `competitor_prefs` JSONB on `businesses`. On save: wipes non-manual `competitor_matches` rows + `health_scores` 24h cache so the next /generate-report rebuilds with new prefs. X-User-Id header for ownership check |
| `app/services/competitor_preview.py` | exists — complete | Cheap preview pipeline (Nearby Search + Haiku tag, no Apify, no Cohere) for the onboarding preferences form. Caches per (place_id, radius_m) in `competitor_preview_cache` with 1-hour TTL |
| `app/services/competitor_pipeline.py` | exists — complete | Competitor pipeline v2 — orchestrates Nearby Search (paginated prominence + distance-rank) → hard pre-filters (review-count floor, type exclusion, name keywords) → Haiku sub-category tag → retail brand top-up via Text Search → top-N cap by rating → Apify review fetch (parallelised) → Cohere centroid embeddings → cosine similarity filter → upsert `competitor_matches` (7-day TTL). Manual rows persist across rebuilds. Cache hit short-circuits the whole flow. |
| `app/services/competitor_analysis.py` | exists — complete | Sonnet-generated themes (what competitors are praised for) and opportunities (gaps to exploit) from cached Apify reviews. One call per /generate-report cache miss. |
| `app/services/embeddings.py` | exists — complete | Cohere client (`embed-multilingual-v3.0`, 1024-dim) + Supabase `review_embeddings` cache. Per-review and per-business-centroid units, content-keyed by SHA-256 text_hash to skip re-embedding identical text. Includes `cosine_similarity`, `rank_by_similarity`, pgvector parsing helpers. |
| `app/services/review_classifier.py` | exists — complete | Haiku batched sentiment + topic tagging for up to 50 reviews; carries reviewer-credibility fields forward into each classified entry so downstream weighting can apply per-review without index alignment |
| `app/services/review_credibility.py` | exists — complete | `credibility_weight(review)` returns 1.5 / 1.2 / 1.0 / 0.5 from `reviewer_review_count` and `reviewer_is_local_guide`. Absent fields → neutral 1.0 (preserves backward compat). Consumed by `health_score.review_score` and `compute_velocity(weighted=True)` |
| `app/services/pos_pipeline.py` | exists — complete | POS ingestion + signal computation (revenue 3-window, slow-cat, AOV, repeat-rate) + chart_data() for dashboard. `_window_trend()` daily-averages any recent/prior window pair so `revenue_trend_acute_pct` (7-vs-28) and `revenue_trend_chronic_pct` (90-vs-90) sit alongside the original 30-vs-30 `revenue_trend_pct` |
| `app/services/pos_column_matcher.py` | exists — complete | Three-layer deterministic column matcher (exact / difflib fuzzy / value-sniff) for heterogeneous POS exports (Petpooja, DotPe, Tally, Vyapar, hand-built Excel). `ingest_pos_csv` delegates to `canonicalise()` before validation. No LLM. |
| `scripts/generate_synthetic_pos.py` | exists — complete | Faker + Pandas CSV generator — 5 profiles, 90-day data, reproducible (SEED=42) |
| `scripts/seed_test_data.py` | exists — complete | CLI tool to upload a synthetic CSV to a given business_id |
| `tests/test_connections.py` | exists | Verifies Supabase connectivity |
| `tests/test_google_places.py` | exists | End-to-end test for google_places.py (5 Bangalore place IDs) |
| `tests/test_pos_pipeline.py` | exists | End-to-end test for pos_pipeline.py (requires Supabase) |
| `tests/test_health_score.py` | exists | Unit + integration tests for health_score.py (23 assertions, no external deps) |
| `tests/test_csv_scoring.py` | exists | CSV-based scoring test with mock Google data (no Supabase) |
| `tests/test_embeddings.py` | exists | 33 unit tests for the embeddings service — text_hash normalisation, cosine similarity edge cases, centroid text builder, mocked Cohere client, rank_by_similarity ordering. No external API calls. |
| `tests/test_competitor_pipeline.py` | exists | Unit tests for the orchestrator — hard pre-filters, sub-category filter, cache hit short-circuit, empty-candidate path, hard-filter wipe, happy path, below-threshold fallback, no-own-reviews path, plus 5 custom-prefs override cases (override floor, max-reviews cap, allowed-set widening, custom radius pass-through, min/max review filter). All API calls mocked. |
| `tests/test_competitor_preview.py` | exists | 14 unit tests for the preview service + endpoint — bucket logic, sub-category counts, top examples, 1h cache hit/miss, 404/422/manual placeholder paths. All API calls mocked. |
| `tests/test_competitor_prefs.py` | exists | 14 unit tests for `CompetitorPrefs`/`PreferencesRequest` models + PUT /preferences endpoint — radius enum, min/max range, custom-mode requires prefs, 404/403/400/204 paths, ownership check, sub-category whitelist. |
| `tests/test_pos_column_matcher.py` | exists | 50 unit tests for the three-layer column matcher (no external deps) — Layer 1 exact, Layer 2 fuzzy, Layer 3 value-sniffing, granularity, line-item aggregation, customer placeholder cleaning (incl. NaN regression), validation |
| `tests/test_pos_multi_window.py` | exists | 9 unit tests for `_window_trend()` — flat data, asymmetric 7-vs-28, growth/decline windows, empty-window None paths, zero-prior division guard. No external deps |
| `tests/test_review_credibility.py` | exists | 17 unit tests — credibility weight buckets, backward-compat (absent fields → 1.0), `review_score` integration showing power reviewers up-weight + fake accounts down-weight, `compute_velocity(weighted=True)` |
| `tests/test_history.py` | exists | History endpoint test |
| `tests/test_insights.py` | exists | Insights quality gate — 10 profiles × Claude call (requires ANTHROPIC_API_KEY) |
| `tests/test_e2e.py` | exists | End-to-end acceptance test — 5 businesses × 6 steps via TestClient |
| `conftest.py` | exists | Empty conftest marks project root for pytest |
| `pytest.ini` | exists | testpaths = tests, pythonpath = . |
| `data/business_biz_00{1-5}_pos.csv` | exists — generated | 90-day synthetic POS CSVs (360–450 rows each); re-generate with `python scripts/generate_synthetic_pos.py` |
| `migrations/2026-04-30-competitor-pipeline-v2.sql` | applied | Creates `review_embeddings` and `competitor_matches` |
| `migrations/2026-05-02-manual-competitors.sql` | applied | Adds `is_manual` column + index to `competitor_matches` |
| `migrations/2026-05-03-pos-product-name.sql` | applied | Adds nullable `product_name` column to `pos_records` for line-item granularity uploads |
| `migrations/add_customer_columns.sql` | applied | Adds nullable `unique_customers` + `returning_customers` to `pos_records` |
| `migrations/2026-05-04-competitor-prefs.sql` | applied | Adds `competitor_prefs_mode` + `competitor_prefs JSONB` + `competitor_prefs_updated_at` to `businesses`; creates `competitor_preview_cache(place_id, radius_m, payload, fetched_at)` |
| `vyaparai-frontend/app/onboard/preferences/page.tsx` | exists — complete | Onboarding Step 2 page — sub-categories / distance / review-count range / "Let Refloat decide" CTA |
| `vyaparai-frontend/components/ui/PrefsForm.tsx` | exists — complete | Shared component reused on the dashboard's Competitor settings drawer. Auto + custom paths; live preview via `getCompetitorPreview` |
| `render.yaml` | exists | Render web-service deployment config for the FastAPI backend |
| `vyaparai-frontend/` | exists | Next.js 14 (App Router) dashboard — Supabase Google Sign-In, Competitors tab with manual-add search + insight cards, POS tab with 7d/15d/30d window toggle |

## Database tables

- `businesses` — id, name, place_id (unique), category, owner_name, is_active, user_id (Supabase auth link, optional)
- `health_scores` — id, business_id, final_score, review_score, competitor_score, pos_score, google_rating, total_reviews, insights (JSONB), action, report_payload (JSONB — full ReportResponse used by the 24h cache), created_at
- `pos_records` — id, business_id, date, product_category, units_sold, revenue, transaction_count, avg_order_value, source, unique_customers (nullable), returning_customers (nullable), product_name (nullable) — customer columns from `migrations/add_customer_columns.sql`; `product_name` from `migrations/2026-05-03-pos-product-name.sql` for line-item Petpooja/DotPe uploads
- `actions_log` — id, business_id, kind ('weekly_action_done' | 'insight_actioned' | 'insight_saved'), target_text, note, created_at
- `external_reviews` — place_id, review_id (unique pair), source, rating, text, author_name, posted_at, owner_reply, raw (JSONB) — Apify cache. `raw` JSONB is read at load-time to surface reviewer-credibility fields (`reviewerNumberOfReviews`, `isLocalGuide`) without a schema migration
- `review_syncs` — place_id (unique), last_synced_at, total_reviews, source — Apify TTL marker (7d own / 30d competitor)
- `review_embeddings` — id, place_id, review_id (NULL for centroid rows), is_centroid, embedding (`vector(1024)`), text_hash (SHA-256 cache key), created_at — pgvector store for Cohere embeddings. ivfflat cosine index. UNIQUE (place_id, review_id, is_centroid)
- `competitor_matches` — id, business_id (FK businesses), competitor_pid, competitor_name, rating, review_count, similarity (cosine 0..1), sub_category, is_manual (BOOLEAN, default false — pinned via `/competitors/{id}`, not wiped by 7-day rebuild), matched_at — relationship cache. UNIQUE (business_id, competitor_pid)
- `businesses` (extended) — `competitor_prefs_mode TEXT` (enum 'auto'|'custom', default 'auto'), `competitor_prefs JSONB` (nullable; shape `{radius_m, min_reviews, max_reviews, subcategories[]}`), `competitor_prefs_updated_at TIMESTAMPTZ`. Mode='auto' preserves today's hardcoded-default pipeline behaviour
- `competitor_preview_cache` — place_id, radius_m, payload (JSONB), fetched_at — onboarding preview cache. PRIMARY KEY (place_id, radius_m). 1-hour TTL via `fetched_at` cutoff (no automatic eviction at MVP scale)

## Health score formula

```
final_score = int(review_score * 0.40 + competitor_score * 0.25 + pos_score * 0.35)
```

- `review_score`: rating quality (0–55) + volume velocity/log scale (0–25) + recent trend (0–20). All three components apply **reviewer-credibility weights** when reviewer-profile fields are present (Local Guide AND ≥200 reviews → 1.5x; either alone → 1.2x; default → 1.0x; lifetime count present AND <5 → 0.5x). Absent fields default to neutral 1.0 so legacy callers without credibility data score identically to before.
  - Quality formula: `((rating - 1) / 4.0) * 55` — normalised within the actual Google [1–5] scale so a 1-star rating scores near 0 quality points
  - Volume formula: when dated reviews are available (Apify path), `compute_velocity(weighted=True)` sums credibility weights over the last `REVIEW_VELOCITY_LOOKBACK_MONTHS` and divides by months — so a Local Guide's review counts as 1.5 of one fake account's 0.5. `_velocity_pts` then maps to 0–25 with full marks at `REVIEW_VELOCITY_FULL_MARKS_RATE = 8.0`. When dated reviews are absent, falls back to flat `log10(total_reviews) * 10`. `now` is injected for deterministic testing.
  - Trend formula: when classified reviews are available, weighted average sentiment (each `sentiment_score` × that review's credibility weight ÷ total weight). Else weighted star average over up to 50 reviews. `(weighted_avg / 5.0) * 20`.
- `competitor_score`: clamp(60 + (my_rating - mean_competitor_rating) * 30, 0, 100). No competitors = 65. Competitor list is the **similarity-filtered output** from `competitor_pipeline.run()`: Nearby Search (paginated prominence + distance-rank) → review-count floor → primary-type exclusion → name-keyword exclusion → Haiku sub-category tag → retail brand top-up → top-N rating cap → Apify reviews (parallel) → Cohere centroid → cosine similarity ≥ `SIMILARITY_THRESHOLD = 0.55`. Below-threshold fallback keeps the top 3 so the score never goes neutral by accident. Manual rows pinned via `/competitors/{id}` always lead the list. 7-day cache via `competitor_matches`.
- `pos_score`: **multi-window** revenue trend (0–40, category-aware bands) + slow inventory (0–25) + AOV health (0–15) + repeat-customer rate trend (0–20) = 100. Revenue trend scores each available window — 7-vs-28 (acute), 30-vs-30 (current), 90-vs-90 (chronic) — and takes the worst, with one carve-out: if the worst is the acute window AND both current and chronic sit at-or-above the 25-pt neutral midpoint, the acute reading is dropped as week-on-week noise (post-festival lulls, single closed weekends). Backward-compatible — short uploads with only the current window score identically to the previous single-window behaviour. No data = 50. Repeat-rate column missing = neutral 10/20 so absence does not penalise.

## Claude API usage

Sonnet `claude-sonnet-4-20250514` for `insights.py` and `competitor_analysis.py` (themes/opportunities). Haiku `claude-haiku-4-5-20251001` for `review_classifier.py` (sentiment + topic on up to 50 reviews per call) and `competitor_pipeline.py` (one batched sub-category tagger call per /generate-report cache miss).
Insights output: strict JSON `{"insights": ["..."], "action": "..."}` — count is dynamic 3–6 based on signal richness (`insight_count()`). Dominant complaint topic and review velocity are injected into the prompt.
Rule: always strip markdown backticks before `json.loads()`. Retry once on parse failure with a stricter "JSON only" suffix.
Quality bar: insights must name specific product categories and competitor names. Generic advice = failed quality gate.

## Design constraints — never violate these

- Never push directly to `main` branch — always use a feature branch
- Never commit `.env` — it contains real API keys
- Never use `print()` for errors — use Python `logging` module to `logs/module1.log`
- Never let one business failure crash the entire pipeline — always wrap in try/except and continue
- Never hardcode API keys — always read from `os.getenv()`
- POS score must default to 50 (neutral) if no pos_records exist for a business — never crash

## What is out of scope — do not build these

- WhatsApp delivery (V2)
- Monday scheduler (V2)
- Hindi language (V2)
- Zomato or Swiggy scraping
- ML forecasting models
- Multi-agent system

(Note: a Next.js frontend with Supabase Google Sign-In was added in `vyaparai-frontend/` — originally out of scope, now in. CLAUDE.md still focuses on the backend.)

## Environment variables needed

```
GOOGLE_PLACES_API_KEY
ANTHROPIC_API_KEY
SUPABASE_URL
SUPABASE_KEY
APIFY_TOKEN          # optional — without it, reviews fall back to Google's 5-review cap
COHERE_API_KEY       # required — competitor pipeline v2 uses Cohere multilingual embeddings
ALLOWED_ORIGINS      # optional, comma-separated; defaults to "*"
```

## How to run

```bash
source venv/bin/activate
uvicorn app.main:app --reload
# Swagger UI at localhost:8000/docs
```

## Quality gates before calling MVP done

- [ ] `test_google_places.py` passes for ≥ 4/5 businesses (blocked: enable legacy Places API in GCP console)
- [ ] 10 Claude outputs rated ≥ 3.5/5 average on specificity
- [ ] Pipeline runs 10 businesses without unhandled exceptions
- [x] Healthy synthetic profile scores 75+ (scored 89 in test_health_score.py — Session 3)
- [x] Struggling synthetic profile scores below 40 (scored 38 in test_health_score.py — Session 3)
- [ ] Slow category in synthetic data correctly flagged by name

## Update this file when

- A new file is added to the project
- The health score formula weights change
- A new table or column is added to the database
- An endpoint is added, renamed, or removed
- A quality gate is passed or modified

---

*Last updated: 04 May 2026 (Session 13 — Competitor preferences form: onboarding Step 2 + dashboard settings drawer + pipeline overrides + 1h preview cache).*

*Session 13 archive (04 May 2026 — Competitor preferences form):
**Database** — new migration `migrations/2026-05-04-competitor-prefs.sql` adds 3 columns to `businesses` (`competitor_prefs_mode TEXT default 'auto'` checked enum, `competitor_prefs JSONB nullable`, `competitor_prefs_updated_at TIMESTAMPTZ`) and creates `competitor_preview_cache(place_id, radius_m, payload JSONB, fetched_at)` with PK on (place_id, radius_m).
**Backend** — new `app/services/competitor_preview.py` runs only the cheap stages of the competitor pipeline (Nearby Search + Haiku tag, no Apify, no Cohere) and caches results 1h. New `app/api/preferences.py` exposes `PUT /preferences/{business_id}` with X-User-Id ownership check; on save it wipes non-manual `competitor_matches` rows + `health_scores` 24h cache so the next /generate-report rebuilds with new prefs. Manual pins survive. `app/api/competitors.py` adds `GET /competitors/preview/{business_id}?radius_m=` returning bucket counts (5+/20+/50+/100+/200+), per-sub-category counts, and top-5 examples. `app/services/competitor_pipeline.py` reads `competitor_prefs_mode + competitor_prefs` at the top of `run()` and overrides radius / min review floor / max review cap / allowed sub-categories — `mode=auto` (default for all existing rows) preserves byte-identical behaviour. New helpers: `_load_prefs()`, `_drop_above_max_reviews()`, override args on `_drop_dead_listings()` and `_drop_wrong_subcategory()`.
**Frontend** — onboarding flow now Account → POS → Business → Preferences → Dashboard (Steps component extended). New page `vyaparai-frontend/app/onboard/preferences/page.tsx` and shared component `vyaparai-frontend/components/ui/PrefsForm.tsx` reused on the dashboard's Competitor settings drawer. Hero "Let Refloat decide" CTA submits `mode:auto` and routes home; "Or customize" reveals sub-category multi-select pills (with live counts), 5 distance pills, and a two-thumb logarithmic review-range slider.
**Tests** — 14 in `test_competitor_prefs.py`, 14 in `test_competitor_preview.py`, 5 new override cases added to `test_competitor_pipeline.py` (15 total there). All 33 new tests pass; existing 10 pipeline tests also pass — backward compatibility confirmed.*

*Last updated: 04 May 2026 (Session 12 — Multi-window POS analysis + reviewer credibility weighting + frontend POS-window toggle).*

*Session 12 archive (04 May 2026 — Accuracy roadmap items #8 + #10):
**#8 Multi-window POS analysis** — `pos_pipeline.pos_signals()` now returns three trend windows: existing 30-vs-30 `revenue_trend_pct`, plus `revenue_trend_acute_pct` (last 7 days vs prior 28, daily-averaged) and `revenue_trend_chronic_pct` (last 90 vs prior 90). New `_window_trend()` helper uses strict `>` boundaries so a 30-day window covers exactly 30 days. Fetch widened to 180 days so the chronic prior is reachable. `health_score._multi_window_revenue_pts()` scores each available window and returns the worst, with acute-noise suppression: when the worst is acute AND both current+chronic are at-or-above the 25-pt neutral midpoint, acute is dropped (kills post-festival false alarms). Backward-compatible — single-window short uploads behave identically to before. `PosSignals` model + `report.py` extended with the two new fields. Tests: 9 unit tests in `test_pos_multi_window.py`, 6 in `test_health_score.py` Part E.
**#10 Reviewer credibility weighting** — new `app/services/review_credibility.py` with `credibility_weight(review)` returning 1.5/1.2/1.0/0.5 based on `reviewer_review_count` + `reviewer_is_local_guide`. Absent fields → neutral 1.0 so legacy tests still pass. `apify_reviews._normalize_review` and `_load_from_cache` surface the two reviewer fields (cache reads them out of the existing `raw` JSONB — no migration). `review_classifier.classify_reviews` carries credibility forward into each output entry to avoid index-alignment bugs. `health_score.review_score` applies weights to: velocity (`compute_velocity(weighted=True)`), Claude-sentiment trend, and the star-rating fallback trend. User-facing `reviews_per_month` stays a literal count via `weighted=False`. Tests: 17 unit tests in `test_review_credibility.py`.
**Frontend** — POS tab in `app/dashboard/page.tsx:1150` now has a 7d/15d/30d pill toggle that filters the weekly revenue chart and the "Last Xd Revenue" stat. Defaults to 30d. Limited to weekly granularity since the report payload only exposes weekly buckets — true daily resolution would need a `days` query parameter on `/generate-report` and a daily array in `chart_data`.*

*Session 11 archive (02 May 2026 — Mall-tenant fix + manual competitors + rich dashboard):
Three layered fixes for retail discovery (Phoenix Mall blind spot): (1) `places_nearby` now paginates 2 pages and adds a `rank_by=distance` call; (2) Text Search top-up via `RETAIL_BRAND_KEYWORDS` per Haiku sub-category tag; (3) `NAME_EXCLUSION_KEYWORDS` wired as a hard filter (drops Sunglass Hut/luggage/etc.). Sub-category vocab expanded with `eyewear`, `luggage`, `jewellery`. Apify competitor fetches parallelised (8 workers) and brand-top-up text-searches parallelised — cold-cache /generate-report dropped from minutes to ~35–45s. **Manual competitors:** new `is_manual` column on `competitor_matches` (migration `2026-05-02-manual-competitors.sql`), POST/DELETE `/competitors/{business_id}` router, split cache reads (auto with TTL vs manual evergreen). Frontend Competitors tab now has debounced manual-add search, "Added" badge with × remove, 4-tile hero strip, Sonnet themes/opportunities panel, volume leaders, sub-category mix bar. Threat criteria tightened — requires `rating > yours AND review_count >= 50 AND >= 10% your volume`. Cohere downgraded 6.1.0 → 5.13.12 to unblock Render build (pydantic-core conflict).*

*Session 10 archive (30 April 2026 — Competitor pipeline v2 (embeddings)):
Built the pipeline using Cohere `embed-multilingual-v3.0` (1024-dim) and Supabase `pgvector`. Two new tables (`review_embeddings`, `competitor_matches`) added via `migrations/2026-04-30-competitor-pipeline-v2.sql`. Cost per report: 1 Haiku tag call + 1 Sonnet insights call + 1 Cohere embed batch (~24k tokens ≈ $0.0024) on cache miss; cache hits cost only the Sonnet insights call.*

*Session 9 archive (28 April 2026):
1. Added `pos_column_matcher.py` (three-layer deterministic column matcher) and 50 unit tests.
2. Removed the old deterministic 5-signal competitor pipeline pending the v2 rebuild now landed in Session 10.*
