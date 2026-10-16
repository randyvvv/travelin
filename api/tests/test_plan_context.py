from datetime import date

from travelin.ai.plan_context import build_context, day_intervals, describe_hours, trip_dates

from .plan_fixtures import CATALOG, MEMBERS, OPEN_24_HOURS, PLACES, TRIP, daily

SATURDAY, SUNDAY = date(2026, 10, 24), date(2026, 10, 25)


def test_trip_dates_are_inclusive():
    assert trip_dates("2026-10-24", "2026-10-26") == ["2026-10-24", "2026-10-25", "2026-10-26"]


def test_day_intervals_for_regular_hours():
    assert day_intervals(daily(9, 17), SATURDAY) == [(540, 1020)]


def test_day_intervals_closed_unknown_and_24_hours():
    assert day_intervals(daily(18, 23, range(1, 7)), SUNDAY) == []
    assert day_intervals(None, SUNDAY) is None
    assert day_intervals(OPEN_24_HOURS, SATURDAY) == [(0, 1440)]


def test_day_intervals_after_midnight():
    hours = {"periods": [{"open": {"day": 6, "hour": 18}, "close": {"day": 0, "hour": 2}}]}
    assert day_intervals(hours, SATURDAY) == [(1080, 1440)]
    assert day_intervals(hours, SUNDAY) == [(0, 120)]


def test_describe_hours():
    assert describe_hours([(540, 1020), (1080, 1440)]) == "09:00-17:00, 18:00-24:00"
    assert describe_hours([]) == "closed"
    assert describe_hours(None) == "unknown"
    assert describe_hours([(0, 1440)]) == "open 24 hours"


def test_build_context_uses_aliases_and_only_submitted_votes():
    late = {
        "id": "uid-late",
        "displayName": "Late Larry",
        "prefs": {},
        "votes": {"pl-d": "must"},
        "votesSubmittedAt": None,
    }
    context = build_context(TRIP, [*MEMBERS, late], PLACES, CATALOG)
    model, lookup = context["model"], context["lookup"]

    assert [m["id"] for m in model["members"]] == ["M1", "M2", "M3"]
    assert lookup["members"]["M3"] == "uid-late"
    assert lookup["places"]["P1"] == "pl-a"
    taman_sari = model["places"][0]
    assert taman_sari["votes"] == {"must": ["M1", "M2"], "maybe": [], "skip": []}
    assert taman_sari["hours"] == {"2026-10-24": "09:00-17:00", "2026-10-25": "09:00-17:00"}
    market = model["places"][3]
    assert market["votes"]["must"] == []  # Larry hasn't submitted
    assert lookup["voterCount"] == 2
    assert model["catalog"][0]["sku"] == "yog-stay-courtyard"
    assert "uid-hana" not in str(model)  # the model never sees Firebase UIDs
