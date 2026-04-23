"""
test_pos_pipeline.py — validates ingest_pos_csv() and pos_signals().

Prerequisites (run once if not done yet):
  Apply the DB schema in Supabase SQL Editor (see docs/architecture.md).

Run:
  python test_pos_pipeline.py
"""
import uuid
import sys
import os

from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

from pos_pipeline import ingest_pos_csv, pos_signals

# ── Deterministic test UUIDs ───────────────────────────────────────────────────

_NS = uuid.UUID("00000000-0000-0000-0000-000000000001")

TEST_BUSINESSES = [
    {
        "biz_id": "biz_001",
        "name": "Test Restaurant Healthy",
        "category": "restaurant",
        "place_id": "TEST_PLACE_biz_001",
    },
    {
        "biz_id": "biz_002",
        "name": "Test Restaurant Struggling",
        "category": "restaurant",
        "place_id": "TEST_PLACE_biz_002",
    },
    {
        "biz_id": "biz_003",
        "name": "Test Kirana Store",
        "category": "kirana",
        "place_id": "TEST_PLACE_biz_003",
    },
    {
        "biz_id": "biz_004",
        "name": "Test Retail Shop",
        "category": "retail",
        "place_id": "TEST_PLACE_biz_004",
    },
    {
        "biz_id": "biz_005",
        "name": "Test Cafe",
        "category": "cafe",
        "place_id": "TEST_PLACE_biz_005",
    },
]


def test_uuid(biz_id: str) -> str:
    return str(uuid.uuid5(_NS, biz_id))


# ── Assertion tracking ─────────────────────────────────────────────────────────

_passed = 0
_total = 0


def check(condition: bool, label: str, actual) -> None:
    global _passed, _total
    _total += 1
    if condition:
        _passed += 1
        print(f"  PASS: {label}")
    else:
        print(f"  FAIL: {label} — got {actual!r}")


# ── Step 1: verify CSV files exist ────────────────────────────────────────────

print("\n=== Pre-flight: verifying CSV files ===")
all_csvs_present = True
for b in TEST_BUSINESSES:
    path = os.path.join("data", f"business_{b['biz_id']}_pos.csv")
    if os.path.exists(path):
        print(f"  OK  {path}")
    else:
        print(f"  MISSING  {path}")
        all_csvs_present = False

if not all_csvs_present:
    print("\nERROR: One or more CSV files missing. Run: python generate_synthetic_pos.py")
    sys.exit(1)

# ── Step 2: upsert test businesses into Supabase ──────────────────────────────

print("\n=== Upserting test businesses ===")
rows = [
    {
        "id": test_uuid(b["biz_id"]),
        "name": b["name"],
        "place_id": b["place_id"],
        "category": b["category"],
        "owner_name": "Test Owner",
        "is_active": True,
    }
    for b in TEST_BUSINESSES
]

try:
    resp = supabase.table("businesses").upsert(rows, on_conflict="id").execute()
    print(f"  Upserted {len(resp.data)} business rows")
except Exception as exc:
    print(f"\nERROR: Could not upsert businesses: {exc}")
    print("Make sure the DB schema has been applied (docs/architecture.md).")
    sys.exit(1)

# ── Step 3: ingest CSVs ────────────────────────────────────────────────────────

print("\n=== Ingesting POS CSVs ===")
for b in TEST_BUSINESSES:
    filepath = os.path.join("data", f"business_{b['biz_id']}_pos.csv")
    bid = test_uuid(b["biz_id"])
    try:
        n = ingest_pos_csv(filepath, bid)
        print(f"  Ingested {n:>4} rows for {b['biz_id']} ({b['name']})")
    except Exception as exc:
        print(f"  ERROR ingesting {b['biz_id']}: {exc}")
        sys.exit(1)

# ── Step 4 & 5: compute signals + run assertions ───────────────────────────────

print("\n=== Signal validation ===")

for b in TEST_BUSINESSES:
    bid = test_uuid(b["biz_id"])
    signals = pos_signals(bid)
    print(f"\n{b['biz_id']} — {b['name']}")
    print(f"  signals: {signals}")

    trend = signals["revenue_trend_pct"]
    slow  = signals["slow_categories"]
    top   = signals["top_product"]
    aov   = signals["aov_direction"]

    if b["biz_id"] == "biz_001":
        # 12%/90-day trend → ~4% period-over-period; just confirm direction
        check(trend is not None and trend > 0,
              "Healthy trend detected (positive direction)", trend)
        check(slow == [],
              "No slow categories flagged", slow)
        check(aov in ("rising", "stable"),
              "AOV direction is rising or stable", aov)
        check(top is not None,
              "Top product identified", top)

    elif b["biz_id"] == "biz_002":
        # Mutton Dishes goes slow exactly at the 30-day boundary, amplifying the
        # -18% base trend to ~-20%+ period-over-period — reliably < -10
        check(trend is not None and trend < -10,
              "Declining trend detected (<-10%)", trend)
        check("Mutton Dishes" in slow,
              "Slow category flagged: Mutton Dishes", slow)
        check(top is not None,
              "Top product identified", top)

    elif b["biz_id"] == "biz_003":
        check("Snacks" in slow,
              "Slow category flagged: Snacks", slow)
        check(trend is not None and -8 <= trend <= 8,
              "Flat trend confirmed (-8% to +8%)", trend)
        check(top is not None,
              "Top product identified", top)

    elif b["biz_id"] == "biz_004":
        # +5% base + 25% seasonal spike in last 30 days → ~8-14% period-over-period
        # (Footwear slow, weight 0.15, slightly offsets the spike)
        check(trend is not None and trend > 5,
              "Seasonal spike detected (>5%)", trend)
        check("Footwear" in slow,
              "Slow category flagged: Footwear", slow)

    elif b["biz_id"] == "biz_005":
        check("Cakes" in slow,
              "Slow category flagged: Cakes", slow)
        check(trend is not None,
              "Trend value is not None", trend)

# ── Step 6: null-return guard for unknown business ────────────────────────────

print("\n=== Null-return guard (unknown business_id) ===")
fake_uuid = str(uuid.uuid4())
null_signals = pos_signals(fake_uuid)
expected_null = {
    "revenue_trend_pct": None,
    "slow_categories": [],
    "top_product": None,
    "aov_direction": None,
}
if null_signals == expected_null:
    print(f"  PASS: pos_signals(unknown) returned all-None dict without raising")
else:
    print(f"  FAIL: pos_signals(unknown) returned unexpected: {null_signals!r}")

# ── Step 7: duplicate detection guard ────────────────────────────────────────

print("\n=== Duplicate detection (re-ingest biz_001) ===")
b = TEST_BUSINESSES[0]
filepath = os.path.join("data", f"business_{b['biz_id']}_pos.csv")
bid = test_uuid(b["biz_id"])
n = ingest_pos_csv(filepath, bid)
if n == 0:
    print(f"  PASS: Re-ingesting biz_001 inserted 0 rows (all duplicates skipped)")
else:
    print(f"  WARN: Re-ingesting biz_001 inserted {n} rows — duplicate detection may be incomplete")

# ── Summary ────────────────────────────────────────────────────────────────────

print(f"\n{'='*50}")
print(f"Signal validation: {_passed}/{_total} assertions passed")
if _passed < _total:
    print("\nFailed assertions detected. Check:")
    print("  1. SLOW_THRESHOLD in pos_pipeline.py (currently 0.35)")
    print("  2. slow_categories uses prior period (days 30-60) as baseline")
    print("  3. Revenue-based comparison (not units_sold) for high-price categories")
else:
    print("All assertions passed. POS pipeline is ready.")
print("="*50)
