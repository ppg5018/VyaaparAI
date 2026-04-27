# changelog.md — VyaparAI Module 1

All notable changes to this project. Most recent entry at the top.
Format: `## [date] — [what changed]`

---

## [27 April 2026] — Improvement #1 — Time-decayed review volume

- `review_score()` now accepts optional `all_reviews_with_dates` and `now` parameters. When dated reviews are provided, the volume sub-score weights each review by `1 / (1 + months_old / 6)` so recent reviews count more than stale ones. Old call sites are unaffected (strict additive change).
- Added `REVIEW_HALFLIFE_MONTHS = 6` to `app/config.py` and `parse_posted_at()` helper in `apify_reviews.py`. `app/api/report.py` now passes parsed Apify timestamps into `review_score()`.
- 8 new assertions in `tests/test_health_score.py` (31/31 passing); calibration unchanged on the no-dated-reviews path.

## [24 April 2026] — Session 4 — FastAPI endpoints + e2e test (MVP complete pending GCP unblock)

- Built `main.py`: FastAPI app with 4 endpoints (GET /, POST /onboard, POST /upload-pos/{id}, POST /generate-report/{id}, GET /history/{id})
- Pydantic v2 `@field_validator` for place_id (must start ChIJ) and category (allowlist)
- All error paths tested: 400, 404, 409, 422, 500, 502, 503 — all return correct status codes
- Installed `python-multipart` for UploadFile support
- Created pyiceberg stub in venv (storage3 2.28.3 hard-imports it; no Windows binary wheel available)
- Built `test_e2e.py`: 5-business acceptance test with 6 steps per business (onboard → pos upload → report → validate → supabase check → history)
- Server starts cleanly: `uvicorn main:app --reload`; Swagger at localhost:8000/docs shows all 4 endpoints
- GCP blocker confirmed: "Places API" (legacy) not enabled — all Google Places calls return REQUEST_DENIED; e2e test will pass once enabled and real Pune Place IDs are inserted in test_e2e.py

## [April 2026] — Project initialised

- Created project spec doc (product + engineering requirements)
- Created CLAUDE.md, architecture.md, project-status.md
- Created .env.example with all required keys
- Defined database schema: businesses, health_scores, pos_records
- Defined health score formula: review × 0.40 + competitor × 0.25 + pos × 0.35
- Decided: POS score defaults to 50 (neutral) when no data — not 0
- Decided: synthetic CSV first, Petpooja API when approved
- Decided: WhatsApp + scheduler + Hindi deferred to V2
- Created GitHub issues #1–#14 covering all MVP phases

---

*Add a new entry every time you:*
- *Add or remove a file*
- *Change a function signature or formula*
- *Add or modify a database table/column*
- *Make a scope decision (in or out)*
- *Pass a quality gate*
- *Fix a bug that could recur*
