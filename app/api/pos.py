import os
import logging
import tempfile

from fastapi import APIRouter, HTTPException, UploadFile, File

from app.models import UploadPOSResponse
from app.database import supabase
from app.services import pos_pipeline

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/pos-dashboard/{business_id}")
def pos_dashboard(
    business_id: str,
    from_date: str | None = None,
    to_date: str | None = None,
    category: str | None = None,
) -> dict:
    """Aggregated POS metrics, charts, and operational insights for the dashboard.

    Query params:
        from_date: ISO date YYYY-MM-DD (defaults to earliest record).
        to_date:   ISO date YYYY-MM-DD (defaults to latest record).
        category:  optional product_category filter.
    """
    biz = supabase.table("businesses").select("id").eq("id", business_id).execute()
    if not biz.data:
        raise HTTPException(status_code=404, detail=f"Business {business_id} not found")
    return pos_pipeline.dashboard_data(business_id, from_date, to_date, category)


@router.post("/upload-pos/{business_id}", response_model=UploadPOSResponse)
async def upload_pos(business_id: str, file: UploadFile = File(...)) -> UploadPOSResponse:
    """Ingest a POS CSV file for an existing business."""
    # 1. Validate business exists
    biz = supabase.table("businesses").select("id").eq("id", business_id).execute()
    if not biz.data:
        logger.error("[upload-pos] business_id=%s not found", business_id)
        raise HTTPException(status_code=404, detail=f"Business {business_id} not found")

    # 2. Validate file type
    is_csv = (file.content_type == "text/csv") or (file.filename or "").endswith(".csv")
    if not is_csv:
        raise HTTPException(status_code=422, detail="File must be CSV")

    tmp_path = None
    try:
        # 3. Write to temp file
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
            tmp.write(await file.read())
            tmp_path = tmp.name

        # 4. Wipe existing POS data for this business so the upload is a full replace,
        # not an append. Otherwise categories from prior uploads (e.g. cafe + kirana
        # + restaurant) all coexist and pollute the signals & Claude prompt.
        try:
            supabase.table("pos_records").delete().eq("business_id", business_id).execute()
            logger.info("[upload-pos] business_id=%s cleared existing pos_records", business_id)
        except Exception as exc:
            logger.error(
                "[upload-pos] business_id=%s failed to clear old pos_records: %s",
                business_id, exc,
            )
            raise HTTPException(status_code=500, detail="Failed to clear existing POS data")

        # 5. Ingest
        try:
            rows_inserted = pos_pipeline.ingest_pos_csv(tmp_path, business_id)
        except ValueError as exc:
            logger.error(
                "[upload-pos] business_id=%s CSV validation failed: %s", business_id, exc
            )
            raise HTTPException(status_code=422, detail=str(exc))
        except FileNotFoundError as exc:
            logger.error(
                "[upload-pos] business_id=%s temp file missing: %s", business_id, exc
            )
            raise HTTPException(status_code=500, detail="Internal error writing temp file")
        except RuntimeError as exc:
            logger.error(
                "[upload-pos] business_id=%s Supabase error: %s", business_id, exc
            )
            raise HTTPException(status_code=500, detail="Database error during POS ingestion")

    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except Exception:
                pass

    # Always invalidate the report cache on upload — even 0-row uploads imply the
    # user intends a refresh, and they may have meant to replace older data.
    try:
        supabase.table("health_scores").update({"report_payload": None}).eq(
            "business_id", business_id
        ).execute()
        logger.info("[upload-pos] business_id=%s report cache invalidated", business_id)
    except Exception as exc:
        logger.warning(
            "[upload-pos] business_id=%s cache invalidation failed (non-fatal): %s",
            business_id, exc,
        )

    logger.info("[upload-pos] business_id=%s rows_inserted=%d", business_id, rows_inserted)
    return UploadPOSResponse(
        business_id=business_id,
        rows_inserted=rows_inserted,
        status="success",
    )
