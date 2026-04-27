import os
from dotenv import load_dotenv

load_dotenv()

# API keys
ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
GOOGLE_PLACES_API_KEY: str = os.getenv("GOOGLE_PLACES_API_KEY", "")
SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY: str = os.getenv("SUPABASE_KEY", "")
APIFY_TOKEN: str = os.getenv("APIFY_TOKEN", "")

# Apify
APIFY_REVIEWS_ACTOR = "compass~google-maps-reviews-scraper"
REVIEW_CACHE_TTL_DAYS_OWN = 7         # Re-sync user's own reviews weekly
REVIEW_CACHE_TTL_DAYS_COMPETITOR = 30 # Re-sync competitor reviews monthly

# Review time-decay (kept for weighted-count fallback)
REVIEW_HALFLIFE_MONTHS = 6  # months at which a review's volume weight drops to 0.5

# Review velocity scoring
REVIEW_VELOCITY_LOOKBACK_MONTHS = 6   # window for rate calculation
REVIEW_VELOCITY_FULL_MARKS_RATE = 8.0 # reviews/month at which velocity scores full 25 pts

# Claude models
CLAUDE_MODEL = "claude-sonnet-4-20250514"
HAIKU_MODEL  = "claude-haiku-4-5-20251001"   # fast + cheap — used for review classification
MAX_TOKENS = 800
HAIKU_MAX_TOKENS = 4096  # classifier returns up to 50 JSON objects

# Health score weights
REVIEW_WEIGHT = 0.40
COMPETITOR_WEIGHT = 0.25
POS_WEIGHT = 0.35

# Health score thresholds
HEALTHY_THRESHOLD = 80
WATCH_THRESHOLD = 60
NO_COMPETITORS_NEUTRAL = 65
NO_POS_DATA_NEUTRAL = 50

# POS pipeline
MIN_REVENUE_PER_DAY_FOR_SLOW_FLAG = 50.0
AOV_CHANGE_THRESHOLD_PCT = 5
BATCH_SIZE = 500

# Category-specific POS thresholds
# growth_full:    trend % at which revenue_pts maxes out (50 pts)
# growth_neutral: trend % where revenue_pts is at midpoint (25 pts) — "acceptable floor"
# growth_floor:   trend % below which revenue_pts is 0
# slow_threshold: ratio of recent_avg/prior_avg below which a category is flagged slow
CATEGORY_POS_THRESHOLDS: dict[str, dict] = {
    "restaurant":    {"growth_full": 15, "growth_neutral":  -5, "growth_floor": -30, "slow_threshold": 0.40},
    "cafe":          {"growth_full": 15, "growth_neutral":  -5, "growth_floor": -30, "slow_threshold": 0.40},
    "pharmacy":      {"growth_full":  8, "growth_neutral":  -2, "growth_floor": -20, "slow_threshold": 0.50},
    "medical":       {"growth_full":  8, "growth_neutral":  -2, "growth_floor": -20, "slow_threshold": 0.50},
    "retail":        {"growth_full": 20, "growth_neutral": -10, "growth_floor": -40, "slow_threshold": 0.30},
    "grocery":       {"growth_full": 20, "growth_neutral": -10, "growth_floor": -40, "slow_threshold": 0.30},
    "manufacturing": {"growth_full": 30, "growth_neutral": -20, "growth_floor": -50, "slow_threshold": 0.25},
    "distributor":   {"growth_full": 30, "growth_neutral": -20, "growth_floor": -50, "slow_threshold": 0.25},
}
DEFAULT_POS_THRESHOLDS: dict = {
    "growth_full": 10, "growth_neutral": 0, "growth_floor": -30, "slow_threshold": 0.35
}

# Google Places
COMPETITOR_RADIUS_METERS = 800
MAX_COMPETITORS = 10
MAX_REVIEW_TEXT_LENGTH = 200

# Valid business categories
VALID_CATEGORIES: set[str] = {
    "restaurant", "cafe", "retail", "grocery",
    "pharmacy", "medical", "manufacturing", "distributor",
}

# Logging
LOG_FILE = "logs/module1.log"
LOG_FORMAT = "%(asctime)s — %(levelname)s — %(message)s"
