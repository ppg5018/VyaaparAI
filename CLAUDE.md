# CLAUDE.md — VyaparAI Module 1

This file is Claude Code's memory for this project. Read it at the start of every session.

---

## Project goal

Build a FastAPI backend that generates a 0–100 business health score for Indian MSMEs using Google Places data (reviews + competitors) + synthetic POS sales data, then generates 3 specific insights using the Claude API. MVP only — no UI, no WhatsApp, no scheduler.

## Current phase

MVP — building and testing locally. No deployment yet.

## Architecture in one paragraph

`main.py` is the FastAPI app with 4 endpoints. `/onboard` registers a business. `/upload-pos` ingests a CSV into `pos_records`. `/generate-report` runs the full pipeline: `google_places.py` fetches data → `health_score.py` computes 3 sub-scores → `pos_pipeline.py` computes POS signals → `insights.py` calls Claude API → result saved to `health_scores` table in Supabase. `/history` returns past scores. All data lives in Supabase PostgreSQL. No caching layer. No auth.

## Tech stack

- Python 3.11 + FastAPI + Uvicorn
- Supabase (PostgreSQL) via supabase-py
- Google Maps Python client (Places API)
- Anthropic SDK — model: `claude-sonnet-4-20250514`
- Pandas + Faker for synthetic POS data

## Key files

| File | Purpose |
|---|---|
| `main.py` | All FastAPI endpoints |
| `google_places.py` | Google Places fetch + parse |
| `health_score.py` | Score engine — review + competitor + POS sub-scores |
| `insights.py` | Claude API call + JSON parse |
| `pos_pipeline.py` | POS ingestion + signal computation |
| `generate_synthetic_pos.py` | Faker + Pandas CSV generator |

## Database tables

- `businesses` — id, name, place_id (unique), category, owner_name, is_active
- `health_scores` — id, business_id, final_score, review_score, competitor_score, pos_score, google_rating, total_reviews, insights (JSONB), action, created_at
- `pos_records` — id, business_id, date, product_category, units_sold, revenue, transaction_count, avg_order_value, source

## Health score formula

```
final_score = int(review_score * 0.40 + competitor_score * 0.25 + pos_score * 0.35)
```

- `review_score`: rating quality (0–55) + volume log scale (0–25) + recent trend (0–20)
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
uvicorn main:app --reload
# Swagger UI at localhost:8000/docs
```

## Quality gates before calling MVP done

- [ ] 10 Claude outputs rated ≥ 3.5/5 average on specificity
- [ ] Pipeline runs 10 businesses without unhandled exceptions
- [ ] Healthy synthetic profile scores 75+
- [ ] Struggling synthetic profile scores below 40
- [ ] Slow category in synthetic data correctly flagged by name

## Update this file when

- A new file is added to the project
- The health score formula weights change
- A new table or column is added to the database
- An endpoint is added, renamed, or removed
- A quality gate is passed or modified

---

*Last updated: April 2026*
