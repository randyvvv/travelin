"""Place Summary: Gemini grounded on Google Maps describes each verified place."""

import re
from typing import Any

from google.genai import types
from pydantic import ValidationError

from ..config import get_settings
from .genai import client, fast_config
from .schemas import PlaceSummary, VerifiedPlace

MAX_SOURCES = 5

PROMPT = """\
A group of friends is deciding whether to visit {name} ({address}) on a trip to {destination}.
Using Google Maps information about this place, reply with ONLY a JSON object with these keys:
"highlights": three short points from what visitors say, each under 15 words,
"best_time": the best time of day or week to visit, and why, in one sentence,
"price_note": typical spend per person in Indonesian rupiah, or the ticket price, in one sentence,
"dietary_note": whether it has halal or vegetarian options, or "Not known" if unclear,
"crowd_note": when it tends to be busy, in one sentence, phrased as an estimate."""

_JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)


def parse_summary(text: str | None) -> PlaceSummary | None:
    """The grounded answer is free text that should contain one JSON object."""
    match = _JSON_OBJECT.search(text or "")
    if not match:
        return None
    try:
        return PlaceSummary.model_validate_json(match.group(0))
    except ValidationError:
        return None


def maps_sources(response: types.GenerateContentResponse) -> list[dict[str, Any]]:
    """Google Maps sources the UI must show under the summary."""
    candidate = response.candidates[0] if response.candidates else None
    metadata = candidate.grounding_metadata if candidate else None
    sources: list[dict[str, Any]] = []
    seen: set[str] = set()
    for chunk in (metadata.grounding_chunks if metadata else None) or []:
        maps = chunk.maps
        if maps and maps.uri and maps.uri not in seen:
            seen.add(maps.uri)
            sources.append(
                {"title": maps.title or "Google Maps", "uri": maps.uri, "placeId": maps.place_id}
            )
    return sources[:MAX_SOURCES]


async def summarize(
    place: VerifiedPlace, destination: str
) -> tuple[PlaceSummary, list[dict[str, Any]]]:
    model = get_settings().fast_model
    response = await client().aio.models.generate_content(
        model=model,
        contents=PROMPT.format(name=place.name, address=place.address, destination=destination),
        config=fast_config(
            tools=[types.Tool(google_maps=types.GoogleMaps())],
            tool_config=types.ToolConfig(
                retrieval_config=types.RetrievalConfig(
                    lat_lng=types.LatLng(latitude=place.lat, longitude=place.lng)
                )
            ),
        ),
    )
    summary = parse_summary(response.text)
    if summary is None:
        # Second pass without tools, so the schema can be enforced.
        reformatted = await client().aio.models.generate_content(
            model=model,
            contents=f"Rewrite this description of {place.name} as JSON:\n\n{response.text}",
            config=fast_config(response_mime_type="application/json", response_schema=PlaceSummary),
        )
        summary = reformatted.parsed
        if not isinstance(summary, PlaceSummary):
            summary = PlaceSummary.model_validate_json(reformatted.text or "{}")
    return summary, maps_sources(response)
