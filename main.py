import os
import logging
import tempfile
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, UploadFile, File
from pydantic import BaseModel, Field, field_validator
from supabase import create_client
from dotenv import load_dotenv

import google_places
import pos_pipeline
import health_score
import insights

load_dotenv()
os.makedirs("logs", exist_ok=True)

_fmt = logging.Formatter("%(asctime)s — %(levelname)s — %(message)s")
logger = logging.getLogger("vyaparai.main")
logger.setLevel(logging.DEBUG)
if not logger.handlers:
    _fh = logging.FileHandler("logs/module1.log", encoding="utf-8")
    _fh.setLevel(logging.DEBUG)
    _fh.setFormatter(_fmt)
    _ch = logging.StreamHandler()
    _ch.setLevel(logging.WARNING)
    _ch.setFormatter(_fmt)
    logger.addHandler(_fh)
    logger.addHandler(_ch)

supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

app = FastAPI(title="VyaparAI Module 1", version="0.1.0")

VALID_CATEGORIES = {
    "restaurant", "cafe", "retail", "grocery", "pharmacy",
    "medical", "manufacturing", "distributor",
}


class OnboardRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    place_id: str = Field(..., min_length=10)
    category: str
    owner_name: str = Field(..., min_length=1, max_length=100)

    @field_validator("place_id")
    @classmethod
    def validate_place_id(cls, v: str) -> str:
        if not v.startswith("ChIJ"):
            raise ValueError("place_id must start with ChIJ")
        return v

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: str) -> str:
        if v not in VALID_CATEGORIES:
            raise ValueError(f"category must be one of {sorted(VALID_CATEGORIES)}")
        return v


# ── Endpoints ──────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {"status": "VyaparAI Module 1 running"}


@app.post("/onboard", status_code=201)
def onboard(req: OnboardRequest):
    # 1. Validate place_id via Google Places
    try:
        biz_details = google_places.get_business_details(req.place_id)
    except ValueError as exc:
        logger.error("[onboard] place_id=%s invalid: %s", req.place_id, exc)
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        logger.error("[onboard] place_id=%s Google API unavailable: %s", req.place_id, exc)
        raise HTTPException(
            status_code=503, detail="Google Places API unavailable — try again later"
        )

    # 2. Check for duplicate
    existing = (
        supabase.table("businesses").select("id").eq("place_id", req.place_id).execute()
    )
    if existing.data:
        existing_id = existing.data[0]["id"]
        logger.warning(
            "[onboard] place_id=%s already exists as business_id=%s",
            req.place_id, existing_id,
        )
        raise HTTPException(
            status_code=409,
            detail={"error": "Business already onboarded", "business_id": existing_id},
        )

    # 3. Insert
    result = supabase.table("businesses").insert({
        "name": req.name,
        "place_id": req.place_id,
        "category": req.category,
        "owner_name": req.owner_name,
        "is_active": True,
    }).execute()
    row = result.data[0]

    logger.info("[onboard] Registered business_id=%s name=%s", row["id"], req.name)
    return {
        "business_id": row["id"],
        "name": row["name"],
        "place_id": row["place_id"],
        "google_verified_name": biz_details["name"],
    }


@app.post("/upload-pos/{business_id}")
async def upload_pos(business_id: str, file: UploadFile = File(...)):
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

    logger.info(
        "[upload-pos] business_id=%s rows_inserted=%d", business_id, rows_inserted
    )
    return {"business_id": business_id, "rows_inserted": rows_inserted, "status": "success"}


@app.post("/generate-report/{business_id}")
def generate_report(business_id: str):
    # 1. Look up business
    biz_result = supabase.table("businesses").select("*").eq("id", business_id).execute()
    if not biz_result.data:
        logger.error("[generate-report] business_id=%s not found", business_id)
        raise HTTPException(status_code=404, detail=f"Business {business_id} not found")

    biz = biz_result.data[0]

    # 2. Fetch Google data
    try:
        google_data = google_places.fetch_all_data(biz["place_id"], biz["category"])
    except Exception as exc:
        logger.error(
            "[generate-report] business_id=%s Google fetch failed: %s", business_id, exc
        )
        raise HTTPException(status_code=502, detail="Failed to fetch Google data")

    # 3. POS signals — never raises
    signals = pos_pipeline.pos_signals(business_id, days=30)

    # 4. Sub-scores
    r_score = health_score.review_score(
        rating=google_data["rating"],
        total_reviews=google_data["total_reviews"],
        recent_reviews=google_data["reviews"],
    )
    c_score = health_score.competitor_score(
        my_rating=google_data["rating"],
        competitors=google_data["competitors"],
    )
    p_score = health_score.pos_score(signals)

    # 5. Final score + band
    score_result = health_score.calculate_health_score(r_score, c_score, p_score)

    # 6. Generate insights via Claude
    try:
        insights_result = insights.generate_insights(
            business_data=google_data,
            scores=score_result,
            pos_signals=signals,
        )
    except RuntimeError as exc:
        logger.error(
            "[generate-report] business_id=%s insight generation failed: %s", business_id, exc
        )
        raise HTTPException(status_code=500, detail="Insight generation failed")

    # 7. Persist to health_scores
    supabase.table("health_scores").insert({
        "business_id": business_id,
        "final_score": score_result["final_score"],
        "review_score": r_score,
        "competitor_score": c_score,
        "pos_score": p_score,
        "google_rating": google_data["rating"],
        "total_reviews": google_data["total_reviews"],
        "insights": insights_result["insights"],
        "action": insights_result["action"],
    }).execute()

    logger.info(
        "[generate-report] business_id=%s score=%d band=%s",
        business_id, score_result["final_score"], score_result["band"],
    )

    return {
        "business_id": business_id,
        "business_name": google_data["name"],
        "final_score": score_result["final_score"],
        "band": score_result["band"],
        "sub_scores": {
            "review_score": r_score,
            "competitor_score": c_score,
            "pos_score": p_score,
        },
        "google_rating": google_data["rating"],
        "total_reviews": google_data["total_reviews"],
        "insights": insights_result["insights"],
        "action": insights_result["action"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/history/{business_id}")
def history(business_id: str, limit: int = 12):
    # 1. Validate business exists
    biz = supabase.table("businesses").select("id").eq("id", business_id).execute()
    if not biz.data:
        logger.error("[history] business_id=%s not found", business_id)
        raise HTTPException(status_code=404, detail=f"Business {business_id} not found")

    limit = max(1, min(52, limit))

    # 2. Query history, newest first
    result = (
        supabase.table("health_scores")
        .select("*")
        .eq("business_id", business_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )

    scores = [
        {
            "final_score": row["final_score"],
            "review_score": row["review_score"],
            "competitor_score": row["competitor_score"],
            "pos_score": row["pos_score"],
            "google_rating": row["google_rating"],
            "insights": row["insights"],
            "action": row["action"],
            "created_at": row["created_at"],
        }
        for row in result.data
    ]

    return {"business_id": business_id, "count": len(scores), "scores": scores}
