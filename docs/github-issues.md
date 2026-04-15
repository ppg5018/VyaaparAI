# GitHub Issues — VyaparAI Module 1 MVP

Paste each block below into GitHub Issues (New Issue). Label each with the labels shown.
Create these labels first: `setup`, `database`, `google-api`, `pos`, `scoring`, `claude-api`, `fastapi`, `testing`

---

## Issue #1

**Title:** Project setup — venv, dependencies, API key applications

**Labels:** `setup`

**Body:**
Set up the Python project foundation.

Tasks:
- Create project folder `vyaparai-m1`
- Create Python 3.11 virtual environment
- Install: `fastapi uvicorn anthropic supabase googlemaps httpx python-dotenv pandas faker`
- Save `requirements.txt`
- Apply for Google Places API key (console.cloud.google.com)
- Apply for Anthropic API key (console.anthropic.com)
- Set up Supabase project, copy URL + key
- Create `.env` from `.env.example`
- Add `.env` to `.gitignore`

**Done when:** `pip install -r requirements.txt` runs clean. All 4 keys are in `.env`.

---

## Issue #2

**Title:** Database — create all 3 tables + indexes in Supabase

**Labels:** `database`

**Body:**
Run the full SQL schema in Supabase SQL Editor.

Tables to create: `businesses`, `health_scores`, `pos_records`
Indexes to create: `idx_pos_biz`, `idx_scores_biz`

Full SQL is in `spec-doc.md` → Part 2 → Database section.

**Done when:** All 3 tables visible in Supabase Table Editor. Python one-liner `supabase.table("businesses").select("*").execute()` returns empty list with no error.

---

## Issue #3

**Title:** google_places.py — build `get_business_details()`

**Labels:** `google-api`

**Body:**
Build function that takes a Google Place ID and returns structured business data.

Fields to return: name, rating, total_reviews, lat, lng, last 5 reviews (rating + text + relative_time)
Use: `gmaps.place(place_id, fields=[...])`

**Done when:** Called with 3 real Place IDs, returns correct data matching Google Maps.

---

## Issue #4

**Title:** google_places.py — build `get_nearby_competitors()`

**Labels:** `google-api`

**Body:**
Build function that returns top 10 competitors within 800m, sorted by rating.

Use: `gmaps.places_nearby(location=(lat, lng), radius=800, type=place_type)`
Category mapping: restaurant→restaurant, retail→store, manufacturing→industrial

Handle: zero results nearby (return empty list, don't crash)

**Done when:** Returns accurate competitor list for 3 real test businesses. Verified against Google Maps.

---

## Issue #5

**Title:** google_places.py — add error handling + retry logic

**Labels:** `google-api`, `testing`

**Body:**
Wrap all Google API calls in try/except.

Rules:
- Timeout → retry once after 2 seconds
- Invalid place_id → raise `ValueError` with descriptive message
- API quota exceeded → log warning, return empty dict, do not crash
- All errors logged to `logs/module1.log`

**Done when:** Tested with invalid place_id (returns 400), tested with network disconnect (retries once).

---

## Issue #6

**Title:** generate_synthetic_pos.py — build synthetic CSV generator

**Labels:** `pos`

**Body:**
Generate 90 days of realistic daily POS data per business using Faker + Pandas.

Columns: `date`, `product_category`, `units_sold`, `revenue`, `transaction_count`, `avg_order_value`
Categories: 4–5 per business (e.g. dal makhani, paneer dishes, beverages, snacks, thali)

Patterns to inject:
- Weekday dips (Monday–Tuesday ~20% below avg)
- Weekend spikes (Friday–Sunday ~30% above avg)
- One deliberately slow category (units < 30% of avg for last 30 days)
- Slight overall revenue decline (~10%) over 90 days

Generate CSVs for 5 test businesses → save to `data/business_{id}_pos.csv`

**Done when:** 5 CSVs generated. Each has 90 rows. Slow category is clearly identifiable.

---

## Issue #7

**Title:** pos_pipeline.py — build `ingest_pos_csv()`

**Labels:** `pos`

**Body:**
Function to validate, parse, and bulk-insert a POS CSV into `pos_records` table.

Steps:
1. Read CSV with pandas
2. Validate required columns exist (raise 422 with missing column list if not)
3. Convert date column to ISO format
4. Bulk insert into Supabase `pos_records` with `business_id` and `source='synthetic'`
5. Return count of rows inserted

Design for future Petpooja CSV format: add a column mapper dict at the top of the function so renaming columns for real data requires one line change.

**Done when:** Ingests all 5 synthetic CSVs without error. Row counts in Supabase match CSV row counts.

---

## Issue #8

**Title:** pos_pipeline.py — build `pos_signals()`

**Labels:** `pos`, `testing`

**Body:**
Compute business signals from last N days of `pos_records`.

Return dict:
```python
{
    "revenue_trend_pct": float,   # % change vs prior 30 days
    "slow_categories": [str],      # categories with units < 30% avg for 14 days
    "top_product": str,            # highest revenue category
    "aov_direction": str           # "rising" | "falling" | "stable"
}
```

If no records for business_id: return all None values.

**Done when:** Run on deliberately slow test dataset → `slow_categories` contains the slow category name. Run on declining revenue dataset → `revenue_trend_pct` is negative.

---

## Issue #9

**Title:** health_score.py — build all 3 sub-score functions

**Labels:** `scoring`

**Body:**
Build three scoring functions:

`review_score(rating, total_reviews, recent_reviews) -> int`
- Rating quality: `(rating / 5.0) * 55`
- Volume: `min(25, math.log10(max(total_reviews, 1)) * 10)`
- Recent trend: `(avg_of_recent_ratings / 5.0) * 20`

`competitor_score(my_rating, competitors: list) -> int`
- Formula: `clamp(60 + (my_rating - mean_competitor_ratings) * 30, 0, 100)`
- No competitors: return 65

`pos_score(signals: dict) -> int`
- Revenue trend → 0–50 pts (positive = 50, -30%+ = 0, linear)
- Slow categories → 0–30 pts (0 slow = 30, 1 = 20, 2 = 10, 3+ = 0)
- AOV direction → rising = 20, stable = 12, falling = 5
- All signals None: return 50

**Done when:** Unit tested with known inputs. Output matches expected scores ±2 pts.

---

## Issue #10

**Title:** health_score.py — build `calculate_health_score()` + validation test

**Labels:** `scoring`, `testing`

**Body:**
Combine 3 sub-scores into final score:
```python
final = int(review_score * 0.40 + competitor_score * 0.25 + pos_score * 0.35)
```

Validation test (write as a script, not a unit test framework):
- Healthy profile: 4.5 stars, 300 reviews, recent avg 4.4, beats all competitors by 0.4, revenue +15%, no slow categories, AOV rising → must score 75+
- Struggling profile: 3.1 stars, 22 reviews, recent avg 2.8, trails competitors by 0.6, revenue -18%, 2 slow categories, AOV falling → must score below 40

**Done when:** Both profiles pass. Log the exact sub-scores for future reference.

---

## Issue #11

**Title:** insights.py — build Claude prompt + `generate_insights()`

**Labels:** `claude-api`

**Body:**
Build the prompt that injects all signals and calls Claude API.

Prompt must include: business name, final score, rating, review count, last 3 review snippets, top 3 competitor names + ratings, revenue_trend_pct, slow_categories list, aov_direction.

System instruction: advisor for Indian MSMEs, specific advice, always name products and competitors, actions under ₹2,000 and 3 hours.

Output enforcement: `"Return ONLY valid JSON with no markdown: {"insights": ["...", "...", "..."], "action": "..."}`

Retry logic: strip backticks → `json.loads()` → if fails, retry once with stricter prompt → if fails again, log and raise.

**Done when:** Called for 5 different business profiles. Returns valid JSON every time. Insights name at least one specific product and one competitor in each output.

---

## Issue #12

**Title:** insights.py — quality gate: 10 outputs rated ≥ 3.5/5

**Labels:** `claude-api`, `testing`

**Body:**
Run `generate_insights()` for 10 varied synthetic business profiles. Rate each output 1–5 on:
- Does it name a specific product category? (not "some products")
- Does it name a specific competitor? (not "nearby competitors")
- Is the action achievable in under ₹2,000 and 3 hours?
- Is the advice different from the previous week's advice?

Calculate average. If below 3.5: iterate the prompt and re-test. Document changes in `changelog.md`.

**Done when:** 10 outputs rated, average ≥ 3.5/5. Results logged.

---

## Issue #13

**Title:** main.py — build all 4 FastAPI endpoints

**Labels:** `fastapi`

**Body:**
Build the 4 endpoints:

`POST /onboard` — body: `{name, place_id, category, owner_name}` → validate place_id via Google → insert businesses → return `{business_id}`

`POST /upload-pos/{business_id}` — file: CSV upload → call `ingest_pos_csv()` → return `{rows_inserted}`

`POST /generate-report/{business_id}` — full pipeline → save to health_scores → return full report JSON

`GET /history/{business_id}` — return last 12 health_scores ordered by created_at DESC

All endpoints: proper HTTP status codes (400 for bad input, 404 for unknown business_id, 500 for pipeline failures). All errors logged to `logs/module1.log`.

**Done when:** All 4 endpoints testable via Swagger at `localhost:8000/docs`. Each returns correct response for valid input and correct error for invalid input.

---

## Issue #14

**Title:** End-to-end test — 5 synthetic businesses, full pipeline

**Labels:** `testing`

**Body:**
Final MVP acceptance test.

Steps:
1. Onboard 5 synthetic businesses via `POST /onboard` (use 5 real Place IDs)
2. Upload 90-day synthetic CSV for each via `POST /upload-pos/{id}`
3. Call `POST /generate-report/{id}` for each
4. For each report, verify:
   - Final score is between 0–100
   - Sub-scores are plausible for the business profile
   - Insights JSON has exactly 3 strings and 1 action string
   - At least one insight names a specific product category
   - All data correctly saved in Supabase health_scores table
5. Call `GET /history/{id}` — confirm score appears

**Done when:** All 5 businesses have a generated report. All 4 checks pass for each. No unhandled exceptions in logs.

---

*Create all 14 issues in GitHub before starting to code. Use issue numbers in commit messages: `git commit -m "feat: add get_business_details() — closes #3"`*
