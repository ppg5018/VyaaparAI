"""Unit tests for the POS column matcher.

Pure stdlib + pandas — no Supabase, no API calls.
Run: python tests/test_pos_column_matcher.py
"""
import io
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd

from app.services.pos_column_matcher import (
    CANONICAL_FIELDS,
    canonicalise,
    detect_granularity,
    identify_columns,
    load_dataframe,
    validate,
    _normalise,
    _LAYER1_LOOKUP,
)


passed = 0
failed = 0


def check(condition: bool, label: str) -> None:
    global passed, failed
    if condition:
        passed += 1
        print(f"  PASS: {label}")
    else:
        failed += 1
        print(f"  FAIL: {label}")


# ── Layer 1: synthetic CSV is zero-ambiguity ─────────────────────────────────


def test_synthetic_csv_layer1():
    print("\n--- Layer 1: synthetic CSV ---")
    csv_path = "data/business_biz_001_pos.csv"
    if not os.path.exists(csv_path):
        print(f"  SKIP: {csv_path} not generated")
        return
    df = load_dataframe(csv_path, "business_biz_001_pos.csv")
    mapping, diag = identify_columns(df)
    check("date" in mapping.values(), "date matched at L1")
    check("product_category" in mapping.values(), "product_category matched at L1")
    check("revenue" in mapping.values(), "revenue matched at L1")
    check(diag["layer2"] == [], "no L2 fallback needed")
    check(diag["layer3"] == [], "no L3 fallback needed")


# ── Layer 1: Petpooja-style camelCase + spaces ───────────────────────────────


def test_petpooja_aliases():
    print("\n--- Layer 1: Petpooja-style aliases ---")
    df = pd.DataFrame({
        "Order Date": ["2026-01-10"],
        "Item Category": ["Snacks"],
        "Bill No": ["INV001"],
        "Quantity": [3],
        "Net Amount": [299.50],
        "Mobile No": ["9876543210"],
    })
    mapping, diag = identify_columns(df)
    check(mapping["Order Date"] == "date", "Order Date → date")
    check(mapping["Item Category"] == "product_category", "Item Category → product_category")
    check(mapping["Bill No"] == "invoice_id", "Bill No → invoice_id")
    check(mapping["Quantity"] == "units_sold", "Quantity → units_sold")
    check(mapping["Net Amount"] == "revenue", "Net Amount → revenue (line total)")
    check(mapping["Mobile No"] == "customer_identifier", "Mobile No → customer_identifier")
    check(len(diag["layer2"]) == 0, "no fuzzy matches needed")


# ── Layer 1: line-total preferred over unit-price ────────────────────────────


def test_revenue_prefers_line_total():
    print("\n--- Layer 1: line-total over unit-price ---")
    df = pd.DataFrame({
        "date": ["2026-01-10"],
        "category": ["X"],
        "qty": [2],
        "Unit Price": [50.0],
        "Total": [100.0],
    })
    mapping, _ = identify_columns(df)
    revenue_source = next((raw for raw, c in mapping.items() if c == "revenue"), None)
    check(revenue_source == "Total", f"revenue maps to Total, not Unit Price (got: {revenue_source})")


# ── Layer 2: typo gets fuzzy-matched ─────────────────────────────────────────


def test_layer2_typo():
    print("\n--- Layer 2: typo fuzzy match ---")
    df = pd.DataFrame({
        "date": ["2026-01-10"],
        "category": ["X"],
        "Quanity": [2],          # typo — should fuzz to "quantity"
        "Net Amount": [99.0],
    })
    mapping, diag = identify_columns(df)
    check(mapping.get("Quanity") == "units_sold", "Quanity → units_sold via L2")
    check(any(d["col"] == "Quanity" for d in diag["layer2"]), "Quanity logged in L2 diagnostic")
    # Auto-registration check
    check(_normalise("Quanity") in _LAYER1_LOOKUP, "Quanity now registered in L1 dict")


# ── Layer 3: value-sniffing on unrecognised column names ─────────────────────


def test_layer3_value_sniffing():
    print("\n--- Layer 3: value-sniffing ---")
    df = pd.DataFrame({
        "col_a": ["2026-01-01", "2026-01-02", "2026-01-03"] * 20,  # date-like
        "col_b": ["Snacks"] * 60,
        "col_c": [99.50, 120.75, 50.25] * 20,                       # revenue-like (decimals)
        "col_d": [2, 3, 1] * 20,                                    # units-like
    })
    mapping, diag = identify_columns(df)
    check(mapping.get("col_a") == "date", "col_a sniffed as date")
    check(mapping.get("col_c") == "revenue", "col_c sniffed as revenue (has decimals)")
    check(mapping.get("col_d") == "units_sold", "col_d sniffed as units_sold")
    check(len(diag["layer3"]) >= 3, f"L3 diagnostic populated: {len(diag['layer3'])}")


# ── Layer 3: integer ID column does NOT get matched as revenue ───────────────


def test_layer3_int_ids_not_revenue():
    print("\n--- Layer 3: integer IDs not matched as revenue ---")
    df = pd.DataFrame({
        "date": pd.to_datetime(["2026-01-01"] * 50),
        "category": ["X"] * 50,
        "product_id": list(range(1000, 1050)),  # integer IDs — no decimals
        "amount": [199.99] * 50,
    })
    mapping, _ = identify_columns(df)
    check(mapping.get("amount") == "revenue", "decimal column won the revenue slot")
    check(mapping.get("product_id") != "revenue", "integer ID column not labelled revenue")


# ── Granularity detection ────────────────────────────────────────────────────


def test_granularity_line_item():
    print("\n--- Granularity: line-item ---")
    # 6 rows, only 2 distinct invoices = line-item
    df = pd.DataFrame({
        "date": ["2026-01-01"] * 6,
        "category": ["X"] * 3 + ["Y"] * 3,
        "Bill No": ["INV1", "INV1", "INV1", "INV2", "INV2", "INV2"],
        "qty": [1, 2, 1, 1, 1, 2],
        "amount": [100.0, 50.0, 75.0, 200.0, 150.0, 100.0],
    })
    mapping, _ = identify_columns(df)
    g = detect_granularity(df, mapping)
    check(g == "line_item", f"detected line_item (got: {g})")


def test_granularity_aggregated():
    print("\n--- Granularity: daily-aggregated ---")
    # No invoice column → aggregated
    df = pd.DataFrame({
        "date": ["2026-01-01", "2026-01-02"],
        "product_category": ["X", "Y"],
        "units_sold": [10, 20],
        "revenue": [1000.0, 2000.0],
        "transaction_count": [5, 8],
        "avg_order_value": [200.0, 250.0],
    })
    mapping, _ = identify_columns(df)
    g = detect_granularity(df, mapping)
    check(g == "daily_aggregated", f"detected daily_aggregated (got: {g})")


# ── End-to-end: line-item file canonicalises correctly ───────────────────────


def test_e2e_line_item_aggregation():
    print("\n--- E2E: line-item → aggregated ---")
    df = pd.DataFrame({
        "Order Date": ["2026-01-10"] * 4 + ["2026-01-11"] * 2,
        "Item Category": ["Snacks", "Snacks", "Drinks", "Snacks", "Snacks", "Drinks"],
        "Bill No": ["B1", "B1", "B1", "B2", "B3", "B3"],
        "Quantity": [2, 1, 1, 3, 1, 2],
        "Net Amount": [40.0, 30.0, 50.0, 120.0, 25.0, 100.0],
        "Mobile No": ["9876543210", "9876543210", "9876543210",
                      "9000000001", "9876543210", "9876543210"],
    })
    out, diag = canonicalise(df)
    check(diag["granularity"] == "line_item", "detected as line-item")
    # 4 distinct (date, category) groups: (Jan10,Snacks), (Jan10,Drinks),
    # (Jan11,Snacks), (Jan11,Drinks).
    check(len(out) == 4, f"4 daily-category rows (got {len(out)})")
    snacks_10 = out[(out["date"] == "2026-01-10") & (out["product_category"] == "Snacks")]
    check(not snacks_10.empty, "Jan 10 / Snacks row exists")
    if not snacks_10.empty:
        row = snacks_10.iloc[0]
        check(row["units_sold"] == 6, f"units_sold summed to 6 (got {row['units_sold']})")
        check(abs(row["revenue"] - 190.0) < 0.01, f"revenue summed to 190 (got {row['revenue']})")
        check(row["transaction_count"] == 2, f"2 distinct invoices (got {row['transaction_count']})")
        check(abs(row["avg_order_value"] - 95.0) < 0.01, "AOV = 190/2 = 95")
    # Customer 9876543210 appears on both Jan 10 and Jan 11 → returning
    check("unique_customers" in out.columns, "unique_customers column present")
    check("returning_customers" in out.columns, "returning_customers column present")
    jan11 = out[out["date"] == "2026-01-11"].iloc[0]
    check(jan11["returning_customers"] >= 1, "9876543210 counted as returning on Jan 11")


# ── Customer placeholder cleaning ────────────────────────────────────────────


def test_customer_with_nan_values():
    """Regression: real customer CSVs often have NaN in the phone column —
    re.sub on a float NaN crashed _clean_customer_ids."""
    print("\n--- Customer column with NaN values ---")
    df = pd.DataFrame({
        "date": ["2026-01-01"] * 4,
        "category": ["X"] * 4,
        "Bill No": ["B1", "B2", "B3", "B4"],
        "qty": [1, 1, 1, 1],
        "amount": [10.0, 10.0, 10.0, 10.0],
        # Mixed: real phone, NaN, None, real phone
        "Phone": ["9876543210", float("nan"), None, "9000000001"],
    })
    try:
        out, _ = canonicalise(df)
        check(True, "canonicalise survives NaN/None in customer column")
        check(out.iloc[0]["unique_customers"] == 2,
              f"two real phones counted (got {out.iloc[0]['unique_customers']})")
    except Exception as e:
        check(False, f"crashed on NaN customer: {type(e).__name__}: {e}")


def test_customer_placeholder_cleaning():
    print("\n--- Customer placeholder cleaning ---")
    df = pd.DataFrame({
        "date": ["2026-01-01"] * 5,
        "category": ["X"] * 5,
        "Bill No": ["B1", "B2", "B3", "B4", "B5"],
        "qty": [1] * 5,
        "amount": [10.0] * 5,
        "Mobile No": ["9876543210", "9999999999", "N/A", "Walk-in", "0"],
    })
    out, _ = canonicalise(df)
    # Only 1 of 5 customer IDs is real → unique_customers should be 1
    check(out.iloc[0]["unique_customers"] == 1,
          f"placeholder phones cleaned (unique_customers={out.iloc[0]['unique_customers']})")


# ── Validation: split clean / rejected ───────────────────────────────────────


def test_validate_splits_rows():
    print("\n--- Validate: clean / rejected split ---")
    df = pd.DataFrame({
        "date": ["2026-01-01", "not-a-date", "2026-01-03"],
        "product_category": ["A", "B", "C"],
        "units_sold": [1, 1, 1],
        "revenue": [100.0, 50.0, -10.0],   # row 3 negative
        "transaction_count": [1, 1, 1],
        "avg_order_value": [100.0, 50.0, -10.0],
    })
    clean, rejected = validate(df)
    check(len(clean) == 1, f"1 clean row (got {len(clean)})")
    check(len(rejected) == 2, f"2 rejected rows (got {len(rejected)})")


# ── Loader: bytes path (FastAPI scenario) ────────────────────────────────────


def test_load_from_bytes():
    print("\n--- Loader: from bytes (FastAPI) ---")
    csv_text = b"date,category,qty,amount\n2026-01-01,X,2,99.50\n"
    df = load_dataframe(csv_text, "upload.csv")
    check(len(df) == 1, "1 row loaded from bytes")
    check("date" in df.columns, "date column preserved")


# ── Loader: semicolon delimiter sniffing ─────────────────────────────────────


def test_load_semicolon_delimiter():
    print("\n--- Loader: delimiter sniffing ---")
    csv_text = b"date;category;qty;amount\n2026-01-01;X;2;99.50\n"
    df = load_dataframe(csv_text, "upload.csv")
    check(len(df.columns) == 4, f"semicolon delimiter detected (got {len(df.columns)} cols)")


# ── End-to-end: synthetic CSV passes through unchanged ───────────────────────


def test_synthetic_csv_e2e():
    print("\n--- E2E: synthetic CSV passes through ---")
    csv_path = "data/business_biz_001_pos.csv"
    if not os.path.exists(csv_path):
        print(f"  SKIP: {csv_path} not generated")
        return
    df = load_dataframe(csv_path, "business_biz_001_pos.csv")
    rows_in = len(df)
    out, diag = canonicalise(df)
    check(diag["granularity"] == "daily_aggregated", "synthetic detected as daily-aggregated")
    check(len(out) == rows_in, f"row count preserved ({rows_in} → {len(out)})")
    required = ["date", "product_category", "units_sold", "revenue",
                "transaction_count", "avg_order_value"]
    for col in required:
        check(col in out.columns, f"output has '{col}' column")


def main():
    test_synthetic_csv_layer1()
    test_petpooja_aliases()
    test_revenue_prefers_line_total()
    test_layer2_typo()
    test_layer3_value_sniffing()
    test_layer3_int_ids_not_revenue()
    test_granularity_line_item()
    test_granularity_aggregated()
    test_e2e_line_item_aggregation()
    test_customer_with_nan_values()
    test_customer_placeholder_cleaning()
    test_validate_splits_rows()
    test_load_from_bytes()
    test_load_semicolon_delimiter()
    test_synthetic_csv_e2e()

    print(f"\n{'='*50}")
    print(f"Total: {passed + failed}  |  Passed: {passed}  |  Failed: {failed}")
    print("=" * 50)
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
