"""Builds what the Planner sees, plus the lookups the validator needs to check its answer.

Members and places get short aliases (M1, P1). The model copies those far more reliably
than Firebase UIDs or Google place IDs, and they map back when the plan is saved.
"""

import logging
from datetime import date, timedelta
from typing import Any

import httpx

from ..config import get_settings
from ..db import db

logger = logging.getLogger(__name__)

DAY_MINUTES = 24 * 60
Intervals = list[tuple[int, int]]


def trip_dates(start: str, end: str) -> list[str]:
    first, last = date.fromisoformat(start), date.fromisoformat(end)
    return [
        (first + timedelta(days=offset)).isoformat() for offset in range((last - first).days + 1)
    ]


def day_intervals(opening_hours: dict[str, Any] | None, day: date) -> Intervals | None:
    """Open intervals on `day` in minutes after midnight; None when hours are unknown.

    Uses Places API regularOpeningHours.periods, where day 0 is Sunday. An empty list
    means closed all day.
    """
    periods = (opening_hours or {}).get("periods")
    if not periods:
        return None
    places_day = (day.weekday() + 1) % 7
    intervals: Intervals = []
    for period in periods:
        opens, closes = period.get("open"), period.get("close")
        if opens is None:
            continue
        if closes is None:
            return [(0, DAY_MINUTES)]  # open 24 hours
        open_at = opens["hour"] * 60 + opens.get("minute", 0)
        close_at = closes["hour"] * 60 + closes.get("minute", 0)
        if opens["day"] == places_day:
            intervals.append((open_at, close_at if closes["day"] == places_day else DAY_MINUTES))
        elif closes["day"] == places_day:
            intervals.append((0, close_at))  # opened the day before, closes after midnight
    return sorted(intervals)


def format_minutes(minutes: int) -> str:
    return "24:00" if minutes >= DAY_MINUTES else f"{minutes // 60:02d}:{minutes % 60:02d}"


def describe_hours(intervals: Intervals | None) -> str:
    if intervals is None:
        return "unknown"
    if not intervals:
        return "closed"
    if intervals == [(0, DAY_MINUTES)]:
        return "open 24 hours"
    return ", ".join(f"{format_minutes(a)}-{format_minutes(b)}" for a, b in intervals)


async def fetch_catalog(destination: str) -> list[dict[str, Any]]:
    """Stays and tours the demo merchant sells at the destination; empty if unreachable."""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(
                f"{get_settings().merchant_url}/catalog", params={"destination": destination}
            )
            response.raise_for_status()
            return response.json()["items"]
    except Exception:
        logger.warning("Merchant catalog unavailable for %r", destination, exc_info=True)
        return []


def build_context(
    trip: dict[str, Any],
    members: list[dict[str, Any]],
    places: list[dict[str, Any]],
    catalog: list[dict[str, Any]],
) -> dict[str, Any]:
    """`members` and `places` are Firestore docs with their id under "id"."""
    dates = trip_dates(trip["startDate"], trip["endDate"])
    member_alias = {member["id"]: f"M{index}" for index, member in enumerate(members, 1)}
    place_alias = {place["id"]: f"P{index}" for index, place in enumerate(places, 1)}
    voters = [member for member in members if member.get("votesSubmittedAt") is not None]

    model_places = []
    hours_lookup: dict[str, dict[str, Intervals | None]] = {}
    for place in places:
        alias = place_alias[place["id"]]
        hours = {
            day: day_intervals(place.get("openingHours"), date.fromisoformat(day)) for day in dates
        }
        hours_lookup[alias] = hours
        votes: dict[str, list[str]] = {"must": [], "maybe": [], "skip": []}
        for voter in voters:
            vote = (voter.get("votes") or {}).get(place["id"])
            if vote in votes:
                votes[vote].append(member_alias[voter["id"]])
        summary = place.get("summary") or {}
        model_places.append(
            {
                "id": alias,
                "name": place["name"],
                "category": place.get("category", "other"),
                "rating": place.get("rating"),
                "priceLevel": place.get("priceLevel"),
                "priceNote": summary.get("priceNote", ""),
                "dietaryNote": summary.get("dietaryNote", ""),
                "bestTime": summary.get("bestTime", ""),
                "lat": place["location"]["lat"],
                "lng": place["location"]["lng"],
                "hours": {day: describe_hours(intervals) for day, intervals in hours.items()},
                "votes": votes,
                "savedBy": [
                    member_alias[uid] for uid in place.get("savedBy", []) if uid in member_alias
                ],
            }
        )

    return {
        "model": {
            "trip": {
                "name": trip["name"],
                "destination": trip["destination"]["name"],
                "origin": trip["origin"],
                "dates": dates,
            },
            "members": [
                {
                    "id": member_alias[member["id"]],
                    "name": member["displayName"],
                    **{
                        key: member.get("prefs", {}).get(key)
                        for key in ("budgetIdr", "interests", "dietary", "skip")
                    },
                    "voted": member.get("votesSubmittedAt") is not None,
                }
                for member in members
            ],
            "places": model_places,
            "catalog": [
                {
                    key: item[key]
                    for key in ("sku", "type", "title", "price_idr", "unit", "capacity")
                }
                for item in catalog
            ],
        },
        "lookup": {
            "members": {alias: uid for uid, alias in member_alias.items()},
            "places": {alias: place_id for place_id, alias in place_alias.items()},
            "hours": hours_lookup,
            "catalog": {item["sku"]: item for item in catalog},
            "voterCount": len(voters) or len(members),
        },
    }


async def load_context(trip_id: str) -> dict[str, Any]:
    trip_ref = db().document(f"trips/{trip_id}")
    trip = (await trip_ref.get()).to_dict() or {}
    members = [
        {"id": snapshot.id, **(snapshot.to_dict() or {})}
        async for snapshot in trip_ref.collection("members").order_by("joinedAt").stream()
    ]
    places = [
        {"id": snapshot.id, **(snapshot.to_dict() or {})}
        async for snapshot in trip_ref.collection("places").stream()
    ]
    catalog = await fetch_catalog(trip["destination"]["name"])
    return build_context(trip, members, places, catalog)
