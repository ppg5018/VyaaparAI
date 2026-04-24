import os
import logging
import tempfile

from fastapi import APIRouter, HTTPException, UploadFile, File

from app.models import UploadPOSResponse
from app.database import supabase
from app.services import pos_pipeline

logger = logging.getLogger(__name__)

router = APIRouter()


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

        # 4. Ingest
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

    logger.info("[upload-pos] business_id=%s rows_inserted=%d", business_id, rows_inserted)
    return UploadPOSResponse(
        business_id=business_id,
        rows_inserted=rows_inserted,
        status="success",
    )
