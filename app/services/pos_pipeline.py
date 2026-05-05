import logging
from datetime import datetime, timedelta

import pandas as pd

from app.database import supabase
from app.services import pos_column_matcher
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
        "revenue_trend_acute_pct": None,
        "revenue_trend_chronic_pct": None,
        "slow_categories": [],
        "top_product": None,
        "aov_direction": None,
        "repeat_rate_pct": None,
        "repeat_rate_trend": None,
    }


def _window_trend(
    df: pd.DataFrame,
    today,
    recent_days: int,
    prior_days: int,
) -> float | None:
    """Daily-averaged revenue trend % comparing the last `recent_days`
    against the `prior_days` immediately before that window.

    Daily averaging means asymmetric windows (e.g. 7-vs-28) are comparable.
    Returns None when either window is empty or the prior daily-average is 0.
    """
    # Strict `>` on the lower bound so a recent_days=30 window covers exactly
    # 30 days (today, today-1, ..., today-29) rather than 31. The prior window
    # mirrors this: strictly newer than its lower bound, up to and including
    # the recent boundary day.
    recent_start = pd.Timestamp(today - timedelta(days=recent_days))
    prior_start = pd.Timestamp(today - timedelta(days=recent_days + prior_days))

    recent = df[df["date"] > recent_start]
    prior = df[(df["date"] > prior_start) & (df["date"] <= recent_start)]

    if recent.empty or prior.empty:
        return None

    recent_avg = recent["revenue"].sum() / recent_days
    prior_avg = prior["revenue"].sum() / prior_days

    if prior_avg <= 0:
        return None
    return round(((recent_avg - prior_avg) / prior_avg) * 100, 1)


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

    raw_df = pd.read_csv(filepath)

    # Route through the column matcher so heterogeneous POS exports
    # (Petpooja / DotPe / Tally / Vyapar / hand-built Excel) are canonicalised
    # to pos_records shape before validation. Synthetic CSVs match at Layer 1
    # and pass through unchanged.
    try:
        df, diag = pos_column_matcher.canonicalise(raw_df)
    except ValueError as exc:
        raise ValueError(f"Cannot map POS file columns: {exc}") from exc
    except Exception as exc:
        logger.exception("Column matcher crashed for %s", filepath)
        raise ValueError(
            f"Failed to parse POS file. Raw columns: {list(raw_df.columns)}. Error: {exc}"
        ) from exc
    logger.info(
        "Column mapping diagnostic for %s: L1=%d L2=%d L3=%d unmapped=%d granularity=%s",
        os.path.basename(filepath),
        len(diag["layer1"]), len(diag["layer2"]), len(diag["layer3"]),
        len(diag["unmapped"]), diag["granularity"],
    )

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(
            f"CSV missing required columns after mapping: {missing}. "
            f"Mapped columns: {list(df.columns)}. "
            f"Unmapped raw columns: {diag['unmapped']}"
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

    neg_rev_count = int((df["revenue"] < 0).sum())
    if neg_rev_count:
        logger.warning(
            "POS file has %d row(s) with negative revenue (refunds/returns); "
            "keeping them so daily totals net correctly",
            neg_rev_count,
        )
    df["avg_order_value"] = df["avg_order_value"].clip(lower=0)

    logger.info(
        "CSV validated: %d rows, date range %s to %s",
        len(df), df["date"].min(), df["date"].max(),
    )

    # Duplicate detection. Key includes product_name when the upload has it
    # so per-item rollups don't all collapse to the first item per category.
    has_product = "product_name" in df.columns
    unique_dates = df["date"].unique().tolist()
    existing_set: set[tuple] = set()
    if unique_dates:
        try:
            existing = (
                supabase.table("pos_records")
                .select("date, product_category, product_name")
                .eq("business_id", business_id)
                .in_("date", unique_dates)
                .execute()
            )
            if has_product:
                existing_set = {
                    (r["date"], r["product_category"], r.get("product_name"))
                    for r in existing.data
                }
            else:
                existing_set = {
                    (r["date"], r["product_category"]) for r in existing.data
                }
        except Exception as exc:
            raise RuntimeError(
                f"Failed to query existing pos_records for business {business_id}: {exc}"
            ) from exc

    if existing_set:
        before = len(df)
        if has_product:
            df = df[
                ~df.apply(
                    lambda row: (row["date"], row["product_category"], row.get("product_name")) in existing_set,
                    axis=1,
                )
            ]
        else:
            df = df[
                ~df.apply(
                    lambda row: (row["date"], row["product_category"]) in existing_set,
                    axis=1,
                )
            ]
        skipped = before - len(df)
        logger.warning(
            "Skipped %d duplicate row(s) for business_id=%s",
            skipped, business_id,
        )

    if df.empty:
        logger.info("Inserted 0 rows into pos_records (all duplicates)")
        return 0

    df["business_id"] = business_id
    df["source"] = "synthetic"

    # Include optional product_name + customer columns only when the CSV provides them.
    base_cols = ["business_id", "date", "product_category", "units_sold", "revenue",
                 "transaction_count", "avg_order_value", "source"]
    optional_cols = [
        c for c in ("product_name", "unique_customers", "returning_customers")
        if c in df.columns
    ]
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
    # Widen fetch so the chronic 90-vs-90 window has its full prior period
    # even when the caller passes a shorter `days` (e.g. 30).
    fetch_days = max(days * 2, 180)
    cutoff = today - timedelta(days=fetch_days)

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
        len(df), fetch_days, business_id,
    )

    recent_cutoff = pd.Timestamp(today - timedelta(days=days))
    recent_df = df[df["date"] >= recent_cutoff]
    prior_df = df[df["date"] < recent_cutoff]

    # Revenue trend. Primary path: configured `days` window vs the prior
    # `days` window. Fallback: when the prior window is empty (short upload
    # — e.g. a fresh 3-month Petpooja CSV against a 180-day window), split
    # the available data 50/50 by date midpoint so the user still gets a
    # meaningful signal instead of a blank.
    trend = None
    try:
        recent_rev = recent_df["revenue"].sum()
        prior_rev = prior_df["revenue"].sum()
        if prior_rev > 0:
            trend = round(((recent_rev - prior_rev) / prior_rev) * 100, 1)
        elif not df.empty:
            mid = df["date"].min() + (df["date"].max() - df["date"].min()) / 2
            second_half_rev = df[df["date"] >= mid]["revenue"].sum()
            first_half_rev = df[df["date"] < mid]["revenue"].sum()
            if first_half_rev > 0:
                trend = round(((second_half_rev - first_half_rev) / first_half_rev) * 100, 1)
                logger.info(
                    "revenue_trend_pct: prior %d-day window empty, used 50/50 split (rev %.0f → %.0f, trend=%.1f%%)",
                    days, first_half_rev, second_half_rev, trend,
                )
    except Exception as exc:
        logger.warning("revenue_trend_pct computation failed: %s", exc)

    # Multi-window analysis (#8). Acute catches sudden week-on-week shifts;
    # chronic surfaces structural decline that a 30-day window can miss.
    # Daily-averaged so the 7-vs-28 comparison is apples-to-apples.
    acute_trend: float | None = None
    chronic_trend: float | None = None
    try:
        acute_trend = _window_trend(df, today, recent_days=7, prior_days=28)
        chronic_trend = _window_trend(df, today, recent_days=90, prior_days=90)
        logger.debug(
            "multi-window trends: acute(7v28)=%s%% current(%dv%d)=%s%% chronic(90v90)=%s%%",
            acute_trend, days, days, trend, chronic_trend,
        )
    except Exception as exc:
        logger.warning("multi-window trend computation failed: %s", exc)

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

    # Top product by revenue in recent period. Prefer product_name when the
    # upload preserved it (Petpooja/DotPe ItemName). Fall back to category
    # for files that only have a category column.
    top_product = None
    try:
        scope = recent_df if not recent_df.empty else df
        if not scope.empty:
            if "product_name" in scope.columns:
                named = scope[scope["product_name"].notna() & (scope["product_name"] != "")]
                if not named.empty:
                    top_product = (
                        named.groupby("product_name")["revenue"].sum().idxmax()
                    )
            if not top_product:
                top_product = (
                    scope.groupby("product_category")["revenue"].sum().idxmax()
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
        "revenue_trend_acute_pct": acute_trend,
        "revenue_trend_chronic_pct": chronic_trend,
        "slow_categories": slow_cats,
        "top_product": top_product,
        "aov_direction": aov_direction,
        "repeat_rate_pct": repeat_rate_pct,
        "repeat_rate_trend": repeat_rate_trend,
    }
    logger.info(
        "Signals for business_id=%s: trend=%s%% (acute=%s%% chronic=%s%%) slow=%s top=%s aov=%s repeat=%.1f%%(trend=%s%%)",
        business_id, trend, acute_trend, chronic_trend, slow_cats, top_product, aov_direction,
        repeat_rate_pct or 0, repeat_rate_trend,
    )
    return signals


def chart_data(business_id: str, weeks: int = 8) -> dict:
    """Return weekly revenue rollup + revenue-by-category for the dashboard.

    Returns {"weekly_revenue": [...], "revenue_by_category": [...]}. Empty lists when
    no POS data exists. Never raises.
    """
    today = datetime.now().date()
    cutoff = today - timedelta(days=weeks * 7)

    try:
        result = (
            supabase.table("pos_records")
            .select("date, product_category, revenue")
            .eq("business_id", business_id)
            .gte("date", cutoff.isoformat())
            .execute()
        )
    except Exception as exc:
        logger.warning("[chart_data] supabase query failed: %s", exc)
        return {"weekly_revenue": [], "revenue_by_category": []}

    if not result.data:
        return {"weekly_revenue": [], "revenue_by_category": []}

    df = pd.DataFrame(result.data)
    df["date"] = pd.to_datetime(df["date"])
    df["revenue"] = pd.to_numeric(df["revenue"], errors="coerce").fillna(0.0)

    # Weekly revenue — last `weeks` weeks ending today.
    weekly = []
    for w in range(weeks - 1, -1, -1):
        week_end = today - timedelta(days=w * 7)
        week_start = week_end - timedelta(days=6)
        mask = (df["date"] >= pd.Timestamp(week_start)) & (df["date"] <= pd.Timestamp(week_end))
        rev = float(df.loc[mask, "revenue"].sum())
        # Label like "W1Apr" — week-of-month + month abbreviation.
        month = week_end.strftime("%b")
        wom = (week_end.day - 1) // 7 + 1
        weekly.append({"week": f"W{wom}{month}", "rev": rev})

    # Revenue by category — over the full window.
    by_cat = (
        df.groupby("product_category")["revenue"]
        .sum()
        .sort_values(ascending=False)
        .head(8)
    )
    total = float(by_cat.sum()) or 1.0
    categories = [
        {"name": name, "rev": float(rev), "pct": round(float(rev) / total * 100, 1)}
        for name, rev in by_cat.items()
    ]

    return {"weekly_revenue": weekly, "revenue_by_category": categories}


def _empty_dashboard() -> dict:
    return {
        "metrics": {
            "total_revenue": 0.0,
            "total_orders": 0,
            "total_units": 0,
            "avg_order_value": 0.0,
            "avg_daily_revenue": 0.0,
            "best_selling_item": None,
            "best_selling_revenue": 0.0,
            "date_range": {"from": None, "to": None, "days": 0},
        },
        "daily_revenue": [],
        "weekly_revenue": [],
        "weekly_growth": {"best_week": None, "worst_week": None},
        "peak_day_of_week": [],
        "revenue_by_category": [],
        "categories": [],
    }


def dashboard_data(
    business_id: str,
    from_date: str | None = None,
    to_date: str | None = None,
    category: str | None = None,
) -> dict:
    """Build the POS Insights Dashboard payload from `pos_records`.

    All metrics, charts, and breakdowns are derived from a single query
    so the frontend renders one consistent snapshot. Filters are applied
    via Supabase WHERE clauses, not in pandas, to keep payloads small.

    Date range defaults to the full extent of the business's data.
    Returns an empty-but-shaped payload when no data exists; never raises.
    """
    try:
        q = (
            supabase.table("pos_records")
            .select("date, product_category, product_name, units_sold, "
                    "revenue, transaction_count, avg_order_value")
            .eq("business_id", business_id)
        )
        if from_date:
            q = q.gte("date", from_date)
        if to_date:
            q = q.lte("date", to_date)
        if category:
            q = q.eq("product_category", category)
        result = q.execute()
    except Exception as exc:
        logger.warning("[dashboard_data] supabase query failed: %s", exc)
        return _empty_dashboard()

    if not result.data:
        return _empty_dashboard()

    df = pd.DataFrame(result.data)
    df["date"] = pd.to_datetime(df["date"])
    df["revenue"] = pd.to_numeric(df["revenue"], errors="coerce").fillna(0.0)
    df["transaction_count"] = pd.to_numeric(df["transaction_count"], errors="coerce").fillna(0).astype(int)
    df["units_sold"] = pd.to_numeric(df["units_sold"], errors="coerce").fillna(0).astype(int)

    # Build the categories list from the FULL business dataset (not filtered),
    # so the filter dropdown shows every category even after one is selected.
    try:
        cat_q = (
            supabase.table("pos_records")
            .select("product_category")
            .eq("business_id", business_id)
            .execute()
        )
        all_categories = sorted({
            r["product_category"] for r in (cat_q.data or [])
            if r.get("product_category")
        })
    except Exception:
        all_categories = sorted(df["product_category"].dropna().unique().tolist())

    # ── Top-line metrics ────────────────────────────────────────────────────
    total_revenue = float(df["revenue"].sum())
    total_orders = int(df["transaction_count"].sum())
    total_units = int(df["units_sold"].sum())
    aov = round(total_revenue / total_orders, 2) if total_orders > 0 else 0.0

    date_min = df["date"].min().date()
    date_max = df["date"].max().date()
    days_span = (date_max - date_min).days + 1
    avg_daily_rev = round(total_revenue / days_span, 2) if days_span > 0 else 0.0

    # Best-selling product. Prefer named items; fall back to category.
    best_item: str | None = None
    best_item_rev = 0.0
    if "product_name" in df.columns:
        named = df.dropna(subset=["product_name"])
        named = named[named["product_name"].astype(str).str.strip() != ""]
        if not named.empty:
            top = named.groupby("product_name")["revenue"].sum().sort_values(ascending=False)
            if len(top) > 0:
                best_item = str(top.index[0])
                best_item_rev = float(top.iloc[0])
    if not best_item:
        cat_top = df.groupby("product_category")["revenue"].sum().sort_values(ascending=False)
        if len(cat_top) > 0:
            best_item = str(cat_top.index[0])
            best_item_rev = float(cat_top.iloc[0])

    # ── Daily revenue series ────────────────────────────────────────────────
    daily = (
        df.groupby(df["date"].dt.date)
        .agg(revenue=("revenue", "sum"), orders=("transaction_count", "sum"))
        .reset_index()
    )
    # Reindex to a complete date axis so gaps are visible (rev=0).
    full_index = pd.date_range(date_min, date_max, freq="D").date
    daily = (
        daily.set_index("date")
        .reindex(full_index, fill_value=0)
        .reset_index()
        .rename(columns={"index": "date"})
    )
    daily["date"] = pd.to_datetime(daily["date"]).dt.strftime("%Y-%m-%d")
    daily_revenue = daily.to_dict("records")

    # ── Weekly revenue + week-over-week growth ──────────────────────────────
    df["week_start"] = df["date"].dt.to_period("W-SUN").apply(lambda p: p.start_time.date())
    weekly = (
        df.groupby("week_start")
        .agg(revenue=("revenue", "sum"), orders=("transaction_count", "sum"))
        .reset_index()
        .sort_values("week_start")
    )
    weekly_records: list[dict] = []
    prev_rev: float | None = None
    for _, row in weekly.iterrows():
        ws = row["week_start"]
        rev = float(row["revenue"])
        growth = None
        if prev_rev is not None and prev_rev > 0:
            growth = round(((rev - prev_rev) / prev_rev) * 100, 1)
        weekly_records.append({
            "week_start": ws.isoformat(),
            "label": f"W{(ws.day - 1) // 7 + 1}{ws.strftime('%b')}",
            "revenue": rev,
            "orders": int(row["orders"]),
            "growth_pct": growth,
        })
        prev_rev = rev

    best_week = max(weekly_records, key=lambda w: w["revenue"], default=None)
    worst_week = min(weekly_records, key=lambda w: w["revenue"], default=None)

    # ── Peak Sales Day analysis (day-of-week) ───────────────────────────────
    df["dow_idx"] = df["date"].dt.dayofweek  # 0=Mon
    df["dow_name"] = df["date"].dt.strftime("%a")  # Mon, Tue...
    dow = (
        df.groupby(["dow_idx", "dow_name"])["revenue"]
        .agg(["sum", "count", "mean"])
        .reset_index()
        .sort_values("dow_idx")
    )
    # avg revenue PER DAY-OF-WEEK across the date range (e.g. avg of all Mondays)
    weeks_in_range = max(1, days_span // 7)
    peak_day = []
    for _, r in dow.iterrows():
        peak_day.append({
            "day": r["dow_name"],
            "total_revenue": float(r["sum"]),
            # rough per-occurrence average: total ÷ (occurrences of that DoW in range)
            "avg_revenue": round(float(r["sum"]) / weeks_in_range, 2),
        })

    # ── Revenue by category (donut) ─────────────────────────────────────────
    by_cat = (
        df.groupby("product_category")["revenue"]
        .sum()
        .sort_values(ascending=False)
        .head(8)
    )
    cat_total = float(by_cat.sum()) or 1.0
    revenue_by_category = [
        {"name": name, "revenue": float(rev), "pct": round(float(rev) / cat_total * 100, 1)}
        for name, rev in by_cat.items()
    ]

    return {
        "metrics": {
            "total_revenue": round(total_revenue, 2),
            "total_orders": total_orders,
            "total_units": total_units,
            "avg_order_value": aov,
            "avg_daily_revenue": avg_daily_rev,
            "best_selling_item": best_item,
            "best_selling_revenue": round(best_item_rev, 2),
            "date_range": {
                "from": date_min.isoformat(),
                "to": date_max.isoformat(),
                "days": days_span,
            },
        },
        "daily_revenue": daily_revenue,
        "weekly_revenue": weekly_records,
        "weekly_growth": {"best_week": best_week, "worst_week": worst_week},
        "peak_day_of_week": peak_day,
        "revenue_by_category": revenue_by_category,
        "categories": all_categories,
    }
