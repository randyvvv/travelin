"""A small two-day Yogyakarta trip shared by the planning tests.

24 Oct 2026 is a Saturday (Places API day 6); 25 Oct is a Sunday (day 0).
"""

from travelin.ai.planner import (
    Compromise,
    MemberEstimate,
    PlannedDay,
    PlannedStop,
    PlanResult,
)


def daily(open_hour: int, close_hour: int, days: range = range(7)) -> dict:
    return {
        "periods": [
            {
                "open": {"day": day, "hour": open_hour, "minute": 0},
                "close": {"day": day, "hour": close_hour, "minute": 0},
            }
            for day in days
        ]
    }


OPEN_24_HOURS = {"periods": [{"open": {"day": 0, "hour": 0, "minute": 0}}]}

TRIP = {
    "name": "Jogja long weekend",
    "startDate": "2026-10-24",
    "endDate": "2026-10-25",
    "origin": "Jakarta",
    "destination": {"name": "Yogyakarta", "lat": -7.7956, "lng": 110.3695},
}

MEMBERS = [
    {
        "id": "uid-hana",
        "displayName": "Hana",
        "prefs": {"budgetIdr": 2_000_000, "interests": ["Culture & history"], "dietary": ["Halal"], "skip": []},
        "votes": {"pl-a": "must", "pl-b": "must", "pl-c": "skip"},
        "votesSubmittedAt": "submitted",
    },
    {
        "id": "uid-raka",
        "displayName": "Raka",
        "prefs": {"budgetIdr": 1_000_000, "interests": ["Nightlife"], "dietary": [], "skip": ["Shopping"]},
        "votes": {"pl-a": "must", "pl-c": "must"},
        "votesSubmittedAt": "submitted",
    },
]  # fmt: skip


def place(place_id: str, name: str, category: str, hours: dict | None, **summary: str) -> dict:
    return {
        "id": place_id,
        "name": name,
        "category": category,
        "location": {"lat": -7.80, "lng": 110.37},
        "openingHours": hours,
        "summary": summary,
        "savedBy": ["uid-hana"],
    }


PLACES = [
    place("pl-a", "Taman Sari", "attraction", daily(9, 17)),
    place("pl-b", "Gudeg Yu Djum", "food", OPEN_24_HOURS, dietaryNote="Halal"),
    place("pl-c", "Mabes Bar", "nightlife", daily(18, 23, range(1, 7))),  # closed Sundays
    place("pl-d", "Beringharjo Market", "shopping", None),  # hours unknown
]

CATALOG = [
    {
        "sku": "yog-stay-courtyard",
        "type": "stay",
        "destination": "Yogyakarta",
        "title": "Courtyard Homestay (demo)",
        "price_idr": 850_000,
        "unit": "night",
        "capacity": 6,
    }
]


def stop(alias: str, start: str, end: str, attendees: list[str], cost: int = 50_000) -> PlannedStop:
    return PlannedStop(
        place=alias,
        start=start,
        end=end,
        attendees=attendees,
        est_cost_per_person_idr=cost,
        note="",
    )


def valid_plan(**changes) -> PlanResult:
    """Aliases: M1 Hana, M2 Raka; P1 Taman Sari, P2 Gudeg, P3 Mabes Bar, P4 Market."""
    plan = PlanResult(
        days=[
            PlannedDay(
                date="2026-10-24",
                title="Water castle and gudeg",
                stops=[
                    stop("P1", "09:00", "11:00", ["M1", "M2"]),
                    stop("P2", "12:00", "13:00", ["M1", "M2"]),
                    stop("P3", "19:00", "21:00", ["M2"]),
                ],
            ),
            PlannedDay(
                date="2026-10-25",
                title="Market morning",
                stops=[stop("P4", "10:00", "11:00", ["M1"])],
            ),
        ],
        stay_sku="yog-stay-courtyard",
        stay_reason="Fits both budgets.",
        compromises=[
            Compromise(
                member="M1", gave_up="Bar night", got="Free evening", reason="She skips bars."
            )
        ],
        why_this_plan="Hana gets her history fix while Raka gets his night out.",
        estimates=[
            MemberEstimate(member="M1", amount_idr=900_000),
            MemberEstimate(member="M2", amount_idr=900_000),
        ],
    )
    return plan.model_copy(update=changes)
