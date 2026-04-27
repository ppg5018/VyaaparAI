import logging
from datetime import datetime, timedelta

import pandas as pd

from app.database import supabase
from app.config import (
    CATEGORY_POS_THRESHOLDS,
    DEFAULT_POS_THRESHOLDS,
    MIN_REVENUE_PER_DAY_FOR_SLOW_FLAG,
    AOV_CHANGE_THRESHOLD_PCT,
    BATCH_SIZE,
)

logger = logging.getLogger(__name__)

REQUIRED_COLUMNS = [
    "date", "product_category", "units_sold", "revenue",
    "transaction_count", "avg_order_value",
]


def _chunks(lst: list, n: int):
    """Yield successive n-sized chunks from lst."""
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


def _null_signals() -> dict:
    """Return an all-None signals dict used when no POS data exists."""
    return {
        "revenue_trend_pct": None,
        "slow_categories": [],
        "top_product": None,
        "aov_direction": None,
        "repeat_rate_pct": None,
        "repeat_rate_trend": None,
    }


def ingest_pos_csv(filepath: str, business_id: str) -> int:
    """Read a POS CSV, validate it, and insert new rows into pos_records.

    Returns the number of rows actually inserted (0 if all were duplicates).
    Raises FileNotFoundError or ValueError for bad inputs.
    Raises RuntimeError on Supabase write failure.
    """
    import os
    logger.info("Ingesting CSV: %s for business_id=%s", filepath, business_id)

    if not os.path.exists(filepath):
        raise FileNotFoundError(f"CSV not found: {filepath}")

    df = pd.read_csv(filepath)

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(
            f"CSV missing required columns: {missing}. Found: {list(df.columns)}"
        )

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

    # Duplicate detection
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

    # Include optional customer columns only when the CSV provides them.
    base_cols = ["business_id", "date", "product_category", "units_sold", "revenue",
                 "transaction_count", "avg_order_value", "source"]
    optional_cols = [c for c in ("unique_customers", "returning_customers") if c in df.columns]
    records = df[base_cols + optional_cols].to_dict("records")

    total_inserted = 0
    try:
        for batch in _chunks(records, BATCH_SIZE):
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

    logger.info(
        "Inserted %d rows into pos_records for business_id=%s", total_inserted, business_id
    )
    return total_inserted


def pos_signals(business_id: str, days: int = 30, category: str = "") -> dict:
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

    logger.info(
        "Found %d records in last %d days for business_id=%s",
        len(df), days * 2, business_id,
    )

    recent_cutoff = pd.Timestamp(today - timedelta(days=days))
    recent_df = df[df["date"] >= recent_cutoff]
    prior_df = df[df["date"] < recent_cutoff]

    # Revenue trend
    trend = None
    try:
        recent_rev = recent_df["revenue"].sum()
        prior_rev = prior_df["revenue"].sum()
        if prior_rev > 0:
            trend = round(((recent_rev - prior_rev) / prior_rev) * 100, 1)
    except Exception as exc:
        logger.warning("revenue_trend_pct computation failed: %s", exc)

    # Slow categories — compare last 14 days vs prior period (days 30–60 ago)
    slow_cats: list[str] = []
    try:
        thresholds = CATEGORY_POS_THRESHOLDS.get(category, DEFAULT_POS_THRESHOLDS)
        slow_threshold = thresholds["slow_threshold"]

        last_14_cutoff = pd.Timestamp(today - timedelta(days=14))
        prior_slow_end = pd.Timestamp(today - timedelta(days=days))

        recent_14_df = df[df["date"] >= last_14_cutoff]
        prior_slow_df = df[df["date"] < prior_slow_end]

        PRIOR_DAYS = days
        RECENT_DAYS = 14

        for cat in df["product_category"].unique():
            cat_prior = prior_slow_df[prior_slow_df["product_category"] == cat]["revenue"].sum()
            prior_avg = cat_prior / PRIOR_DAYS

            if prior_avg < MIN_REVENUE_PER_DAY_FOR_SLOW_FLAG:
                continue

            cat_recent = recent_14_df[recent_14_df["product_category"] == cat]["revenue"].sum()
            recent_avg = cat_recent / RECENT_DAYS

            if recent_avg < slow_threshold * prior_avg:
                slow_cats.append(cat)

        slow_cats = sorted(slow_cats)[:5]
        logger.debug(
            "slow_categories: category=%s slow_threshold=%.2f flagged=%s",
            category, slow_threshold, slow_cats,
        )
    except Exception as exc:
        logger.warning("slow_categories computation failed: %s", exc)
        slow_cats = []

    # Top product by revenue in recent period
    top_product = None
    try:
        if not recent_df.empty:
            top_product = (
                recent_df.groupby("product_category")["revenue"].sum().idxmax()
            )
    except Exception as exc:
        logger.warning("top_product computation failed: %s", exc)

    # AOV direction
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

    # Repeat customer rate — only available when unique_customers column exists
    repeat_rate_pct = None
    repeat_rate_trend = None
    try:
        if "unique_customers" in df.columns and "returning_customers" in df.columns:
            df["unique_customers"] = pd.to_numeric(df["unique_customers"], errors="coerce").fillna(0)
            df["returning_customers"] = pd.to_numeric(df["returning_customers"], errors="coerce").fillna(0)

            daily = (
                df.groupby("date")[["unique_customers", "returning_customers"]]
                .sum()
                .reset_index()
            )

            recent_daily = daily[daily["date"] >= recent_cutoff]
            prior_daily = daily[daily["date"] < recent_cutoff]

            recent_total = recent_daily["unique_customers"].sum()
            recent_return = recent_daily["returning_customers"].sum()
            prior_total = prior_daily["unique_customers"].sum()
            prior_return = prior_daily["returning_customers"].sum()

            if recent_total > 0:
                repeat_rate_pct = round((recent_return / recent_total) * 100, 1)

            if prior_total > 0 and recent_total > 0:
                prior_rate = prior_return / prior_total
                recent_rate = recent_return / recent_total
                if prior_rate > 0:
                    repeat_rate_trend = round(((recent_rate - prior_rate) / prior_rate) * 100, 1)

            logger.debug(
                "repeat_rate: recent=%.1f%% trend=%s%%",
                repeat_rate_pct or 0, repeat_rate_trend,
            )
    except Exception as exc:
        logger.warning("repeat_rate computation failed: %s", exc)

    signals = {
        "revenue_trend_pct": trend,
        "slow_categories": slow_cats,
        "top_product": top_product,
        "aov_direction": aov_direction,
        "repeat_rate_pct": repeat_rate_pct,
        "repeat_rate_trend": repeat_rate_trend,
    }
    logger.info(
        "Signals for business_id=%s: trend=%s%% slow=%s top=%s aov=%s repeat=%.1f%%(trend=%s%%)",
        business_id, trend, slow_cats, top_product, aov_direction,
        repeat_rate_pct or 0, repeat_rate_trend,
    )
    return signals
