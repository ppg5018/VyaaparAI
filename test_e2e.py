"""
End-to-end acceptance test for VyaparAI Module 1.

PRE-REQUISITES before running:
  1. Enable "Places API" (legacy) in GCP console for your GOOGLE_PLACES_API_KEY project.
     Go to: console.cloud.google.com → APIs & Services → Library → search "Places API"
     Enable the one called simply "Places API" (NOT "Places API (New)").

  2. Fill in the 5 real Pune Place IDs below.
     How to get a Place ID: open Google Maps → search the business → click Share
     → copy the link. The ID looks like ChIJ... in the URL. Or use:
     https://developers.google.com/maps/documentation/places/web-service/place-id

  3. Start the server:
     source venv/bin/activate   (or venv\\Scripts\\activate on Windows)
     uvicorn main:app --reload

  4. Run this test:
     python test_e2e.py

Passes when: 5/5 businesses complete all 6 steps without assertion failures.
"""

import sys
import requests

BASE = "http://localhost:8000"

# ── Fill in real Pune Place IDs before running ─────────────────────────────────
# How to find a Place ID:
#   Google Maps → search business → Share → copy link → extract ChIJ... segment.
#   Or: maps.googleapis.com/maps/api/place/findplacefromtext/json?input=...

TEST_BUSINESSES = [
    {
        "name": "Vaishali Restaurant",
        "place_id": "ChIJQ-INPeG_wjsRxqh06SKJIdo",   # FC Road, Pune
        "category": "restaurant",
        "owner_name": "E2E Test Owner 1",
        "pos_csv": "data/business_biz_001_pos.csv",
    },
    {
        "name": "Cafe Goodluck",
        "place_id": "ChIJGasrwJy8wjsRDOdA_5fzBz4",   # Deccan Gymkhana, Pune
        "category": "cafe",
        "owner_name": "E2E Test Owner 2",
        "pos_csv": "data/business_biz_002_pos.csv",
    },
    {
        "name": "Hotel Shreyas",
        "place_id": "ChIJLaTh6M6_wjsRwDw9wNUqg6M",   # Erandwane, Pune
        "category": "restaurant",
        "owner_name": "E2E Test Owner 3",
        "pos_csv": "data/business_biz_003_pos.csv",
    },
    {
        "name": "D-Mart Aundh",
        "place_id": "ChIJByb6dM6-wjsRmKLSZ8lx10c",   # Aundh, Pune
        "category": "grocery",
        "owner_name": "E2E Test Owner 4",
        "pos_csv": "data/business_biz_004_pos.csv",
    },
    {
        "name": "Westside Pune",
        "place_id": "ChIJa3rFVfW_wjsRs1a6oJfYMAI",   # Camp, Pune
        "category": "retail",
        "owner_name": "E2E Test Owner 5",
        "pos_csv": "data/business_biz_005_pos.csv",
    },
]

PLACEHOLDER_WARN = """
WARNING: The Place IDs in TEST_BUSINESSES may be placeholders.
Replace them with real Pune Place IDs before running.
See the instructions at the top of this file.
"""


def check_server():
    try:
        r = requests.get(BASE + "/", timeout=5)
        r.raise_for_status()
        print(f"Server OK — {r.json()['status']}")
    except Exception as exc:
        print(f"ERROR: Cannot reach server at {BASE}")
        print(f"  Start it with: uvicorn main:app --reload")
        print(f"  Detail: {exc}")
        sys.exit(1)


def run_business(biz: dict, idx: int) -> dict:
    name = biz["name"]
    print(f"\n{'─' * 60}")
    print(f"Business {idx+1}/5: {name}")
    print(f"{'─' * 60}")

    result = {
        "name": name,
        "passed": False,
        "final_score": None,
        "band": None,
        "failure": None,
    }

    # ── STEP 1: Onboard ────────────────────────────────────────────────────────
    payload = {
        "name": biz["name"],
        "place_id": biz["place_id"],
        "category": biz["category"],
        "owner_name": biz["owner_name"],
    }
    resp = requests.post(f"{BASE}/onboard", json=payload, timeout=30)

    if resp.status_code == 409:
        # Already onboarded from a previous test run — reuse the existing ID
        business_id = resp.json()["detail"]["business_id"]
        print(f"  [onboard] Already registered — reusing business_id={business_id}")
    elif resp.status_code == 201:
        business_id = resp.json()["business_id"]
        google_name = resp.json()["google_verified_name"]
        print(f"  [onboard] OK — business_id={business_id}  google_name={google_name!r}")
    else:
        result["failure"] = f"onboard returned {resp.status_code}: {resp.text[:200]}"
        print(f"  [onboard] FAIL — {result['failure']}")
        return result

    # ── STEP 2: Upload POS CSV ─────────────────────────────────────────────────
    try:
        with open(biz["pos_csv"], "rb") as f:
            files = {"file": ("pos.csv", f, "text/csv")}
            resp = requests.post(
                f"{BASE}/upload-pos/{business_id}", files=files, timeout=60
            )
    except FileNotFoundError:
        result["failure"] = f"POS CSV not found: {biz['pos_csv']}"
        print(f"  [upload-pos] FAIL — {result['failure']}")
        return result

    if resp.status_code not in (200,):
        result["failure"] = f"upload-pos returned {resp.status_code}: {resp.text[:200]}"
        print(f"  [upload-pos] FAIL — {result['failure']}")
        return result

    rows = resp.json()["rows_inserted"]
    print(f"  [upload-pos] OK — {rows} rows ingested")

    # ── STEP 3: Generate report ────────────────────────────────────────────────
    resp = requests.post(f"{BASE}/generate-report/{business_id}", timeout=120)
    if resp.status_code != 200:
        result["failure"] = f"generate-report returned {resp.status_code}: {resp.text[:200]}"
        print(f"  [generate-report] FAIL — {result['failure']}")
        return result

    report = resp.json()
    print(f"  [generate-report] OK — score={report['final_score']}  band={report['band']}")

    # ── STEP 4: Validate report structure ──────────────────────────────────────
    failures = []

    if not (0 <= report["final_score"] <= 100):
        failures.append(f"final_score {report['final_score']} out of range")
    if report["band"] not in ("healthy", "watch", "at_risk"):
        failures.append(f"unexpected band {report['band']!r}")
    if len(report["insights"]) != 3:
        failures.append(f"expected 3 insights, got {len(report['insights'])}")
    if not all(isinstance(i, str) and len(i) > 30 for i in report["insights"]):
        failures.append("one or more insights are too short or not strings")
    if not (isinstance(report["action"], str) and len(report["action"]) > 30):
        failures.append(f"action too short or not a string: {report['action']!r}")

    if failures:
        result["failure"] = "Report validation: " + "; ".join(failures)
        print(f"  [validate] FAIL — {result['failure']}")
        return result

    print(f"  [validate] OK — structure valid")
    print(f"  Insight 1: {report['insights'][0][:120]}...")
    print(f"  Action:    {report['action'][:120]}...")

    # ── STEP 5: Verify Supabase save ───────────────────────────────────────────
    # Use the history endpoint as a proxy for the DB save
    resp = requests.get(f"{BASE}/history/{business_id}?limit=1", timeout=15)
    if resp.status_code != 200:
        result["failure"] = f"history returned {resp.status_code}: {resp.text[:200]}"
        print(f"  [supabase-check] FAIL — {result['failure']}")
        return result

    hist = resp.json()
    if hist["count"] == 0:
        result["failure"] = "health_scores row not found — Supabase insert may have failed"
        print(f"  [supabase-check] FAIL — {result['failure']}")
        return result

    saved_score = hist["scores"][0]["final_score"]
    if saved_score != report["final_score"]:
        result["failure"] = (
            f"saved score {saved_score} does not match report score {report['final_score']}"
        )
        print(f"  [supabase-check] FAIL — {result['failure']}")
        return result

    print(f"  [supabase-check] OK — row saved with final_score={saved_score}")

    # ── STEP 6: History retrieval ──────────────────────────────────────────────
    resp = requests.get(f"{BASE}/history/{business_id}", timeout=15)
    assert resp.status_code == 200, f"history status {resp.status_code}"
    h = resp.json()
    assert h["count"] >= 1, "history count should be >= 1"
    assert h["scores"][0]["final_score"] == report["final_score"], (
        f"history first score {h['scores'][0]['final_score']} != report {report['final_score']}"
    )
    print(f"  [history] OK — {h['count']} record(s) returned")

    result.update(passed=True, final_score=report["final_score"], band=report["band"])
    print(f"  PASSED — score={result['final_score']}  band={result['band']}")
    return result


def main():
    print(PLACEHOLDER_WARN)
    check_server()

    results = []
    for idx, biz in enumerate(TEST_BUSINESSES):
        try:
            r = run_business(biz, idx)
        except AssertionError as exc:
            r = {
                "name": biz["name"],
                "passed": False,
                "final_score": None,
                "band": None,
                "failure": f"Assertion failed: {exc}",
            }
            print(f"  ASSERTION FAIL — {r['failure']}")
        except Exception as exc:
            r = {
                "name": biz["name"],
                "passed": False,
                "final_score": None,
                "band": None,
                "failure": f"Unexpected error: {type(exc).__name__}: {exc}",
            }
            print(f"  UNEXPECTED FAIL — {r['failure']}")
        results.append(r)

    passed = [r for r in results if r["passed"]]
    failed = [r for r in results if not r["passed"]]

    scores = [r["final_score"] for r in passed if r["final_score"] is not None]
    avg_score = round(sum(scores) / len(scores), 1) if scores else "N/A"

    bands = [r["band"] for r in passed if r["band"]]
    healthy = bands.count("healthy")
    watch = bands.count("watch")
    at_risk = bands.count("at_risk")

    print(f"\n{'═' * 60}")
    print("E2E TEST SUMMARY")
    print(f"{'═' * 60}")
    print(f"Passed: {len(passed)}/5 businesses")
    print(f"Average score (passed only): {avg_score}")
    print(f"Healthy band: {healthy}  |  Watch: {watch}  |  At risk: {at_risk}")

    if failed:
        print(f"\nFailed businesses:")
        for r in failed:
            print(f"  • {r['name']}: {r['failure']}")

    if len(passed) == 5:
        print("\nMVP COMPLETE")
    else:
        print(f"\n{len(failed)} business(es) failed — see details above.")
    print(f"{'═' * 60}")


if __name__ == "__main__":
    main()
