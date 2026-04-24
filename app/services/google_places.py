import time
import logging

import googlemaps
import googlemaps.exceptions

from app.config import (
    GOOGLE_PLACES_API_KEY,
    COMPETITOR_RADIUS_METERS,
    MAX_COMPETITORS,
    MAX_REVIEW_TEXT_LENGTH,
)

logger = logging.getLogger(__name__)

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
_gmaps_client: googlemaps.Client | None = None


def _get_client() -> googlemaps.Client:
    """Return the shared googlemaps client, initialising it on first call."""
    global _gmaps_client
    if _gmaps_client is None:
        if not GOOGLE_PLACES_API_KEY:
            raise RuntimeError(
                "GOOGLE_PLACES_API_KEY is not set. Add it to your .env file."
            )
        # retry_over_query_limit=False: OVER_QUERY_LIMIT raises ApiError
        # immediately instead of being silently retried for 60 s.
        _gmaps_client = googlemaps.Client(
            key=GOOGLE_PLACES_API_KEY,
            retry_over_query_limit=False,
        )
    return _gmaps_client


def get_business_details(place_id: str) -> dict:
    """Fetch name, rating, reviews, and GPS from Google Places Details API.

    Raises:
        ValueError: place_id is invalid or not found.
        RuntimeError: quota exceeded, or timeout after one retry.
    """
    def _call() -> dict:
        return _get_client().place(
            place_id,
            fields=_PLACE_FIELDS,
            reviews_sort="newest",
        )

    try:
        try:
            response = _call()
        except googlemaps.exceptions.Timeout:
            logger.warning("Google API timeout for place_id=%s, retrying in 2s", place_id)
            time.sleep(2)
            response = _call()

    except googlemaps.exceptions.Timeout:
        logger.error("get_business_details timeout after retry for place_id=%s", place_id)
        raise RuntimeError("Google API timeout after retry")

    except googlemaps.exceptions.ApiError as exc:
        if exc.status == "OVER_QUERY_LIMIT":
            logger.warning("Google API quota exceeded for place_id=%s", place_id)
            raise RuntimeError("Google API quota exceeded")
        logger.error("get_business_details ApiError for place_id=%s: %s", place_id, exc)
        raise ValueError(f"Invalid place_id: {place_id}")

    except Exception as exc:
        logger.error("get_business_details failed for place_id=%s: %s", place_id, exc)
        raise

    result = response.get("result", {})
    if not result:
        raise ValueError(f"Invalid place_id: {place_id}")

    business_status = result.get("business_status", "UNKNOWN")
    if business_status == "CLOSED_PERMANENTLY":
        logger.warning(
            "Business '%s' (place_id=%s) is CLOSED_PERMANENTLY",
            result.get("name", place_id), place_id,
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
    """Normalise raw Google review objects into clean dicts.

    Always returns a list. Never raises.
    """
    if not raw_reviews:
        return []

    parsed = []
    for rev in raw_reviews:
        text = rev.get("text", "") or ""
        if len(text) > MAX_REVIEW_TEXT_LENGTH:
            text = text[:MAX_REVIEW_TEXT_LENGTH] + "..."

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
    radius: int = COMPETITOR_RADIUS_METERS,
    exclude_place_id: str | None = None,
) -> list:
    """Return up to MAX_COMPETITORS nearby competitors sorted by rating descending.

    Never raises — returns an empty list on any failure so one bad
    nearby-search never kills the pipeline.
    """
    place_type = _CATEGORY_TYPE_MAP.get(category, _CATEGORY_TYPE_MAP["default"])

    def _call() -> dict:
        return _get_client().places_nearby(
            location=(lat, lng),
            radius=radius,
            type=place_type,
        )

    try:
        try:
            response = _call()
        except googlemaps.exceptions.Timeout:
            logger.warning("Competitor search timeout for (%s,%s), retrying in 2s", lat, lng)
            time.sleep(2)
            response = _call()

    except googlemaps.exceptions.Timeout:
        logger.warning("get_nearby_competitors timeout after retry for (%s,%s)", lat, lng)
        return []

    except Exception as exc:
        logger.warning("get_nearby_competitors failed for (%s,%s): %s", lat, lng, exc)
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
    return competitors[:MAX_COMPETITORS]


def fetch_all_data(place_id: str, category: str) -> dict:
    """Fetch business details and nearby competitors from Google Places.

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
    except Exception as exc:
        logger.warning(
            "fetch_all_data: competitor fetch raised unexpectedly for place_id=%s: %s",
            place_id, exc,
        )
        competitors = []

    logger.info(
        "Fetched data for %s: %d reviews, %d competitors",
        details["name"], details["total_reviews"], len(competitors),
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
