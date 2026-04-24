# VyaparAI Module 1

FastAPI backend that generates a 0–100 business health score for Indian MSMEs using Google Places reviews, nearby competitor data, and POS sales signals. Produces 3 specific AI-generated insights via Claude.

## Requirements

- Python 3.11+
- Google Places API key (legacy "Places API" enabled in GCP)
- Anthropic API key
- Supabase project (free tier works)

## Setup

```bash
git clone <repo-url> && cd vyaparai-m1
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Fill in GOOGLE_PLACES_API_KEY, ANTHROPIC_API_KEY, SUPABASE_URL, SUPABASE_KEY
```

## Database

Run the SQL from `docs/architecture.md` in the Supabase SQL Editor to create the three tables (`businesses`, `health_scores`, `pos_records`).

## Generate test data

```bash
python scripts/generate_synthetic_pos.py
# Creates data/business_biz_00{1-5}_pos.csv (5 business profiles, 90 days each)
```

## Run server

```bash
uvicorn app.main:app --reload
# Swagger UI: http://localhost:8000/docs
```

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/onboard` | Register a business (validates Google Place ID) |
| POST | `/upload-pos/{business_id}` | Ingest POS CSV file |
| POST | `/generate-report/{business_id}` | Full scoring + Claude insights pipeline |
| GET | `/history/{business_id}` | Last N health score records |

## Run tests

```bash
# Unit tests (no external dependencies):
python tests/test_health_score.py

# CSV scoring with mock Google data:
python tests/test_csv_scoring.py

# End-to-end acceptance test (requires Google Places API + real Place IDs in test_e2e.py):
python tests/test_e2e.py

# Supabase connectivity check:
python tests/test_connections.py
```
