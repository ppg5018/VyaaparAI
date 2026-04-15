# E2E Test

Run a full end-to-end smoke test for one synthetic business through every endpoint.
Use this as a quick sanity check before running `/quality-gate`.

## Goal

Verify that all four API endpoints work together without errors and that the
response shapes are correct. One business, one pass through the entire pipeline.

## Steps

### 0 — Preflight

- Confirm `.env` is present and all four env vars are set:
  `GOOGLE_PLACES_API_KEY`, `ANTHROPIC_API_KEY`, `SUPABASE_URL`, `SUPABASE_KEY`
- Start the FastAPI server if not already running:
  ```
  uvicorn main:app --reload &
  ```
  Wait for `Application startup complete` in stdout before continuing.
- Tail `logs/module1.log` in the background so errors surface immediately.

### 1 — Onboard a synthetic business (`POST /onboard`)

Call `/onboard` with a realistic Indian MSME:
```json
{
  "name": "E2E Test Kirana Store",
  "place_id": "ChIJe2e-test-placeholder",
  "category": "grocery",
  "owner_name": "Test Owner"
}
```
**Assert:**
- HTTP 200 or 201
- Response contains a `business_id` (UUID)
- No ERROR lines appear in `logs/module1.log`

Save `business_id` for subsequent steps.

> If `/onboard` returns a 409 (duplicate), extract `business_id` from the error
> body or query Supabase and reuse the existing record — do not fail the test.

### 2 — Upload synthetic POS data (`POST /upload-pos`)

Generate a small synthetic CSV using `generate_synthetic_pos.py` (or inline via
`pandas` + `Faker`) with:
- 30 rows, 3 months of daily sales
- Categories: `snacks`, `beverages`, `stationery` (stationery = near-zero units)
- Upload via `/upload-pos` with the `business_id` from step 1

**Assert:**
- HTTP 200
- Response confirms rows ingested (count > 0)
- No ERROR lines in log

### 3 — Generate health report (`POST /generate-report`)

Call `/generate-report` with the `business_id`.

**Assert response shape:**
- `final_score` is an integer 0–100
- `review_score`, `competitor_score`, `pos_score` are all present
- `insights` is an array of exactly 3 non-empty strings
- `action` is a non-empty string

**Assert content:**
- `pos_score` is not exactly 50 (confirms POS data was used, not default)
- At least one insight contains a product category name (e.g. "stationery",
  "snacks", "beverages") — verifies Claude used real POS data
- No ERROR or EXCEPTION lines in `logs/module1.log` during this call

### 4 — Retrieve history (`GET /history/{business_id}`)

Call `/history/{business_id}`.

**Assert:**
- HTTP 200
- Response is a list with at least one entry
- The most recent entry's `final_score` matches the score from step 3

### 5 — Log check

After all calls, scan `logs/module1.log` for any ERROR or EXCEPTION lines
introduced during this test run (use the timestamp of step 0 as the boundary).
Report any found — these are failures even if HTTP calls returned 200.

## Output format

```
E2E Test — VyaaparAI Module 1
==============================
business_id : <uuid>
final_score : <int>

Step | Endpoint              | Result  | Detail
-----|-----------------------|---------|-------
  0  | Preflight             | PASS/FAIL | <env/server note>
  1  | POST /onboard         | PASS/FAIL | <http status>
  2  | POST /upload-pos      | PASS/FAIL | <rows ingested>
  3  | POST /generate-report | PASS/FAIL | <score + insight snippet>
  4  | GET  /history         | PASS/FAIL | <entry count>
  5  | Log check             | PASS/FAIL | <error count or "clean">

Overall: PASS / FAIL
```

If any step fails, print the raw response body and the relevant log lines.
Do **not** delete the test business from Supabase — it can be reused on the next run.
