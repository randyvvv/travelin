"""Places API (New) client, used to geocode destinations and to verify places."""

from typing import Any

import httpx

from .config import get_settings

SEARCH_TEXT_URL = "https://places.googleapis.com/v1/places:searchText"
PLACE_DETAILS_URL = "https://places.googleapis.com/v1/places/{place_id}"
PHOTO_MEDIA_URL = "https://places.googleapis.com/v1/{photo_name}/media"

PHOTO_DETAILS_FIELD_MASK = ",".join(
    ("id", "photos.name", "photos.authorAttributions", "photos.googleMapsUri", "googleMapsUri")
)
PHOTO_SEARCH_FIELD_MASK = ",".join(
    (
        "places.id",
        "places.displayName",
        "places.photos.name",
        "places.photos.authorAttributions",
        "places.photos.googleMapsUri",
        "places.googleMapsUri",
    )
)

# Everything a place card, the planner, and the validator need.
PLACE_FIELDS = (
    "id",
    "displayName",
    "formattedAddress",
    "location",
    "types",
    "googleMapsUri",
    "regularOpeningHours",
    "rating",
    "userRatingCount",
    "priceLevel",
    "priceRange",
    "photos",
)
SEARCH_FIELD_MASK = ",".join(f"places.{field}" for field in PLACE_FIELDS)
DETAIL_FIELD_MASK = ",".join(PLACE_FIELDS)

# Home only needs enough current data to render a recommendation card. Keep
# photos out of this lookup because the photo endpoint resolves them lazily.
HOME_IDEA_FIELD_MASK = ",".join(
    (
        "id",
        "displayName",
        "formattedAddress",
        "location",
        "types",
        "googleMapsUri",
        "rating",
        "userRatingCount",
    )
)

_client: httpx.AsyncClient | None = None


class PlacesUnavailableError(RuntimeError):
    """Raised when no Places API key is configured."""


def _api_key() -> str:
    api_key = get_settings().places_api_key
    if not api_key:
        raise PlacesUnavailableError("PLACES_API_KEY is not set")
    return api_key


def _http() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=10)
    return _client


async def search_text(
    query: str,
    *,
    field_mask: str,
    bias: tuple[float, float, float] | None = None,
    page_size: int = 3,
) -> list[dict[str, Any]]:
    """Text Search. `bias` is (lat, lng, radius_m); results may still fall outside it."""
    body: dict[str, Any] = {
        "textQuery": query,
        "languageCode": "en",
        "regionCode": "ID",
        "pageSize": page_size,
    }
    if bias is not None:
        lat, lng, radius = bias
        body["locationBias"] = {
            "circle": {"center": {"latitude": lat, "longitude": lng}, "radius": radius}
        }

    response = await _http().post(
        SEARCH_TEXT_URL,
        json=body,
        headers={"X-Goog-Api-Key": _api_key(), "X-Goog-FieldMask": field_mask},
    )
    response.raise_for_status()
    return response.json().get("places", [])


async def get_place(place_id: str) -> dict[str, Any] | None:
    """Place Details (New); None if Google has no such place."""
    response = await _http().get(
        PLACE_DETAILS_URL.format(place_id=place_id),
        params={"languageCode": "en", "regionCode": "ID"},
        headers={"X-Goog-Api-Key": _api_key(), "X-Goog-FieldMask": DETAIL_FIELD_MASK},
    )
    if response.status_code in (400, 404):
        return None
    response.raise_for_status()
    return response.json()


async def fresh_home_idea_details(place_id: str) -> dict[str, Any] | None:
    """Resolve only the current fields needed to display a Home idea card."""
    response = await _http().get(
        PLACE_DETAILS_URL.format(place_id=place_id),
        params={"languageCode": "en", "regionCode": "ID"},
        headers={"X-Goog-Api-Key": _api_key(), "X-Goog-FieldMask": HOME_IDEA_FIELD_MASK},
    )
    if response.status_code in (400, 404):
        return None
    response.raise_for_status()
    return response.json()


async def fresh_place_photo(place_id: str) -> dict[str, Any] | None:
    """Resolve a Place's current photo URI and attribution without persisting it."""
    details = await _http().get(
        PLACE_DETAILS_URL.format(place_id=place_id),
        params={"languageCode": "en", "regionCode": "ID"},
        headers={
            "X-Goog-Api-Key": _api_key(),
            "X-Goog-FieldMask": PHOTO_DETAILS_FIELD_MASK,
        },
    )
    if details.status_code in (400, 404):
        return None
    details.raise_for_status()
    place = details.json()
    photos = place.get("photos") or []
    if not photos or not photos[0].get("name"):
        return {
            "photoUri": None,
            "authorAttributions": [],
            "googleMapsUri": place.get("googleMapsUri"),
        }
    return await _photo_result(photos[0], place.get("googleMapsUri"))


async def fresh_curated_photo(query: str) -> dict[str, Any] | None:
    """Find a curated destination and resolve its current first photo."""
    places = await search_text(query, field_mask=PHOTO_SEARCH_FIELD_MASK, page_size=1)
    if not places:
        return None
    place = places[0]
    photos = place.get("photos") or []
    if not photos or not photos[0].get("name"):
        return {
            "photoUri": None,
            "authorAttributions": [],
            "googleMapsUri": place.get("googleMapsUri"),
            "placeName": place.get("displayName", {}).get("text"),
        }
    result = await _photo_result(photos[0], place.get("googleMapsUri"))
    if result is not None:
        result["placeName"] = place.get("displayName", {}).get("text")
    return result


async def _photo_result(photo: dict[str, Any], maps_uri: str | None) -> dict[str, Any] | None:
    """Exchange a transient Places photo name for its short-lived media URI."""
    google_maps_uri = photo.get("googleMapsUri") or maps_uri
    response = await _http().get(
        PHOTO_MEDIA_URL.format(photo_name=photo["name"]),
        params={"maxWidthPx": 960, "skipHttpRedirect": "true"},
        headers={"X-Goog-Api-Key": _api_key()},
    )
    if response.status_code in (400, 404):
        return {
            "photoUri": None,
            "authorAttributions": photo.get("authorAttributions", []),
            "googleMapsUri": google_maps_uri,
        }
    response.raise_for_status()
    photo_uri = response.json().get("photoUri")
    return {
        "photoUri": photo_uri,
        "authorAttributions": photo.get("authorAttributions", []),
        "googleMapsUri": google_maps_uri,
    }


async def geocode(query: str) -> tuple[float, float] | None:
    places = await search_text(query, field_mask="places.location", page_size=1)
    if not places:
        return None
    location = places[0]["location"]
    return location["latitude"], location["longitude"]
