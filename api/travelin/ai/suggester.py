"""Suggester: Gemini grounded on Google Maps proposes places that fit the squad,
for trips where nobody saved Reels (or not enough of them)."""

import re
from collections import Counter
from typing import Any

from google.genai import types
from pydantic import BaseModel, ValidationError

from ..config import get_settings
from .genai import client, fast_config
from .schemas import Category

SUGGESTION_COUNT = 8

# Places API types, most specific first, mapped onto Travelin's categories.
_TYPE_CATEGORIES: list[tuple[set[str], Category]] = [
    ({"cafe", "coffee_shop", "tea_house", "bakery"}, "cafe"),
    ({"bar", "night_club", "pub", "karaoke"}, "nightlife"),
    ({"beach"}, "beach"),
    ({"lodging", "hotel", "guest_house", "hostel", "resort_hotel", "bed_and_breakfast"}, "stay"),
    (
        {"national_park", "park", "hiking_area", "natural_feature", "garden", "botanical_garden"},
        "nature",
    ),
    ({"shopping_mall", "market", "store", "clothing_store", "department_store"}, "shopping"),
    ({"amusement_park", "zoo", "aquarium", "water_park", "bowling_alley", "spa"}, "activity"),
    ({"restaurant", "food", "meal_takeaway", "food_court"}, "food"),
    (
        {"tourist_attraction", "museum", "art_gallery", "historical_landmark", "place_of_worship"},
        "attraction",
    ),
]


def category_from_types(place_types: list[str]) -> Category:
    found = set(place_types)
    for type_names, category in _TYPE_CATEGORIES:
        if found & type_names:
            return category
    return "other"


class Suggestion(BaseModel):
    name: str
    category: Category = "other"
    reason: str = ""


class Suggestions(BaseModel):
    places: list[Suggestion]


PROMPT = """\
A group of {size} friends is planning a trip to {destination} from {start} to {end}.
What they're into: {interests}.
Food needs in the group: {dietary}.
Things some of them would rather skip: {skips}.
Already on their list (don't repeat these): {existing}.

Using Google Maps, suggest {count} specific, well-reviewed places in {destination} this group
would enjoy: a mix of food, cafés, sights, and outdoor spots that fits their interests and
food needs. Prefer places that are open on their trip dates.

Reply with ONLY a JSON object:
{{"places": [{{"name": "name as on Google Maps", "category": "one of food, cafe, attraction,
nature, beach, stay, nightlife, shopping, activity, other", "reason": "one sentence on why it
fits this group"}}]}}"""

_JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)


def describe(values: list[str], fallback: str) -> str:
    """ "Nature (3), Local food (2)" — counts show what the group cares about most."""
    counts = Counter(values)
    return ", ".join(f"{value} ({n})" for value, n in counts.most_common()) or fallback


def build_prompt(
    trip: dict[str, Any], members: list[dict[str, Any]], existing: list[str], count: int
) -> str:
    prefs = [member.get("prefs") or {} for member in members]
    return PROMPT.format(
        size=len(members),
        destination=trip["destination"]["name"],
        start=trip["startDate"],
        end=trip["endDate"],
        interests=describe([i for p in prefs for i in p.get("interests", [])], "not shared yet"),
        dietary=describe([d for p in prefs for d in p.get("dietary", [])], "none"),
        skips=describe([s for p in prefs for s in p.get("skip", [])], "nothing"),
        existing=", ".join(existing) or "nothing yet",
        count=count,
    )


def parse_suggestions(text: str | None) -> list[Suggestion] | None:
    match = _JSON_OBJECT.search(text or "")
    if not match:
        return None
    try:
        return Suggestions.model_validate_json(match.group(0)).places
    except ValidationError:
        return None


async def suggest(
    trip: dict[str, Any],
    members: list[dict[str, Any]],
    existing: list[str],
    count: int = SUGGESTION_COUNT,
) -> list[Suggestion]:
    destination = trip["destination"]
    retrieval = (
        types.RetrievalConfig(
            lat_lng=types.LatLng(latitude=destination["lat"], longitude=destination["lng"])
        )
        if destination.get("lat") is not None
        else None
    )
    model = get_settings().fast_model
    response = await client().aio.models.generate_content(
        model=model,
        contents=build_prompt(trip, members, existing, count),
        config=fast_config(
            tools=[types.Tool(google_maps=types.GoogleMaps())],
            tool_config=types.ToolConfig(retrieval_config=retrieval) if retrieval else None,
        ),
    )
    suggestions = parse_suggestions(response.text)
    if suggestions is None:
        reformatted = await client().aio.models.generate_content(
            model=model,
            contents=f"Rewrite these place suggestions as JSON:\n\n{response.text}",
            config=fast_config(response_mime_type="application/json", response_schema=Suggestions),
        )
        parsed = reformatted.parsed
        suggestions = (
            parsed.places
            if isinstance(parsed, Suggestions)
            else Suggestions.model_validate_json(reformatted.text or '{"places": []}').places
        )
    return suggestions[:count]
