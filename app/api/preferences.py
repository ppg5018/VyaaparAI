"""User-controlled competitor-preference saves.

PUT body validated by `PreferencesRequest`. On success:
- Updates `businesses.competitor_prefs_mode` + `competitor_prefs` (JSON or NULL).
- Wipes non-manual `competitor_matches` rows for this business so the next
  /generate-report rebuilds with the new prefs.
- Wipes `health_scores` rows for this business so the 24h report cache
  doesn't serve stale numbers under the old prefs.

Manual `competitor_matches` rows (`is_manual=true`) are preserved.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Header, HTTPException, Response

from app.config import SUBCATEGORIES_BY_CATEGORY
from app.database import supabase
from app.models import PreferencesRequest

logger = logging.getLogger(__name__)

router = APIRouter()


@router.put("/preferences/{business_id}", status_code=204)
def save_preferences(
    business_id: str,
    body: PreferencesRequest,
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> Response:
    biz_resp = (
        supabase.table("businesses")
        .select("id, user_id, category")
        .eq("id", business_id)
        .execute()
    )
    if not biz_resp.data:
        raise HTTPException(status_code=404, detail="Business not found")
    biz = biz_resp.data[0]

    if biz.get("user_id") and x_user_id and biz["user_id"] != x_user_id:
        raise HTTPException(status_code=403, detail="Not authorised for this business")

    if body.mode == "custom" and body.prefs and body.prefs.subcategories:
        allowed = set(SUBCATEGORIES_BY_CATEGORY.get(biz["category"], []))
        unknown = [t for t in body.prefs.subcategories if t not in allowed]
        if unknown:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown sub-category tag(s): {unknown}. "
                       f"Allowed: {sorted(allowed)}",
            )

    update_payload: dict = {
        "competitor_prefs_mode": body.mode,
        "competitor_prefs": body.prefs.model_dump() if body.prefs else None,
        "competitor_prefs_updated_at": datetime.now(timezone.utc).isoformat(),
    }
    supabase.table("businesses").update(update_payload).eq("id", business_id).execute()

    try:
        supabase.table("competitor_matches").delete().eq(
            "business_id", business_id
        ).eq("is_manual", False).execute()
    except Exception as exc:
        logger.warning("[preferences.put] competitor_matches wipe failed: %s", exc)

    try:
        supabase.table("health_scores").delete().eq("business_id", business_id).execute()
    except Exception as exc:
        logger.warning("[preferences.put] health_scores wipe failed: %s", exc)

    logger.info(
        "[preferences.put] business_id=%s mode=%s radius=%s min=%s max=%s subcats=%s",
        business_id, body.mode,
        body.prefs.radius_m if body.prefs else None,
        body.prefs.min_reviews if body.prefs else None,
        body.prefs.max_reviews if body.prefs else None,
        body.prefs.subcategories if body.prefs else None,
    )
    return Response(status_code=204)
