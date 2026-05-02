"""Sonnet-driven competitor theme + opportunity extraction.

Runs once per /generate-report cache miss. Uses the user's reviews + cached
Apify reviews from the matched competitors to surface:
  - themes:        what competitors are consistently praised for that the user is not
  - opportunities: gaps competitors leave that the user could exploit

Designed to be cheap (one Sonnet call) and resilient — empty output on any
failure so the rest of the report still renders.
"""
from __future__ import annotations

import json
import logging

import anthropic

from app.config import ANTHROPIC_API_KEY, CLAUDE_MODEL, MAX_TOKENS
from app.services import apify_reviews

logger = logging.getLogger(__name__)


def _strip_markdown(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
    if text.endswith("```"):
        text = text.rsplit("```", 1)[0]
    return text.strip()


def _format_review_block(reviews: list[dict], cap: int = 6) -> str:
    out = []
    for r in reviews[:cap]:
        rating = r.get("rating", 0)
        text = (r.get("text") or "").strip().replace("\n", " ")
        if not text:
            continue
        out.append(f"- {rating}★ {text[:240]}")
    return "\n".join(out)


def analyze_competitors(
    my_business_name: str,
    my_reviews: list[dict],
    competitors: list[dict],
    max_competitors: int = 4,
) -> dict:
    """Return {themes, opportunities, analyzed_count}.

    `competitors` is the matched list from `competitor_pipeline.run()` — each
    entry needs at least `place_id`, `name`, `rating`. We pull cached Apify
    reviews per competitor (no fresh API calls — purely cache hits).
    """
    empty = {"themes": [], "opportunities": [], "analyzed_count": 0}
    if not my_reviews or not competitors:
        return empty

    # Pull cached reviews for the top N competitors. apify_reviews.get_reviews
    # short-circuits to the cache when within the 30-day competitor TTL.
    blocks: list[str] = []
    analyzed_count = 0
    for c in competitors[:max_competitors]:
        pid = c.get("place_id")
        if not pid:
            continue
        try:
            revs = apify_reviews.get_reviews(pid, max_reviews=10, is_competitor=True)
        except Exception as exc:
            logger.warning("[competitor_analysis] could not load reviews for %s: %s", pid, exc)
            continue
        sample = _format_review_block(revs)
        if not sample:
            continue
        blocks.append(
            f"### {c.get('name','?')} — {c.get('rating',0)}★ "
            f"({c.get('review_count',0)} reviews)\n{sample}"
        )
        analyzed_count += 1

    if not blocks:
        return empty

    my_sample = _format_review_block(my_reviews, cap=8)
    if not my_sample:
        return empty

    prompt = f"""You are analysing competitor reviews for an Indian small business owner.
The user's business: {my_business_name}.

USER'S OWN REVIEWS (sample):
{my_sample}

COMPETITORS (sample reviews each):
{chr(10).join(blocks)}

Return strictly valid JSON in this exact shape:
{{
  "themes": ["...", "...", "..."],
  "opportunities": ["...", "...", "..."]
}}

Rules:
- "themes" = 3 specific things competitors are consistently praised for that the
  user's reviews do NOT mention. Each must name at least one competitor and one
  concrete behaviour or product. No generic advice.
- "opportunities" = 3 specific gaps in the competitors' experience that the user
  could exploit. Each must reference an actual complaint pattern from the
  competitor reviews above.
- Each item: 14–28 words, plain English, action-flavoured.
- No markdown, no preamble, only the JSON object.
"""

    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = msg.content[0].text
    except Exception as exc:
        logger.warning("[competitor_analysis] Sonnet call failed: %s", exc)
        return empty

    try:
        parsed = json.loads(_strip_markdown(raw))
    except json.JSONDecodeError as exc:
        logger.warning("[competitor_analysis] JSON parse failed: %s — raw=%s", exc, raw[:300])
        return empty

    themes = parsed.get("themes") or []
    opps = parsed.get("opportunities") or []
    if not isinstance(themes, list) or not isinstance(opps, list):
        return empty

    themes = [str(t)[:280] for t in themes if isinstance(t, str)][:5]
    opps = [str(o)[:280] for o in opps if isinstance(o, str)][:5]

    logger.info(
        "[competitor_analysis] analyzed=%d themes=%d opportunities=%d",
        analyzed_count, len(themes), len(opps),
    )
    return {"themes": themes, "opportunities": opps, "analyzed_count": analyzed_count}
