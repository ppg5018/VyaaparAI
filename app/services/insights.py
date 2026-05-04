import json
import logging

import anthropic

from app.config import ANTHROPIC_API_KEY, CLAUDE_MODEL, MAX_TOKENS

logger = logging.getLogger(__name__)


MIN_INSIGHTS = 3
MAX_INSIGHTS = 6


def insight_count(business_data: dict, pos_signals: dict) -> int:
    """Decide how many insights to request based on available signal richness.

    Why: a business with 50 reviews + full POS data deserves more, distinct
    suggestions than one with 2 reviews and no POS data.
    """
    score = MIN_INSIGHTS
    total_reviews = business_data.get("total_reviews", 0) or 0
    if total_reviews >= 20:
        score += 1
    competitors = business_data.get("competitors") or []
    if len(competitors) >= 3:
        score += 1
    pos_signal_keys = ("revenue_trend_pct", "slow_categories", "top_product", "aov_direction", "repeat_rate_pct")
    pos_present = sum(1 for k in pos_signal_keys if pos_signals.get(k))
    if pos_present >= 2:
        score += 1
    if pos_present >= 4:
        score += 1
    return min(MAX_INSIGHTS, score)


def build_prompt(
    business_data: dict,
    scores: dict,
    pos_signals: dict,
    count: int,
    dominant_complaint: str | None = None,
    reviews_per_month: float | None = None,
    photo_count: int = 0,
    previously_shown: list[str] | None = None,
) -> str:
    """Assemble the full Claude prompt from business data, scores, and POS signals."""
    name = business_data.get("name", "Unknown Business")
    rating = business_data.get("rating", 0.0)
    total_reviews = business_data.get("total_reviews", 0)
    final_score = scores.get("final_score", 0)
    band = scores.get("band", "unknown")

    all_reviews = business_data.get("reviews", [])
    reviews = all_reviews[:50]  # send up to 50 reviews to Claude
    if reviews:
        snippets = [
            f"- {r['rating']}★ ({r.get('relative_time', 'recently')}): {r['text'][:300]}"
            for r in reviews
            if r.get("text", "").strip()
        ]
        review_snippets = "\n".join(snippets) if snippets else "No review text available"
    else:
        review_snippets = "No reviews available"

    # Competitor block — these are the similarity-filtered matches from
    # competitor_pipeline.run(), already ranked by relevance.
    competitors = business_data.get("competitors", [])[:3]
    if competitors:
        comp_lines = []
        for c in competitors:
            sim_str = (
                f", similarity={c['similarity']:.2f}" if c.get("similarity") is not None else ""
            )
            comp_lines.append(
                f"- {c['name']}: {c['rating']}★ ({c['review_count']} reviews{sim_str})"
            )
        competitor_lines = "\n".join(comp_lines)
    else:
        competitor_lines = "No relevant competitors found within 800m"

    revenue_trend_pct = pos_signals.get("revenue_trend_pct")
    slow_categories = pos_signals.get("slow_categories", [])
    top_product = pos_signals.get("top_product")
    aov_direction = pos_signals.get("aov_direction")
    repeat_rate_pct = pos_signals.get("repeat_rate_pct")
    repeat_rate_trend = pos_signals.get("repeat_rate_trend")

    revenue_trend_str = (
        "No POS data available" if revenue_trend_pct is None
        else f"{revenue_trend_pct:+.1f}% vs prior month"
    )
    slow_categories_str = (
        "None — all categories healthy" if not slow_categories
        else ", ".join(slow_categories)
    )
    top_product_str = top_product if top_product is not None else "No POS data available"
    aov_str = aov_direction if aov_direction is not None else "No POS data available"

    if repeat_rate_pct is None:
        repeat_str = "No customer data available"
    else:
        trend_tag = (
            f", trend {repeat_rate_trend:+.1f}% vs prior period" if repeat_rate_trend is not None else ""
        )
        repeat_str = f"{repeat_rate_pct:.1f}% of visits are returning customers{trend_tag}"

    insight_slots = ", ".join(['"..."'] * count)

    if dominant_complaint:
        topic_display = dominant_complaint.replace("_", " ")
        complaint_line = f"Dominant complaint topic (Claude-analysed): {topic_display}"
    else:
        complaint_line = "Dominant complaint topic: insufficient data"

    velocity_str = (
        f"{reviews_per_month:.1f} reviews/month (last 6 months)"
        if reviews_per_month is not None
        else "unknown"
    )
    photo_str = (
        "0 — no photos on Google Maps (visibility risk)"
        if photo_count == 0
        else f"{photo_count} photos on Google Maps"
    )

    # Exclusion block — only included when previously_shown has content.
    # We pass things the user has already seen / actioned / saved so Claude
    # doesn't restate them with slightly different wording.
    if previously_shown:
        excl_lines = "\n".join(f"- {s[:200]}" for s in previously_shown[:30])
        exclusion_block = (
            "\n\nPREVIOUSLY-SHOWN SUGGESTIONS — the user has already seen these. "
            "Generate fundamentally NEW angles. Do not restate, paraphrase, or "
            "give the same recommendation about the same subject:\n"
            f"{excl_lines}\n"
        )
    else:
        exclusion_block = ""

    return f"""You are a business advisor for Indian MSME owners. Be specific, not generic.
Always name specific products and competitors. Never say "some products" or
"nearby competitors". Actions must cost under ₹2,000 and take under 3 hours.

Business: {name}
Rating: {rating}/5 ({total_reviews} reviews)
Health score: {final_score}/100 (band: {band})

Last {len(reviews)} reviews (newest first) — read ACROSS reviews and look for
patterns that appear in 3+ reviews (e.g. "service slow" mentioned 4 times):
{review_snippets}

Top similarity-matched competitors within 800m (semantically similar businesses):
{competitor_lines}

Sales signals (last 30 days):
Revenue trend: {revenue_trend_str}
Slow-moving categories: {slow_categories_str}
Top product by revenue: {top_product_str}
Average order value: {aov_str}
Repeat customer rate: {repeat_str}

Review analysis (Claude-rated sentiment, not raw stars):
{complaint_line}
Review velocity: {velocity_str}
Google Maps photos: {photo_str}{exclusion_block}

Generate exactly {count} insights and 1 action.

Each insight belongs to exactly ONE of these three themes:
  [SALES]   revenue trend, AOV, top/slow products, pricing, promotions, channel mix
  [CX]      review themes, service/quality complaints, dominant complaints, food
  [PERF]    operations, photos/visibility, competitor gap, repeat-rate, review velocity

Across the {count} insights you MUST collectively cover all three themes when
{count} >= 3. No two insights may share the same primary subject (same product,
same review theme, same competitor, same POS signal). Each insight must name a
specific product / theme / competitor and cite actual numbers from the data above.

Do NOT prefix insights with the bracket tag — keep them clean prose.

The action must:
- Cost under ₹2,000
- Take under 3 hours of owner's time
- Be doable this week
- Be the single highest-impact thing to do, distinct from the insights

Return ONLY valid JSON, no markdown, no preamble. The "insights" array must contain
exactly {count} strings:
{{"insights": [{insight_slots}], "action": "..."}}"""


def strip_markdown(text: str) -> str:
    """Remove markdown code fences from Claude's response before json.loads()."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
    if text.endswith("```"):
        text = text.rsplit("```", 1)[0]
    return text.strip()


def _call_claude(prompt: str) -> str:
    """Send a single prompt to Claude and return the raw text response."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    msg = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=MAX_TOKENS,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text


def _parse_and_validate(response_text: str, expected_count: int) -> dict:
    """Parse and structurally validate Claude's JSON output."""
    cleaned = strip_markdown(response_text)
    result = json.loads(cleaned)
    assert "insights" in result and isinstance(result["insights"], list)
    assert len(result["insights"]) == expected_count, (
        f"expected {expected_count} insights, got {len(result['insights'])}"
    )
    assert "action" in result and isinstance(result["action"], str)
    assert all(isinstance(i, str) for i in result["insights"])
    return result


def generate_insights(
    business_data: dict,
    scores: dict,
    pos_signals: dict,
    dominant_complaint: str | None = None,
    reviews_per_month: float | None = None,
    photo_count: int = 0,
    previously_shown: list[str] | None = None,
) -> dict:
    """Call Claude API, parse JSON insights, retry once on parse failure.

    `previously_shown` is a list of suggestion strings the user has already
    seen (sourced from `actions_log`). Passed to Claude so it can avoid
    restating or paraphrasing them in the new batch.

    Returns: {"insights": [str, str, str], "action": str}
    Raises:
        anthropic.RateLimitError: caller must handle backoff.
        anthropic.AuthenticationError: caller must fix API key.
        RuntimeError: if both attempts fail to produce valid JSON.
    """
    count = insight_count(business_data, pos_signals)
    prompt = build_prompt(
        business_data, scores, pos_signals, count,
        dominant_complaint, reviews_per_month, photo_count,
        previously_shown=previously_shown,
    )
    response_text = None

    try:
        response_text = _call_claude(prompt)
        logger.debug("Claude response (attempt 1): %s", response_text)
        return _parse_and_validate(response_text, count)
    except (anthropic.RateLimitError, anthropic.AuthenticationError):
        raise
    except anthropic.APITimeoutError as exc:
        logger.warning("API timeout on attempt 1, retrying: %s", exc)
    except (json.JSONDecodeError, AssertionError, ValueError, KeyError, IndexError) as exc:
        logger.warning(
            "Parse/validation failed on attempt 1: %s | raw: %.300s", exc, response_text
        )

    stricter_prompt = (
        prompt
        + f"\n\nCRITICAL: Output must be ONLY the JSON object. "
        f"No text before or after. No markdown. Start with {{ and end with }}. "
        f"The insights array must contain exactly {count} strings."
    )
    response_text = None

    try:
        response_text = _call_claude(stricter_prompt)
        logger.debug("Claude response (attempt 2): %s", response_text)
        return _parse_and_validate(response_text, count)
    except (anthropic.RateLimitError, anthropic.AuthenticationError):
        raise
    except Exception as exc:
        logger.error(
            "Claude insights failed after retry. Error: %s | raw: %.300s",
            exc, response_text,
        )
        raise RuntimeError("Claude insights generation failed after retry") from exc
