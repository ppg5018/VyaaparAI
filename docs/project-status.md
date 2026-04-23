# project-status.md — VyaparAI Module 1

Read this at the start of every coding session to know exactly where you left off.

---

## Current status

**Phase:** MVP — Building
**Sprint:** Phase 3 — Google Places pipeline (built, blocked on GCP config)
**Last worked on:** 23 April 2026
**Blocking issue:** Legacy Places API not enabled in Google Cloud Console — must enable before test passes

---

## What is done

- [x] Phase 1 — Project setup (venv, requirements.txt, .gitignore, .env.example, repo pushed to GitHub)
- [ ] Phase 2 — Database schema (SQL not yet applied in Supabase)
- [x] Phase 3 — Google Places pipeline (`google_places.py` complete, `test_google_places.py` written)
- [ ] Phase 4 — POS synthetic data pipeline
- [ ] Phase 5 — Health score engine
- [ ] Phase 6 — Claude insights engine
- [ ] Phase 7 — FastAPI endpoints + end-to-end test

---

## What to do next (pick up here)

**Right now — unblock the test (5 minutes):**
1. Go to console.cloud.google.com → APIs & Services → Library
2. Search "Places API" → enable the one simply called **Places API** (NOT "Places API (New)")
3. Wait 30 seconds, then run: `venv\Scripts\python.exe -X utf8 test_google_places.py`
4. Verify ≥ 4/5 businesses fetch successfully

**After test passes:**
- Phase 2 — paste the SQL schema from `docs/architecture.md` into Supabase SQL Editor and run it. Confirm all 3 tables exist (`businesses`, `health_scores`, `pos_records`).

**After Phase 2:**
- Phase 5 — build `health_score.py` (pure Python, no external calls, depends on google_places.py output schema)

---

## Decisions made this session

- `google_places.py` uses `retry_over_query_limit=False` on the Google Maps client so OVER_QUERY_LIMIT raises ApiError immediately instead of being silently retried for 60 s and surfacing as a Timeout
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

---

*Update this file at the END of every coding session. Takes 2 minutes. Saves 20 minutes of re-orientation next time.*
