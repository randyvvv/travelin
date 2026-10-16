import copy

from travelin.ai.plan import humanize
from travelin.ai.plan_context import build_context
from travelin.ai.planner import Compromise, MemberEstimate, PlannedDay
from travelin.ai.validator import validate

from .plan_fixtures import CATALOG, MEMBERS, PLACES, TRIP, stop, valid_plan

CONTEXT = build_context(TRIP, MEMBERS, PLACES, CATALOG)


def errors_for(plan, context=CONTEXT) -> list[str]:
    return validate(plan, context).errors


def day(date: str, *stops) -> PlannedDay:
    return PlannedDay(date=date, title="", stops=list(stops))


SUNDAY_MARKET = day("2026-10-25", stop("P4", "10:00", "11:00", ["M1"]))


def test_valid_plan_passes_with_a_heads_up_for_unknown_hours():
    report = validate(valid_plan(), CONTEXT)
    assert report.errors == []
    assert report.warnings == [
        "Opening hours for Beringharjo Market are unknown; check before you go."
    ]


def test_stop_outside_opening_hours():
    plan = valid_plan(
        days=[
            day("2026-10-24", stop("P1", "08:00", "10:00", ["M1", "M2"]), stop("P2", "12:00", "13:00", ["M1"])),
            day("2026-10-25", stop("P3", "19:00", "20:00", ["M2"])),
        ]
    )  # fmt: skip
    errors = errors_for(plan)
    assert any("P1 (Taman Sari) is not open 08:00-10:00 on Saturday" in e for e in errors)
    assert any("P3 (Mabes Bar) is not open 19:00-20:00 on Sunday" in e for e in errors)


def test_overlapping_and_invalid_times():
    plan = valid_plan(
        days=[
            day(
                "2026-10-24",
                stop("P1", "09:00", "11:00", ["M1", "M2"]),
                stop("P2", "10:30", "12:00", ["M1", "M2"]),
                stop("P3", "21:00", "20:00", ["M2"]),
            ),
            SUNDAY_MARKET,
        ]
    )
    errors = errors_for(plan)
    assert any("P2 (Gudeg Yu Djum) on 2026-10-24 overlaps" in e for e in errors)
    assert any("invalid times 21:00-20:00" in e for e in errors)


def test_skip_preferences_and_halal_needs():
    places = copy.deepcopy(PLACES)
    places[1]["summary"]["dietaryNote"] = "Not halal: the gudeg is cooked with pork lard"
    context = build_context(TRIP, MEMBERS, places, CATALOG)
    plan = valid_plan(
        days=[
            day("2026-10-24", stop("P1", "09:00", "11:00", ["M1", "M2"]), stop("P2", "12:00", "13:00", ["M1", "M2"])),
            day("2026-10-25", stop("P4", "10:00", "11:00", ["M1", "M2"])),
        ],
        compromises=[Compromise(member="M2", gave_up="Mabes Bar", got="x", reason="y")],
    )  # fmt: skip
    errors = errors_for(plan, context)
    assert "M1 (Hana) eats halal but attends P2 (Gudeg Yu Djum), which is not halal." in errors
    assert "M2 (Raka) wants to skip shopping but attends P4 (Beringharjo Market)." in errors


def test_must_places_need_a_slot_or_an_explanation():
    without_taman_sari = [
        day("2026-10-24", stop("P2", "12:00", "13:00", ["M1", "M2"])),
        SUNDAY_MARKET,
    ]
    plan = valid_plan(days=without_taman_sari)
    assert any("P1 (Taman Sari) is a must" in e for e in errors_for(plan))

    explained = valid_plan(
        days=without_taman_sari,
        compromises=[
            Compromise(member="M1", gave_up="Taman Sari", got="A slow morning", reason="Rain"),
            Compromise(member="M2", gave_up="Mabes Bar", got="Early night", reason="Closed"),
        ],
    )
    assert errors_for(explained) == []


def test_over_budget_needs_a_compromise():
    over = [
        MemberEstimate(member="M1", amount_idr=900_000),
        MemberEstimate(member="M2", amount_idr=1_500_000),
    ]
    assert any(
        "M2 (Raka) is estimated at Rp1,500,000" in e for e in errors_for(valid_plan(estimates=over))
    )

    with_compromise = valid_plan(
        estimates=over,
        compromises=[Compromise(member="M2", gave_up="Budget", got="Night out", reason="Worth it")],
    )
    assert errors_for(with_compromise) == []


def test_missing_day_unknown_place_and_stay():
    plan = valid_plan(
        days=[day("2026-10-24", stop("P1", "09:00", "11:00", ["M1", "M2"]), stop("P9", "12:00", "13:00", ["M1"]))],
        stay_sku="moon-base",
    )  # fmt: skip
    errors = errors_for(plan)
    assert "The plan has no day for 2026-10-25." in errors
    assert "P9 on 2026-10-24 is not in the places list." in errors
    assert "Stay moon-base is not in the catalog." in errors


def test_humanize_replaces_aliases_with_names():
    assert humanize("P1 (Taman Sari) is not open", CONTEXT) == "Taman Sari is not open"
    assert humanize("There is no spend estimate for M2.", CONTEXT) == (
        "There is no spend estimate for Raka."
    )
