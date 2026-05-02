"""Three-layer deterministic column matcher for heterogeneous POS uploads.

Indian POS systems (Petpooja, DotPe, BharatPe, Tally, Vyapar, Khatabook,
Shopify, plus hand-built Excel sheets) export sales data with wildly
different column names, date formats, and granularities. This module maps
any incoming DataFrame to the canonical `pos_records` schema using:

    Layer 1: O(1) exact lookup against a normalised synonym dict
    Layer 2: difflib fuzzy match (stdlib only) — auto-registers new aliases
    Layer 3: structural value sniffing (date parse / numeric range / uniqueness)

It also detects whether a file is line-item or daily-aggregated and rolls
line-item rows into the per-day-per-category shape expected by `pos_records`.

No LLM calls. Cost = 0. Latency = milliseconds.

Public surface:
    load_dataframe(source, filename) -> pd.DataFrame
    identify_columns(columns) -> tuple[dict[str, str], dict]
    canonicalise(df, business_id) -> tuple[pd.DataFrame, dict]
    validate(df) -> tuple[pd.DataFrame, pd.DataFrame]
"""
from __future__ import annotations

import io
import json
import logging
import re
from difflib import get_close_matches
from typing import IO, Union

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────

CANONICAL_FIELDS = (
    "date",
    "product_category",
    "invoice_id",
    "units_sold",
    "revenue",
    "customer_identifier",
    "payment_method",
    # Pre-aggregated daily summaries — present in synthetic CSVs and in
    # already-rolled-up shopkeeper Excel files. Preserved verbatim through
    # canonicalisation so the existing pipeline can use them.
    "transaction_count",
    "avg_order_value",
    "unique_customers",
    "returning_customers",
)

# Synonym lists — order matters for `revenue` (line-totals first, unit-prices last).
# Cover at least 8 aliases per field across Petpooja / DotPe / Tally / Vyapar /
# Khatabook / Shopify / WooCommerce / hand-built Excel.
SYNONYMS: dict[str, list[str]] = {
    "date": [
        "date", "order_date", "orderDate", "bill_date", "billDate",
        "invoice_date", "invoiceDate", "txn_date", "transaction_date",
        "transactionDate", "sale_date", "saleDate", "created_at",
        "createdAt", "Created At", "Order Date", "Bill Date", "Invoice Date",
        "Tarikh", "tarikh", "Sales Date", "Posting Date", "Voucher Date",
        "Day", "Date of Sale",
    ],
    "product_category": [
        "product_category", "productCategory", "category", "Category",
        "item_category", "itemCategory", "Item Category", "category_name",
        "categoryName", "CATEGORY_NM", "menu_category", "menuCategory",
        "Menu Category", "department", "Department", "section", "Section",
        "group", "Group", "product_type", "productType", "item_type",
        "itemType", "Item Group", "Stock Group", "vibhag",
    ],
    "invoice_id": [
        "invoice_id", "invoiceId", "Invoice ID", "Invoice No", "invoice_no",
        "invoiceNo", "invoice_number", "invoiceNumber", "bill_no",
        "billNo", "Bill No", "bill_number", "billNumber", "Bill Number",
        "order_id", "orderId", "Order ID", "order_no", "orderNo",
        "Order No", "txn_id", "transaction_id", "transactionId",
        "receipt_no", "receiptNo", "Receipt No", "voucher_no",
        "voucherNo", "Voucher No", "kot_no", "KOT No",
    ],
    "units_sold": [
        # Units / qty across systems. Plain "units" is a common Excel header.
        "units_sold", "unitsSold", "Units Sold", "units", "Units",
        "quantity", "Quantity", "qty", "Qty", "QTY", "qty_sold",
        "qtySold", "Qty Sold", "Quantity Sold", "item_qty", "itemQty",
        "Item Qty", "no_of_units", "noOfUnits", "Units Count",
        "count", "Count", "pieces", "Pieces", "pcs", "Pcs", "PCS",
        "matra", "sankhya",
    ],
    # IMPORTANT: line-totals first (preferred), unit-prices last.
    # The matcher and value-sniffer respect this order on conflict.
    "revenue": [
        # Line totals (preferred — qty × price, post-tax or net)
        "revenue", "Revenue", "total", "Total", "line_total", "lineTotal",
        "Line Total", "net_amount", "netAmount", "Net Amount", "net_total",
        "netTotal", "Net Total", "amount", "Amount", "amt", "Amt",
        "gross_amount", "grossAmount", "Gross Amount", "grand_total",
        "grandTotal", "Grand Total", "final_amount", "finalAmount",
        "Final Amount", "total_amount", "totalAmount", "Total Amount",
        "bill_amount", "billAmount", "Bill Amount", "invoice_total",
        "invoiceTotal", "Invoice Total", "sale_amount", "saleAmount",
        "Sale Amount", "sales_value", "Sales Value", "value", "Value",
        "kul_rakam", "rakam",
        # Unit prices (last-resort — only used if no line-total column exists)
        "unit_price", "unitPrice", "Unit Price", "price", "Price",
        "rate", "Rate", "mrp", "MRP", "selling_price", "sellingPrice",
        "Selling Price",
    ],
    "customer_identifier": [
        "customer_identifier", "customerIdentifier", "customer_id",
        "customerId", "Customer ID", "customer", "Customer",
        "customer_name", "customerName", "Customer Name", "phone",
        "Phone", "mobile", "Mobile", "mobile_no", "mobileNo",
        "Mobile No", "phone_no", "phoneNo", "Phone No", "contact",
        "Contact", "contact_no", "contactNo", "Contact No", "cust_phone",
        "custPhone", "cust_id", "custId", "guest_phone",
    ],
    "payment_method": [
        "payment_method", "paymentMethod", "Payment Method",
        "payment_mode", "paymentMode", "Payment Mode", "mode_of_payment",
        "Mode of Payment", "pay_mode", "payMode", "tender", "Tender",
        "tender_type", "tenderType", "Tender Type", "payment_type",
        "paymentType", "Payment Type", "payment", "Payment", "method",
        "Method", "transaction_type",
    ],
    # Pre-aggregated columns — recognised so they pass through verbatim
    # rather than landing in the unmapped bucket.
    "transaction_count": [
        "transaction_count", "transactionCount", "Transaction Count",
        "txn_count", "txnCount", "Txn Count", "bill_count", "billCount",
        "Bill Count", "invoice_count", "invoiceCount", "Invoice Count",
        "no_of_invoices", "no_of_bills", "orders", "Orders", "order_count",
    ],
    "avg_order_value": [
        "avg_order_value", "avgOrderValue", "Avg Order Value", "average_order_value",
        "Average Order Value", "aov", "AOV", "avg_bill_value", "avgBillValue",
        "Avg Bill Value", "average_bill", "Average Bill", "avg_ticket",
        "Avg Ticket", "average_ticket_size",
    ],
    "unique_customers": [
        "unique_customers", "uniqueCustomers", "Unique Customers",
        "distinct_customers", "Distinct Customers", "customer_count",
        "customerCount", "Customer Count", "no_of_customers",
        "footfall", "Footfall", "covers", "Covers",
    ],
    "returning_customers": [
        "returning_customers", "returningCustomers", "Returning Customers",
        "repeat_customers", "Repeat Customers", "repeat_count",
        "repeatCount", "Repeat Count", "loyal_customers",
    ],
}

# Normalised customer placeholder strings → treated as null.
# Includes common Indian default phone numbers and POS placeholders.
CUSTOMER_PLACEHOLDERS = {
    "", "na", "none", "null", "nil", "0", "00", "000",
    "9999999999", "0000000000", "1111111111", "1234567890",
    "notavailable", "notapplicable", "anonymous", "guest",
    "walkin", "walkincustomer", "cashcustomer", "cash", "test",
}

# Common Indian date formats — tried in order before falling back to dayfirst=True.
DATE_FORMATS = (
    "%Y-%m-%d",
    "%d-%m-%Y",
    "%d/%m/%Y",
    "%d-%m-%y",
    "%d/%m/%y",
    "%d %b %Y",
    "%d-%b-%Y",
    "%Y/%m/%d",
    "%m/%d/%Y",  # only matched if dayfirst attempt fails
)

# Layer 2 fuzzy match tightness. 0.82 catches typos & abbreviations
# (Quanity, Qty., CATEGORY_NM) without matching unrelated columns.
FUZZY_THRESHOLD = 0.82

# Layer 3 sample size — header-less columns we sniff by value.
SNIFF_SAMPLE_SIZE = 50

# Plausible per-row revenue range (INR). Filters out integer product-ID columns.
REVENUE_MIN = 1.0
REVENUE_MAX = 5_000_000.0
# Fraction of revenue values that must contain a decimal portion to qualify.
# Distinguishes a money column from an int-id column.
REVENUE_DECIMAL_FRACTION = 0.30

# Type-coercion thresholds for value sniffing.
DATE_PARSE_THRESHOLD = 0.80
NUMERIC_PARSE_THRESHOLD = 0.90
INVOICE_UNIQUENESS_THRESHOLD = 0.50
INVOICE_LEN_MIN = 4
INVOICE_LEN_MAX = 40

# Granularity heuristic: if unique invoices < total rows * threshold, line-item.
LINE_ITEM_RATIO_THRESHOLD = 0.95

# ── Module-load: precompute Layer 1 lookup ───────────────────────────────────


def _normalise(name: str) -> str:
    """Strip non-alphanumeric chars and lowercase. Order-preserving across calls."""
    return re.sub(r"[^a-z0-9]+", "", str(name).lower())


# Layer 1 lookup: normalised_synonym → canonical field name.
# Iteration order preserves the SYNONYMS list order (Python 3.7+),
# so the first canonical field that claims a normalised key wins —
# matching our line-totals-before-unit-prices preference.
_LAYER1_LOOKUP: dict[str, str] = {}
# Synonym priority within a canonical field — lower = higher priority.
# Used at conflict resolution time: when two raw columns both map to the
# same canonical field (e.g. "Total" and "Unit Price" both → revenue),
# we keep the one whose synonym appears earlier in SYNONYMS[canonical].
_SYNONYM_PRIORITY: dict[str, int] = {}
for _canonical, _aliases in SYNONYMS.items():
    for _idx, _alias in enumerate(_aliases):
        _key = _normalise(_alias)
        if not _key:
            continue
        if _key not in _LAYER1_LOOKUP:
            _LAYER1_LOOKUP[_key] = _canonical
        # Record best (lowest) priority seen across all canonical fields.
        if _key not in _SYNONYM_PRIORITY or _idx < _SYNONYM_PRIORITY[_key]:
            _SYNONYM_PRIORITY[_key] = _idx


def _register_alias(alias: str, canonical: str) -> None:
    """Auto-register a fuzzy-matched alias into the Layer 1 dict for next time."""
    key = _normalise(alias)
    if key and key not in _LAYER1_LOOKUP:
        _LAYER1_LOOKUP[key] = canonical
        logger.info("auto-registered alias '%s' → %s", alias, canonical)


# ── File loader ──────────────────────────────────────────────────────────────


SourceLike = Union[str, bytes, IO[bytes]]


def load_dataframe(source: SourceLike, filename: str) -> pd.DataFrame:
    """Load a POS file into a raw DataFrame. CSV / XLSX / JSON.

    `source` may be a path string, raw bytes (FastAPI `await file.read()`),
    or a file-like object. `filename` is required so we can pick the parser
    when bytes are passed.
    """
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if isinstance(source, (bytes, bytearray)):
        buf: IO[bytes] = io.BytesIO(source)
    elif isinstance(source, str):
        buf = open(source, "rb")
    else:
        buf = source

    try:
        if ext == "csv":
            data = buf.read()
            if not isinstance(data, bytes):
                data = data.encode("utf-8")
            text = data.decode("utf-8-sig", errors="replace")
            # Sniff delimiter from the first non-empty line.
            sample = next((ln for ln in text.splitlines() if ln.strip()), "")
            delim = ","
            if sample:
                counts = {d: sample.count(d) for d in (",", ";", "\t", "|")}
                delim = max(counts, key=counts.get) if max(counts.values()) > 0 else ","
            return pd.read_csv(io.StringIO(text), sep=delim)
        if ext in ("xlsx", "xls"):
            return pd.read_excel(buf)
        if ext == "json":
            data = buf.read()
            if isinstance(data, bytes):
                data = data.decode("utf-8-sig", errors="replace")
            payload = json.loads(data)
            if isinstance(payload, dict):
                # Common wrappers: {"data": [...]} or {"records": [...]}
                for key in ("data", "records", "rows", "items"):
                    if key in payload and isinstance(payload[key], list):
                        payload = payload[key]
                        break
            return pd.DataFrame(payload)
        raise ValueError(
            f"Unsupported file type '{ext}'. Supported: csv, xlsx, xls, json."
        )
    finally:
        if isinstance(source, str):
            buf.close()


# ── Layer 1 + 2 + 3 column matcher ───────────────────────────────────────────


def _layer1_match(col: str, claimed: set[str]) -> str | None:
    """Exact match against the precomputed normalised synonym lookup."""
    canonical = _LAYER1_LOOKUP.get(_normalise(col))
    if canonical and canonical not in claimed:
        return canonical
    return None


def _layer2_match(
    col: str, claimed: set[str]
) -> tuple[str, float] | None:
    """difflib fuzzy match against all known synonyms."""
    norm = _normalise(col)
    if not norm:
        return None
    candidates = list(_LAYER1_LOOKUP.keys())
    matches = get_close_matches(norm, candidates, n=1, cutoff=FUZZY_THRESHOLD)
    if not matches:
        return None
    canonical = _LAYER1_LOOKUP[matches[0]]
    if canonical in claimed:
        return None
    # Approximate similarity from difflib (ratio is implicit in the cutoff).
    from difflib import SequenceMatcher
    score = SequenceMatcher(None, norm, matches[0]).ratio()
    return canonical, round(score, 3)


def _try_parse_date_series(series: pd.Series) -> float:
    """Return the fraction of values that successfully parse as a date."""
    non_null = series.dropna().astype(str).head(SNIFF_SAMPLE_SIZE)
    if non_null.empty:
        return 0.0
    parsed = pd.to_datetime(non_null, errors="coerce", dayfirst=True)
    return float(parsed.notna().mean())


def _looks_like_revenue(series: pd.Series) -> bool:
    """Numeric, plausible INR range, and at least some decimals (not int IDs)."""
    sample = series.dropna().head(SNIFF_SAMPLE_SIZE)
    if sample.empty:
        return False
    nums = pd.to_numeric(sample, errors="coerce")
    if nums.notna().mean() < NUMERIC_PARSE_THRESHOLD:
        return False
    in_range = ((nums >= REVENUE_MIN) & (nums <= REVENUE_MAX)).mean()
    if in_range < NUMERIC_PARSE_THRESHOLD:
        return False
    # Decimal check — guards against integer product-ID columns.
    has_decimal = ((nums % 1) != 0).mean()
    return bool(has_decimal >= REVENUE_DECIMAL_FRACTION)


def _looks_like_units(series: pd.Series) -> bool:
    """Small positive integers."""
    sample = series.dropna().head(SNIFF_SAMPLE_SIZE)
    if sample.empty:
        return False
    nums = pd.to_numeric(sample, errors="coerce")
    if nums.notna().mean() < NUMERIC_PARSE_THRESHOLD:
        return False
    valid = nums.dropna()
    if valid.empty:
        return False
    int_like = ((valid % 1) == 0).mean()
    in_range = ((valid > 0) & (valid <= 1000)).mean()
    return bool(int_like >= NUMERIC_PARSE_THRESHOLD and in_range >= NUMERIC_PARSE_THRESHOLD)


def _looks_like_invoice_id(series: pd.Series) -> bool:
    """ID-plausible string length, high uniqueness, and not a decimal-float column."""
    sample = series.dropna().astype(str).head(SNIFF_SAMPLE_SIZE)
    if sample.empty:
        return False
    lens = sample.str.len()
    len_ok = ((lens >= INVOICE_LEN_MIN) & (lens <= INVOICE_LEN_MAX)).mean()
    if len_ok < NUMERIC_PARSE_THRESHOLD:
        return False
    uniqueness = sample.nunique() / len(sample)
    if uniqueness < INVOICE_UNIQUENESS_THRESHOLD:
        return False
    # Reject decimal-float columns — invoice IDs are alphanumeric or pure ints,
    # never columns like 118.07 / 295.18 that obviously look like money/AOV.
    nums = pd.to_numeric(sample, errors="coerce")
    numeric_frac = nums.notna().mean()
    if numeric_frac >= NUMERIC_PARSE_THRESHOLD:
        valid = nums.dropna()
        if not valid.empty and ((valid % 1) != 0).mean() >= REVENUE_DECIMAL_FRACTION:
            return False
    return True


def _layer3_match(
    col: str, series: pd.Series, claimed: set[str]
) -> str | None:
    """Value-sniffing in a fixed priority order: date → invoice_id → revenue → units."""
    if "date" not in claimed and _try_parse_date_series(series) >= DATE_PARSE_THRESHOLD:
        return "date"
    if "invoice_id" not in claimed and _looks_like_invoice_id(series):
        return "invoice_id"
    if "revenue" not in claimed and _looks_like_revenue(series):
        return "revenue"
    if "units_sold" not in claimed and _looks_like_units(series):
        return "units_sold"
    return None


def identify_columns(df: pd.DataFrame) -> tuple[dict[str, str], dict]:
    """Map raw → canonical column names. Returns (mapping, diagnostic).

    `mapping` keys are raw column names; values are canonical field names.
    `diagnostic` records which layer matched each column (or unmapped).
    """
    mapping: dict[str, str] = {}
    claimed: set[str] = set()
    diag: dict = {"layer1": [], "layer2": [], "layer3": [], "unmapped": []}

    # Pass 1 — Layer 1 (exact). Two-step so synonym-list order wins on conflict.
    # Step 1a: collect every (raw_col, canonical, priority) candidate.
    l1_candidates: list[tuple[str, str, int]] = []
    for col in df.columns:
        norm = _normalise(col)
        canonical = _LAYER1_LOOKUP.get(norm)
        if canonical:
            l1_candidates.append((col, canonical, _SYNONYM_PRIORITY.get(norm, 999)))
    # Step 1b: resolve per canonical field — keep the candidate with lowest priority.
    by_canonical: dict[str, tuple[str, int]] = {}
    for col, canonical, prio in l1_candidates:
        if canonical not in by_canonical or prio < by_canonical[canonical][1]:
            by_canonical[canonical] = (col, prio)
    for canonical, (col, _prio) in by_canonical.items():
        mapping[col] = canonical
        claimed.add(canonical)
        diag["layer1"].append(str(col))

    # Pass 2 — Layer 2 (fuzzy). Skip already-mapped raw columns.
    for col in df.columns:
        if col in mapping:
            continue
        result = _layer2_match(col, claimed)
        if result:
            canonical, score = result
            mapping[col] = canonical
            claimed.add(canonical)
            _register_alias(str(col), canonical)
            diag["layer2"].append(
                {"col": str(col), "mapped_to": canonical, "score": score}
            )

    # Pass 3 — Layer 3 (value-sniffing). Skip already-mapped raw columns.
    for col in df.columns:
        if col in mapping:
            continue
        canonical = _layer3_match(col, df[col], claimed)
        if canonical:
            mapping[col] = canonical
            claimed.add(canonical)
            diag["layer3"].append({"col": str(col), "mapped_to": canonical})

    diag["unmapped"] = [str(c) for c in df.columns if c not in mapping]
    return mapping, diag


# ── Type cleaning ────────────────────────────────────────────────────────────


def _coerce_dates(series: pd.Series) -> pd.Series:
    """Try a sequence of explicit Indian formats, then fall back to dayfirst=True."""
    s = series.astype(str).str.strip()
    out = pd.Series([pd.NaT] * len(s), index=s.index, dtype="datetime64[ns]")
    for fmt in DATE_FORMATS:
        mask = out.isna()
        if not mask.any():
            break
        attempt = pd.to_datetime(s[mask], format=fmt, errors="coerce")
        out.loc[mask] = attempt
    if out.isna().any():
        mask = out.isna()
        attempt = pd.to_datetime(s[mask], errors="coerce", dayfirst=True)
        out.loc[mask] = attempt
    return out


def _clean_customer_ids(series: pd.Series) -> pd.Series:
    """Strip whitespace, lowercase, replace placeholder strings with NaN.

    Coerces to str up front (NaN → 'nan') so the regex lambda never receives
    a float, then re-NaNs the placeholder values via the lookup set.
    """
    s = series.astype(str).str.strip().str.lower()
    norm = s.map(lambda v: re.sub(r"[^a-z0-9]+", "", str(v)))
    # Treat the literal "nan" string from astype(str) as a placeholder too.
    placeholders = CUSTOMER_PLACEHOLDERS | {"nan", "none"}
    return s.where(~norm.isin(placeholders), other=np.nan)


# ── Granularity detection ────────────────────────────────────────────────────


def detect_granularity(df: pd.DataFrame, mapping: dict[str, str]) -> str:
    """Return 'line_item' or 'daily_aggregated'."""
    invoice_col = next(
        (raw for raw, canon in mapping.items() if canon == "invoice_id"), None
    )
    if invoice_col is None or len(df) == 0:
        return "daily_aggregated"
    unique = df[invoice_col].nunique(dropna=True)
    if unique == 0:
        return "daily_aggregated"
    if unique < len(df) * LINE_ITEM_RATIO_THRESHOLD:
        return "line_item"
    return "daily_aggregated"


# ── Aggregation (line-item → per-day-per-category) ───────────────────────────


def _aggregate_line_items(df: pd.DataFrame) -> pd.DataFrame:
    """Roll line-item rows into the per-day-per-category pos_records shape.

    Customer stats (unique / returning) are computed per-day, NOT per-category,
    then joined back onto each (date, category) row.
    """
    has_invoice = "invoice_id" in df.columns
    has_units = "units_sold" in df.columns
    has_customer = "customer_identifier" in df.columns

    # Returning-customer flag is whole-upload scope: appears on >1 distinct date.
    returning_set: set[str] = set()
    if has_customer:
        cust_dates = df.dropna(subset=["customer_identifier", "date"]).groupby(
            "customer_identifier"
        )["date"].nunique()
        returning_set = set(cust_dates[cust_dates > 1].index)

    # Per-(date, category) aggregation.
    grouped = df.groupby(["date", "product_category"], dropna=False)
    agg_dict: dict[str, str] = {"revenue": "sum"}
    if has_units:
        agg_dict["units_sold"] = "sum"
    agg = grouped.agg(agg_dict).reset_index()

    if has_invoice:
        txn = (
            df.dropna(subset=["invoice_id"])
            .groupby(["date", "product_category"])["invoice_id"]
            .nunique()
            .reset_index(name="transaction_count")
        )
        agg = agg.merge(txn, on=["date", "product_category"], how="left")
        agg["transaction_count"] = agg["transaction_count"].fillna(0).astype(int).clip(lower=1)
    else:
        agg["transaction_count"] = 1

    if not has_units:
        agg["units_sold"] = agg["transaction_count"]

    agg["avg_order_value"] = np.where(
        agg["transaction_count"] > 0,
        agg["revenue"] / agg["transaction_count"],
        0.0,
    )

    # Per-day customer rollup (NOT per category).
    if has_customer:
        non_null = df.dropna(subset=["customer_identifier"])
        if not non_null.empty:
            unique_per_day = (
                non_null.groupby("date")["customer_identifier"].nunique()
            )
            returning_rows = non_null[non_null["customer_identifier"].isin(returning_set)]
            if not returning_rows.empty:
                returning_per_day = (
                    returning_rows.groupby("date")["customer_identifier"].nunique()
                )
            else:
                returning_per_day = pd.Series(dtype=int)
            cust_df = pd.DataFrame({
                "date": unique_per_day.index,
                "unique_customers": unique_per_day.values,
            })
            cust_df["returning_customers"] = (
                cust_df["date"].map(returning_per_day).fillna(0).astype(int)
            )
            agg = agg.merge(cust_df, on="date", how="left")
        else:
            agg["unique_customers"] = 0
            agg["returning_customers"] = 0
        agg["unique_customers"] = agg.get("unique_customers", 0)
        agg["returning_customers"] = agg.get("returning_customers", 0)
        agg["unique_customers"] = (
            pd.to_numeric(agg["unique_customers"], errors="coerce").fillna(0).astype(int)
        )
        agg["returning_customers"] = (
            pd.to_numeric(agg["returning_customers"], errors="coerce").fillna(0).astype(int)
        )

    return agg


# ── Top-level canonicalise: raw DataFrame → pos_records-ready DataFrame ──────


def canonicalise(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Map columns, clean types, aggregate if line-item.

    Returns (canonical_df, diagnostic). The diagnostic includes the column
    mapping report, detected granularity, and row counts before/after.
    """
    if df.empty:
        return df.copy(), {
            "layer1": [], "layer2": [], "layer3": [], "unmapped": [],
            "granularity": "daily_aggregated", "rows_in": 0, "rows_out": 0,
        }

    mapping, diag = identify_columns(df)
    granularity = detect_granularity(df, mapping)
    diag["granularity"] = granularity
    diag["rows_in"] = int(len(df))

    # Apply rename — only rename mapped columns, leave the rest untouched.
    renamed = df.rename(columns=mapping).copy()

    # Drop columns we don't care about so downstream agg is clean.
    keep = [c for c in renamed.columns if c in CANONICAL_FIELDS]
    work = renamed[keep].copy()

    if "date" not in work.columns:
        raise ValueError(
            "No date column could be mapped from the upload. "
            f"Unmapped raw columns: {diag['unmapped']}"
        )
    work["date"] = _coerce_dates(work["date"])
    if "revenue" in work.columns:
        work["revenue"] = pd.to_numeric(work["revenue"], errors="coerce").fillna(0.0)
    if "units_sold" in work.columns:
        work["units_sold"] = (
            pd.to_numeric(work["units_sold"], errors="coerce").fillna(0).astype(int)
        )
    if "customer_identifier" in work.columns:
        work["customer_identifier"] = _clean_customer_ids(work["customer_identifier"])

    # Default category if absent.
    if "product_category" not in work.columns:
        work["product_category"] = "Uncategorised"
    else:
        work["product_category"] = (
            work["product_category"].fillna("Uncategorised").astype(str).str.strip()
        )
        work.loc[work["product_category"] == "", "product_category"] = "Uncategorised"

    if granularity == "line_item":
        if "revenue" not in work.columns:
            raise ValueError(
                "Cannot aggregate line-item file without a recognised revenue column."
            )
        out = _aggregate_line_items(work)
    else:
        # Aggregated-style data — could be one row per transaction (with customer
        # column) or already-summed daily totals. If a customer column exists, we
        # still need to roll it up per day-category.
        out = _aggregate_line_items(work) if "customer_identifier" in work.columns \
            else work.copy()
        if "transaction_count" not in out.columns:
            out["transaction_count"] = (
                out["units_sold"] if "units_sold" in out.columns else 1
            )
        out["transaction_count"] = (
            pd.to_numeric(out["transaction_count"], errors="coerce")
            .fillna(1).astype(int).clip(lower=1)
        )
        if "units_sold" not in out.columns:
            out["units_sold"] = out["transaction_count"]
        if "revenue" not in out.columns:
            out["revenue"] = 0.0
        out["avg_order_value"] = np.where(
            out["transaction_count"] > 0,
            out["revenue"] / out["transaction_count"],
            0.0,
        )

    # Output `date` as YYYY-MM-DD strings to match the existing pipeline contract.
    out["date"] = pd.to_datetime(out["date"], errors="coerce").dt.strftime("%Y-%m-%d")

    # Order the output columns to match pos_records. Include any optional
    # pre-aggregated columns (unique_customers / returning_customers) that
    # were either in the source file or computed during line-item aggregation.
    ordered = ["date", "product_category", "units_sold", "revenue",
               "transaction_count", "avg_order_value",
               "unique_customers", "returning_customers"]
    out = out[[c for c in ordered if c in out.columns]]

    diag["rows_out"] = int(len(out))
    logger.info(
        "Column mapping: L1=%d L2=%d L3=%d unmapped=%d  granularity=%s  rows %d→%d",
        len(diag["layer1"]), len(diag["layer2"]), len(diag["layer3"]),
        len(diag["unmapped"]), granularity, diag["rows_in"], diag["rows_out"],
    )
    return out, diag


# ── Validation ───────────────────────────────────────────────────────────────


def validate(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split rows into (clean, rejected). Never raises.

    Reject when: date is null/unparseable OR revenue is negative.
    Warn (do NOT reject) when transaction_count is 0.
    """
    if df.empty:
        return df.copy(), df.copy()

    parsed_date = pd.to_datetime(df["date"], errors="coerce")
    bad_date = parsed_date.isna()
    bad_rev = pd.to_numeric(df.get("revenue", 0), errors="coerce").fillna(0) < 0

    bad_mask = bad_date | bad_rev
    rejected = df[bad_mask].copy()
    clean = df[~bad_mask].copy()

    zero_txn = (pd.to_numeric(clean.get("transaction_count", 1), errors="coerce") == 0).sum()
    if zero_txn:
        logger.warning("validate: %d row(s) have transaction_count=0", int(zero_txn))
    if not rejected.empty:
        logger.warning(
            "validate: rejected %d row(s) — bad_date=%d, neg_revenue=%d",
            len(rejected), int(bad_date.sum()), int(bad_rev.sum()),
        )
    return clean, rejected
