import os
import random
import logging
from datetime import datetime, timedelta

import pandas as pd
from faker import Faker

# ── Reproducibility ────────────────────────────────────────────────────────────

SEED = 42
random.seed(SEED)
Faker.seed(SEED)

# ── Logging ────────────────────────────────────────────────────────────────────

os.makedirs("logs", exist_ok=True)
_fmt = logging.Formatter("%(asctime)s — %(levelname)s — %(message)s")
logger = logging.getLogger("vyaparai.synthetic_pos")
logger.setLevel(logging.INFO)
if not logger.handlers:
    _fh = logging.FileHandler("logs/module1.log")
    _fh.setLevel(logging.INFO)
    _fh.setFormatter(_fmt)
    _ch = logging.StreamHandler()
    _ch.setLevel(logging.WARNING)
    _ch.setFormatter(_fmt)
    logger.addHandler(_fh)
    logger.addHandler(_ch)

# ── Business profiles ──────────────────────────────────────────────────────────

BUSINESS_PROFILES = [
    {
        "business_id": "biz_001",
        "description": "Healthy restaurant (growing)",
        "categories": ["Dal Makhani", "Paneer Dishes", "Biryani", "Thali", "Beverages"],
        "base_revenue": 8000,
        "trend_pct": 12,
        "slow_category": None,
        "slow_category_start_days_ago": 0,
        "slow_category_factor": 1.0,
        "weekend_boost": 0.35,
        "weekday_dip": 0.15,
        # repeat rate rising: loyal customer base growing with the business
        "repeat_rate_start": 0.50,
        "repeat_rate_end": 0.62,
        "category_weights": {
            "Dal Makhani": 0.20,
            "Paneer Dishes": 0.30,
            "Biryani": 0.25,
            "Thali": 0.15,
            "Beverages": 0.10,
        },
        "unit_prices": {
            "Dal Makhani": 180,
            "Paneer Dishes": 200,
            "Biryani": 220,
            "Thali": 150,
            "Beverages": 80,
        },
    },
    {
        "business_id": "biz_002",
        "description": "Struggling restaurant (declining)",
        "categories": ["Chicken Dishes", "Mutton Dishes", "Roti", "Rice", "Cold Drinks"],
        "base_revenue": 6500,
        "trend_pct": -18,
        "slow_category": "Mutton Dishes",
        "slow_category_start_days_ago": 30,
        "slow_category_factor": 0.25,
        "weekend_boost": 0.20,
        "weekday_dip": 0.10,
        # repeat rate sharply declining: customers not coming back — early warning
        "repeat_rate_start": 0.60,
        "repeat_rate_end": 0.28,
        "category_weights": {
            "Chicken Dishes": 0.35,
            "Mutton Dishes": 0.25,
            "Roti": 0.15,
            "Rice": 0.15,
            "Cold Drinks": 0.10,
        },
        "unit_prices": {
            "Chicken Dishes": 220,
            "Mutton Dishes": 280,
            "Roti": 20,
            "Rice": 80,
            "Cold Drinks": 40,
        },
    },
    {
        "business_id": "biz_003",
        "description": "Kirana store (stable, one slow category)",
        "categories": ["Atta", "Rice", "Oil", "Sugar", "Snacks"],
        "base_revenue": 4200,
        "trend_pct": 2,
        "slow_category": "Snacks",
        "slow_category_start_days_ago": 21,
        "slow_category_factor": 0.30,
        "weekend_boost": 0.08,
        "weekday_dip": 0.05,
        # kirana: very high repeat (neighbourhood regulars), very stable
        "repeat_rate_start": 0.72,
        "repeat_rate_end": 0.70,
        "category_weights": {
            "Atta": 0.25,
            "Rice": 0.25,
            "Oil": 0.20,
            "Sugar": 0.15,
            "Snacks": 0.15,
        },
        "unit_prices": {
            "Atta": 50,
            "Rice": 60,
            "Oil": 120,
            "Sugar": 45,
            "Snacks": 30,
        },
    },
    {
        "business_id": "biz_004",
        "description": "Retail shop (seasonal spike)",
        "categories": ["Kurtas", "Sarees", "Accessories", "Footwear"],
        "base_revenue": 5500,
        "trend_pct": 5,
        # Applied on top of trend_pct: +25% ramp over the last 30 days
        "seasonal_spike": {"last_n_days": 30, "pct": 25},
        "slow_category": "Footwear",
        "slow_category_start_days_ago": 14,
        "slow_category_factor": 0.10,
        "weekend_boost": 0.40,
        "weekday_dip": 0.20,
        # retail: lower base repeat (fashion = less habitual), mild rise with seasonal spike
        "repeat_rate_start": 0.38,
        "repeat_rate_end": 0.46,
        "category_weights": {
            "Kurtas": 0.35,
            "Sarees": 0.30,
            "Accessories": 0.20,
            "Footwear": 0.15,
        },
        "unit_prices": {
            "Kurtas": 800,
            "Sarees": 1500,
            "Accessories": 300,
            "Footwear": 700,
        },
    },
    {
        "business_id": "biz_005",
        "description": "Cafe (weekend heavy, weekday dead)",
        "categories": ["Coffee", "Sandwiches", "Cakes", "Shakes"],
        "base_revenue": 3800,
        "trend_pct": -5,
        "slow_category": "Cakes",
        "slow_category_start_days_ago": 15,  # ramp starts 15d ago, fully slow for 10d
        "slow_category_factor": 0.20,
        "weekend_boost": 0.60,
        "weekday_dip": 0.25,
        # cafe: moderate repeat rate but declining (customers finding alternatives)
        "repeat_rate_start": 0.55,
        "repeat_rate_end": 0.32,
        "category_weights": {
            "Coffee": 0.35,
            "Sandwiches": 0.25,
            "Cakes": 0.25,
            "Shakes": 0.15,
        },
        "unit_prices": {
            "Coffee": 120,
            "Sandwiches": 150,
            "Cakes": 200,
            "Shakes": 140,
        },
    },
]

# Slow category drops in gradually over this many days rather than a hard cliff.
_SLOW_RAMP_DAYS = 5


# ── Core functions ─────────────────────────────────────────────────────────────

def generate_daily_pattern(
    base_revenue: float,
    day: datetime,
    weekend_boost: float,
    weekday_dip: float,
    day_index: int,
    total_days: int,
    trend_pct: float,
) -> float:
    """Return expected daily revenue for a single date.

    Trend is applied linearly: day 0 = 1.0x, day total_days-1 = (1 + trend_pct/100)x.
    Weekend (Fri/Sat/Sun) boosts and Mon/Tue dips are applied as multipliers.
    ±15% uniform noise ensures the data never looks perfectly linear.
    """
    trend_multiplier = 1.0 + (trend_pct / 100.0) * (day_index / total_days)

    weekday = day.weekday()  # 0=Mon … 6=Sun
    if weekday in (4, 5, 6):   # Fri, Sat, Sun
        dow_multiplier = 1.0 + weekend_boost
    elif weekday in (0, 1):    # Mon, Tue
        dow_multiplier = 1.0 - weekday_dip
    else:
        dow_multiplier = 1.0

    noise = random.uniform(0.85, 1.15)
    return base_revenue * trend_multiplier * dow_multiplier * noise


def generate_business_pos(business_profile: dict) -> pd.DataFrame:
    """Generate 90 days of per-category POS data for one business profile.

    Returns a DataFrame sorted by date then product_category with columns:
    date, product_category, units_sold, revenue, transaction_count, avg_order_value
    """
    total_days = 90
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday = today - timedelta(days=1)

    slow_cat = business_profile["slow_category"]
    # day_index at which the slow period begins (0-based, 0 = oldest day)
    slow_start_idx = (
        total_days - business_profile["slow_category_start_days_ago"]
        if slow_cat
        else total_days  # never triggers
    )

    seasonal_spike = business_profile.get("seasonal_spike")
    spike_start_idx = (
        total_days - seasonal_spike["last_n_days"]
        if seasonal_spike
        else total_days  # never triggers
    )

    rows = []
    for day_index in range(total_days):
        # day_index 0 = 89 days before yesterday; day_index 89 = yesterday
        current_date = yesterday - timedelta(days=(total_days - 1 - day_index))

        daily_revenue = generate_daily_pattern(
            base_revenue=business_profile["base_revenue"],
            day=current_date,
            weekend_boost=business_profile["weekend_boost"],
            weekday_dip=business_profile["weekday_dip"],
            day_index=day_index,
            total_days=total_days,
            trend_pct=business_profile["trend_pct"],
        )

        # Seasonal spike: gradual ramp over the spike window
        if seasonal_spike and day_index >= spike_start_idx:
            days_into_spike = day_index - spike_start_idx
            spike_mult = 1.0 + (seasonal_spike["pct"] / 100.0) * (
                days_into_spike / seasonal_spike["last_n_days"]
            )
            daily_revenue *= spike_mult

        # Slow category factor: eases in over _SLOW_RAMP_DAYS to avoid a hard cliff
        days_since_slow = day_index - slow_start_idx
        if not slow_cat or days_since_slow <= 0:
            slow_factor = 1.0
        elif days_since_slow <= _SLOW_RAMP_DAYS:
            t = days_since_slow / _SLOW_RAMP_DAYS
            slow_factor = 1.0 + t * (business_profile["slow_category_factor"] - 1.0)
        else:
            slow_factor = business_profile["slow_category_factor"]

        # Interpolate repeat rate linearly across the 90-day window with small noise.
        repeat_rate = (
            business_profile["repeat_rate_start"]
            + (business_profile["repeat_rate_end"] - business_profile["repeat_rate_start"])
            * (day_index / max(1, total_days - 1))
        )
        repeat_rate = max(0.05, min(0.95, repeat_rate + random.uniform(-0.04, 0.04)))

        for category in business_profile["categories"]:
            weight = business_profile["category_weights"][category]
            unit_price = business_profile["unit_prices"][category]

            cat_revenue = daily_revenue * weight
            if category == slow_cat:
                cat_revenue *= slow_factor

            units_sold = max(1, int(cat_revenue / unit_price))
            transaction_count = max(1, int(units_sold * random.uniform(0.6, 0.9)))
            avg_order_value = round(cat_revenue / transaction_count, 2)

            # unique_customers proxied by transaction_count; returning_customers derived
            # from the interpolated repeat rate so the trend is detectable by pos_pipeline.
            unique_customers = transaction_count
            returning_customers = max(0, int(unique_customers * repeat_rate))

            rows.append({
                "date": current_date.strftime("%Y-%m-%d"),
                "product_category": category,
                "units_sold": units_sold,
                "revenue": round(cat_revenue, 2),
                "transaction_count": transaction_count,
                "avg_order_value": avg_order_value,
                "unique_customers": unique_customers,
                "returning_customers": returning_customers,
            })

    df = pd.DataFrame(
        rows,
        columns=["date", "product_category", "units_sold", "revenue",
                 "transaction_count", "avg_order_value",
                 "unique_customers", "returning_customers"],
    )
    df = df.sort_values(["date", "product_category"]).reset_index(drop=True)
    logger.info(
        f"Generated {len(df)} rows for {business_profile['business_id']} "
        f"({business_profile['description']})"
    )
    return df


def save_to_csv(df: pd.DataFrame, business_id: str) -> str:
    """Save DataFrame to data/business_{business_id}_pos.csv.

    Creates the data/ directory if needed. Returns the full filepath.
    """
    os.makedirs("data", exist_ok=True)
    filepath = os.path.join("data", f"business_{business_id}_pos.csv")
    df.to_csv(filepath, index=False, float_format="%.2f")
    return filepath


# ── Validation ─────────────────────────────────────────────────────────────────

def _print_validation(all_data: dict) -> None:
    """Print slow-category ratios and revenue sanity checks for all businesses."""
    print("\n" + "=" * 65)
    print("VALIDATION SUMMARY")
    print("=" * 65)

    today_ts = pd.Timestamp.now().normalize()

    for profile in BUSINESS_PROFILES:
        biz_id = profile["business_id"]
        df = all_data[biz_id]
        total_rev = df["revenue"].sum()

        # Revenue sanity: base * 90 days * average trend factor (midpoint = 0.5)
        expected_rev = (
            profile["base_revenue"] * 90 * (1.0 + profile["trend_pct"] / 200.0)
        )
        rev_ratio = total_rev / expected_rev if expected_rev else 0

        print(f"\n{biz_id} — {profile['description']}")
        print(
            f"  Total revenue : ₹{total_rev:>12,.2f}"
            f"  (expected ~₹{expected_rev:,.0f}, ratio {rev_ratio:.2f})"
        )

        slow_cat = profile["slow_category"]
        if not slow_cat:
            print("  Slow category : none")
            continue

        cat_df = df[df["product_category"] == slow_cat].copy()
        cat_df["_date"] = pd.to_datetime(cat_df["date"])

        # Use only the fully-slow window (exclude ramp days) for a clean signal.
        # Revenue is used instead of units_sold to avoid max(1,...) clamping
        # on high-price categories (e.g. Footwear at ₹700/unit).
        fully_slow_days = max(1, profile["slow_category_start_days_ago"] - _SLOW_RAMP_DAYS)
        recent_days = min(14, fully_slow_days)
        recent_cutoff = today_ts - pd.Timedelta(days=recent_days)
        recent = cat_df[cat_df["_date"] >= recent_cutoff]

        # Prior window: days 30–90 ago — solidly before the slow period for all profiles
        prior_end = today_ts - pd.Timedelta(days=30)
        prior_start = today_ts - pd.Timedelta(days=90)
        prior = cat_df[
            (cat_df["_date"] >= prior_start) & (cat_df["_date"] < prior_end)
        ]

        if recent.empty or prior.empty:
            print(f"  Slow category : {slow_cat} — insufficient data")
            continue

        avg_recent = recent["revenue"].mean()
        avg_prior = prior["revenue"].mean()
        ratio = avg_recent / avg_prior if avg_prior > 0 else 0
        expected_factor = profile["slow_category_factor"]
        tolerance = 0.10
        status = "✓" if abs(ratio - expected_factor) <= tolerance else "✗ CHECK"

        print(f"  Slow category : {slow_cat}")
        print(f"    Last {recent_days:2d}d avg : ₹{avg_recent:7.2f}/day (revenue)")
        print(f"    Prior 60d avg : ₹{avg_prior:7.2f}/day (revenue)")
        print(
            f"    Ratio         : {ratio:.3f}  "
            f"(expected ~{expected_factor:.2f}, tol ±{tolerance:.2f})  {status}"
        )


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    all_data = {}

    for profile in BUSINESS_PROFILES:
        df = generate_business_pos(profile)
        filepath = save_to_csv(df, profile["business_id"])

        first_date = df["date"].min()
        last_date = df["date"].max()
        total_rev = df["revenue"].sum()

        slow_cat = profile["slow_category"]
        if slow_cat:
            slow_df = df[df["product_category"] == slow_cat].copy()
            slow_df["_date"] = pd.to_datetime(slow_df["date"])
            today_ts = pd.Timestamp.now().normalize()
            cutoff = today_ts - pd.Timedelta(days=30)
            last_30_avg = slow_df[slow_df["_date"] >= cutoff]["units_sold"].mean()
            prior_avg = slow_df[slow_df["_date"] < cutoff]["units_sold"].mean()
            slow_summary = (
                f"{slow_cat} — last 30d avg {last_30_avg:.1f} units, "
                f"prior 60d avg {prior_avg:.1f} units"
            )
        else:
            slow_summary = "none"

        print(f"\nGenerated {profile['business_id']} ({profile['description']}):")
        print(f"  Total rows   : {len(df)}")
        print(f"  Date range   : {first_date} to {last_date}")
        print(f"  Total revenue: ₹{total_rev:,.2f}")
        print(f"  Slow category: {slow_summary}")
        print(f"  File saved   : {filepath}")

        all_data[profile["business_id"]] = df

    _print_validation(all_data)
