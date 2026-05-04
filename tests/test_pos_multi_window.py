"""
test_pos_multi_window.py — unit tests for the multi-window trend helper.

Pure pandas, no Supabase. Run: python tests/test_pos_multi_window.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import date, timedelta

import pandas as pd

from app.services.pos_pipeline import _window_trend


_passed = 0
_total = 0


def check(condition: bool, label: str, actual) -> None:
    global _passed, _total
    _total += 1
    tag = "PASS" if condition else "FAIL"
    print(f"  {tag}: {label}  (actual={actual})")
    if condition:
        _passed += 1


def _build(today: date, daily_revenues: list[float]) -> pd.DataFrame:
    """Build a DataFrame with one row per day going back len(daily_revenues) days.

    Index 0 = oldest day, index -1 = today. Each entry is the revenue for that day.
    """
    rows = []
    n = len(daily_revenues)
    for i, rev in enumerate(daily_revenues):
        rows.append({"date": pd.Timestamp(today - timedelta(days=n - 1 - i)), "revenue": rev})
    return pd.DataFrame(rows)


TODAY = date(2026, 5, 4)


# 1. Equal-window trend — flat data → 0%
df_flat = _build(TODAY, [100.0] * 60)
t = _window_trend(df_flat, TODAY, recent_days=30, prior_days=30)
check(t == 0.0, "1. Flat data 30-vs-30: trend = 0%", t)

# 2. Asymmetric window (7-vs-28) — flat data still 0%
df_flat56 = _build(TODAY, [100.0] * 56)
t = _window_trend(df_flat56, TODAY, recent_days=7, prior_days=28)
check(t == 0.0, "2. Flat data 7-vs-28 (asymmetric): trend = 0%", t)

# 3. 90-vs-90 with growth in the recent window
df_growing = _build(TODAY, [100.0] * 90 + [120.0] * 90)
t = _window_trend(df_growing, TODAY, recent_days=90, prior_days=90)
check(t == 20.0, "3. 90-vs-90 with +20% in recent half: trend = 20%", t)

# 4. 7-vs-28 detects acute spike that 30-vs-30 misses
# Last 7 days double, prior 28 days flat.
days = [100.0] * 28 + [200.0] * 7
df_acute = _build(TODAY, days)
acute = _window_trend(df_acute, TODAY, recent_days=7, prior_days=28)
check(acute == 100.0, "4. Acute 7-vs-28 catches +100% spike", acute)

# 5. Recent window empty → None
df_short = _build(TODAY - timedelta(days=14), [100.0] * 30)
# All data ends 14 days ago, so the last 7 days have no rows
t = _window_trend(df_short, TODAY, recent_days=7, prior_days=28)
check(t is None, "5. Empty recent window returns None", t)

# 6. Prior window empty → None (only 5 days of history, 30-vs-30 can't fill prior)
df_tiny = _build(TODAY, [100.0] * 5)
t = _window_trend(df_tiny, TODAY, recent_days=30, prior_days=30)
check(t is None, "6. Empty prior window returns None", t)

# 7. Prior daily-avg = 0 → None (avoids division by zero)
df_zero_prior = _build(TODAY, [0.0] * 30 + [100.0] * 30)
t = _window_trend(df_zero_prior, TODAY, recent_days=30, prior_days=30)
check(t is None, "7. Zero-revenue prior window returns None (no div-by-zero)", t)

# 8. Negative trend — recent window down 50%
df_decline = _build(TODAY, [200.0] * 30 + [100.0] * 30)
t = _window_trend(df_decline, TODAY, recent_days=30, prior_days=30)
check(t == -50.0, "8. 50% decline 30-vs-30: trend = -50%", t)

# 9. Daily-averaging: doubling daily revenue in recent (asymmetric) window
# Prior 28 days: 100/day. Recent 7 days: 200/day. Trend = (200-100)/100 = 100%.
days_db = [100.0] * 28 + [200.0] * 7
df_db = _build(TODAY, days_db)
t = _window_trend(df_db, TODAY, recent_days=7, prior_days=28)
check(t == 100.0, "9. Daily-averaged 7-vs-28: doubled-daily → +100%", t)


print(f"\n{'='*50}")
print(f"Total assertions: {_passed}/{_total} passed")
print("="*50)

if _passed != _total:
    sys.exit(1)
