"""Planner: Gemini drafts the itinerary from votes, preferences, and verified places."""

import json
from typing import Any

from google.genai import types
from pydantic import BaseModel

from ..config import get_settings
from .genai import client


class PlannedStop(BaseModel):
    place: str  # P alias
    start: str  # HH:MM
    end: str
    attendees: list[str]  # M aliases
    est_cost_per_person_idr: int
    note: str


class PlannedDay(BaseModel):
    date: str  # YYYY-MM-DD
    title: str
    stops: list[PlannedStop]


class Compromise(BaseModel):
    member: str
    gave_up: str
    got: str
    reason: str


class MemberEstimate(BaseModel):
    member: str
    amount_idr: int


class PlanResult(BaseModel):
    days: list[PlannedDay]
    stay_sku: str
    stay_reason: str
    compromises: list[Compromise]
    why_this_plan: str
    estimates: list[MemberEstimate]


INSTRUCTIONS = """\
You are Travelin's trip planner. Plan a day-by-day itinerary for a group of friends from the
trip data below. Refer to places only by their id (P1, P2...) and to members only by their id
(M1, M2...).

Priorities, in order:
1. Hard rules. Every stop is inside the place's opening hours for that date ("closed" and
   "unknown" are listed per date). Food stops respect the dietary needs of the members
   attending them. Members are left out of stops for activities they want to skip.
2. Include every place that at least half of the voters marked "must". If one cannot fit,
   say why in compromises.
3. Prefer places with more "must" votes and more members who saved them. Leave out places
   most voters marked "skip".
4. Keep each member's estimated total spend within their budget. If that is impossible,
   say so in compromises.
5. Put nearby places (by lat/lng) on the same day, leave travel time between stops, and
   plan lunch around 12:00 and dinner around 19:00 when food places are available.

Format rules:
- Days run 08:00-21:00. At most 6 stops per day. Times are 24-hour HH:MM. Stops are in time
  order and do not overlap. Use each place at most once.
- attendees lists the members at that stop; normally everyone.
- est_cost_per_person_idr is a realistic rupiah estimate from priceNote or priceLevel; 0 if free.
- If a catalog stay fits the group size and budgets, put its sku in stay_sku and explain why
  in stay_reason. Otherwise leave both empty.
- compromises has one entry per real trade-off: the member, what they gave up, what they got
  instead, and why.
- why_this_plan is under 120 words, warm and specific, and names members and the key
  trade-offs by name (not by id).
- estimates gives every member's total estimated spend for the trip, including their share
  of the stay.
Write everything in English."""


def build_prompt(
    context: dict[str, Any], previous: dict[str, Any] | None, errors: list[str]
) -> str:
    prompt = f"{INSTRUCTIONS}\n\nTRIP DATA:\n{json.dumps(context['model'], ensure_ascii=False)}"
    if previous is not None:
        prompt += (
            f"\n\nYOUR PREVIOUS PLAN:\n{json.dumps(previous, ensure_ascii=False)}"
            "\n\nIt broke these rules:\n"
            + "\n".join(f"- {error}" for error in errors)
            + "\n\nFix every problem and return the complete plan again."
        )
    return prompt


async def generate(
    context: dict[str, Any], previous: dict[str, Any] | None = None, errors: list[str] = ()
) -> PlanResult:
    response = await client().aio.models.generate_content(
        model=get_settings().planner_model,
        contents=build_prompt(context, previous, list(errors)),
        config=types.GenerateContentConfig(
            response_mime_type="application/json", response_schema=PlanResult
        ),
    )
    result = response.parsed
    if not isinstance(result, PlanResult):
        result = PlanResult.model_validate_json(response.text or "{}")
    return result
