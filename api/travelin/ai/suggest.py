"""Suggest workflow (ADK): Gemini proposes places for the squad, then the same verify and
summarize nodes as the Reel pipeline check each one on Google Maps and describe it."""

import logging
from typing import Any

from google.adk import Context, Workflow
from google.adk.workflow import node
from google.cloud.firestore import (
    SERVER_TIMESTAMP,
    AsyncDocumentReference,
    AsyncTransaction,
    async_transactional,
)

from ..db import db
from ..places import geocode
from . import suggester
from .ingest import place_document, summarize_place, verify_candidate
from .runner import run_workflow, trip_id_from
from .schemas import Candidate, VerifiedPlace
from .suggester import category_from_types

logger = logging.getLogger(__name__)

ACTIVE_STAGES = {"starting", "thinking", "verifying", "summarizing"}
GENERIC_FAILURE = "Couldn't get suggestions right now. Please try again."


def is_suggesting(trip: dict[str, Any]) -> bool:
    return (trip.get("suggesting") or {}).get("stage") in ACTIVE_STAGES


async def claim_suggesting(trip_ref: AsyncDocumentReference) -> bool:
    """Starts a suggestion run unless one is already going or the trip left gathering."""

    @async_transactional
    async def claim(transaction: AsyncTransaction) -> bool:
        trip = (await trip_ref.get(transaction=transaction)).to_dict() or {}
        if trip.get("status") != "gathering" or is_suggesting(trip):
            return False
        transaction.update(
            trip_ref,
            {
                "suggesting": {
                    "stage": "starting",
                    "done": 0,
                    "total": 0,
                    "added": 0,
                    "startedAt": SERVER_TIMESTAMP,
                }
            },
        )
        return True

    return await claim(db().transaction())


async def _stage(trip_ref: AsyncDocumentReference, stage: str, total: int = 0) -> None:
    await trip_ref.update(
        {"suggesting.stage": stage, "suggesting.done": 0, "suggesting.total": total}
    )


async def _fail(trip_ref: AsyncDocumentReference, message: str) -> None:
    await trip_ref.update(
        {
            "suggesting.stage": "failed",
            "suggesting.error": message,
            "suggesting.finishedAt": SERVER_TIMESTAMP,
        }
    )


async def _suggest(ctx: Context, trip_id: str, trip_ref: AsyncDocumentReference) -> dict:
    trip = (await trip_ref.get()).to_dict() or {}
    destination = dict(trip["destination"])
    if destination.get("lat") is None:
        coords = await geocode(destination["name"])
        if coords:
            destination["lat"], destination["lng"] = coords
            await trip_ref.update({"destination": destination})
    members = [
        snapshot.to_dict() or {} async for snapshot in trip_ref.collection("members").stream()
    ]
    places_ref = trip_ref.collection("places")
    existing = {snapshot.id: snapshot.get("name") async for snapshot in places_ref.stream()}
    suggestions_ref = trip_ref.collection("suggestions")
    saved_suggestions = {
        snapshot.id: snapshot.get("name") async for snapshot in suggestions_ref.stream()
    }
    known_ids = set(existing) | set(saved_suggestions)
    known_names = [*existing.values(), *saved_suggestions.values()]

    await _stage(trip_ref, "thinking")
    suggestions = await suggester.suggest(
        {**trip, "destination": destination}, members, known_names
    )

    jobs = [
        {
            "tripId": trip_id,
            "destination": destination,
            "candidate": Candidate(
                name=suggestion.name,
                city_hint=destination["name"],
                category=suggestion.category,
                confidence=1.0,
            ).model_dump(),
            "reason": suggestion.reason,
            "progress": "suggesting",
        }
        for suggestion in suggestions
    ]
    await _stage(trip_ref, "verifying", len(jobs))
    fresh: dict[str, dict[str, Any]] = {}
    for outcome in await ctx.run_node(verify_candidate, jobs):
        place = outcome.get("place")
        if place and place["place_id"] not in known_ids:
            fresh.setdefault(place["place_id"], outcome)

    await _stage(trip_ref, "summarizing", len(fresh))
    summaries = await ctx.run_node(
        summarize_place,
        [
            {
                "tripId": trip_id,
                "destination": destination,
                "place": o["place"],
                "progress": "suggesting",
            }
            for o in fresh.values()
        ],
    )

    batch = db().batch()
    for outcome, summary in zip(fresh.values(), summaries, strict=True):
        place = VerifiedPlace(**outcome["place"])
        category = outcome["category"]
        if category == "other":
            category = category_from_types(place.types)
        suggestion = place_document(
            place,
            category,
            summary["summary"],
            summary["sources"],
            suggestion={"reason": outcome["reason"]},
        )
        # Google photo references can expire and must not be cached.
        suggestion.pop("photoName", None)
        suggestion["createdAt"] = SERVER_TIMESTAMP
        batch.set(suggestions_ref.document(place.place_id), suggestion)
    batch.update(
        trip_ref,
        {
            "suggesting.stage": "done",
            "suggesting.added": len(fresh),
            "suggesting.finishedAt": SERVER_TIMESTAMP,
        },
    )
    await batch.commit()
    return {"ok": True, "added": len(fresh)}


@node(name="suggest_places", rerun_on_resume=True)
async def suggest_places(ctx: Context, node_input: Any) -> dict:
    trip_id = trip_id_from(node_input)
    trip_ref = db().document(f"trips/{trip_id}")
    try:
        return await _suggest(ctx, trip_id, trip_ref)
    except Exception:
        logger.exception("Suggestions failed for trip %s", trip_id)
        await _fail(trip_ref, GENERIC_FAILURE)
        return {"ok": False}


suggest_workflow = Workflow(name="travelin_suggest", edges=[("START", suggest_places)])


async def run_suggest(trip_id: str) -> None:
    try:
        await run_workflow(suggest_workflow, trip_id)
    except Exception:
        logger.exception("Suggest workflow crashed for trip %s", trip_id)
        await _fail(db().document(f"trips/{trip_id}"), GENERIC_FAILURE)
