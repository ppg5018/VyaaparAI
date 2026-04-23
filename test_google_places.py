"""
Run this after filling in real Pune Place IDs to verify the pipeline.
Get Place IDs: Google Maps → search a business → share link → copy ChIJ... ID.

Usage:
    python test_google_places.py
"""

from dotenv import load_dotenv
load_dotenv()

from google_places import fetch_all_data

TEST_PLACE_IDS = [
    ("ChIJ_REPLACE_1", "restaurant"),
    ("ChIJ_REPLACE_2", "restaurant"),
    ("ChIJ_REPLACE_3", "retail"),
    ("ChIJ_REPLACE_4", "grocery"),
    ("ChIJ_REPLACE_5", "restaurant"),
]

def run_tests():
    success_count = 0
    total_competitors = 0
    errors = []

    for place_id, category in TEST_PLACE_IDS:
        print(f"\n{'─' * 60}")
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
                print(f"  Top review:  (none returned)")

            n_comp = len(data["competitors"])
            print(f"  Competitors: {n_comp} found")
            for comp in data["competitors"][:3]:
                print(f"    • {comp['name']} — {comp['rating']}★ ({comp['review_count']} reviews)")

            total_competitors += n_comp
            success_count += 1

        except ValueError as e:
            msg = f"[ValueError] {place_id}: {e}"
            print(f"  ERROR: {msg}")
            errors.append(msg)
        except RuntimeError as e:
            msg = f"[RuntimeError] {place_id}: {e}"
            print(f"  ERROR: {msg}")
            errors.append(msg)
        except Exception as e:
            msg = f"[{type(e).__name__}] {place_id}: {e}"
            print(f"  ERROR: {msg}")
            errors.append(msg)

    print(f"\n{'=' * 60}")
    print(f"Successfully fetched: {success_count}/{len(TEST_PLACE_IDS)} businesses")
    print(f"Total competitors found: {total_competitors}")
    if errors:
        print("Errors:")
        for err in errors:
            print(f"  • {err}")
    else:
        print("No errors.")
    print("=" * 60)


if __name__ == "__main__":
    run_tests()
