# architecture.md — VyaparAI Module 1

Update this file after every major structural change to the codebase.

---

## System overview

```
Developer (CLI / Swagger UI)
        │
        ▼
   FastAPI (app/main.py)
   localhost:8000
        │
        ├── POST /onboard ──────────────────────► Supabase: businesses table
        │   (app/api/onboard.py)
        │
        ├── POST /upload-pos/{id} ──────────────► Supabase: pos_records table
        │   (app/api/pos.py)                        (via app/services/pos_pipeline.py)
        │
        ├── POST /generate-report/{id}
        │   (app/api/report.py)
        │         │
        │         ├── app/services/google_places.py ► Google Places API
        │         │   (fetch details + competitors)      (external)
        │         │
        │         ├── app/services/health_score.py ─► Pure Python computation
        │         │   review_score()                    (no external calls)
        │         │   competitor_score()
        │         │   pos_score()  ◄── pos_pipeline.py ◄── Supabase: pos_records
        │         │   calculate_health_score()
        │         │
        │         ├── app/services/insights.py ──────► Anthropic Claude API
        │         │   generate_insights()                (external)
        │         │   (injects all signals into prompt)
        │         │
        │         └──────────────────────────────────► Supabase: health_scores table
        │                                               (save final report)
        │
        └── GET /history/{id} ──────────────────────► Supabase: health_scores table
            (app/api/history.py)                        (read last 12 scores)
```

---

## Component responsibilities

### app/main.py — FastAPI factory

- Creates the FastAPI app via `create_app()`, registers 4 APIRouters
- Calls `setup_logging()` once at startup
- Does NOT contain business logic — delegates entirely to `app/api/` and `app/services/`

### app/config.py — Centralised configuration

- Single source of truth for all `os.getenv()` calls and numeric constants
- All services import named constants from here (no raw `os.getenv()` anywhere else)
- Constants: all API keys, CLAUDE_MODEL, MAX_TOKENS, score weights, thresholds, BATCH_SIZE, etc.

### app/database.py — Supabase singleton

- Creates and exports a single `supabase` client instance
- All services do `from app.database import supabase`

### app/logging_config.py — Logging setup

- `setup_logging()` creates `logs/module1.log` and sets log levels
- Suppresses noisy loggers: httpx, anthropic, supabase, httpcore

### app/models.py — Pydantic v2 models

- `OnboardRequest` (with `@field_validator` for category validation)
- `OnboardResponse`, `UploadPOSResponse`, `SubScores`, `ReportResponse`, `HistoryScore`, `HistoryResponse`

### app/api/ — Endpoint routers

- `onboard.py` — `POST /onboard` — register a business, validate place_id
- `pos.py` — `POST /upload-pos/{business_id}` — ingest POS CSV via UploadFile
- `report.py` — `POST /generate-report/{business_id}` — full scoring + insights pipeline
- `history.py` — `GET /history/{business_id}` — last N health score records

### app/services/google_places.py — Google data pipeline

**Functions:**
- `get_business_details(place_id: str) -> dict` — calls `gmaps.place()`, returns name, rating, review count, GPS, last 5 reviews
- `get_nearby_competitors(lat, lng, category) -> list` — calls `gmaps.places_nearby()`, returns top 10 within 800m
- `parse_reviews(details: dict) -> list` — extracts rating, text (200 char), relative_time from raw response
- `fetch_all_data(place_id, category) -> dict` — single call combining all above

**External dependency:** Google Maps Python client → Google Places API
**Error handling:** try/except on all gmaps calls, 1 retry on timeout, ValueError on bad place_id

### app/services/health_score.py — Scoring engine

**Functions:**
- `review_score(rating, total_reviews, recent_reviews, all_reviews_with_dates=None, now=None) -> int` — 0–100. When `all_reviews_with_dates` is supplied, the volume sub-score uses a time-decayed weighted count (half-life = `REVIEW_HALFLIFE_MONTHS`); otherwise falls back to flat `log10(total_reviews)`. `now` is injected for determinism.
- `_weighted_review_count(reviews_with_dates, now, halflife_months) -> float` — internal helper; `weight = 1 / (1 + months_old / halflife_months)`, future-dated reviews clamped to age 0, unparseable dates skipped silently.
- `competitor_score(my_rating, competitors) -> int` — 0–100, 65 if no competitors
- `pos_score(signals: dict) -> int` — 0–100, 50 if no POS data
- `calculate_health_score(review_s, competitor_s, pos_s) -> int` — weighted combination

**External dependencies:** None (pure computation)
**Weights:** review × 0.40, competitor × 0.25, pos × 0.35

### app/services/insights.py — Claude API integration

**Functions:**
- `build_prompt(business_data, scores, pos_signals) -> str` — assembles the full prompt
- `generate_insights(prompt) -> dict` — calls Claude API, parses JSON, retries once on failure
- `strip_markdown(text) -> str` — removes backtick wrappers before json.loads()

**External dependency:** Anthropic SDK → Claude API (`claude-sonnet-4-20250514`)
**Output schema:** `{"insights": [str, str, str], "action": str}`
**Retry logic:** if json.loads() fails, retry once with stricter ending instruction

### app/services/pos_pipeline.py — POS data layer

**Functions:**
- `ingest_pos_csv(filepath, business_id) -> int` — validates, converts dates, bulk inserts, returns row count
- `pos_signals(business_id, days=30) -> dict` — queries pos_records, returns revenue_trend_pct, slow_categories, top_product, aov_direction

**External dependency:** Supabase client (reads/writes pos_records)
**Fallback:** if no records found for business_id, returns all None values → triggers pos_score neutral (50)

### scripts/generate_synthetic_pos.py — Test data factory

**Functions:**
- `generate_business_pos(business_id, days=90, categories=None) -> pd.DataFrame` — creates realistic daily sales with patterns
- `save_to_csv(df, business_id)` — saves to `data/business_{id}_pos.csv`

**External dependency:** Faker, Pandas (no network calls)
**Patterns injected:** weekday dips, weekend spikes, one slow category, declining revenue curve

---

## Data flow — generate-report endpoint (detailed)

```
1. Receive POST /generate-report/{business_id}
2. Look up business in Supabase → get place_id, category
3. Call google_places.fetch_all_data(place_id, category)
   └── Returns: {rating, total_reviews, reviews[], lat, lng, competitors[]}
4. Call health_score.review_score(rating, total_reviews, reviews)
   └── Returns: int 0-100
5. Call health_score.competitor_score(rating, competitors)
   └── Returns: int 0-100
6. Call pos_pipeline.pos_signals(business_id, days=30)
   └── Returns: {revenue_trend_pct, slow_categories[], top_product, aov_direction}
7. Call health_score.pos_score(signals)
   └── Returns: int 0-100 (or 50 if signals are None)
8. Call health_score.calculate_health_score(r_score, c_score, p_score)
   └── Returns: int 0-100 (final)
9. Call insights.build_prompt(business_data, scores, signals)
   └── Returns: str prompt
10. Call insights.generate_insights(prompt)
    └── Returns: {"insights": [...], "action": "..."}
11. Insert into health_scores table in Supabase
12. Return full JSON response
```

---

## Database schema

```sql
CREATE TABLE businesses (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  place_id TEXT UNIQUE NOT NULL,
  category TEXT,
  owner_name TEXT,
  is_active BOOLEAN DEFAULT true,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE health_scores (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  business_id UUID REFERENCES businesses(id) ON DELETE CASCADE,
  final_score INTEGER,
  review_score INTEGER,
  competitor_score INTEGER,
  pos_score INTEGER,
  google_rating NUMERIC(2,1),
  total_reviews INTEGER,
  insights JSONB,
  action TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE pos_records (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  business_id UUID REFERENCES businesses(id) ON DELETE CASCADE,
  date DATE NOT NULL,
  product_category TEXT,
  units_sold INTEGER,
  revenue NUMERIC(10,2),
  transaction_count INTEGER,
  avg_order_value NUMERIC(8,2),
  source TEXT DEFAULT 'synthetic'
);

CREATE INDEX idx_pos_biz ON pos_records(business_id, date DESC);
CREATE INDEX idx_scores_biz ON health_scores(business_id, created_at DESC);
```

---

## Key decisions log

| Decision | Why | Alternative rejected |
|---|---|---|
| FastAPI over Django | Async support, auto Swagger docs, minimal boilerplate | Django: too heavy for an API-only backend |
| Supabase over raw PostgreSQL | Free tier, built-in REST, no infra management | Raw PG: requires hosting setup |
| POS score weight at 35% | Meaningful signal even with partial data | Lower weight: would make score feel unresponsive to sales trends |
| pos_score defaults to 50, not 0 | Missing data ≠ unhealthy | Default to 0: punishes businesses without digital POS unfairly |
| Synthetic POS not ML model | 90 days of data minimum needed for ML. Linear trends sufficient now. | ML model: data doesn't exist yet |
| Single retry on Claude failures | Avoids runaway API costs. Log failures for prompt tuning. | No retry: poor UX. 3 retries: too slow + expensive. |

---

*architecture.md · VyaparAI Module 1 · Last updated: 24 April 2026 (Session 7 — modular refactor: app/, services/, tests/, scripts/)*
*Update this file whenever: a new file is added, a function signature changes, a table is modified, or a key decision is made.*
