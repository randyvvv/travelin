"""Extractor: Gemini watches a Reel and lists the named places in it."""

from typing import Any

from google.genai import types

from ..config import get_settings
from .genai import client, fast_config
from .schemas import Candidate, ExtractResult

MIN_CONFIDENCE = 0.4

VIDEO_MIME_TYPES = {
    "mp4": "video/mp4",
    "m4v": "video/mp4",
    "mov": "video/quicktime",
    "webm": "video/webm",
    "3gp": "video/3gpp",
}

PROMPT = """\
You are watching a short travel video that a friend saved for a group trip to {destination}.

List every specific, named place a traveler could visit: restaurants, cafés, attractions,
beaches, viewpoints, markets, shops, places to stay, and activities. Use what is shown on
screen, written in captions or on-screen text, and said in the voice-over.

Rules:
- Only include places with a proper name. Skip generic mentions such as "a beach" or "street food".
- Write the name the way it would appear on Google Maps, in its original language.
- city_hint: the city or area the video suggests for the place, or "" if unclear.
- appears_at_sec: the second at which the place is first shown or named.
- evidence: how you know the name (on_screen_text, caption, speech, or visual).
- quote: the exact words or text that name the place, if any.
- confidence: from 0 to 1, how sure you are that this is a real, specific place.

Return an empty list if the video names no specific places."""


def video_part(reel: dict[str, Any]) -> types.Part:
    storage_path = reel.get("storagePath")
    if storage_path:
        extension = storage_path.rsplit(".", 1)[-1].lower()
        return types.Part.from_uri(
            file_uri=f"gs://{get_settings().storage_bucket}/{storage_path}",
            mime_type=VIDEO_MIME_TYPES.get(extension, "video/mp4"),
        )
    # YouTube links go to Gemini as-is.
    return types.Part.from_uri(file_uri=reel["sourceUrl"], mime_type="video/mp4")


async def extract(reel: dict[str, Any], destination: str) -> list[Candidate]:
    response = await client().aio.models.generate_content(
        model=get_settings().fast_model,
        contents=[video_part(reel), PROMPT.format(destination=destination)],
        config=fast_config(response_mime_type="application/json", response_schema=ExtractResult),
    )
    result = response.parsed
    if not isinstance(result, ExtractResult):
        result = ExtractResult.model_validate_json(response.text or '{"places": []}')
    return [candidate for candidate in result.places if candidate.confidence >= MIN_CONFIDENCE]
