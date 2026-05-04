from typing import Literal, Optional
from pydantic import BaseModel, Field, field_validator, model_validator
from app.config import VALID_CATEGORIES


class OnboardRequest(BaseModel):
    """Request body for POST /onboard."""

    name: str = Field(..., min_length=1, max_length=200)
    place_id: Optional[str] = Field(None, min_length=10)
    category: str
    owner_name: str = Field(..., min_length=1, max_length=100)
    user_id: Optional[str] = None

    @field_validator("place_id")
    @classmethod
    def validate_place_id(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not v.startswith("ChIJ"):
            raise ValueError("place_id must start with ChIJ")
        return v

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: str) -> str:
        normalized = v.lower()
        if normalized not in VALID_CATEGORIES:
            raise ValueError(f"category must be one of {sorted(VALID_CATEGORIES)}")
        return normalized


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


class Review(BaseModel):
    """A single parsed Google review."""

    rating: int
    text: str
    relative_time: str


class Competitor(BaseModel):
    """A nearby competitor from Google Places."""

    name: str
    rating: float
    review_count: int
    place_id: str | None = None
    is_manual: bool = False
    sub_category: str | None = None


class CompetitorAnalysis(BaseModel):
    """AI-generated comparison of competitor reviews vs. ours."""

    themes: list[str] = []
    opportunities: list[str] = []
    analyzed_count: int = 0


class PosSignals(BaseModel):
    """POS signals used by the dashboard. All fields are optional — null when no POS data."""

    revenue_trend_pct: float | None = None
    revenue_trend_acute_pct: float | None = None    # 7d vs prior 28d (daily-averaged)
    revenue_trend_chronic_pct: float | None = None  # 90d vs prior 90d
    slow_categories: list[str] = []
    top_product: str | None = None
    aov_direction: str | None = None
    repeat_rate_pct: float | None = None
    repeat_rate_trend: float | None = None


class WeeklyRevenue(BaseModel):
    """One bar in the 8-week revenue chart."""

    week: str   # e.g. "W1Apr"
    rev: float


class CategoryRevenue(BaseModel):
    """One row in the revenue-by-category table."""

    name: str
    rev: float
    pct: float


class ReportResponse(BaseModel):
    """Response body for POST /generate-report/{business_id}."""

    business_id: str
    business_name: str
    address: str = ""
    category: str = ""
    owner_name: str = ""
    final_score: int
    band: str
    sub_scores: SubScores
    google_rating: float
    total_reviews: int
    reviews_per_month: float | None = None
    photo_count: int = 0
    reviews: list[Review]
    competitors: list[Competitor]
    insights: list[str]
    action: str
    dominant_complaint: str | None = None
    competitor_analysis: CompetitorAnalysis = CompetitorAnalysis()
    pos_signals: PosSignals = PosSignals()
    weekly_revenue: list[WeeklyRevenue] = []
    revenue_by_category: list[CategoryRevenue] = []
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
    dominant_complaint: str | None = None
    created_at: str


class HistoryResponse(BaseModel):
    """Response body for GET /history/{business_id}."""

    business_id: str
    count: int
    scores: list[HistoryScore]


class CompetitorPrefs(BaseModel):
    """User-controlled overrides for competitor auto-discovery."""

    radius_m: Literal[500, 800, 1000, 1500, 2000] = 800
    min_reviews: int = Field(0, ge=0, le=10000)
    max_reviews: Optional[int] = Field(None, ge=1, le=100000)
    subcategories: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_range(self) -> "CompetitorPrefs":
        if self.max_reviews is not None and self.max_reviews < self.min_reviews:
            raise ValueError("max_reviews must be >= min_reviews")
        return self


class PreferencesRequest(BaseModel):
    """Body for PUT /preferences/{business_id}."""

    mode: Literal["auto", "custom"]
    prefs: Optional[CompetitorPrefs] = None

    @model_validator(mode="after")
    def _check_prefs_required(self) -> "PreferencesRequest":
        if self.mode == "custom" and self.prefs is None:
            raise ValueError("prefs required when mode='custom'")
        return self


class CompetitorPreviewResponse(BaseModel):
    """Response body for GET /competitors/preview/{business_id}."""

    radius_m: int
    total_candidates: int
    review_buckets: dict[str, int]
    subcategory_counts: dict[str, int]
    top_examples: list[dict]
    own_subcategory: Optional[str] = None
