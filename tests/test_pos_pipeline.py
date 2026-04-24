"""
test_pos_pipeline.py — end-to-end test for the POS pipeline service.

Requires: Supabase connection and a business with uploaded POS data.
Run: python tests/test_pos_pipeline.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.pos_pipeline import ingest_pos_csv, pos_signals
from app.database import supabase


def run_tests() -> None:
    """Validate ingest_pos_csv and pos_signals against Supabase."""
    passed = 0
    failed = 0

    def check(condition: bool, label: str) -> None:
        nonlocal passed, failed
        if condition:
            passed += 1
            print(f"  PASS: {label}")
        else:
            failed += 1
            print(f"  FAIL: {label}")

    # Look up an existing business_id from the businesses table
    result = supabase.table("businesses").select("id, name").limit(1).execute()
    if not result.data:
        print("ERROR: No businesses found in Supabase. Run /onboard first.")
        sys.exit(1)

    biz = result.data[0]
    business_id = biz["id"]
    print(f"\nTesting with business: {biz['name']} ({business_id})")

    # Test pos_signals (reads from pos_records — never raises)
    print("\n--- pos_signals() ---")
    signals = pos_signals(business_id, days=30)
    check(isinstance(signals, dict), "Returns a dict")
    check("revenue_trend_pct" in signals, "Has revenue_trend_pct key")
    check("slow_categories" in signals, "Has slow_categories key")
    check("top_product" in signals, "Has top_product key")
    check("aov_direction" in signals, "Has aov_direction key")
    check(isinstance(signals["slow_categories"], list), "slow_categories is a list")

    if signals["revenue_trend_pct"] is not None:
        check(isinstance(signals["revenue_trend_pct"], float), "revenue_trend_pct is a float")
    if signals["aov_direction"] is not None:
        check(
            signals["aov_direction"] in ("rising", "stable", "falling"),
            f"aov_direction is valid: {signals['aov_direction']}",
        )

    print(f"\nSignals: {signals}")

    # Test CSV validation errors (no Supabase write needed)
    print("\n--- ingest_pos_csv() validation ---")
    import tempfile, os
    with tempfile.NamedTemporaryFile(suffix=".csv", mode="w", delete=False) as f:
        f.write("wrong_col,bad_col\n1,2\n")
        bad_path = f.name

    try:
        try:
            ingest_pos_csv(bad_path, business_id)
            check(False, "Should raise ValueError for missing columns")
        except ValueError:
            check(True, "Raises ValueError for missing columns")
    finally:
        os.unlink(bad_path)

    print(f"\n{'='*50}")
    print(f"Total: {passed + failed}  |  Passed: {passed}  |  Failed: {failed}")
    print("="*50)


if __name__ == "__main__":
    run_tests()
