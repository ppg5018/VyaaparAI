import os
import time
import logging
import math

import googlemaps
import googlemaps.exceptions
from dotenv import load_dotenv

load_dotenv()
os.makedirs("logs", exist_ok=True)

_fmt = logging.Formatter("%(asctime)s — %(levelname)s — %(message)s")

logger = logging.getLogger("vyaparai.google_places")
logger.setLevel(logging.INFO)

if not logger.handlers:
    _fh = logging.FileHandler("logs/module1.log")
    _fh.setLevel(logging.INFO)
    _fh.setFormatter(_fmt)

    _ch = logging.StreamHandler()
    _ch.setLevel(logging.WARNING)
    _ch.setFormatter(_fmt)

    logger.addHandler(_fh)
    logger.addHandler(_ch)

_PLACE_FIELDS = [
    "name",
    "rating",
    "user_ratings_total",
    "reviews",
    "geometry",
    "business_status",
    "formatted_address",
]

_CATEGORY_TYPE_MAP = {
    "restaurant": "restaurant",
    "cafe": "cafe",
    "grocery": "grocery_or_supermarket",
    "retail": "store",
    "pharmacy": "pharmacy",
    "medical": "doctor",
    "manufacturing": "establishment",
    "distributor": "establishment",
    "default": "establishment",
}

# Lazy-initialised so importing this module never fails if the key is absent.
_gmaps_client: googlemaps.Client = None


def _get_client() -> googlemaps.Client:
    global _gmaps_client
    if _gmaps_client is None:
        api_key = os.getenv("GOOGLE_PLACES_API_KEY")
        if not api_key:
            raise RuntimeError(
                "GOOGLE_PLACES_API_KEY is not set. Add it to your .env file."
            )
        # retry_over_query_limit=False so OVER_QUERY_LIMIT raises ApiError
        # immediately instead of being silently retried for 60 s and then
        # surfacing as a generic Timeout.
        _gmaps_client = googlemaps.Client(
            key=api_key,
            retry_over_query_limit=False,
        )
    return _gmaps_client


# ── Public functions ───────────────────────────────────────────────────────────

def get_business_details(place_id: str) -> dict:
    """Fetch name, rating, reviews, and GPS from Google Places Details API.

    Raises:
        ValueError: place_id is invalid or not found.
        RuntimeError: quota exceeded, or timeout after one retry.
    """
    def _call():
        return _get_client().place(
            place_id,
            fields=_PLACE_FIELDS,
            reviews_sort="newest",
        )

    try:
        try:
            response = _call()
        except googlemaps.exceptions.Timeout:
            logger.warning(
                f"Google API timeout for place_id={place_id}, retrying in 2 s..."
            )
            time.sleep(2)
            response = _call()

    except googlemaps.exceptions.Timeout:
        logger.error(
            f"get_business_details failed for place_id={place_id}: "
            f"timeout after retry"
        )
        raise RuntimeError("Google API timeout after retry")

    except googlemaps.exceptions.ApiError as e:
        if e.status == "OVER_QUERY_LIMIT":
            logger.warning(
                f"Google API quota exceeded for place_id={place_id}"
            )
            raise RuntimeError("Google API quota exceeded")
        logger.error(
            f"get_business_details failed for place_id={place_id}: {e}"
        )
        raise ValueError(f"Invalid place_id: {place_id}")

    except Exception as e:
        logger.error(
            f"get_business_details failed for place_id={place_id}: {e}"
        )
        raise

    result = response.get("result", {})
    if not result:
        raise ValueError(f"Invalid place_id: {place_id}")

    business_status = result.get("business_status", "UNKNOWN")
    if business_status == "CLOSED_PERMANENTLY":
        logger.warning(
            f"Business '{result.get('name', place_id)}' "
            f"(place_id={place_id}) is CLOSED_PERMANENTLY"
        )

    geo = result.get("geometry", {}).get("location", {})
    return {
        "name": result.get("name", ""),
        "rating": float(result.get("rating", 0.0)),
        "total_reviews": int(result.get("user_ratings_total", 0)),
        "lat": float(geo.get("lat", 0.0)),
        "lng": float(geo.get("lng", 0.0)),
        "address": result.get("formatted_address", ""),
        "business_status": business_status,
        "raw_reviews": result.get("reviews", [])[:5],
    }


def parse_reviews(raw_reviews: list) -> list:
    """Normalise raw review objects into clean dicts.

    Always returns a list. Never raises.
    """
    if not raw_reviews:
        return []

    parsed = []
    for rev in raw_reviews:
        text = rev.get("text", "") or ""
        if len(text) > 200:
            text = text[:200] + "..."

        parsed.append({
            "rating": int(rev.get("rating", 0)),
            "text": text,
            "relative_time": rev.get("relative_time_description", ""),
            "timestamp": int(rev.get("time", 0)),
        })

    parsed.sort(key=lambda r: r["timestamp"], reverse=True)
    return parsed


def get_nearby_competitors(
    lat: float,
    lng: float,
    category: str,
    radius: int = 800,
    exclude_place_id: str = None,
) -> list:
    """Return up to 10 nearby competitors sorted by rating descending.

    Never raises — returns an empty list on any failure so one bad
    nearby-search never kills the pipeline.
    """
    place_type = _CATEGORY_TYPE_MAP.get(category, _CATEGORY_TYPE_MAP["default"])

    def _call():
        return _get_client().places_nearby(
            location=(lat, lng),
            radius=radius,
            type=place_type,
        )

    try:
        try:
            response = _call()
        except googlemaps.exceptions.Timeout:
            logger.warning(
                f"Competitor search timeout for ({lat},{lng}), retrying in 2 s..."
            )
            time.sleep(2)
            response = _call()

    except googlemaps.exceptions.Timeout:
        logger.warning(
            f"get_nearby_competitors failed for ({lat},{lng}): timeout after retry"
        )
        return []

    except Exception as e:
        logger.warning(
            f"get_nearby_competitors failed for ({lat},{lng}): {e}"
        )
        return []

    competitors = []
    for place in response.get("results", []):
        pid = place.get("place_id", "")
        if exclude_place_id and pid == exclude_place_id:
            continue
        competitors.append({
            "name": place.get("name", ""),
            "rating": float(place.get("rating", 0.0)),
            "review_count": int(place.get("user_ratings_total", 0)),
            "place_id": pid,
        })

    competitors.sort(key=lambda c: c["rating"], reverse=True)
    return competitors[:10]


def fetch_all_data(place_id: str, category: str) -> dict:
    """Single public entry point called by main.py.

    Raises if get_business_details() fails (caller handles it).
    Competitor failures are swallowed so one bad nearby-search never kills
    the pipeline.
    """
    details = get_business_details(place_id)
    reviews = parse_reviews(details["raw_reviews"])

    try:
        competitors = get_nearby_competitors(
            lat=details["lat"],
            lng=details["lng"],
            category=category,
            exclude_place_id=place_id,
        )
    except Exception as e:
        logger.warning(
            f"fetch_all_data: competitor fetch raised unexpectedly for "
            f"place_id={place_id}: {e}"
        )
        competitors = []

    logger.info(
        f"Fetched data for {details['name']}: "
        f"{details['total_reviews']} reviews, "
        f"{len(competitors)} competitors found"
    )

    return {
        "name": details["name"],
        "rating": details["rating"],
        "total_reviews": details["total_reviews"],
        "lat": details["lat"],
        "lng": details["lng"],
        "address": details["address"],
        "business_status": details["business_status"],
        "reviews": reviews,
        "competitors": competitors,
    }
