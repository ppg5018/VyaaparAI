"""
test_review_credibility.py — unit tests for credibility weighting (#10).

Pure Python, no external deps. Run: python tests/test_review_credibility.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta, timezone

from app.services.review_credibility import credibility_weight
from app.services.health_score import review_score, compute_velocity


_passed = 0
_total = 0


def check(condition: bool, label: str, actual) -> None:
    global _passed, _total
    _total += 1
    tag = "PASS" if condition else "FAIL"
    print(f"  {tag}: {label}  (actual={actual})")
    if condition:
        _passed += 1


# ── credibility_weight() ───────────────────────────────────────────────────────

print("\n=== credibility_weight() ===")

# 1. Power reviewer (Local Guide + 200+ reviews) → 1.5
w = credibility_weight({"reviewer_review_count": 250, "reviewer_is_local_guide": True})
check(w == 1.5, "1. Local Guide AND 200+ reviews → 1.5", w)

# 2. 200+ reviews alone → 1.2
w = credibility_weight({"reviewer_review_count": 250, "reviewer_is_local_guide": False})
check(w == 1.2, "2. 200+ reviews alone → 1.2", w)

# 3. Local Guide alone → 1.2
w = credibility_weight({"reviewer_review_count": 50, "reviewer_is_local_guide": True})
check(w == 1.2, "3. Local Guide alone → 1.2", w)

# 4. Mid-range reviewer (5..199) → 1.0
w = credibility_weight({"reviewer_review_count": 30, "reviewer_is_local_guide": False})
check(w == 1.0, "4. Mid-range reviewer (30 reviews) → 1.0", w)

# 5. Single-review account (count present, < 5) → 0.5
w = credibility_weight({"reviewer_review_count": 1, "reviewer_is_local_guide": False})
check(w == 0.5, "5. 1 review (likely fake/coerced) → 0.5", w)

# 6. Truthful 0 reviews → 0.5 (Apify reports 0 only when known-empty profile)
w = credibility_weight({"reviewer_review_count": 0, "reviewer_is_local_guide": False})
check(w == 0.5, "6. 0 reviews (known empty) → 0.5", w)

# 7. Field absent (unknown profile) → neutral 1.0
w = credibility_weight({})
check(w == 1.0, "7. No credibility fields → neutral 1.0", w)

# 8. None for review_count → neutral 1.0 (preserves backward compat)
w = credibility_weight({"reviewer_review_count": None})
check(w == 1.0, "8. None review_count → neutral 1.0", w)

# 9. Non-dict input → neutral 1.0 (defensive)
w = credibility_weight(None)
check(w == 1.0, "9. None input → 1.0 (defensive)", w)

# 10. Non-numeric review_count → treated as 0 (with has_count=True → 0.5)
# This is the truthful interpretation of garbage data: don't trust it.
w = credibility_weight({"reviewer_review_count": "not-a-number"})
check(w == 0.5, "10. Non-numeric count: treats as low-credibility", w)


# ── review_score() with credibility ────────────────────────────────────────────

print("\n=== review_score() credibility weighting ===")

# 11. Backward compat: tests without credibility fields produce same score as before
s_baseline = review_score(4.5, 280, [{"rating": 4.4}] * 5)
# Expectation: identical to the value asserted in test_health_score.py (around 90)
check(s_baseline >= 75, "11. No credibility fields: backward-compat score >= 75", s_baseline)

# 12. Adding all-power reviewers up-weights sentiment
power_reviews = [
    {"rating": 5, "reviewer_review_count": 300, "reviewer_is_local_guide": True}
    for _ in range(5)
]
s_power = review_score(4.5, 280, power_reviews)
check(s_power >= s_baseline, "12. Power reviewers: trend score >= baseline", f"power={s_power} baseline={s_baseline}")

# 13. Adding all-fake reviewers (mixed sentiment 1★) down-weights but only at 0.5x
# Star reviews of 1.0 with weight 0.5 vs 4.4 in baseline — score drops.
fake_reviews = [
    {"rating": 1, "reviewer_review_count": 1, "reviewer_is_local_guide": False}
    for _ in range(5)
]
s_fake = review_score(4.5, 280, fake_reviews)
check(s_fake < s_baseline, "13. Fake-reviewer 1★ block lowers trend score", f"fake={s_fake} baseline={s_baseline}")

# 14. Mixed credibility: one power reviewer's 5★ outweighs four fake 1★ reviews
mixed = [
    {"rating": 5, "reviewer_review_count": 500, "reviewer_is_local_guide": True},  # 1.5
    {"rating": 1, "reviewer_review_count": 1, "reviewer_is_local_guide": False},   # 0.5
    {"rating": 1, "reviewer_review_count": 1, "reviewer_is_local_guide": False},   # 0.5
    {"rating": 1, "reviewer_review_count": 1, "reviewer_is_local_guide": False},   # 0.5
    {"rating": 1, "reviewer_review_count": 1, "reviewer_is_local_guide": False},   # 0.5
]
# weighted avg = (5*1.5 + 1*0.5*4) / (1.5 + 0.5*4) = (7.5 + 2) / 3.5 = 2.71
# unweighted avg = (5 + 1*4) / 5 = 1.8
# So mixed should score higher than fake-only block of 1★
s_mixed = review_score(4.5, 280, mixed)
check(s_mixed > s_fake, "14. One credible 5★ outweighs four fake 1★", f"mixed={s_mixed} fake={s_fake}")


# ── compute_velocity() weighted=True ──────────────────────────────────────────

print("\n=== compute_velocity() weighted credibility ===")

NOW = datetime(2026, 5, 4, tzinfo=timezone.utc)


def _dated(months_old: float, **extra) -> dict:
    return {"published_at": NOW - timedelta(days=months_old * 30.44), **extra}


# 15. 8 power reviewers in last month → weighted velocity > 8/6 (raw)
power_dated = [_dated(0.5, reviewer_review_count=300, reviewer_is_local_guide=True) for _ in range(8)]
v_raw = compute_velocity(power_dated, NOW, weighted=False)
v_weighted = compute_velocity(power_dated, NOW, weighted=True)
check(v_weighted > v_raw, "15. Weighted velocity > raw with all-power reviewers", f"raw={v_raw:.2f} weighted={v_weighted:.2f}")

# 16. 8 single-review fake accounts → weighted velocity < raw
fake_dated = [_dated(0.5, reviewer_review_count=1) for _ in range(8)]
v_raw_f = compute_velocity(fake_dated, NOW, weighted=False)
v_weighted_f = compute_velocity(fake_dated, NOW, weighted=True)
check(v_weighted_f < v_raw_f, "16. Weighted velocity < raw with all-fake accounts", f"raw={v_raw_f:.2f} weighted={v_weighted_f:.2f}")

# 17. weighted=False is default (backward compat — report.py call still gets a literal count)
# Existing test_health_score.py Part D passes — covered there. Spot-check here:
neutral_dated = [_dated(0.5) for _ in range(6)]  # no credibility fields
v_default = compute_velocity(neutral_dated, NOW)
check(v_default == 1.0, "17. weighted=False default: 6 reviews / 6 months = 1.0", v_default)


print(f"\n{'='*50}")
print(f"Total assertions: {_passed}/{_total} passed")
print("="*50)

if _passed != _total:
    sys.exit(1)
