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

# Competitor matching filters
MIN_COMPETITOR_REVIEWS = 20   # default — restaurants/cafes get many reviews so 20 is meaningful
# Mall/brand retail stores have far fewer Google Maps reviews than restaurants.
# Lower thresholds per category so Bata, Adidas, Puma etc. aren't dropped.
CATEGORY_MIN_COMPETITOR_REVIEWS: dict[str, int] = {
    "restaurant":    20,
    "cafe":          20,
    "retail":         5,
    "grocery":        5,
    "pharmacy":       5,
    "medical":        5,
    "manufacturing":  3,
    "distributor":    3,
}
PRICE_TIER_TOLERANCE = 1      # keep competitors within ±N price levels of my own
MIN_COMPETITORS_AFTER_FILTER = 3   # if filters strip below this, fall back to the unfiltered set

# Google primary types that are excluded when comparing against each user category.
# Catches the "Indian dhaba listed under restaurant + ice cream parlour also under restaurant" problem.
CATEGORY_EXCLUSION_MAP: dict[str, set[str]] = {
    "restaurant": {
        "ice_cream_shop", "bakery", "cafe", "meal_takeaway", "meal_delivery",
        "convenience_store", "supermarket", "grocery_or_supermarket",
        "liquor_store", "bar", "night_club",
    },
    "cafe": {
        "ice_cream_shop", "liquor_store", "bar", "night_club",
        "grocery_or_supermarket", "pharmacy",
    },
    "retail": {
        "pharmacy", "bank", "atm", "gas_station",
        "restaurant", "cafe", "hospital", "doctor",
    },
    "pharmacy": {
        "convenience_store", "supermarket", "grocery_or_supermarket",
        "restaurant", "cafe", "liquor_store",
    },
    "grocery": {
        "restaurant", "cafe", "pharmacy", "bank", "atm", "gas_station",
    },
}

# Name keywords (case-insensitive substring match) that indicate a competitor
# is a different business type than what Google's `types` field suggests.
# Keep keywords specific — generic terms like "shop" or "store" cause false positives.
NAME_EXCLUSION_KEYWORDS: dict[str, list[str]] = {
    "restaurant": [
        # Ice cream
        "ice cream", "icecream", "naturals", "baskin", "robbins",
        "kwality", "softy", "gelato", "frozen yogurt", "kulfi",
        # Bakery / cake
        "bakery", "bakers", "cake", "monginis", "bread", "patisserie",
        "pastry", "muffin", "brownie",
        # Sweets / mithai
        "sweets", "sweet shop", "mithai", "halwai", "namkeen",
        "ladoo", "rasgulla", "halwa",
        # Café / coffee
        "café", "cafe", "coffee", "starbucks", "ccd", "barista",
        "tea house", "chai",
        # Juice / beverages
        "juice bar", "juice center", "lassi",
        # Pan / tobacco
        "pan shop", "paan",
    ],
    "cafe": [
        "liquor", "wine", "beer", "bar", "pub", "brewery",
        "pharmacy", "chemist", "medical",
    ],
    "retail": [
        # Cross-category (not retail at all)
        "pharmacy", "chemist", "hospital", "clinic",
        "bank", "atm", "petrol", "fuel",
        # Intra-retail sub-category leaks — catches obvious mismatches when
        # Haiku tagging is unavailable. Specific brand/keyword tokens; avoid
        # generic words ("store", "shop") that would over-match.
        "optician", "opticals", "spectacle",
        "mattress", "sleepwell", "kurlon",
        "samsung", "lg ", "sony", "vivo", "oppo",
        "jockey", "vip", "rupa",
        "tanishq", "kalyan jewellers", "joyalukkas",
    ],
    "pharmacy": [
        "restaurant", "dhaba", "hotel", "café", "cafe",
        "sweets", "bakery",
    ],
}

# Sub-category vocabulary per parent category. Haiku picks one tag per business.
# Keep lists short — too many options dilutes Haiku's accuracy.
SUBCATEGORIES_BY_CATEGORY: dict[str, list[str]] = {
    "restaurant": [
        "north_indian", "south_indian", "chinese", "biryani", "fast_food",
        "pure_veg_thali", "non_veg_grill", "multicuisine", "cafe_bakery", "general",
    ],
    "cafe": [
        "coffee_shop", "bakery", "dessert_parlour", "chai_stall", "cafe_bistro", "general",
    ],
    "retail": [
        "clothing", "electronics", "footwear", "home_goods", "general_store", "general",
    ],
    "grocery": ["supermarket", "kirana", "organic", "general"],
    "pharmacy": ["chain", "independent", "general"],
    "medical": ["clinic", "diagnostic", "specialist", "general"],
    "manufacturing": ["general"],
    "distributor": ["general"],
}

# Valid business categories
VALID_CATEGORIES: set[str] = {
    "restaurant", "cafe", "retail", "grocery",
    "pharmacy", "medical", "manufacturing", "distributor",
}

# Logging
LOG_FILE = "logs/module1.log"
LOG_FORMAT = "%(asctime)s — %(levelname)s — %(message)s"
