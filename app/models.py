from typing import Optional
from pydantic import BaseModel, Field, field_validator
from app.config import VALID_CATEGORIES


class OnboardRequest(BaseModel):
    """Request body for POST /onboard."""

    name: str = Field(..., min_length=1, max_length=200)
    place_id: str = Field(..., min_length=10)
    category: str
    owner_name: str = Field(..., min_length=1, max_length=100)

    @field_validator("place_id")
    @classmethod
    def validate_place_id(cls, v: str) -> str:
        """Ensure place_id starts with the Google Places ChIJ prefix."""
        if not v.startswith("ChIJ"):
            raise ValueError("place_id must start with ChIJ")
        return v

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: str) -> str:
        """Ensure category is one of the supported business types."""
        if v not in VALID_CATEGORIES:
            raise ValueError(f"category must be one of {sorted(VALID_CATEGORIES)}")
        return v


class OnboardResponse(BaseModel):
    """Response body for POST /onboard."""

    business_id: str
    name: str
    place_id: str
    google_verified_name: str


class UploadPOSResponse(BaseModel):
    """Response body for POST /upload-pos/{business_id}."""

    business_id: str
    rows_inserted: int
    status: str


class SubScores(BaseModel):
    """The three sub-scores that compose the final health score."""

    review_score: int
    competitor_score: int
    pos_score: int


class ReportResponse(BaseModel):
    """Response body for POST /generate-report/{business_id}."""

    business_id: str
    business_name: str
    final_score: int
    band: str
    sub_scores: SubScores
    google_rating: float
    total_reviews: int
    insights: list[str]
    action: str
    generated_at: str


class HistoryScore(BaseModel):
    """A single health score record returned in the history list."""

    final_score: int
    review_score: int
    competitor_score: int
    pos_score: int
    google_rating: float
    insights: list[str]
    action: str
    created_at: str


class HistoryResponse(BaseModel):
    """Response body for GET /history/{business_id}."""

    business_id: str
    count: int
    scores: list[HistoryScore]
