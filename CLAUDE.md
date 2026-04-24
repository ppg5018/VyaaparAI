# CLAUDE.md — VyaparAI Module 1

This file is Claude Code's memory for this project. Read it at the start of every session.

---

## Project goal

Build a FastAPI backend that generates a 0–100 business health score for Indian MSMEs using Google Places data (reviews + competitors) + synthetic POS sales data, then generates 3 specific insights using the Claude API. MVP only — no UI, no WhatsApp, no scheduler.

## Current phase

MVP — building and testing locally. No deployment yet.

## Architecture in one paragraph

`app/main.py` is the lean FastAPI factory that registers 4 APIRouters from `app/api/`. All env vars and constants live in `app/config.py`; all services import named constants from there. `app/database.py` holds the single Supabase client. `/onboard` registers a business. `/upload-pos` ingests a CSV into `pos_records`. `/generate-report` runs the full pipeline: `app/services/google_places.py` fetches data → `app/services/health_score.py` computes 3 sub-scores → `app/services/pos_pipeline.py` computes POS signals → `app/services/insights.py` calls Claude API → result saved to `health_scores` table in Supabase. `/history` returns past scores. All data lives in Supabase PostgreSQL. No caching layer. No auth.

## Tech stack

- Python 3.11 + FastAPI + Uvicorn
- Supabase (PostgreSQL) via supabase-py
- Google Maps Python client (Places API)
- Anthropic SDK — model: `claude-sonnet-4-20250514`
- Pandas + Faker for synthetic POS data

## Key files

| File | Status | Purpose |
|---|---|---|
| `app/main.py` | exists — complete | FastAPI factory — registers 4 APIRouters, calls setup_logging() |
| `app/config.py` | exists — complete | Single source of truth for all env vars and numeric constants |
| `app/database.py` | exists — complete | Singleton Supabase client |
| `app/logging_config.py` | exists — complete | setup_logging() — file + console handlers, suppresses noisy loggers |
| `app/models.py` | exists — complete | All Pydantic v2 models — OnboardRequest, ReportResponse, etc. |
| `app/api/onboard.py` | exists — complete | POST /onboard router |
| `app/api/pos.py` | exists — complete | POST /upload-pos/{business_id} router |
| `app/api/report.py` | exists — complete | POST /generate-report/{business_id} router |
| `app/api/history.py` | exists — complete | GET /history/{business_id} router |
| `app/services/google_places.py` | exists — complete | Google Places fetch + parse (4 functions) |
| `app/services/health_score.py` | exists — complete | Score engine — review + competitor + POS sub-scores |
| `app/services/insights.py` | exists — complete | Claude API call + JSON parse, retry logic |
| `app/services/pos_pipeline.py` | exists — complete | POS ingestion + signal computation |
| `scripts/generate_synthetic_pos.py` | exists — complete | Faker + Pandas CSV generator — 5 profiles, 90-day data, reproducible (SEED=42) |
| `scripts/seed_test_data.py` | exists — complete | CLI tool to upload a synthetic CSV to a given business_id |
| `tests/test_connections.py` | exists | Verifies Supabase connectivity |
| `tests/test_google_places.py` | exists | End-to-end test for google_places.py (5 Bangalore place IDs) |
| `tests/test_pos_pipeline.py` | exists | End-to-end test for pos_pipeline.py (requires Supabase) |
| `tests/test_health_score.py` | exists | Unit + integration tests for health_score.py (23 assertions, no external deps) |
| `tests/test_csv_scoring.py` | exists | CSV-based scoring test with mock Google data (no Supabase) |
| `tests/test_insights.py` | exists | Insights quality gate — 10 profiles × Claude call (requires ANTHROPIC_API_KEY) |
| `tests/test_e2e.py` | exists | End-to-end acceptance test — 5 businesses × 6 steps via TestClient |
| `conftest.py` | exists | Empty conftest marks project root for pytest |
| `pytest.ini` | exists | testpaths = tests, pythonpath = . |
| `data/business_biz_00{1-5}_pos.csv` | exists — generated | 90-day synthetic POS CSVs (360–450 rows each); re-generate with `python scripts/generate_synthetic_pos.py` |

## Database tables

- `businesses` — id, name, place_id (unique), category, owner_name, is_active
- `health_scores` — id, business_id, final_score, review_score, competitor_score, pos_score, google_rating, total_reviews, insights (JSONB), action, created_at
- `pos_records` — id, business_id, date, product_category, units_sold, revenue, transaction_count, avg_order_value, source

## Health score formula

```
final_score = int(review_score * 0.40 + competitor_score * 0.25 + pos_score * 0.35)
```

- `review_score`: rating quality (0–55) + volume log scale (0–25) + recent trend (0–20)
  - Quality formula: `((rating - 1) / 4.0) * 55` — normalised within the actual Google [1–5] scale so a 1-star rating scores near 0 quality points
- `competitor_score`: clamp(60 + (my_rating - mean_competitor_rating) * 30, 0, 100). No competitors = 65.
- `pos_score`: revenue trend (0–50) + slow inventory (0–30) + AOV health (0–20). No data = 50.

## Claude API usage

Model: `claude-sonnet-4-20250514`
Output: strict JSON `{"insights": ["...", "...", "..."], "action": "..."}`
Rule: always strip markdown backticks before `json.loads()`. Retry once on parse failure.
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
- Any frontend or UI
- Authentication
- Zomato or Swiggy scraping
- ML forecasting models
- Multi-agent system

## Environment variables needed

```
GOOGLE_PLACES_API_KEY
ANTHROPIC_API_KEY
SUPABASE_URL
SUPABASE_KEY
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

*Last updated: 24 April 2026 (Session 7 — modular refactor complete: app/, app/api/, app/services/, tests/, scripts/; uvicorn entry point is now `app.main:app`)*
