"""
test_health_score.py — validates health_score service

Part A: unit tests on each function
Part B: full synthetic profile integration tests
Part C: edge case integration tests
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta, timezone

from app.services.health_score import review_score, competitor_score, pos_score, calculate_health_score

_passed = 0
_total = 0


def check(condition: bool, label: str, actual) -> None:
    global _passed, _total
    _total += 1
    if condition:
        _passed += 1
        print(f"  PASS: {label}  (actual={actual})")
    else:
        print(f"  FAIL: {label}  (actual={actual})")


# ── PART A: Unit Tests ─────────────────────────────────────────────────────────

print("\n=== Part A: Unit Tests ===")
print("\n-- review_score() --")

s = review_score(5.0, 1000, [{"rating": 5}] * 5)
check(s >= 90, "1. Perfect profile: score >= 90", s)

s = review_score(1.5, 5, [{"rating": 1}] * 5)
check(s <= 25, "2. Awful profile: score <= 25", s)

s = review_score(3.5, 50, [{"rating": 3.5}] * 5)
check(50 <= s <= 65, "3. Mediocre profile: 50 <= score <= 65", s)

s = review_score(5.0, 1, [])
check(60 <= s <= 75, "4. High rating, no reviews: 60 <= score <= 75", s)

s = review_score(4.0, 100, [])
check(55 <= s <= 75, "5. Empty recent_reviews: 55 <= score <= 75", s)

print("\n-- competitor_score() --")

s = competitor_score(4.5, [{"rating": 4.0}] * 5)
check(72 <= s <= 78, "1. Beating competitors by 0.5: 72 <= score <= 78", s)

s = competitor_score(4.0, [{"rating": 4.0}] * 5)
check(58 <= s <= 62, "2. Matching competitors: 58 <= score <= 62", s)

s = competitor_score(3.5, [{"rating": 4.0}] * 5)
check(42 <= s <= 48, "3. Trailing by 0.5: 42 <= score <= 48", s)

s = competitor_score(4.0, [])
check(s == 65, "4. No competitors: score == 65", s)

s = competitor_score(4.2, [{"rating": 4.0}])
check(65 <= s <= 70, "5. Single competitor: 65 <= score <= 70", s)

print("\n-- pos_score() --")

s = pos_score({"revenue_trend_pct": None, "slow_categories": [], "top_product": None, "aov_direction": None})
check(s == 50, "1. All-None signals: score == 50", s)

s = pos_score({"revenue_trend_pct": 12.0, "slow_categories": [], "top_product": "Paneer Dishes", "aov_direction": "rising"})
check(s >= 95, "2. Healthy signals: score >= 95", s)

s = pos_score({"revenue_trend_pct": -18.0, "slow_categories": ["X", "Y"], "top_product": None, "aov_direction": "falling"})
check(s <= 30, "3. Struggling signals: score <= 30", s)

s = pos_score({"revenue_trend_pct": 2.0, "slow_categories": ["X"], "top_product": None, "aov_direction": "stable"})
check(60 <= s <= 80, "4. Mixed signals: 60 <= score <= 80", s)


# ── PART B: Integration Tests ──────────────────────────────────────────────────

print("\n=== Part B: Integration Tests ===")
print("\n-- HEALTHY_PROFILE --")

healthy_review_s = review_score(4.5, 280, [{"rating": 4.4}] * 5)
healthy_comp_s = competitor_score(4.5, [
    {"rating": 4.1}, {"rating": 4.0}, {"rating": 3.8}, {"rating": 4.2}, {"rating": 3.9},
])
healthy_pos_s = pos_score({
    "revenue_trend_pct": 15.0,
    "slow_categories": [],
    "top_product": "Paneer Dishes",
    "aov_direction": "rising",
})
healthy_result = calculate_health_score(healthy_review_s, healthy_comp_s, healthy_pos_s)
print(f"  HEALTHY_PROFILE: review={healthy_review_s}, competitor={healthy_comp_s}, "
      f"pos={healthy_pos_s}, final={healthy_result['final_score']}, band={healthy_result['band']}")

check(healthy_result["final_score"] >= 75, "HEALTHY_PROFILE: final_score >= 75", healthy_result["final_score"])
check(healthy_result["band"] in ("healthy", "watch"), "HEALTHY_PROFILE: band is 'healthy' or 'watch'", healthy_result["band"])

print("\n-- STRUGGLING_PROFILE --")

struggling_review_s = review_score(3.1, 22, [{"rating": 2.8}] * 5)
struggling_comp_s = competitor_score(3.1, [
    {"rating": 3.8}, {"rating": 4.0}, {"rating": 3.9}, {"rating": 3.7}, {"rating": 4.1},
])
struggling_pos_s = pos_score({
    "revenue_trend_pct": -22.0,
    "slow_categories": ["Mutton Dishes", "Rice"],
    "top_product": "Chicken Dishes",
    "aov_direction": "falling",
})
struggling_result = calculate_health_score(struggling_review_s, struggling_comp_s, struggling_pos_s)
print(f"  STRUGGLING_PROFILE: review={struggling_review_s}, competitor={struggling_comp_s}, "
      f"pos={struggling_pos_s}, final={struggling_result['final_score']}, band={struggling_result['band']}")

check(struggling_result["final_score"] < 40, "STRUGGLING_PROFILE: final_score < 40", struggling_result["final_score"])
check(struggling_result["band"] == "at_risk", "STRUGGLING_PROFILE: band == 'at_risk'", struggling_result["band"])
check(
    healthy_result["final_score"] - struggling_result["final_score"] >= 35,
    f"Sensitivity gap >= 35 points",
    healthy_result["final_score"] - struggling_result["final_score"],
)


# ── PART C: Edge Case Integration Tests ───────────────────────────────────────

print("\n=== Part C: Edge Cases ===")

result = calculate_health_score(85, 65, 50)
check(65 <= result["final_score"] <= 75,
      "1. Rural kirana (great reviews, no POS, no competitors): 65 <= final <= 75",
      result["final_score"])

result = calculate_health_score(25, 50, 90)
check(45 <= result["final_score"] <= 60,
      "2. B2B (bad reviews, great POS): 45 <= final <= 60",
      result["final_score"])

result = calculate_health_score(100, 100, 100)
check(result["final_score"] == 100, "3. Everything perfect: final == 100", result["final_score"])

result = calculate_health_score(0, 0, 0)
check(result["final_score"] == 0, "4. Everything zero: final == 0", result["final_score"])


# ── PART D: Time-Decayed Review Volume ────────────────────────────────────────

print("\n=== Part D: Time-Decayed Review Volume ===")

NOW = datetime(2026, 4, 27, tzinfo=timezone.utc)

def _dated(months_old_list):
    return [{"published_at": NOW - timedelta(days=m * 30.44)} for m in months_old_list]

# 1. Recent-reviews business beats stale-reviews business
recent_reviews_dated = _dated([0.5] * 800)  # all under a month old
stale_reviews_dated = _dated([60] * 800)    # all 5 years old
s_recent = review_score(4.5, 800, [{"rating": 4.5}] * 5, all_reviews_with_dates=recent_reviews_dated, now=NOW)
s_stale = review_score(4.5, 800, [{"rating": 4.5}] * 5, all_reviews_with_dates=stale_reviews_dated, now=NOW)
check(s_recent - s_stale >= 5, "1. Recent-800 beats stale-800 by >= 5 pts", f"recent={s_recent} stale={s_stale} diff={s_recent - s_stale}")

# 2. Empty all_reviews_with_dates falls back to flat log-volume — identical to pre-change
s_baseline = review_score(4.0, 100, [{"rating": 4.0}] * 5)
s_empty = review_score(4.0, 100, [{"rating": 4.0}] * 5, all_reviews_with_dates=[], now=NOW)
check(s_baseline == s_empty, "2. Empty list falls back to log-volume (matches baseline)", f"baseline={s_baseline} empty={s_empty}")

# 3. all_reviews_with_dates=None — same as omitting the parameter
s_none = review_score(4.0, 100, [{"rating": 4.0}] * 5, all_reviews_with_dates=None, now=NOW)
check(s_baseline == s_none, "3. None falls back to log-volume (matches baseline)", f"baseline={s_baseline} none={s_none}")

# 4. Mixed ages between extremes
mixed_dated = _dated([m for m in (1, 12, 24, 36) for _ in range(50)])  # 200 reviews evenly across 4 years
s_mixed = review_score(4.5, 200, [{"rating": 4.5}] * 5, all_reviews_with_dates=mixed_dated, now=NOW)
recent_200 = _dated([1] * 200)
stale_200 = _dated([60] * 200)
s_recent200 = review_score(4.5, 200, [{"rating": 4.5}] * 5, all_reviews_with_dates=recent_200, now=NOW)
s_stale200 = review_score(4.5, 200, [{"rating": 4.5}] * 5, all_reviews_with_dates=stale_200, now=NOW)
check(s_stale200 < s_mixed < s_recent200, "4. Mixed-age score sits strictly between recent-only and stale-only", f"stale={s_stale200} mixed={s_mixed} recent={s_recent200}")

# 5. Future-dated review clamps to age 0 (weight 1.0); no crash
future_dated = [{"published_at": NOW + timedelta(days=30)}]
s_future = review_score(4.0, 1, [], all_reviews_with_dates=future_dated, now=NOW)
single_now = [{"published_at": NOW}]
s_now_single = review_score(4.0, 1, [], all_reviews_with_dates=single_now, now=NOW)
check(s_future == s_now_single, "5. Future-dated review behaves like a 0-month-old review (clamped, no crash)", f"future={s_future} now={s_now_single}")

# 6. Unparseable / missing date — review skipped silently, others still counted
mixed_invalid = [
    {"published_at": NOW},
    {"published_at": "not-a-datetime"},
    {},
    {"published_at": None},
    {"published_at": NOW - timedelta(days=30)},
]
s_invalid = review_score(4.0, 5, [], all_reviews_with_dates=mixed_invalid, now=NOW)
two_valid = [{"published_at": NOW}, {"published_at": NOW - timedelta(days=30)}]
s_two_valid = review_score(4.0, 5, [], all_reviews_with_dates=two_valid, now=NOW)
check(s_invalid == s_two_valid, "6. Unparseable/missing dates are skipped silently", f"invalid={s_invalid} two_valid={s_two_valid}")

# 7. Single very recent review — weighted count = 1.0 → log10(1)*10 = 0 volume points
s_single = review_score(4.0, 1, [], all_reviews_with_dates=[{"published_at": NOW}], now=NOW)
# quality_pts = ((4-1)/4)*55 = 41.25, volume_pts = 0, trend_pts = 10 (no recent_reviews) → 51
check(s_single == 51, "7. Single very recent review: volume_pts = 0 (matches existing 1-review behaviour)", s_single)

# 8. Determinism — two consecutive calls with same now produce identical output
s_d1 = review_score(4.5, 800, [{"rating": 4.5}] * 5, all_reviews_with_dates=recent_reviews_dated, now=NOW)
s_d2 = review_score(4.5, 800, [{"rating": 4.5}] * 5, all_reviews_with_dates=recent_reviews_dated, now=NOW)
check(s_d1 == s_d2, "8. Determinism: same inputs + same now -> same score", f"call1={s_d1} call2={s_d2}")


# ── Summary ────────────────────────────────────────────────────────────────────

print(f"\n{'='*50}")
print(f"Total assertions: {_passed}/{_total} passed")
if _passed == _total:
    print("All assertions passed. health_score.py is ready.")
else:
    print(f"{_total - _passed} assertion(s) failed — fix the functions before proceeding.")
print("="*50)
