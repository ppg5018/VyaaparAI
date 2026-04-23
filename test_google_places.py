"""
Resolves Pune businesses by name via Text Search, then runs the full pipeline.
No hardcoded Place IDs — avoids stale ID issues.

Usage:
    python test_google_places.py
"""

import os
import requests
from dotenv import load_dotenv
load_dotenv()

from google_places import fetch_all_data

_BASE_URL = "https://places.googleapis.com/v1"

TEST_BUSINESSES = [
    ("Vaishali Restaurant Pune FC Road",     "restaurant"),  # iconic Pune restaurant
    ("Vohuman Cafe Pune",                    "cafe"),        # iconic Irani cafe
    ("Chitale Bandhu Mithaiwale Pune",       "retail"),      # iconic sweet & snack shop
    ("Dorabjee's Grocery Store Pune Camp",   "grocery"),     # heritage grocery store
    ("Roopali Hotel Deccan Pune",            "restaurant"),  # legendary local eatery
]


def resolve_place_id(query: str) -> str | None:
    """Use Text Search to get a fresh Place ID for a business name."""
    resp = requests.post(
        f"{_BASE_URL}/places:searchText",
        headers={
            "X-Goog-Api-Key": os.getenv("GOOGLE_PLACES_API_KEY"),
            "X-Goog-FieldMask": "places.id,places.displayName",
            "Content-Type": "application/json",
        },
        json={"textQuery": query},
        timeout=10,
    )
    if resp.status_code != 200:
        print(f"  Text Search failed ({resp.status_code}): {resp.text[:200]}")
        return None
    places = resp.json().get("places", [])
    if not places:
        return None
    return places[0]["id"]


def run_tests():
    success_count = 0
    total_competitors = 0
    errors = []

    for query, category in TEST_BUSINESSES:
        print(f"\n{'─' * 60}")
        print(f"Resolving: {query}  [{category}]")

        place_id = resolve_place_id(query)
        if not place_id:
            msg = f"No Place ID found for '{query}'"
            print(f"  ERROR: {msg}")
            errors.append(msg)
            continue

        print(f"  Place ID: {place_id}")

        try:
            data = fetch_all_data(place_id, category)

            print(f"  Name:        {data['name']}")
            print(f"  Rating:      {data['rating']} ({data['total_reviews']} reviews)")
            print(f"  Status:      {data['business_status']}")
            print(f"  Address:     {data['address']}")

            if data["reviews"]:
                print(f"  Reviews ({len(data['reviews'])}):")
                for i, rev in enumerate(data["reviews"], 1):
                    snippet = rev["text"][:120] or "(no text)"
                    print(f"    {i}. {rev['rating']}★ [{rev['relative_time']}] \"{snippet}\"")
            else:
                print(f"  Reviews: (none returned)")

            n_comp = len(data["competitors"])
            print(f"  Competitors ({n_comp} found, showing top 3):")
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

    print(f"\n{'=' * 60}", flush=True)
    print(f"Successfully fetched: {success_count}/{len(TEST_BUSINESSES)} businesses")
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
