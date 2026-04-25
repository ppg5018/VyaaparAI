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

# Claude model
CLAUDE_MODEL = "claude-sonnet-4-20250514"
MAX_TOKENS = 800

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
# 0.35 catches biz_003 Snacks whose slow_factor is exactly 0.30
SLOW_THRESHOLD = 0.35
MIN_REVENUE_PER_DAY_FOR_SLOW_FLAG = 50.0
AOV_CHANGE_THRESHOLD_PCT = 5
BATCH_SIZE = 500

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
