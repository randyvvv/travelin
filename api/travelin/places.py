"""Places API (New) client, used to geocode destinations and to verify places."""

from typing import Any

import httpx

from .config import get_settings

SEARCH_TEXT_URL = "https://places.googleapis.com/v1/places:searchText"
PLACE_DETAILS_URL = "https://places.googleapis.com/v1/places/{place_id}"

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


async def geocode(query: str) -> tuple[float, float] | None:
    places = await search_text(query, field_mask="places.location", page_size=1)
    if not places:
        return None
    location = places[0]["location"]
    return location["latitude"], location["longitude"]
