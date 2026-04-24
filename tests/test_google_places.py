"""
test_google_places.py — end-to-end test for the google_places service.

PRE-REQUISITE: Enable "Places API" (legacy) in GCP console.
  console.cloud.google.com → APIs & Services → Library → "Places API"

Run: python tests/test_google_places.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.google_places import fetch_all_data

TEST_PLACE_IDS = [
    ("ChIJrTLr-GyuEmsRBfy61i59si0", "cafe"),        # Starbucks (baseline)
    ("ChIJVXealLUWrjsRja_At0z9AGY", "restaurant"),  # Toit Brewpub, Indiranagar
    ("ChIJb1uQz2oUrjsRZ7pQ7FqR7Y4", "restaurant"),  # Truffles, Koramangala
    ("ChIJR8l4xqYUrjsR9dQXnVt9cNc", "cafe"),        # Brahmin's Coffee Bar, Basavanagudi
    ("ChIJh8P6z5sUrjsR0s7iQn7y1nA", "restaurant"),  # Vidyarthi Bhavan, Gandhi Bazaar
]


def run_tests() -> None:
    """Fetch data for all test places and report success/failure."""
    success_count = 0
    total_competitors = 0
    errors = []

    for place_id, category in TEST_PLACE_IDS:
        print(f"\n{'-' * 60}")
        print(f"Testing: {place_id}  [{category}]")

        try:
            data = fetch_all_data(place_id, category)

            print(f"  Name:        {data['name']}")
            print(f"  Rating:      {data['rating']} ({data['total_reviews']} reviews)")
            print(f"  Status:      {data['business_status']}")
            print(f"  Address:     {data['address']}")

            if data["reviews"]:
                snippet = data["reviews"][0]["text"][:100]
                print(f"  Top review:  \"{snippet}\"")
            else:
                print("  Top review:  (none returned)")

            n_comp = len(data["competitors"])
            print(f"  Competitors: {n_comp} found")
            for comp in data["competitors"][:3]:
                print(f"    • {comp['name']} — {comp['rating']}★ ({comp['review_count']} reviews)")

            total_competitors += n_comp
            success_count += 1

        except ValueError as exc:
            msg = f"[ValueError] {place_id}: {exc}"
            print(f"  ERROR: {msg}")
            errors.append(msg)
        except RuntimeError as exc:
            msg = f"[RuntimeError] {place_id}: {exc}"
            print(f"  ERROR: {msg}")
            errors.append(msg)
        except Exception as exc:
            msg = f"[{type(exc).__name__}] {place_id}: {exc}"
            print(f"  ERROR: {msg}")
            errors.append(msg)

    print(f"\n{'=' * 60}", flush=True)
    print(f"Successfully fetched: {success_count}/{len(TEST_PLACE_IDS)} businesses")
    print(f"Total competitors found: {total_competitors}")
    if errors:
        print("Errors:")
        for err in errors:
            print(f"  • {err}")
    else:
        print("No errors.")
    print("=" * 60, flush=True)


if __name__ == "__main__":
    run_tests()
