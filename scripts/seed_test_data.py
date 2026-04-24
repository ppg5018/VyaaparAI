"""
seed_test_data.py — Upload all 5 synthetic POS CSVs to an existing business.

Usage:
    python scripts/seed_test_data.py <business_id> [csv_index]

    business_id  UUID from the businesses table
    csv_index    1-5 (default: 1) — which synthetic CSV to upload

Example:
    python scripts/seed_test_data.py abc123... 1
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.pos_pipeline import ingest_pos_csv
from app.logging_config import setup_logging

setup_logging()


def main() -> None:
    """Insert synthetic POS data for a given business_id."""
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    business_id = sys.argv[1]
    csv_index = int(sys.argv[2]) if len(sys.argv) > 2 else 1

    if not (1 <= csv_index <= 5):
        print(f"ERROR: csv_index must be 1–5, got {csv_index}")
        sys.exit(1)

    csv_path = f"data/business_biz_00{csv_index}_pos.csv"

    if not os.path.exists(csv_path):
        print(f"ERROR: {csv_path} not found. Run: python scripts/generate_synthetic_pos.py")
        sys.exit(1)

    print(f"Seeding {csv_path} → business_id={business_id}")
    rows = ingest_pos_csv(csv_path, business_id)
    print(f"Done — {rows} rows inserted.")


if __name__ == "__main__":
    main()
