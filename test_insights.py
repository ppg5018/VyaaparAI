"""
Interactive quality gate: 10 synthetic profiles → manual 1-5 ratings.
Pass threshold: overall average >= 3.5/5.

Run: python test_insights.py
Log: logs/insights_test.log
"""
import os
import sys
import json
import logging

# Windows console default encoding (cp1252) can't handle ★ or ₹ in Claude output.
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr.encoding and sys.stderr.encoding.lower() != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from insights import generate_insights

os.makedirs("logs", exist_ok=True)

_test_logger = logging.getLogger("vyaparai.insights_test")
_test_logger.setLevel(logging.DEBUG)
if not _test_logger.handlers:
    _fh = logging.FileHandler("logs/insights_test.log", encoding="utf-8")
    _fh.setLevel(logging.DEBUG)
    _fh.setFormatter(logging.Formatter("%(asctime)s — %(levelname)s — %(message)s"))
    _test_logger.addHandler(_fh)

CRITERIA = [
    "Names specific product/category by name",
    "Names specific competitor by name (if applicable)",
    "References actual numbers from data",
    "Action cost under ₹2,000",
    "Action time under 3 hours",
]

# ---------------------------------------------------------------------------
# 10 synthetic profiles
# Each entry: (label, business_data, scores, pos_signals)
# ---------------------------------------------------------------------------
PROFILES = [
    # ------------------------------------------------------------------
    # 1. Healthy restaurant — strong on all signals
    # ------------------------------------------------------------------
    (
        "Profile 1 — Healthy restaurant (biz_001)",
        {
            "name": "Spice Garden Restaurant",
            "rating": 4.5,
            "total_reviews": 320,
            "lat": 12.9716, "lng": 77.5946,
            "address": "12 MG Road, Bengaluru",
            "business_status": "OPERATIONAL",
            "reviews": [
                {"rating": 5, "relative_time": "2 days ago",
                 "text": "Best Chicken Biryani in the area! Huge portion, amazing aroma. Will definitely come back."},
                {"rating": 5, "relative_time": "1 week ago",
                 "text": "Paneer Butter Masala was outstanding. Perfectly spiced and creamy."},
                {"rating": 4, "relative_time": "2 weeks ago",
                 "text": "Great food and fast service. The Gulab Jamun dessert is a must-try."},
            ],
            "competitors": [
                {"name": "Royal Feast Restaurant", "rating": 4.2, "review_count": 210, "place_id": "abc1"},
                {"name": "Punjab Da Dhaba", "rating": 3.9, "review_count": 145, "place_id": "abc2"},
                {"name": "Taste of India", "rating": 4.1, "review_count": 98, "place_id": "abc3"},
            ],
        },
        {"final_score": 89, "review_score": 85, "competitor_score": 75, "pos_score": 92, "band": "healthy"},
        {"revenue_trend_pct": 12.5, "slow_categories": [], "top_product": "Biryani", "aov_direction": "rising"},
    ),

    # ------------------------------------------------------------------
    # 2. Struggling restaurant — bad reviews, strong competition, slow categories
    # ------------------------------------------------------------------
    (
        "Profile 2 — Struggling restaurant (biz_002)",
        {
            "name": "Annapoorna Dhaba",
            "rating": 3.2,
            "total_reviews": 45,
            "lat": 12.9740, "lng": 77.6010,
            "address": "5 Brigade Road, Bengaluru",
            "business_status": "OPERATIONAL",
            "reviews": [
                {"rating": 2, "relative_time": "3 days ago",
                 "text": "Mutton curry was watery and tasteless. Paid ₹320 for this disappointment. Not returning."},
                {"rating": 2, "relative_time": "1 week ago",
                 "text": "Fish curry smelled off. The place is losing its old charm since new places opened nearby."},
                {"rating": 3, "relative_time": "3 weeks ago",
                 "text": "Veg thali is decent but everything else has gone downhill."},
            ],
            "competitors": [
                {"name": "Annapurna Grand", "rating": 4.5, "review_count": 380, "place_id": "def1"},
                {"name": "Sree Sagar Hotel", "rating": 4.3, "review_count": 290, "place_id": "def2"},
                {"name": "New Kamath Restaurant", "rating": 4.0, "review_count": 175, "place_id": "def3"},
            ],
        },
        {"final_score": 38, "review_score": 42, "competitor_score": 20, "pos_score": 48, "band": "at_risk"},
        {"revenue_trend_pct": -32.0, "slow_categories": ["Mutton Dishes", "Fish Curry"],
         "top_product": "Veg Thali", "aov_direction": "falling"},
    ),

    # ------------------------------------------------------------------
    # 3. Flat kirana — stable but slow snacks category
    # ------------------------------------------------------------------
    (
        "Profile 3 — Flat kirana with slow snacks (biz_003)",
        {
            "name": "Ram Provision Store",
            "rating": 3.8,
            "total_reviews": 28,
            "lat": 13.0067, "lng": 77.5752,
            "address": "34 Malleswaram 8th Cross, Bengaluru",
            "business_status": "OPERATIONAL",
            "reviews": [
                {"rating": 4, "relative_time": "5 days ago",
                 "text": "Good stock of groceries. Prices are reasonable for daily essentials."},
                {"rating": 3, "relative_time": "2 weeks ago",
                 "text": "Snacks section feels stale — the chips packets were past best-before date last time."},
                {"rating": 4, "relative_time": "1 month ago",
                 "text": "Very convenient location. Always find what I need."},
            ],
            "competitors": [
                {"name": "Namdhari's Fresh", "rating": 4.4, "review_count": 310, "place_id": "ghi1"},
                {"name": "More Supermarket", "rating": 3.9, "review_count": 205, "place_id": "ghi2"},
                {"name": "Shree Sai Provision", "rating": 3.6, "review_count": 42, "place_id": "ghi3"},
            ],
        },
        {"final_score": 55, "review_score": 58, "competitor_score": 48, "pos_score": 57, "band": "watch"},
        {"revenue_trend_pct": 1.5, "slow_categories": ["Snacks"],
         "top_product": "Groceries", "aov_direction": "stable"},
    ),

    # ------------------------------------------------------------------
    # 4. Festival-spiking retail — sarees boom, blouses lagging
    # ------------------------------------------------------------------
    (
        "Profile 4 — Festival-spiking retail (biz_004)",
        {
            "name": "Meera Sarees & Textiles",
            "rating": 4.3,
            "total_reviews": 156,
            "lat": 12.9850, "lng": 77.5533,
            "address": "78 Commercial Street, Bengaluru",
            "business_status": "OPERATIONAL",
            "reviews": [
                {"rating": 5, "relative_time": "1 day ago",
                 "text": "Bought 3 Kanjivaram sarees for Ugadi — the quality and pricing are unbeatable. Highly recommend."},
                {"rating": 4, "relative_time": "4 days ago",
                 "text": "Beautiful Pattu Sarees collection. Blouse stitching takes too long though."},
                {"rating": 5, "relative_time": "1 week ago",
                 "text": "Best saree shop on Commercial Street. Staff helped me pick the perfect silk for my daughter's wedding."},
            ],
            "competitors": [
                {"name": "Nalli Silk Sarees", "rating": 4.6, "review_count": 850, "place_id": "jkl1"},
                {"name": "Kalpana Textiles", "rating": 4.2, "review_count": 320, "place_id": "jkl2"},
                {"name": "Vijayalakshmi Silks", "rating": 4.0, "review_count": 189, "place_id": "jkl3"},
            ],
        },
        {"final_score": 76, "review_score": 78, "competitor_score": 54, "pos_score": 92, "band": "watch"},
        {"revenue_trend_pct": 85.0, "slow_categories": ["Blouses"],
         "top_product": "Sarees", "aov_direction": "rising"},
    ),

    # ------------------------------------------------------------------
    # 5. Weekend cafe — good coffee, slow cakes
    # ------------------------------------------------------------------
    (
        "Profile 5 — Weekend cafe with slow cakes (biz_005)",
        {
            "name": "The Corner Cafe",
            "rating": 4.1,
            "total_reviews": 89,
            "lat": 12.9605, "lng": 77.6409,
            "address": "22 Indiranagar 12th Main, Bengaluru",
            "business_status": "OPERATIONAL",
            "reviews": [
                {"rating": 5, "relative_time": "2 days ago",
                 "text": "The Cold Brew Coffee here is the best I've had in Bangalore. Superb ambiance on weekends."},
                {"rating": 3, "relative_time": "1 week ago",
                 "text": "Coffee is great but the Red Velvet Cake was dry. Looked good but tasted stale."},
                {"rating": 4, "relative_time": "2 weeks ago",
                 "text": "Nice quiet corner for work. Cappuccino is always consistent."},
            ],
            "competitors": [
                {"name": "Matteo Coffee", "rating": 4.5, "review_count": 540, "place_id": "mno1"},
                {"name": "Cafe Azzure", "rating": 4.3, "review_count": 280, "place_id": "mno2"},
                {"name": "Third Wave Coffee", "rating": 4.4, "review_count": 670, "place_id": "mno3"},
            ],
        },
        {"final_score": 68, "review_score": 72, "competitor_score": 42, "pos_score": 81, "band": "watch"},
        {"revenue_trend_pct": -5.0, "slow_categories": ["Cakes"],
         "top_product": "Coffee", "aov_direction": "stable"},
    ),

    # ------------------------------------------------------------------
    # 6. Rural manufacturer — great POS, very few reviews, no competitors
    # ------------------------------------------------------------------
    (
        "Profile 6 — Rural manufacturer, no competitors",
        {
            "name": "Shakti Pickle Works",
            "rating": 4.0,
            "total_reviews": 12,
            "lat": 13.3410, "lng": 77.1120,
            "address": "Near APMC Yard, Tumkur Road",
            "business_status": "OPERATIONAL",
            "reviews": [
                {"rating": 5, "relative_time": "1 week ago",
                 "text": "Authentic homemade Mango Pickle. Uses pure sesame oil — you can taste the difference. Ordered 5 kg."},
                {"rating": 4, "relative_time": "1 month ago",
                 "text": "Lemon Pickle and Mixed Vegetable Pickle both excellent. No artificial preservatives."},
            ],
            "competitors": [],
        },
        {"final_score": 72, "review_score": 61, "competitor_score": 65, "pos_score": 88, "band": "watch"},
        {"revenue_trend_pct": 22.0, "slow_categories": [],
         "top_product": "Mango Pickle", "aov_direction": "rising"},
    ),

    # ------------------------------------------------------------------
    # 7. Urban cafe dominating all nearby competitors
    # ------------------------------------------------------------------
    (
        "Profile 7 — Urban cafe beating all competitors",
        {
            "name": "Brew & Beans Cafe",
            "rating": 4.7,
            "total_reviews": 412,
            "lat": 12.9716, "lng": 77.6411,
            "address": "4 HAL 2nd Stage, Bengaluru",
            "business_status": "OPERATIONAL",
            "reviews": [
                {"rating": 5, "relative_time": "1 day ago",
                 "text": "The Nitro Cold Brew is insane — nothing like it in this area. Worth every rupee at ₹280."},
                {"rating": 5, "relative_time": "3 days ago",
                 "text": "Best specialty coffee in HAL. Their single-origin pour-over from Coorg is exceptional."},
                {"rating": 5, "relative_time": "1 week ago",
                 "text": "Tried 5 cafes nearby. Brew & Beans wins hands down on quality and consistency."},
            ],
            "competitors": [
                {"name": "Java Junction", "rating": 4.2, "review_count": 180, "place_id": "pqr1"},
                {"name": "Cafe Mocha House", "rating": 3.8, "review_count": 95, "place_id": "pqr2"},
                {"name": "Daily Grind Cafe", "rating": 4.0, "review_count": 140, "place_id": "pqr3"},
            ],
        },
        {"final_score": 91, "review_score": 93, "competitor_score": 87, "pos_score": 88, "band": "healthy"},
        {"revenue_trend_pct": 8.5, "slow_categories": [],
         "top_product": "Cold Brew Coffee", "aov_direction": "rising"},
    ),

    # ------------------------------------------------------------------
    # 8. Declining restaurant — new high-rated competitor opened nearby
    # ------------------------------------------------------------------
    (
        "Profile 8 — Declining restaurant vs new competitor",
        {
            "name": "Sagar Restaurant",
            "rating": 3.9,
            "total_reviews": 234,
            "lat": 12.9585, "lng": 77.5915,
            "address": "18 Jayanagar 4th Block, Bengaluru",
            "business_status": "OPERATIONAL",
            "reviews": [
                {"rating": 2, "relative_time": "4 days ago",
                 "text": "Since Coastal Kitchen opened next door with better seafood at lower prices, Sagar has gone downhill. Prawn Masala here is ₹380 vs ₹280 there."},
                {"rating": 3, "relative_time": "2 weeks ago",
                 "text": "Dal Makhani is still good but the Fish Thali portions have shrunk. Coastal Kitchen is eating their lunch."},
                {"rating": 4, "relative_time": "1 month ago",
                 "text": "Old faithful. Dal Makhani and butter naan still reliable."},
            ],
            "competitors": [
                {"name": "Coastal Kitchen", "rating": 4.6, "review_count": 320, "place_id": "stu1"},
                {"name": "Sea Pearl Restaurant", "rating": 4.1, "review_count": 178, "place_id": "stu2"},
                {"name": "Blue Waters Dhaba", "rating": 3.7, "review_count": 89, "place_id": "stu3"},
            ],
        },
        {"final_score": 52, "review_score": 63, "competitor_score": 30, "pos_score": 58, "band": "watch"},
        {"revenue_trend_pct": -18.0, "slow_categories": ["Seafood"],
         "top_product": "Dal Makhani", "aov_direction": "falling"},
    ),

    # ------------------------------------------------------------------
    # 9. Premium restaurant — excellent rating, slow desserts, flat growth
    # ------------------------------------------------------------------
    (
        "Profile 9 — Premium restaurant, slow desserts",
        {
            "name": "The Grand Punjabi",
            "rating": 4.8,
            "total_reviews": 178,
            "lat": 12.9720, "lng": 77.6035,
            "address": "9 Residency Road, Bengaluru",
            "business_status": "OPERATIONAL",
            "reviews": [
                {"rating": 5, "relative_time": "2 days ago",
                 "text": "Best Dal Bukhara outside Delhi. Slow-cooked overnight — you can taste the difference. AOV ₹900 but worth every paisa."},
                {"rating": 5, "relative_time": "5 days ago",
                 "text": "Ordered Gilafi Seekh Kebab and Raan-e-Punjab for a corporate dinner. 14 guests, all impressed. Service was impeccable."},
                {"rating": 5, "relative_time": "2 weeks ago",
                 "text": "Butter Chicken here sets the benchmark. Tried their Shahi Tukda for dessert — lukewarm and not worth ₹320."},
            ],
            "competitors": [
                {"name": "Punjab Grill", "rating": 4.5, "review_count": 445, "place_id": "vwx1"},
                {"name": "Barbeque Nation", "rating": 4.3, "review_count": 1200, "place_id": "vwx2"},
                {"name": "Karim's Bengaluru", "rating": 4.4, "review_count": 320, "place_id": "vwx3"},
            ],
        },
        {"final_score": 82, "review_score": 94, "competitor_score": 72, "pos_score": 62, "band": "healthy"},
        {"revenue_trend_pct": 2.0, "slow_categories": ["Desserts"],
         "top_product": "Butter Chicken", "aov_direction": "stable"},
    ),

    # ------------------------------------------------------------------
    # 10. New business — 50 reviews, still building momentum
    # ------------------------------------------------------------------
    (
        "Profile 10 — New tiffin business, growing",
        {
            "name": "Kavya Tiffin Center",
            "rating": 3.8,
            "total_reviews": 50,
            "lat": 13.0210, "lng": 77.5720,
            "address": "7 Rajajinagar 2nd Block, Bengaluru",
            "business_status": "OPERATIONAL",
            "reviews": [
                {"rating": 4, "relative_time": "3 days ago",
                 "text": "Lunch box delivery is always on time. The Sambar Rice and Rasam are home-style. Very affordable at ₹120."},
                {"rating": 5, "relative_time": "1 week ago",
                 "text": "Best value tiffin in Rajajinagar. The Curd Rice on Fridays is amazing. Running a monthly subscription now."},
                {"rating": 3, "relative_time": "2 weeks ago",
                 "text": "Good food but menu doesn't change much. Would love more variety in the weekly rotation."},
            ],
            "competitors": [
                {"name": "Udupi Tiffin House", "rating": 4.4, "review_count": 320, "place_id": "yz01"},
                {"name": "MTR Tiffin Service", "rating": 4.6, "review_count": 780, "place_id": "yz02"},
                {"name": "Shivaji Meals", "rating": 3.9, "review_count": 145, "place_id": "yz03"},
            ],
        },
        {"final_score": 61, "review_score": 60, "competitor_score": 34, "pos_score": 78, "band": "watch"},
        {"revenue_trend_pct": 15.0, "slow_categories": [],
         "top_product": "Lunch Box", "aov_direction": "stable"},
    ),
]


# ---------------------------------------------------------------------------
# Rating helpers
# ---------------------------------------------------------------------------

def _get_int_rating(prompt_text: str) -> int:
    while True:
        try:
            val = int(input(prompt_text))
            if 1 <= val <= 5:
                return val
            print("        Please enter a number between 1 and 5.")
        except (ValueError, EOFError):
            print("        Please enter a number between 1 and 5.")


def rate_output(label: str, output: dict) -> list[int]:
    print(f"\n{'=' * 65}")
    print(f"  {label}")
    print(f"{'=' * 65}")
    print("\nINSIGHTS:")
    for i, insight in enumerate(output["insights"], 1):
        print(f"  [{i}] {insight}")
    print(f"\nACTION:\n  {output['action']}")
    print(f"\nRate each criterion 1–5:")
    ratings = []
    for i, criterion in enumerate(CRITERIA, 1):
        ratings.append(_get_int_rating(f"  [{i}] {criterion}: "))
    return ratings


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("\nVyaaparAI — Insights Quality Gate")
    print(f"Running {len(PROFILES)} synthetic profiles. Rate each 1–5 on 5 criteria.\n")

    all_ratings: list[list[int]] = []

    for idx, (label, business_data, scores, pos_signals) in enumerate(PROFILES, 1):
        print(f"\n[{idx}/{len(PROFILES)}] Calling Claude for: {label} ...")
        try:
            output = generate_insights(business_data, scores, pos_signals)
        except Exception as exc:
            print(f"  ERROR generating insights: {exc}")
            _test_logger.error("Profile %d (%s) FAILED: %s", idx, label, exc)
            continue

        _test_logger.info(
            "Profile %d (%s) | output: %s",
            idx, label, json.dumps(output),
        )

        ratings = rate_output(label, output)
        all_ratings.append(ratings)

        profile_avg = sum(ratings) / len(ratings)
        print(f"\n  Profile average: {profile_avg:.1f}/5")

        running_avg = (
            sum(sum(r) for r in all_ratings) / (len(all_ratings) * len(CRITERIA))
        )
        print(f"  Running overall average ({len(all_ratings)} profiles): {running_avg:.2f}/5")

        _test_logger.info(
            "Profile %d (%s) | ratings: %s | profile_avg: %.2f | running_avg: %.2f",
            idx, label, ratings, profile_avg, running_avg,
        )

    # ------------------------------------------------------------------
    # Final summary
    # ------------------------------------------------------------------
    print(f"\n{'=' * 65}")
    print("FINAL SUMMARY")
    print(f"{'=' * 65}")
    print(f"Profiles rated: {len(all_ratings)} / {len(PROFILES)}")

    if not all_ratings:
        print("No profiles rated — nothing to summarise.")
        return

    print("\nAverage per criterion:")
    for ci, criterion in enumerate(CRITERIA):
        crit_avg = sum(r[ci] for r in all_ratings) / len(all_ratings)
        print(f"  [{ci + 1}] {criterion}: {crit_avg:.1f}/5")

    overall = sum(sum(r) for r in all_ratings) / (len(all_ratings) * len(CRITERIA))
    print(f"\nOverall average: {overall:.1f}/5")

    if overall >= 3.5:
        print("RESULT: PASS — quality gate cleared (>= 3.5/5)")
    else:
        print("RESULT: FAIL — quality gate not cleared (< 3.5/5)")
        print("\nCommon fixes to iterate the prompt:")
        print("  - Too generic → add more examples to the prompt")
        print("  - Doesn't name products → add 'name X explicitly by name'")
        print("  - Action too expensive → reinforce the ₹2,000 cap with an example")
        print("  - Action too vague → require a step-by-step format")

    _test_logger.info(
        "=== RUN COMPLETE === profiles_rated=%d overall_avg=%.2f PASS=%s",
        len(all_ratings), overall, overall >= 3.5,
    )


if __name__ == "__main__":
    main()
