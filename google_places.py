import os
import time
import logging

import requests
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

_BASE_URL = "https://places.googleapis.com/v1"

_DETAILS_FIELDS = ",".join([
    "displayName",
    "rating",
    "userRatingCount",
    "reviews",
    "location",
    "businessStatus",
    "formattedAddress",
])

_NEARBY_FIELDS = ",".join([
    "places.displayName",
    "places.rating",
    "places.userRatingCount",
    "places.id",
])

_CATEGORY_TYPE_MAP = {
    "restaurant": "restaurant",
    "cafe": "cafe",
    "grocery": "grocery_store",
    "retail": "store",
    "pharmacy": "pharmacy",
    "medical": "doctor",
    "manufacturing": "point_of_interest",
    "distributor": "point_of_interest",
    "default": "point_of_interest",
}


def _api_key() -> str:
    key = os.getenv("GOOGLE_PLACES_API_KEY")
    if not key:
        raise RuntimeError("GOOGLE_PLACES_API_KEY is not set. Add it to your .env file.")
    return key


def _get(url: str, **kwargs) -> requests.Response:
    """GET with one retry on timeout."""
    try:
        return requests.get(url, timeout=10, **kwargs)
    except requests.Timeout:
        logger.warning(f"GET timeout for {url}, retrying in 2 s...")
        time.sleep(2)
        return requests.get(url, timeout=10, **kwargs)


def _post(url: str, **kwargs) -> requests.Response:
    """POST with one retry on timeout."""
    try:
        return requests.post(url, timeout=10, **kwargs)
    except requests.Timeout:
        logger.warning(f"POST timeout for {url}, retrying in 2 s...")
        time.sleep(2)
        return requests.post(url, timeout=10, **kwargs)


# ── Public functions ───────────────────────────────────────────────────────────

def get_business_details(place_id: str) -> dict:
    """Fetch name, rating, reviews, and GPS from Places API (New) v1.

    Raises:
        ValueError: place_id is invalid or not found.
        RuntimeError: quota exceeded, network error, or timeout after retry.
    """
    url = f"{_BASE_URL}/places/{place_id}"
    headers = {
        "X-Goog-Api-Key": _api_key(),
        "X-Goog-FieldMask": _DETAILS_FIELDS,
    }

    try:
        resp = _get(url, headers=headers)
    except requests.Timeout:
        logger.error(f"get_business_details timeout after retry for place_id={place_id}")
        raise RuntimeError("Google API timeout after retry")
    except requests.RequestException as e:
        logger.error(f"get_business_details network error for place_id={place_id}: {e}")
        raise RuntimeError(f"Network error: {e}")

    if resp.status_code == 403:
        logger.warning(f"Google API quota/auth error for place_id={place_id}: {resp.text}")
        raise RuntimeError("Google API quota exceeded or key unauthorised")

    if resp.status_code == 404 or resp.status_code == 400:
        logger.error(f"get_business_details bad place_id={place_id}: {resp.text}")
        raise ValueError(f"Invalid place_id: {place_id}")

    if resp.status_code != 200:
        logger.error(f"get_business_details HTTP {resp.status_code} for place_id={place_id}: {resp.text}")
        raise RuntimeError(f"Unexpected HTTP {resp.status_code}")

    result = resp.json()
    if not result:
        raise ValueError(f"Invalid place_id: {place_id}")

    business_status = result.get("businessStatus", "UNKNOWN")
    name = result.get("displayName", {}).get("text", "")

    if business_status == "CLOSED_PERMANENTLY":
        logger.warning(f"Business '{name}' (place_id={place_id}) is CLOSED_PERMANENTLY")

    loc = result.get("location", {})
    return {
        "name": name,
        "rating": float(result.get("rating", 0.0)),
        "total_reviews": int(result.get("userRatingCount", 0)),
        "lat": float(loc.get("latitude", 0.0)),
        "lng": float(loc.get("longitude", 0.0)),
        "address": result.get("formattedAddress", ""),
        "business_status": business_status,
        "raw_reviews": result.get("reviews", [])[:5],
    }


def parse_reviews(raw_reviews: list) -> list:
    """Normalise raw review objects from Places API (New) into clean dicts.

    Always returns a list. Never raises.
    """
    if not raw_reviews:
        return []

    parsed = []
    for rev in raw_reviews:
        text = rev.get("text", {}).get("text", "") or ""
        if len(text) > 200:
            text = text[:200] + "..."

        # publishTime is an RFC3339 string; store as-is for sorting
        publish_time = rev.get("publishTime", "")

        parsed.append({
            "rating": int(rev.get("rating", 0)),
            "text": text,
            "relative_time": rev.get("relativePublishTimeDescription", ""),
            "publish_time": publish_time,
        })

    parsed.sort(key=lambda r: r["publish_time"], reverse=True)
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
    url = f"{_BASE_URL}/places:searchNearby"
    headers = {
        "X-Goog-Api-Key": _api_key(),
        "X-Goog-FieldMask": _NEARBY_FIELDS,
        "Content-Type": "application/json",
    }
    body = {
        "includedTypes": [place_type],
        "maxResultCount": 20,
        "locationRestriction": {
            "circle": {
                "center": {"latitude": lat, "longitude": lng},
                "radius": float(radius),
            }
        },
    }

    try:
        resp = _post(url, headers=headers, json=body)
    except requests.Timeout:
        logger.warning(f"get_nearby_competitors timeout after retry for ({lat},{lng})")
        return []
    except requests.RequestException as e:
        logger.warning(f"get_nearby_competitors network error for ({lat},{lng}): {e}")
        return []

    if resp.status_code != 200:
        logger.warning(
            f"get_nearby_competitors HTTP {resp.status_code} for ({lat},{lng}): {resp.text}"
        )
        return []

    competitors = []
    for place in resp.json().get("places", []):
        pid = place.get("id", "")
        if exclude_place_id and pid == exclude_place_id:
            continue
        competitors.append({
            "name": place.get("displayName", {}).get("text", ""),
            "rating": float(place.get("rating", 0.0)),
            "review_count": int(place.get("userRatingCount", 0)),
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
