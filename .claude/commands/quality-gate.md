# Quality Gate

Run all MVP quality gates defined in `CLAUDE.md` and report a pass/fail scorecard.

## Steps

1. Read `CLAUDE.md` to confirm the current quality gate list
2. Start the FastAPI server if it is not already running (`uvicorn main:app --reload` in background)
3. Run each gate in order:

### Gate 1 — Claude output specificity (target: ≥ 3.5 / 5 average)
- Call `/generate-report` for 10 different businesses (use existing seeded businesses or onboard synthetic ones)
- For each response, score the `insights` array on specificity (1–5):
  - 5: names specific product categories AND competitor names
  - 3: names one but not the other
  - 1: generic advice with no specifics
- Report average score and flag any response scoring < 3

### Gate 2 — Pipeline stability (target: 0 unhandled exceptions across 10 runs)
- Call `/generate-report` for 10 businesses sequentially
- Monitor `logs/module1.log` for ERROR or EXCEPTION lines introduced during the run
- Report pass if zero unhandled exceptions, fail with log excerpts otherwise

### Gate 3 — Healthy profile scores 75+ 
- Onboard (or reuse) a business with: high Google rating (4.5+), many reviews (200+), strong POS revenue trend
- Run `/generate-report` and assert `final_score >= 75`
- Report actual score

### Gate 4 — Struggling profile scores below 40
- Onboard (or reuse) a business with: low Google rating (< 3.5), few reviews (< 20), declining POS revenue
- Run `/generate-report` and assert `final_score < 40`
- Report actual score

### Gate 5 — Slow inventory category flagged by name
- Upload synthetic POS data that contains a category with zero or near-zero units sold (e.g. "stationery")
- Run `/generate-report` and check that the slow category name appears explicitly in one of the three insights
- Report pass/fail and quote the relevant insight

## Output format

Print a table:

| Gate | Description | Result | Detail |
|------|-------------|--------|--------|
| 1 | Claude specificity ≥ 3.5 avg | PASS / FAIL | avg score |
| 2 | 10 runs, 0 unhandled exceptions | PASS / FAIL | exception count |
| 3 | Healthy profile ≥ 75 | PASS / FAIL | actual score |
| 4 | Struggling profile < 40 | PASS / FAIL | actual score |
| 5 | Slow category flagged by name | PASS / FAIL | quoted insight |

Then update the checkboxes in `CLAUDE.md` for any gates that now pass.
