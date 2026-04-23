import os
import logging
from datetime import datetime, timedelta

import pandas as pd
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()
os.makedirs("logs", exist_ok=True)

_fmt = logging.Formatter("%(asctime)s — %(levelname)s — %(message)s")
logger = logging.getLogger("vyaparai.pos_pipeline")
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

supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

REQUIRED_COLUMNS = [
    "date", "product_category", "units_sold", "revenue",
    "transaction_count", "avg_order_value",
]
# 0.35 (not 0.30) catches biz_003 Snacks whose slow_factor is exactly 0.30
SLOW_THRESHOLD = 0.35
# Revenue-based minimum prevents false positives on genuinely empty categories
# and avoids the units-based MIN_VOLUME problem with high-price items (Footwear ₹700/unit)
MIN_REVENUE_PER_DAY_FOR_SLOW_FLAG = 50.0
AOV_CHANGE_THRESHOLD_PCT = 5


def _chunks(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


def _null_signals() -> dict:
    return {
        "revenue_trend_pct": None,
        "slow_categories": [],
        "top_product": None,
        "aov_direction": None,
    }


def ingest_pos_csv(filepath: str, business_id: str) -> int:
    """Read a POS CSV, validate it, and insert new rows into pos_records.

    Returns the number of rows actually inserted (0 if all were duplicates).
    Raises FileNotFoundError or ValueError for bad inputs.
    Raises RuntimeError on Supabase write failure.
    """
    logger.info("Ingesting CSV: %s for business_id=%s", filepath, business_id)

    if not os.path.exists(filepath):
        raise FileNotFoundError(f"CSV not found: {filepath}")

    df = pd.read_csv(filepath)

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(
            f"CSV missing required columns: {missing}. Found: {list(df.columns)}"
        )

    # --- coerce types ---
    try:
        df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    except Exception as exc:
        raise ValueError(f"Cannot parse 'date' column: {exc}") from exc

    for col in ("units_sold", "transaction_count"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
        bad = df[df[col].isna()]
        if not bad.empty:
            raise ValueError(
                f"Non-numeric value in '{col}' at row {bad.index[0]}: "
                f"{bad.iloc[0].to_dict()}"
            )
        df[col] = df[col].astype(int)

    df["transaction_count"] = df["transaction_count"].clip(lower=1)

    for col in ("revenue", "avg_order_value"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
        bad = df[df[col].isna()]
        if not bad.empty:
            raise ValueError(
                f"Non-numeric value in '{col}' at row {bad.index[0]}: "
                f"{bad.iloc[0].to_dict()}"
            )

    neg_rev = df[df["revenue"] < 0]
    if not neg_rev.empty:
        raise ValueError(
            f"Negative revenue at row {neg_rev.index[0]}: {neg_rev.iloc[0].to_dict()}"
        )
    df["avg_order_value"] = df["avg_order_value"].clip(lower=0)

    logger.info(
        "CSV validated: %d rows, date range %s to %s",
        len(df), df["date"].min(), df["date"].max(),
    )

    # --- duplicate detection ---
    unique_dates = df["date"].unique().tolist()
    existing_set: set[tuple] = set()
    if unique_dates:
        try:
            existing = (
                supabase.table("pos_records")
                .select("date, product_category")
                .eq("business_id", business_id)
                .in_("date", unique_dates)
                .execute()
            )
            existing_set = {
                (r["date"], r["product_category"]) for r in existing.data
            }
        except Exception as exc:
            raise RuntimeError(
                f"Failed to query existing pos_records for business {business_id}: {exc}"
            ) from exc

    if existing_set:
        before = len(df)
        df = df[
            ~df.apply(
                lambda row: (row["date"], row["product_category"]) in existing_set,
                axis=1,
            )
        ]
        skipped = before - len(df)
        logger.warning(
            "Skipped %d duplicate (date, category) combinations for business_id=%s",
            skipped, business_id,
        )

    if df.empty:
        logger.info("Inserted 0 rows into pos_records (all duplicates)")
        return 0

    df["business_id"] = business_id
    df["source"] = "synthetic"

    records = df[
        ["business_id", "date", "product_category", "units_sold", "revenue",
         "transaction_count", "avg_order_value", "source"]
    ].to_dict("records")

    total_inserted = 0
    try:
        for batch in _chunks(records, 500):
            resp = supabase.table("pos_records").insert(batch).execute()
            n = len(resp.data)
            if n != len(batch):
                raise RuntimeError(
                    f"Batch insert mismatch: sent {len(batch)} rows, "
                    f"Supabase confirmed {n} for business {business_id}"
                )
            total_inserted += n
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError(
            f"Failed to insert POS records for business {business_id}: {exc}"
        ) from exc

    logger.info("Inserted %d rows into pos_records for business_id=%s", total_inserted, business_id)
    return total_inserted


def pos_signals(business_id: str, days: int = 30) -> dict:
    """Compute 4 POS signals for the last N days of data.

    Always returns a dict with keys:
      revenue_trend_pct, slow_categories, top_product, aov_direction
    Never raises — returns all-None/empty dict on missing data or errors.
    """
    logger.info("Computing POS signals for business_id=%s, days=%d", business_id, days)

    today = datetime.now().date()
    cutoff = today - timedelta(days=days * 2)  # 60 days of data

    try:
        result = (
            supabase.table("pos_records")
            .select("*")
            .eq("business_id", business_id)
            .gte("date", cutoff.isoformat())
            .execute()
        )
    except Exception as exc:
        logger.error("Supabase query failed for business_id=%s: %s", business_id, exc)
        return _null_signals()

    if not result.data:
        logger.info("No POS records found for business_id=%s", business_id)
        return _null_signals()

    df = pd.DataFrame(result.data)
    df["date"] = pd.to_datetime(df["date"])
    df["revenue"] = pd.to_numeric(df["revenue"], errors="coerce").fillna(0.0)
    df["avg_order_value"] = pd.to_numeric(df["avg_order_value"], errors="coerce").fillna(0.0)

    logger.info("Found %d records in last %d days for business_id=%s", len(df), days * 2, business_id)

    recent_cutoff = pd.Timestamp(today - timedelta(days=days))
    recent_df = df[df["date"] >= recent_cutoff]
    prior_df = df[df["date"] < recent_cutoff]

    # --- revenue_trend_pct ---
    trend = None
    try:
        recent_rev = recent_df["revenue"].sum()
        prior_rev = prior_df["revenue"].sum()
        if prior_rev > 0:
            trend = round(((recent_rev - prior_rev) / prior_rev) * 100, 1)
    except Exception as exc:
        logger.warning("revenue_trend_pct computation failed: %s", exc)

    # --- slow_categories ---
    # Compare last 14 days vs prior period (days 30–60 ago).
    # Using revenue avoids the units-based bias for high-price categories (e.g. Footwear ₹700/unit).
    slow_cats = []
    try:
        last_14_cutoff = pd.Timestamp(today - timedelta(days=14))
        prior_slow_end = pd.Timestamp(today - timedelta(days=days))  # 30 days ago

        recent_14_df = df[df["date"] >= last_14_cutoff]
        prior_slow_df = df[df["date"] < prior_slow_end]

        PRIOR_DAYS = days        # 30 calendar days in the prior window
        RECENT_DAYS = 14         # 14-day comparison window

        for cat in df["product_category"].unique():
            cat_prior = prior_slow_df[prior_slow_df["product_category"] == cat]["revenue"].sum()
            prior_avg = cat_prior / PRIOR_DAYS

            if prior_avg < MIN_REVENUE_PER_DAY_FOR_SLOW_FLAG:
                continue

            cat_recent = recent_14_df[recent_14_df["product_category"] == cat]["revenue"].sum()
            recent_avg = cat_recent / RECENT_DAYS

            if recent_avg < SLOW_THRESHOLD * prior_avg:
                slow_cats.append(cat)

        slow_cats = sorted(slow_cats)[:5]
    except Exception as exc:
        logger.warning("slow_categories computation failed: %s", exc)
        slow_cats = []

    # --- top_product ---
    top_product = None
    try:
        if not recent_df.empty:
            top_product = (
                recent_df.groupby("product_category")["revenue"].sum().idxmax()
            )
    except Exception as exc:
        logger.warning("top_product computation failed: %s", exc)

    # --- aov_direction ---
    aov_direction = None
    try:
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
    except Exception as exc:
        logger.warning("aov_direction computation failed: %s", exc)

    signals = {
        "revenue_trend_pct": trend,
        "slow_categories": slow_cats,
        "top_product": top_product,
        "aov_direction": aov_direction,
    }
    logger.info(
        "Signals for business_id=%s: trend=%s%%, slow=%s, top=%s, aov=%s",
        business_id, trend, slow_cats, top_product, aov_direction,
    )
    return signals
