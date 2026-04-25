import json
import logging

import anthropic

from app.config import ANTHROPIC_API_KEY, CLAUDE_MODEL, MAX_TOKENS
from app.services import apify_reviews, google_places
from app.services.insights import strip_markdown

logger = logging.getLogger(__name__)

MAX_COMPETITORS_TO_ANALYZE = 3


def _fetch_competitor_reviews(competitors: list[dict], my_rating: float) -> list[dict]:
    """For each competitor with rating >= ours, fetch their reviews.

    Caps at MAX_COMPETITORS_TO_ANALYZE. Failures are swallowed so one bad
    competitor never kills the analysis.
    """
    candidates = [c for c in competitors if c.get("rating", 0) >= my_rating]
    candidates = candidates[:MAX_COMPETITORS_TO_ANALYZE]

    enriched = []
    for c in candidates:
        place_id = c.get("place_id")
        if not place_id:
            continue
        try:
            # Try Apify cache first — gets up to 30 reviews, refreshed monthly.
            apify_revs = apify_reviews.get_reviews(
                place_id, max_reviews=30, is_competitor=True,
            )
            if apify_revs:
                enriched.append({
                    "name": c["name"],
                    "rating": c["rating"],
                    "review_count": c["review_count"],
                    "reviews": apify_revs[:30],
                })
                continue

            # Fallback: Google's 5-review cap if Apify cache is empty / fails.
            details = google_places.get_business_details(place_id)
            reviews = google_places.parse_reviews(details["raw_reviews"])
            enriched.append({
                "name": c["name"],
                "rating": c["rating"],
                "review_count": c["review_count"],
                "reviews": reviews[:5],
            })
        except Exception as exc:
            logger.warning(
                "competitor_analysis: failed to fetch reviews for %s: %s",
                c.get("name", place_id), exc,
            )
            continue

    return enriched


def _build_prompt(my_business: dict, my_reviews: list[dict], competitors: list[dict]) -> str:
    """Build the competitor comparison prompt."""
    my_name = my_business.get("name", "this business")
    my_rating = my_business.get("rating", 0.0)

    my_review_lines = [
        f"- {r['rating']}★: {r['text']}"
        for r in my_reviews if r.get("text", "").strip()
    ][:5]
    my_review_block = "\n".join(my_review_lines) or "No reviews with text available"

    comp_blocks = []
    for c in competitors:
        review_lines = [
            f"  - {r['rating']}★: {r['text']}"
            for r in c.get("reviews", []) if r.get("text", "").strip()
        ][:5]
        review_text = "\n".join(review_lines) or "  - No reviews with text"
        comp_blocks.append(
            f"{c['name']} ({c['rating']}★, {c['review_count']} reviews):\n{review_text}"
        )
    competitor_block = "\n\n".join(comp_blocks) if comp_blocks else "No higher-rated competitors found"

    return f"""You are a business advisor analyzing what competitors do better than the user's business.

Be specific. Always name specific products, services, or behaviors mentioned in reviews. Never say "good service" or "quality food" — quote what reviewers actually praise.

User's business: {my_name} ({my_rating}★)
User's reviews:
{my_review_block}

Higher-rated nearby competitors:

{competitor_block}

Compare the reviews. Identify what customers consistently praise about competitors that is NOT praised about the user's business.

Generate:
1. Three "themes" — specific things competitors are known for (each ≤ 80 chars, naming a competitor and a specific behavior/item)
2. Three "opportunities" — concrete actions the user can take this month to close the gap (each ≤ 120 chars, costing under ₹5,000 and doable in under a week)

Return ONLY valid JSON, no markdown, no preamble:
{{"themes": ["...", "...", "..."], "opportunities": ["...", "...", "..."]}}"""


def _call_claude(prompt: str) -> str:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    msg = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=MAX_TOKENS,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text


def _parse(response_text: str) -> dict:
    cleaned = strip_markdown(response_text)
    result = json.loads(cleaned)
    assert "themes" in result and isinstance(result["themes"], list)
    assert "opportunities" in result and isinstance(result["opportunities"], list)
    assert all(isinstance(t, str) for t in result["themes"])
    assert all(isinstance(o, str) for o in result["opportunities"])
    return {
        "themes": result["themes"][:3],
        "opportunities": result["opportunities"][:3],
    }


def analyze_competitors(my_business: dict, competitors: list[dict]) -> dict:
    """Compare the user's business reviews to top competitors' reviews.

    Returns: {"themes": [...], "opportunities": [...], "analyzed_count": int}
    Never raises — returns empty lists on any failure so the main report
    pipeline is unaffected.
    """
    my_rating = my_business.get("rating", 0.0)
    my_reviews = my_business.get("reviews", [])

    if not competitors:
        return {"themes": [], "opportunities": [], "analyzed_count": 0}

    enriched = _fetch_competitor_reviews(competitors, my_rating)
    if not enriched:
        logger.info("competitor_analysis: no higher-rated competitors with reviews found")
        return {"themes": [], "opportunities": [], "analyzed_count": 0}

    prompt = _build_prompt(my_business, my_reviews, enriched)

    try:
        response_text = _call_claude(prompt)
        parsed = _parse(response_text)
        parsed["analyzed_count"] = len(enriched)
        logger.info(
            "competitor_analysis: analyzed %d competitors, generated %d themes",
            len(enriched), len(parsed["themes"]),
        )
        return parsed
    except Exception as exc:
        logger.warning("competitor_analysis: Claude call failed: %s", exc)
        return {"themes": [], "opportunities": [], "analyzed_count": 0}
