import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.database import supabase

logger = logging.getLogger(__name__)
router = APIRouter()

VALID_KINDS = {"weekly_action_done", "insight_actioned", "insight_saved"}


class LogActionRequest(BaseModel):
    kind: str
    target_text: str = Field(..., min_length=1, max_length=2000)
    note: Optional[str] = Field(None, max_length=2000)


class ActionEntry(BaseModel):
    id: str
    business_id: str
    kind: str
    target_text: str
    note: Optional[str] = None
    created_at: str


class ActionsListResponse(BaseModel):
    business_id: str
    count: int
    actions: list[ActionEntry]


def _row_to_entry(row: dict) -> ActionEntry:
    return ActionEntry(
        id=row["id"],
        business_id=row["business_id"],
        kind=row["kind"],
        target_text=row["target_text"],
        note=row.get("note"),
        created_at=row["created_at"],
    )


@router.post("/actions/{business_id}", response_model=ActionEntry)
def log_action(business_id: str, req: LogActionRequest) -> ActionEntry:
    """Persist a user interaction (mark done / actioned / saved) on insights or weekly actions."""
    if req.kind not in VALID_KINDS:
        raise HTTPException(status_code=422, detail=f"kind must be one of {sorted(VALID_KINDS)}")

    biz = supabase.table("businesses").select("id").eq("id", business_id).execute()
    if not biz.data:
        raise HTTPException(status_code=404, detail="Business not found")

    payload = {
        "business_id": business_id,
        "kind": req.kind,
        "target_text": req.target_text[:2000],
        "note": req.note[:2000] if req.note else None,
    }

    try:
        res = supabase.table("actions_log").insert(payload).execute()
    except Exception as exc:
        logger.error("[actions] insert failed for business_id=%s: %s", business_id, exc)
        raise HTTPException(status_code=500, detail="Failed to log action")

    logger.info("[actions] logged kind=%s business_id=%s", req.kind, business_id)
    return _row_to_entry(res.data[0])


@router.get("/actions/{business_id}", response_model=ActionsListResponse)
def list_actions(business_id: str) -> ActionsListResponse:
    """Return all actions logged for a business, newest first."""
    try:
        res = (
            supabase.table("actions_log")
            .select("*")
            .eq("business_id", business_id)
            .order("created_at", desc=True)
            .execute()
        )
    except Exception as exc:
        logger.warning("[actions] list failed (non-fatal) for business_id=%s: %s", business_id, exc)
        return ActionsListResponse(business_id=business_id, count=0, actions=[])

    actions = [_row_to_entry(r) for r in (res.data or [])]
    return ActionsListResponse(business_id=business_id, count=len(actions), actions=actions)


@router.delete("/actions/{action_id}")
def delete_action(action_id: str) -> dict:
    """Undo a previously logged action."""
    try:
        supabase.table("actions_log").delete().eq("id", action_id).execute()
    except Exception as exc:
        logger.error("[actions] delete failed for action_id=%s: %s", action_id, exc)
        raise HTTPException(status_code=500, detail="Failed to delete action")
    logger.info("[actions] deleted action_id=%s", action_id)
    return {"deleted": action_id}
