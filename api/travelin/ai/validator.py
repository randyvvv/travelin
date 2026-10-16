"""Deterministic checks on the Planner's draft. Errors go back to the Planner; warnings
are shown to the squad as "Heads-up"."""

import math
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from .planner import PlanResult
from .verifier import haversine_km

DAY_START, DAY_END = 8 * 60, 21 * 60
MAX_STOPS_PER_DAY = 6
CITY_SPEED_KMH = 25
TRAVEL_BUFFER_MIN = 10
FOOD = {"food", "cafe"}
# "Rather skip" options that map onto a place category without guesswork.
SKIP_CATEGORIES = {"Nightlife": {"nightlife"}, "Shopping": {"shopping"}}
NON_HALAL = re.compile(r"\b(not halal|non-halal|non halal|pork|babi)\b", re.IGNORECASE)
TIME = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


@dataclass
class Report:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def minutes(value: str) -> int | None:
    match = TIME.match(value)
    return int(match[1]) * 60 + int(match[2]) if match else None


def check_attendees(
    attendees: list[str],
    place: dict[str, Any],
    label: str,
    members: dict[str, dict[str, Any]],
    report: Report,
) -> None:
    for alias in attendees:
        member = members.get(alias)
        if member is None:
            report.errors.append(f"{label} lists unknown member {alias}.")
            continue
        who = f"{alias} ({member['name']})"
        for skip in member.get("skip") or []:
            if place["category"] in SKIP_CATEGORIES.get(skip, set()):
                report.errors.append(f"{who} wants to skip {skip.lower()} but attends {label}.")
        if (
            "Halal" in (member.get("dietary") or [])
            and place["category"] in FOOD
            and NON_HALAL.search(place.get("dietaryNote") or "")
        ):
            report.errors.append(f"{who} eats halal but attends {label}, which is not halal.")


def validate(plan: PlanResult, context: dict[str, Any]) -> Report:
    report = Report()
    model, lookup = context["model"], context["lookup"]
    places = {place["id"]: place for place in model["places"]}
    members = {member["id"]: member for member in model["members"]}
    trip_days = set(model["trip"]["dates"])
    compromise_text = " ".join(
        f"{c.member} {c.gave_up} {c.got} {c.reason}" for c in plan.compromises
    ).lower()
    compromised = {c.member for c in plan.compromises}

    seen_days: set[str] = set()
    used_places: set[str] = set()
    for day in plan.days:
        if day.date not in trip_days:
            report.errors.append(f"{day.date} is not one of the trip dates.")
            continue
        if day.date in seen_days:
            report.errors.append(f"{day.date} appears more than once.")
        seen_days.add(day.date)
        if len(day.stops) > MAX_STOPS_PER_DAY:
            report.errors.append(f"{day.date} has {len(day.stops)} stops; the limit is 6.")
        weekday = date.fromisoformat(day.date).strftime("%A")

        previous: tuple[int, dict[str, Any]] | None = None
        for stop in day.stops:
            place = places.get(stop.place)
            if place is None:
                report.errors.append(f"{stop.place} on {day.date} is not in the places list.")
                continue
            label = f"{stop.place} ({place['name']})"
            if stop.place in used_places:
                report.errors.append(f"{label} is used more than once.")
            used_places.add(stop.place)

            start, end = minutes(stop.start), minutes(stop.end)
            if start is None or end is None or start >= end:
                report.errors.append(
                    f"{label} on {day.date} has invalid times {stop.start}-{stop.end}."
                )
                continue
            if start < DAY_START or end > DAY_END:
                report.errors.append(f"{label} on {day.date} is outside 08:00-21:00.")

            intervals = lookup["hours"][stop.place][day.date]
            if intervals is None:
                report.warnings.append(
                    f"Opening hours for {place['name']} are unknown; check before you go."
                )
            elif not any(open_at <= start and end <= close_at for open_at, close_at in intervals):
                report.errors.append(
                    f"{label} is not open {stop.start}-{stop.end} on {weekday} {day.date} "
                    f"(hours: {place['hours'][day.date]})."
                )

            if previous is not None:
                previous_end, previous_place = previous
                if start < previous_end:
                    report.errors.append(f"{label} on {day.date} overlaps the stop before it.")
                else:
                    distance = haversine_km(
                        previous_place["lat"], previous_place["lng"], place["lat"], place["lng"]
                    )
                    needed = math.ceil(distance / CITY_SPEED_KMH * 60) + TRAVEL_BUFFER_MIN
                    if start - previous_end < needed:
                        report.warnings.append(
                            f"Getting from {previous_place['name']} to {place['name']} on "
                            f"{day.date} may take about {needed} minutes."
                        )
            previous = (end, place)
            check_attendees(stop.attendees, place, label, members, report)

    missing_days = trip_days - seen_days
    if missing_days:
        report.errors.append(f"The plan has no day for {', '.join(sorted(missing_days))}.")

    threshold = math.ceil(lookup["voterCount"] / 2)
    for place in model["places"]:
        if place["id"] in used_places or len(place["votes"]["must"]) < threshold:
            continue
        if (
            place["id"].lower() not in compromise_text
            and place["name"].lower() not in compromise_text
        ):
            report.errors.append(
                f"{place['id']} ({place['name']}) is a must for half the voters but is missing "
                "and not explained in compromises."
            )

    estimates = {estimate.member: estimate.amount_idr for estimate in plan.estimates}
    for alias, member in members.items():
        budget = member.get("budgetIdr") or 0
        if alias not in estimates:
            report.errors.append(f"There is no spend estimate for {alias} ({member['name']}).")
        elif budget and estimates[alias] > budget and alias not in compromised:
            report.errors.append(
                f"{alias} ({member['name']}) is estimated at Rp{estimates[alias]:,} against a "
                f"budget of Rp{budget:,}, with no compromise explaining it."
            )

    if plan.stay_sku and plan.stay_sku not in lookup["catalog"]:
        report.errors.append(f"Stay {plan.stay_sku} is not in the catalog.")
    return report
