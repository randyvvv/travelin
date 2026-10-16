"""Plan workflow (ADK): Gemini drafts, code checks, Gemini revises until the plan passes."""

import logging
import re
from typing import Any

from google.adk import Context, Workflow
from google.adk.workflow import node
from google.cloud.firestore import (
    SERVER_TIMESTAMP,
    AsyncDocumentReference,
    AsyncTransaction,
    async_transactional,
)

from ..config import get_settings
from ..db import db, notify
from . import planner
from .plan_context import load_context
from .planner import PlanResult
from .runner import run_workflow, trip_id_from
from .validator import validate

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3
GENERIC_FAILURE = "Something went wrong while planning. Please try again."
_LABELLED_ALIAS = re.compile(r"\b[PM]\d+ \(([^)]+)\)")
_BARE_ALIAS = re.compile(r"\b[PM]\d+\b")


def humanize(message: str, context: dict[str, Any]) -> str:
    """Rewrites "P3 (Taman Sari)" and bare "M2" as plain names for the squad to read."""
    names = {item["id"]: item["name"] for item in context["model"]["places"]}
    names |= {item["id"]: item["name"] for item in context["model"]["members"]}
    message = _LABELLED_ALIAS.sub(r"\1", message)
    return _BARE_ALIAS.sub(lambda match: names.get(match[0], match[0]), message)


async def claim_planning(trip_ref: AsyncDocumentReference) -> bool:
    """Moves a trip from voting to planning; False if it isn't in voting."""

    @async_transactional
    async def claim(transaction: AsyncTransaction) -> bool:
        current = (await trip_ref.get(transaction=transaction)).to_dict() or {}
        if current.get("status") != "voting":
            return False
        transaction.update(
            trip_ref,
            {
                "status": "planning",
                "planning": {"stage": "starting", "attempt": 0, "startedAt": SERVER_TIMESTAMP},
            },
        )
        return True

    return await claim(db().transaction())


async def save_plan(
    trip_id: str,
    trip_ref: AsyncDocumentReference,
    context: dict[str, Any],
    plan: PlanResult,
    issues: list[str],
    attempts: int,
) -> None:
    members = context["lookup"]["members"]
    places = context["lookup"]["places"]
    catalog = context["lookup"]["catalog"]
    itinerary = trip_ref.collection("itinerary")

    batch = db().batch()
    async for old_day in itinerary.stream():
        batch.delete(old_day.reference)
    for index, day in enumerate(sorted(plan.days, key=lambda day: day.date)):
        batch.set(
            itinerary.document(f"{index:02d}"),
            {
                "date": day.date,
                "title": day.title,
                "stops": [
                    {
                        "placeId": places[stop.place],
                        "start": stop.start,
                        "end": stop.end,
                        "attendees": [members[a] for a in stop.attendees if a in members],
                        "estCostPerPersonIdr": max(stop.est_cost_per_person_idr, 0),
                        "note": stop.note,
                    }
                    for stop in day.stops
                    if stop.place in places
                ],
            },
        )

    item = catalog.get(plan.stay_sku)
    stay = (
        {
            "sku": item["sku"],
            "type": item["type"],
            "title": item["title"],
            "priceIdr": item["price_idr"],
            "unit": item["unit"],
            "reason": plan.stay_reason,
        }
        if item
        else None
    )
    warnings = list(dict.fromkeys(humanize(issue, context) for issue in issues))
    batch.set(
        trip_ref.collection("plan").document("current"),
        {
            "whyThisPlan": plan.why_this_plan,
            "compromises": [
                {"uid": members[c.member], "gaveUp": c.gave_up, "got": c.got, "reason": c.reason}
                for c in plan.compromises
                if c.member in members
            ],
            "estimates": [
                {"uid": members[e.member], "amountIdr": max(e.amount_idr, 0)}
                for e in plan.estimates
                if e.member in members
            ],
            "warnings": warnings,
            "stay": stay,
            "model": get_settings().planner_model,
            "attempts": attempts,
            "generatedAt": SERVER_TIMESTAMP,
        },
    )
    batch.update(
        trip_ref,
        {"status": "planned", "planning.stage": "done", "planning.finishedAt": SERVER_TIMESTAMP},
    )
    await batch.commit()

    trip = (await trip_ref.get()).to_dict() or {}
    for uid in trip.get("memberUids", []):
        await notify(
            uid,
            type="plan_ready",
            text=f"Your itinerary for {trip['name']} is ready.",
            trip_id=trip_id,
            link=f"/trips/{trip_id}/itinerary",
        )


async def _fail(trip_ref: AsyncDocumentReference, message: str) -> None:
    await trip_ref.update(
        {
            "status": "voting",
            "planning.stage": "failed",
            "planning.error": message,
            "planning.finishedAt": SERVER_TIMESTAMP,
        }
    )


# --- ADK nodes ---------------------------------------------------------------------------


@node(name="draft_plan")
async def draft_plan(node_input: dict) -> dict:
    plan = await planner.generate(
        node_input["context"], node_input.get("previous"), node_input.get("errors", [])
    )
    return plan.model_dump()


@node(name="check_plan")
async def check_plan(node_input: dict) -> dict:
    report = validate(PlanResult(**node_input["plan"]), node_input["context"])
    return {"errors": report.errors, "warnings": report.warnings}


async def _plan(ctx: Context, trip_id: str, trip_ref: AsyncDocumentReference) -> dict:
    context = await load_context(trip_id)
    if not context["model"]["places"]:
        await _fail(trip_ref, "There are no places to plan with yet.")
        return {"ok": False}

    attempt = 1
    await trip_ref.update({"planning.stage": "drafting", "planning.attempt": attempt})
    plan = await ctx.run_node(draft_plan, {"context": context})
    report = await ctx.run_node(check_plan, {"context": context, "plan": plan})
    while report["errors"] and attempt < MAX_ATTEMPTS:
        attempt += 1
        await trip_ref.update({"planning.stage": "revising", "planning.attempt": attempt})
        plan = await ctx.run_node(
            draft_plan, {"context": context, "previous": plan, "errors": report["errors"]}
        )
        report = await ctx.run_node(check_plan, {"context": context, "plan": plan})

    # Whatever still fails after the last attempt is shown to the squad as a heads-up.
    issues = report["errors"] + report["warnings"]
    await save_plan(trip_id, trip_ref, context, PlanResult(**plan), issues, attempt)
    return {"ok": True, "attempts": attempt}


@node(name="plan_trip", rerun_on_resume=True)
async def plan_trip(ctx: Context, node_input: Any) -> dict:
    trip_id = trip_id_from(node_input)
    trip_ref = db().document(f"trips/{trip_id}")
    try:
        return await _plan(ctx, trip_id, trip_ref)
    except Exception:
        logger.exception("Planning failed for trip %s", trip_id)
        await _fail(trip_ref, GENERIC_FAILURE)
        return {"ok": False}


plan_workflow = Workflow(name="travelin_plan", edges=[("START", plan_trip)])


async def run_plan(trip_id: str) -> None:
    try:
        await run_workflow(plan_workflow, trip_id)
    except Exception:
        logger.exception("Plan workflow crashed for trip %s", trip_id)
        await _fail(db().document(f"trips/{trip_id}"), GENERIC_FAILURE)
