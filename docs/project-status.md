# project-status.md — VyaparAI Module 1

Read this at the start of every coding session to know exactly where you left off.

---

## Current status

**Phase:** MVP — Built; blocked on GCP API enablement before e2e test can pass
**Sprint:** Phase 7 — FastAPI endpoints complete; e2e test written; awaiting GCP unblock
**Last worked on:** 24 April 2026
**Blocking issue:** "Places API" (legacy) not enabled in Google Cloud Console. All Google Places API calls (place details, places nearby, find place) return REQUEST_DENIED. Fix: GCP console → APIs & Services → Library → enable "Places API" (NOT "Places API (New)").

---

## What is done

- [x] Phase 1 — Project setup (venv, requirements.txt, .gitignore, .env.example, repo pushed to GitHub)
- [ ] Phase 2 — Database schema (SQL not yet applied in Supabase)
- [x] Phase 3 — Google Places pipeline (`google_places.py` complete, `test_google_places.py` written; blocked on GCP config)
- [x] Phase 4 — Synthetic POS data (`generate_synthetic_pos.py` complete; 5 CSVs in `data/`, all validation ✓)
- [x] Phase 5 — Health score engine (`health_score.py` complete, 23/23 assertions pass)
- [x] Phase 6 — Claude insights engine (`insights.py` complete with retry logic and quality gate)
- [x] Phase 7 — FastAPI endpoints (`main.py` with 4 endpoints, error handling, Pydantic v2 validation) + `test_e2e.py` written

---

## What to do next (pick up here)

**One blocker stands between now and MVP done:**

Enable "Places API" (legacy) in GCP (5 minutes):
1. Go to console.cloud.google.com → APIs & Services → Library
2. Search "Places API" → enable the one simply called **Places API** (NOT "Places API (New)")
3. Wait 30 seconds, then run: `venv\Scripts\python.exe -X utf8 test_google_places.py`
4. Verify ≥ 4/5 businesses fetch successfully

**Then fill in real Pune Place IDs in `test_e2e.py`:**
- Open Google Maps → search each business → Share → copy ChIJ... Place ID
- Replace the 5 placeholder IDs in `TEST_BUSINESSES` in `test_e2e.py`

**Then run the e2e test:**
```bash
uvicorn main:app --reload   # terminal 1
python test_e2e.py          # terminal 2
```
When 5/5 pass → MVP complete → tag v0.1.0-mvp.

---

## Decisions made this session (Session 2 — 23 Apr 2026)

- `generate_synthetic_pos.py` uses `SEED=42` + `random.seed(SEED)` + `Faker.seed(SEED)` — output is byte-identical across runs
- Slow category drop is **gradual** over `_SLOW_RAMP_DAYS=5` days (not a hard cliff) — realistic decline curve
- biz_004 has an optional `seasonal_spike` dict (`last_n_days`, `pct`) applied as a gradual revenue ramp
- Validation uses **revenue** (not units_sold) to avoid `max(1,...)` clamping on high-price categories (e.g. Footwear ₹700/unit)
- Validation uses the fully-slow window (`start_days_ago - ramp_days`) so the ramp period doesn't inflate the ratio
- biz_005 Cakes: `slow_category_start_days_ago=15` (ramp starts 15d ago, fully slow for 10d — matches "dropped 10 days ago" in spirit)
- All 4 slow-category revenue ratios pass ±0.10 tolerance: biz_002 Mutton 0.22, biz_003 Snacks 0.30, biz_004 Footwear 0.115, biz_005 Cakes 0.17

## Decisions made last session (Session 1 — google_places.py)

- `google_places.py` uses `retry_over_query_limit=False` — OVER_QUERY_LIMIT raises ApiError immediately
- `get_nearby_competitors()` accepts optional `exclude_place_id` so the business itself is filtered from its own competitor list
- `reviews_sort="newest"` used in `gmaps.place()` to ensure the 5 returned reviews are the most recent
- Test place IDs are 5 Bangalore restaurants/cafes (Toit, Truffles, Brahmin's Coffee Bar, Vidyarthi Bhavan, Starbucks as baseline)

---

## Blockers

- **Legacy Places API not enabled** — all 5 test calls return `REQUEST_DENIED`. Fix: enable "Places API" (legacy) in GCP console for the project that owns `GOOGLE_PLACES_API_KEY`.

---

## Notes for next session

- `google_places.py` is complete and syntax-verified. The only reason it returned 0/5 is the GCP API enablement issue — not a code bug.
- Once the Places API is enabled, re-run the test before building `health_score.py`.
- `fetch_all_data()` returns the exact dict schema that `health_score.py` will consume — do not change the output keys.
- `data/business_biz_00X_pos.csv` files are the inputs for `pos_pipeline.py` — do not rename/move them.
- CSV format: `date, product_category, units_sold, revenue, transaction_count, avg_order_value` (6 columns, 360–450 rows per file).
- Re-running `generate_synthetic_pos.py` produces byte-identical CSVs (SEED=42).
- Phase 5 (`health_score.py`) can be built without the GCP blocker being resolved — it only needs the CSV data and the `fetch_all_data()` output schema (which is already documented).

---

*Last updated: 23 April 2026 (Session 2 — generate_synthetic_pos.py complete)*

*Update this file at the END of every coding session. Takes 2 minutes. Saves 20 minutes of re-orientation next time.*
