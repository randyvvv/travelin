"""Verifier: every candidate must match a real Google Maps place, or it is dropped."""

import math
import re
import unicodedata
from typing import Any

from rapidfuzz import fuzz

from ..config import get_settings
from ..places import SEARCH_FIELD_MASK, search_text
from .genai import client, fast_config
from .schemas import Candidate, DroppedPlace, MatchDecision, VerifiedPlace

SEARCH_RADIUS_M = 50_000.0
MAX_DISTANCE_KM = 80.0
# rapidfuzz token_set_ratio, 0-100. Between the two, Gemini decides.
ACCEPT_SCORE = 60.0
REVIEW_SCORE = 40.0


def normalize(name: str) -> str:
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", ascii_name.lower()).strip()


def name_score(a: str, b: str) -> float:
    return fuzz.token_set_ratio(normalize(a), normalize(b))


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    radius_km = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lng2 - lng1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * radius_km * math.asin(math.sqrt(a))


def to_verified(result: dict[str, Any]) -> VerifiedPlace:
    photos = result.get("photos") or []
    return VerifiedPlace(
        place_id=result["id"],
        name=result.get("displayName", {}).get("text", ""),
        address=result.get("formattedAddress", ""),
        lat=result["location"]["latitude"],
        lng=result["location"]["longitude"],
        google_maps_uri=result.get("googleMapsUri", ""),
        types=result.get("types", []),
        rating=result.get("rating"),
        user_rating_count=result.get("userRatingCount"),
        price_level=result.get("priceLevel"),
        price_range=result.get("priceRange"),
        opening_hours=result.get("regularOpeningHours"),
        photo_name=photos[0].get("name") if photos else None,
    )


def best_match(
    candidate: Candidate, results: list[dict[str, Any]], destination: dict[str, Any]
) -> tuple[dict[str, Any] | None, float, str]:
    """Highest-scoring result near the destination, with its score, or a reason it failed."""
    lat, lng = destination.get("lat"), destination.get("lng")
    nearby = []
    for result in results:
        location = result.get("location")
        if not location:
            continue
        if lat is not None and lng is not None:
            distance = haversine_km(lat, lng, location["latitude"], location["longitude"])
            if distance > MAX_DISTANCE_KM:
                continue
        nearby.append(result)
    if not nearby:
        reason = (
            "not found on Google Maps" if not results else f"too far from {destination['name']}"
        )
        return None, 0.0, reason

    scored = [
        (name_score(candidate.name, result.get("displayName", {}).get("text", "")), result)
        for result in nearby
    ]
    score, result = max(scored, key=lambda pair: pair[0])
    return result, score, "no close match on Google Maps"


async def confirm_match(candidate: Candidate, result: dict[str, Any]) -> bool:
    prompt = (
        f"A travel video named a place '{candidate.name}'"
        + (f" (quote: '{candidate.quote}')" if candidate.quote else "")
        + (f" in {candidate.city_hint}" if candidate.city_hint else "")
        + f". Google Maps found '{result.get('displayName', {}).get('text', '')}' at "
        f"'{result.get('formattedAddress', '')}'. Is this the same place? Say no if unsure."
    )
    response = await client().aio.models.generate_content(
        model=get_settings().fast_model,
        contents=prompt,
        config=fast_config(response_mime_type="application/json", response_schema=MatchDecision),
    )
    decision = response.parsed
    if not isinstance(decision, MatchDecision):
        decision = MatchDecision.model_validate_json(response.text or "{}")
    return decision.same_place


async def verify(candidate: Candidate, destination: dict[str, Any]) -> VerifiedPlace | DroppedPlace:
    lat, lng = destination.get("lat"), destination.get("lng")
    results = await search_text(
        f"{candidate.name}, {candidate.city_hint or destination['name']}",
        field_mask=SEARCH_FIELD_MASK,
        bias=(lat, lng, SEARCH_RADIUS_M) if lat is not None and lng is not None else None,
        page_size=3,
    )
    result, score, reason = best_match(candidate, results, destination)
    if result is None:
        return DroppedPlace(name=candidate.name, reason=reason)
    if score >= ACCEPT_SCORE or (score >= REVIEW_SCORE and await confirm_match(candidate, result)):
        return to_verified(result)
    return DroppedPlace(name=candidate.name, reason=reason)
