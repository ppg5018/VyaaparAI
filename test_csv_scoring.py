"""
test_csv_scoring.py — run health_score.py on the 5 synthetic POS CSV files.

Computes pos_signals directly from CSV (no Supabase required) using the same
logic as pos_pipeline.pos_signals(). Google data is mocked because the Places
API is currently blocked; ratings are set to match each business's narrative.

Run:
    python test_csv_scoring.py
"""
import os
from datetime import datetime, timedelta

import pandas as pd

from health_score import review_score, competitor_score, pos_score, calculate_health_score

SLOW_THRESHOLD = 0.35
MIN_REVENUE_PER_DAY = 50.0
AOV_CHANGE_THRESHOLD_PCT = 5
DAYS = 30  # signal window

# ── Mock Google data ───────────────────────────────────────────────────────────
# Ratings and review counts are illustrative — replace with real Places API
# data once the legacy Places API is enabled in GCP.

MOCK_GOOGLE = {
    "biz_001": {
        "description": "Healthy restaurant (growing)",
        "rating": 4.3,
        "total_reviews": 182,
        "recent_reviews": [{"rating": 4.4}, {"rating": 4.5}, {"rating": 4.2}, {"rating": 4.6}, {"rating": 4.3}],
        "competitors": [
            {"rating": 4.0}, {"rating": 3.9}, {"rating": 4.1},
            {"rating": 3.8}, {"rating": 4.2},
        ],
    },
    "biz_002": {
        "description": "Struggling restaurant (declining)",
        "rating": 3.2,
        "total_reviews": 38,
        "recent_reviews": [{"rating": 2.9}, {"rating": 3.1}, {"rating": 2.8}, {"rating": 3.0}, {"rating": 3.2}],
        "competitors": [
            {"rating": 3.9}, {"rating": 4.1}, {"rating": 3.8},
            {"rating": 4.0}, {"rating": 3.7},
        ],
    },
    "biz_003": {
        "description": "Kirana store (stable, Snacks slow)",
        "rating": 3.9,
        "total_reviews": 64,
        "recent_reviews": [{"rating": 3.8}, {"rating": 4.0}, {"rating": 3.9}, {"rating": 3.7}, {"rating": 4.0}],
        "competitors": [
            {"rating": 3.7}, {"rating": 3.8}, {"rating": 3.6},
            {"rating": 3.9}, {"rating": 3.8},
        ],
    },
    "biz_004": {
        "description": "Retail shop (seasonal spike, Footwear slow)",
        "rating": 4.1,
        "total_reviews": 115,
        "recent_reviews": [{"rating": 4.2}, {"rating": 4.0}, {"rating": 4.3}, {"rating": 4.1}, {"rating": 4.0}],
        "competitors": [
            {"rating": 4.0}, {"rating": 3.9}, {"rating": 4.2},
            {"rating": 3.8}, {"rating": 4.1},
        ],
    },
    "biz_005": {
        "description": "Cafe (weekend-heavy, Cakes slow)",
        "rating": 3.6,
        "total_reviews": 47,
        "recent_reviews": [{"rating": 3.5}, {"rating": 3.4}, {"rating": 3.7}, {"rating": 3.3}, {"rating": 3.6}],
        "competitors": [
            {"rating": 4.1}, {"rating": 3.9}, {"rating": 4.0},
            {"rating": 3.8}, {"rating": 4.2},
        ],
    },
}


def compute_pos_signals_from_csv(filepath: str) -> dict:
    """Replicate pos_pipeline.pos_signals() logic directly from a CSV file."""
    df = pd.read_csv(filepath)
    df["date"] = pd.to_datetime(df["date"])
    df["revenue"] = pd.to_numeric(df["revenue"], errors="coerce").fillna(0.0)
    df["avg_order_value"] = pd.to_numeric(df["avg_order_value"], errors="coerce").fillna(0.0)

    today = datetime.now().date()
    recent_cutoff = pd.Timestamp(today - timedelta(days=DAYS))
    prior_cutoff = pd.Timestamp(today - timedelta(days=DAYS * 2))

    recent_df = df[df["date"] >= recent_cutoff]
    prior_df = df[(df["date"] >= prior_cutoff) & (df["date"] < recent_cutoff)]

    # revenue_trend_pct
    recent_rev = recent_df["revenue"].sum()
    prior_rev = prior_df["revenue"].sum()
    trend = round(((recent_rev - prior_rev) / prior_rev) * 100, 1) if prior_rev > 0 else None

    # slow_categories — last 14 days vs prior 30-day baseline
    slow_cats = []
    last_14_cutoff = pd.Timestamp(today - timedelta(days=14))
    recent_14_df = df[df["date"] >= last_14_cutoff]

    for cat in df["product_category"].unique():
        cat_prior = prior_df[prior_df["product_category"] == cat]["revenue"].sum()
        prior_avg = cat_prior / DAYS
        if prior_avg < MIN_REVENUE_PER_DAY:
            continue
        cat_recent = recent_14_df[recent_14_df["product_category"] == cat]["revenue"].sum()
        recent_avg = cat_recent / 14
        if recent_avg < SLOW_THRESHOLD * prior_avg:
            slow_cats.append(cat)
    slow_cats = sorted(slow_cats)[:5]

    # top_product
    top_product = (
        recent_df.groupby("product_category")["revenue"].sum().idxmax()
        if not recent_df.empty else None
    )

    # aov_direction
    recent_aov = recent_df["avg_order_value"].mean()
    prior_aov = prior_df["avg_order_value"].mean()
    if pd.isna(prior_aov) or prior_aov == 0:
        aov_direction = "stable"
    else:
        pct = ((recent_aov - prior_aov) / prior_aov) * 100
        if pct > AOV_CHANGE_THRESHOLD_PCT:
            aov_direction = "rising"
        elif pct < -AOV_CHANGE_THRESHOLD_PCT:
            aov_direction = "falling"
        else:
            aov_direction = "stable"

    return {
        "revenue_trend_pct": trend,
        "slow_categories": slow_cats,
        "top_product": top_product,
        "aov_direction": aov_direction,
        "_recent_rev": round(recent_rev, 2),
        "_prior_rev": round(prior_rev, 2),
    }


# ── Main ───────────────────────────────────────────────────────────────────────

print("\n" + "=" * 65)
print("VyaparAI — Health Score Report (CSV-based POS, mock Google data)")
print("=" * 65)

results = []

for biz_id in ["biz_001", "biz_002", "biz_003", "biz_004", "biz_005"]:
    csv_path = os.path.join("data", f"business_{biz_id}_pos.csv")
    google = MOCK_GOOGLE[biz_id]

    if not os.path.exists(csv_path):
        print(f"\n{biz_id}: CSV not found at {csv_path}. Skipping.")
        continue

    signals = compute_pos_signals_from_csv(csv_path)

    r_score = review_score(
        google["rating"],
        google["total_reviews"],
        google["recent_reviews"],
    )
    c_score = competitor_score(google["rating"], google["competitors"])
    p_score = pos_score(signals)
    result = calculate_health_score(r_score, c_score, p_score)

    results.append((biz_id, google["description"], result, signals))

    band_icon = {"healthy": "GREEN", "watch": "YELLOW", "at_risk": "RED"}[result["band"]]

    print(f"\n{'─'*65}")
    print(f"  {biz_id}  {google['description']}")
    print(f"{'─'*65}")
    print(f"  Google data (mock):  rating={google['rating']}  reviews={google['total_reviews']}")
    print(f"  POS signals:")
    print(f"    revenue_trend_pct : {signals['revenue_trend_pct']:+.1f}%  "
          f"(₹{signals['_prior_rev']:,.0f} → ₹{signals['_recent_rev']:,.0f})")
    print(f"    slow_categories   : {signals['slow_categories'] or '(none)'}")
    print(f"    top_product       : {signals['top_product']}")
    print(f"    aov_direction     : {signals['aov_direction']}")
    print(f"  Sub-scores:")
    print(f"    review_score      : {r_score:>3}")
    print(f"    competitor_score  : {c_score:>3}")
    print(f"    pos_score         : {p_score:>3}")
    print(f"  ┌─────────────────────────────────────┐")
    print(f"  │  Final score : {result['final_score']:>3}   Band : {result['band'].upper():<8}  [{band_icon}]  │")
    print(f"  └─────────────────────────────────────┘")

# ── Summary table ──────────────────────────────────────────────────────────────

print(f"\n{'='*65}")
print(f"  {'Business':<12}  {'Description':<38}  {'Score':>5}  {'Band'}")
print(f"  {'─'*12}  {'─'*38}  {'─'*5}  {'─'*8}")
for biz_id, desc, result, _ in results:
    print(f"  {biz_id:<12}  {desc:<38}  {result['final_score']:>5}  {result['band']}")
print("=" * 65)
print("\nNote: Google ratings are mocked. Re-run after enabling the legacy")
print("Places API to use real ratings and competitor data.")
