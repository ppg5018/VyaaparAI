import math
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
    "photo",   # singular — the API field is "photo", not "photos"
    "price_level",
    # NOTE: "popular_times" is not available in any official Google Places API.
    # That data is shown in the Maps UI but is never exposed via an API field.
    # To get it, a third-party scraper (e.g. Apify populartimes actor) is needed.
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
    # Google returns up to 10 photo references — count is a proxy for visual
    # engagement. Recency is not available via the API (no timestamps on photos).
    photo_count = len(result.get("photos") or result.get("photo") or [])
    raw_price = result.get("price_level")
    price_level = int(raw_price) if isinstance(raw_price, (int, float)) else None
    return {
        "name": result.get("name", ""),
        "rating": float(result.get("rating", 0.0)),
        "total_reviews": int(result.get("user_ratings_total", 0)),
        "lat": float(geo.get("lat", 0.0)),
        "lng": float(geo.get("lng", 0.0)),
        "address": result.get("formatted_address", ""),
        "business_status": business_status,
        "raw_reviews": result.get("reviews", []),
        "photo_count": photo_count,
        "price_level": price_level,
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


def _parse_place(place: dict) -> dict:
    raw_price = place.get("price_level")
    price_level = int(raw_price) if isinstance(raw_price, (int, float)) else None
    return {
        "name": place.get("name", ""),
        "rating": float(place.get("rating", 0.0)),
        "review_count": int(place.get("user_ratings_total", 0)),
        "place_id": place.get("place_id", ""),
        "price_level": price_level,
        "types": place.get("types", []),
    }


def get_nearby_competitors(
    lat: float,
    lng: float,
    category: str,
    radius: int = COMPETITOR_RADIUS_METERS,
    exclude_place_id: str | None = None,
) -> list:
    """Return nearby competitors via two discovery strategies, deduped.

    1) Prominence-ranked nearby search, paginated up to 3 pages (~60 results).
       Default Google ordering — surfaces well-reviewed, popular places first.
    2) Distance-ranked nearby search, single page (~20 closest, no radius cap).
       Mall locations especially need this — strategy (1) collapses to the
       same prominent tenants per page; distance-rank surfaces the literal
       nearest stores even if they don't rank as prominent.

    Never raises — returns [] on any failure so a flaky Nearby Search never
    kills the pipeline.
    """
    place_type = _CATEGORY_TYPE_MAP.get(category, _CATEGORY_TYPE_MAP["default"])
    client = _get_client()
    raw_results: list = []

    # Strategy 1: prominence-ranked, paginated up to 2 pages (~40 results).
    # Each extra page costs a ~2s next_page_token activation wait, so we cap
    # at 2 — brand top-up + distance-rank cover the long tail.
    page_token: str | None = None
    for page in range(2):
        try:
            if page_token:
                response = client.places_nearby(page_token=page_token)
            else:
                response = client.places_nearby(
                    location=(lat, lng), radius=radius, type=place_type,
                )
        except googlemaps.exceptions.Timeout:
            logger.warning("places_nearby (prominence p%d) timeout for (%s,%s)", page, lat, lng)
            break
        except Exception as exc:
            logger.warning("places_nearby (prominence p%d) failed for (%s,%s): %s", page, lat, lng, exc)
            break
        raw_results.extend(response.get("results", []))
        page_token = response.get("next_page_token")
        if not page_token:
            break
        # Google's next_page_token activates after a brief delay (~2s).
        time.sleep(2.0)

    # Strategy 2: distance-ranked, single page. Google rejects radius+rank_by together.
    try:
        response = client.places_nearby(
            location=(lat, lng), rank_by="distance", type=place_type,
        )
        raw_results.extend(response.get("results", []))
    except Exception as exc:
        logger.warning("places_nearby (distance) failed for (%s,%s): %s", lat, lng, exc)

    # Dedupe by place_id.
    seen: set[str] = set()
    competitors: list[dict] = []
    for place in raw_results:
        pid = place.get("place_id", "")
        if not pid or pid in seen:
            continue
        if exclude_place_id and pid == exclude_place_id:
            continue
        seen.add(pid)
        competitors.append(_parse_place(place))

    competitors.sort(key=lambda c: c["rating"], reverse=True)
    logger.info(
        "get_nearby_competitors: %d unique candidates for (%s,%s) type=%s (prominence+distance)",
        len(competitors), lat, lng, place_type,
    )
    # Do NOT cap here — pass all Google results to the competitor matcher so
    # it can filter by type/price/sub-category before the final cap is applied.
    return competitors


def text_search_brand(
    brand: str,
    lat: float,
    lng: float,
    radius: int = COMPETITOR_RADIUS_METERS,
) -> list:
    """Find branded stores via Google Text Search, hard-clipped to `radius` metres.

    Used as a top-up for retail competitor discovery so that same-mall
    brand stores (Adidas, Puma, etc.) that fall off `places_nearby`'s
    prominence-ranked first page still get surfaced. Google biases (not
    clips) by location, so we filter by haversine after the call.

    Returns the same shape as get_nearby_competitors. Empty on any failure.
    """
    try:
        response = _get_client().places(
            query=brand, location=(lat, lng), radius=radius,
        )
    except Exception as exc:
        logger.warning("text_search_brand failed for '%s' near (%s,%s): %s", brand, lat, lng, exc)
        return []

    cos_lat = math.cos(math.radians(lat))
    out: list[dict] = []
    for place in response.get("results", []):
        geo = place.get("geometry", {}).get("location", {})
        plat, plng = geo.get("lat"), geo.get("lng")
        if plat is None or plng is None:
            continue
        # Equirectangular approximation — accurate to <1% at sub-2km radii.
        dy = (plat - lat) * 111_000
        dx = (plng - lng) * 111_000 * cos_lat
        if math.hypot(dx, dy) > radius:
            continue
        if not place.get("place_id"):
            continue
        out.append(_parse_place(place))
    return out


def autocomplete_places(query: str) -> list[dict]:
    """Return up to 5 autocomplete suggestions for a business name query.

    Each result has: place_id, name, address.
    Returns empty list on any failure.
    """
    try:
        results = _get_client().places_autocomplete(
            input_text=query,
            types=["establishment"],
        )
        suggestions = []
        for r in results[:5]:
            fmt = r.get("structured_formatting", {})
            suggestions.append({
                "place_id": r.get("place_id", ""),
                "name":     fmt.get("main_text") or r.get("description", ""),
                "address":  fmt.get("secondary_text") or "",
            })
        return suggestions
    except Exception as exc:
        logger.warning("autocomplete_places failed for '%s': %s", query, exc)
        return []


def find_place_by_name(name: str) -> str | None:
    """Search Google Places by business name and return the best-match place_id.

    Returns None on any failure so callers can fall back gracefully.
    """
    try:
        response = _get_client().find_place(
            input=name,
            input_type="textquery",
            fields=["place_id", "name"],
        )
        candidates = response.get("candidates", [])
        if candidates:
            place_id = candidates[0].get("place_id")
            logger.info("find_place_by_name: '%s' → %s", name, place_id)
            return place_id
    except Exception as exc:
        logger.warning("find_place_by_name failed for '%s': %s", name, exc)
    return None


def fetch_all_data(place_id: str, category: str) -> dict:
    """Fetch business details + nearby competitor candidates from Google Places.

    The competitor list returned here is RAW — it has not been filtered for
    similarity yet. `competitor_pipeline.run()` consumes this list and applies
    the embedding-based matching layer.

    Competitor failures are swallowed so a flaky Nearby Search never kills
    the report pipeline. Raises if get_business_details() fails (caller handles).
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
            "fetch_all_data: nearby competitor fetch failed for place_id=%s: %s",
            place_id, exc,
        )
        competitors = []

    logger.info(
        "Fetched data for %s: %d reviews, %d raw competitor candidates",
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
        "photo_count": details.get("photo_count", 0),
        "price_level": details.get("price_level"),
        "reviews": reviews,
        "competitors": competitors,
    }
