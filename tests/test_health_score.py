"""
test_health_score.py — validates health_score service

Part A: unit tests on each function
Part B: full synthetic profile integration tests
Part C: edge case integration tests
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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


# ── Summary ────────────────────────────────────────────────────────────────────

print(f"\n{'='*50}")
print(f"Total assertions: {_passed}/{_total} passed")
if _passed == _total:
    print("All assertions passed. health_score.py is ready.")
else:
    print(f"{_total - _passed} assertion(s) failed — fix the functions before proceeding.")
print("="*50)
