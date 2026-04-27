# CLAUDE.md — VyaparAI Module 1

This file is Claude Code's memory for this project. Read it at the start of every session.

---

## Project goal

Build a FastAPI backend that generates a 0–100 business health score for Indian MSMEs using Google Places data (reviews + competitors) + synthetic POS sales data, then generates 3 specific insights using the Claude API. MVP only — no UI, no WhatsApp, no scheduler.

## Current phase

MVP — building and testing locally. No deployment yet.

## Architecture in one paragraph

`app/main.py` is the lean FastAPI factory that registers 5 APIRouters from `app/api/` (onboard, pos, report, history, actions) plus a `/health` probe and CORS middleware. All env vars and constants live in `app/config.py`; all services import named constants from there. `app/database.py` holds the single Supabase client. `/onboard` registers a business (with optional Supabase `user_id` linkage). `/upload-pos` ingests a CSV into `pos_records`. `/generate-report` runs the full pipeline: `google_places.fetch_all_data()` → `apify_reviews.get_reviews()` augments with up to 50 scraped reviews → `competitor_matching.filter_competitors()` tiers the competitor list → `review_classifier.classify_reviews()` Haiku-tags sentiment → `health_score` computes 3 sub-scores → `pos_pipeline.pos_signals()` computes POS signals → `insights.generate_insights()` calls Claude Sonnet → `competitor_analysis.analyze_competitors()` produces themes/opportunities → result + full payload saved to `health_scores`. The endpoint cache returns the latest payload < 24h old unless `?force=true`. `/history` returns past scores. `/actions/*` logs user interactions on insights. Auxiliary tables `external_reviews` + `review_syncs` cache Apify reviews; `actions_log` stores user actions.

## Tech stack

- Python 3.11 + FastAPI + Uvicorn
- Supabase (PostgreSQL) via supabase-py
- Google Maps Python client (Places API)
- Anthropic SDK — Sonnet `claude-sonnet-4-20250514` for insights and competitor analysis; Haiku `claude-haiku-4-5-20251001` for review classification and sub-category tagging
- Apify (`compass~google-maps-reviews-scraper`) — bypasses Google's 5-review cap; cached in Supabase
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
| `app/services/competitor_matching.py` | exists — complete | Tiered competitor filter — review-count + price-tier + Haiku sub-category |
| `app/services/competitor_analysis.py` | exists — complete | Sonnet-generated themes/opportunities from higher-rated competitor reviews |
| `app/services/review_classifier.py` | exists — complete | Haiku batched sentiment + topic tagging for up to 50 reviews |
| `app/services/pos_pipeline.py` | exists — complete | POS ingestion + signal computation (revenue, slow-cat, AOV, repeat-rate) + chart_data() for dashboard |
| `scripts/generate_synthetic_pos.py` | exists — complete | Faker + Pandas CSV generator — 5 profiles, 90-day data, reproducible (SEED=42) |
| `scripts/seed_test_data.py` | exists — complete | CLI tool to upload a synthetic CSV to a given business_id |
| `tests/test_connections.py` | exists | Verifies Supabase connectivity |
| `tests/test_google_places.py` | exists | End-to-end test for google_places.py (5 Bangalore place IDs) |
| `tests/test_pos_pipeline.py` | exists | End-to-end test for pos_pipeline.py (requires Supabase) |
| `tests/test_health_score.py` | exists | Unit + integration tests for health_score.py (23 assertions, no external deps) |
| `tests/test_csv_scoring.py` | exists | CSV-based scoring test with mock Google data (no Supabase) |
| `tests/test_competitor_matching.py` | exists | 19 unit tests for the tiered competitor filter (no external API calls) |
| `tests/test_competitor_analysis.py` | exists | Tests for Sonnet competitor-themes generation |
| `tests/test_insights.py` | exists | Insights quality gate — 10 profiles × Claude call (requires ANTHROPIC_API_KEY) |
| `tests/test_e2e.py` | exists | End-to-end acceptance test — 5 businesses × 6 steps via TestClient |
| `conftest.py` | exists | Empty conftest marks project root for pytest |
| `pytest.ini` | exists | testpaths = tests, pythonpath = . |
| `data/business_biz_00{1-5}_pos.csv` | exists — generated | 90-day synthetic POS CSVs (360–450 rows each); re-generate with `python scripts/generate_synthetic_pos.py` |

## Database tables

- `businesses` — id, name, place_id (unique), category, owner_name, is_active, user_id (Supabase auth link, optional)
- `health_scores` — id, business_id, final_score, review_score, competitor_score, pos_score, google_rating, total_reviews, insights (JSONB), action, report_payload (JSONB — full ReportResponse used by the 24h cache), created_at
- `pos_records` — id, business_id, date, product_category, units_sold, revenue, transaction_count, avg_order_value, source
- `actions_log` — id, business_id, kind ('weekly_action_done' | 'insight_actioned' | 'insight_saved'), target_text, note, created_at
- `external_reviews` — place_id, review_id (unique pair), source, rating, text, author_name, posted_at, owner_reply, raw (JSONB) — Apify cache
- `review_syncs` — place_id (unique), last_synced_at, total_reviews, source — Apify TTL marker (7d own / 30d competitor)

## Health score formula

```
final_score = int(review_score * 0.40 + competitor_score * 0.25 + pos_score * 0.35)
```

- `review_score`: rating quality (0–55) + volume log scale (0–25) + recent trend (0–20)
  - Quality formula: `((rating - 1) / 4.0) * 55` — normalised within the actual Google [1–5] scale so a 1-star rating scores near 0 quality points
  - Volume formula: when dated reviews are available (Apify path), each review is weighted by `1 / (1 + months_old / REVIEW_HALFLIFE_MONTHS)` (half-life = 6 months) and `volume_pts = min(25, log10(weighted_count) * 10)`. When dated reviews are absent (Google-Places-only path), falls back to flat `log10(total_reviews) * 10`. `now` is injected for deterministic testing.
- `competitor_score`: clamp(60 + (my_rating - mean_competitor_rating) * 30, 0, 100). No competitors = 65. Competitor list is pre-filtered by `competitor_matching.filter_competitors()` (review-count ≥ 20, price tier ±1, Haiku-tagged sub-category) with a graceful cascade fallback when the strict pipeline strips below MIN_COMPETITORS_AFTER_FILTER.
- `pos_score`: revenue trend (0–40, category-aware bands) + slow inventory (0–25) + AOV health (0–15) + repeat-customer rate trend (0–20) = 100. No data = 50. Repeat-rate column missing = neutral 10/20 so absence does not penalise.

## Claude API usage

Sonnet `claude-sonnet-4-20250514` for `insights.py` and `competitor_analysis.py`. Haiku `claude-haiku-4-5-20251001` for `review_classifier.py` (sentiment + topic on up to 50 reviews per call) and `competitor_matching.py` (one batched sub-category tagger call per /generate-report).
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

*Last updated: 28 April 2026 (Session 8 — tiered competitor matching + full doc refresh: actions router, search-places, by-user lookup, /health, Apify cache, dashboard chart_data, dynamic insight count, Haiku usage)*
