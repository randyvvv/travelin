"""Ingest workflow (ADK): Reels -> candidate places -> verified places -> summaries.

Each step is an ADK node that fans out over its items in parallel. A failure on one
item (a video Gemini can't read, a place Maps can't find) never fails the whole run.
"""

import asyncio
import hashlib
import logging
from typing import Any

from firebase_admin import storage
from google.adk import Context, Workflow
from google.adk.workflow import node
from google.cloud.firestore import SERVER_TIMESTAMP, AsyncDocumentReference, FieldFilter, Increment

from ..config import get_settings
from ..db import db, firebase_app, notify
from ..places import geocode
from . import extractor, summarizer, verifier
from .runner import run_workflow, trip_id_from
from .schemas import Candidate, DroppedPlace, PlaceSummary, VerifiedPlace

logger = logging.getLogger(__name__)

# Every reel with a video is re-read on each run; the cache makes repeats cheap.
READABLE_REEL_STATUSES = ["queued", "processing", "done", "failed"]
GENERIC_FAILURE = "Something went wrong while reading the Reels. Please try again."


# --- Steps -----------------------------------------------------------------------------


async def cache_key(reel: dict[str, Any]) -> str | None:
    """Identifies the video content, so the same sample video hits the same cache entry."""
    if reel.get("storagePath"):
        try:
            bucket = storage.bucket(app=firebase_app())
            blob = await asyncio.to_thread(bucket.get_blob, reel["storagePath"])
        except Exception:
            logger.warning("No content hash for %s", reel["storagePath"], exc_info=True)
            return None
        content = blob.md5_hash if blob else None
    else:
        content = reel.get("sourceUrl")
    return hashlib.sha256(content.encode()).hexdigest() if content else None


async def extract_with_fallback(
    reel: dict[str, Any], destination: str
) -> tuple[list[Candidate], bool]:
    """Live extraction first; a cached result for the same video only if Gemini fails."""
    key = await cache_key(reel)
    cache_ref = db().collection("cache").document(f"extract_{key}") if key else None
    try:
        candidates = await extractor.extract(reel, destination)
    except Exception:
        if cache_ref is not None:
            cached = await cache_ref.get()
            if cached.exists:
                logger.warning("Using cached extraction for reel %s", reel["id"], exc_info=True)
                return [Candidate(**item) for item in cached.get("candidates")], True
        raise
    if cache_ref is not None:
        await cache_ref.set(
            {"candidates": [c.model_dump() for c in candidates], "createdAt": SERVER_TIMESTAMP}
        )
    return candidates, False


def merge_verified(outcomes: list[dict[str, Any]]) -> tuple[list[dict], list[dict]]:
    """Groups verified mentions by Google place ID; de-duplicates dropped names."""
    places: dict[str, dict[str, Any]] = {}
    dropped: dict[str, dict[str, Any]] = {}
    for outcome in outcomes:
        if "dropped" in outcome:
            dropped.setdefault(outcome["dropped"]["name"].lower(), outcome["dropped"])
            continue
        place = outcome["place"]
        entry = places.setdefault(
            place["place_id"],
            {"place": place, "category": outcome["category"], "mentions": [], "savedBy": []},
        )
        entry["mentions"].append(
            {
                "reelId": outcome["reelId"],
                "atSec": outcome["atSec"],
                "evidence": outcome["evidence"],
                "quote": outcome["quote"],
            }
        )
        if outcome["uploaderUid"] not in entry["savedBy"]:
            entry["savedBy"].append(outcome["uploaderUid"])
    return list(places.values()), list(dropped.values())


def place_document(
    entry: dict[str, Any], summary: dict[str, Any], sources: list[dict]
) -> dict[str, Any]:
    place = VerifiedPlace(**entry["place"])
    return {
        "name": place.name,
        "category": entry["category"],
        "address": place.address,
        "location": {"lat": place.lat, "lng": place.lng},
        "googleMapsUri": place.google_maps_uri,
        "types": place.types,
        "rating": place.rating,
        "userRatingCount": place.user_rating_count,
        "priceLevel": place.price_level,
        "priceRange": place.price_range,
        "openingHours": place.opening_hours,
        "photoName": place.photo_name,
        "mentions": entry["mentions"],
        "savedBy": entry["savedBy"],
        "summary": {
            "highlights": summary["highlights"],
            "bestTime": summary["best_time"],
            "priceNote": summary["price_note"],
            "dietaryNote": summary["dietary_note"],
            "crowdNote": summary["crowd_note"],
        },
        "mapsSources": sources,
        "tally": {"must": 0, "maybe": 0, "skip": 0},
    }


# --- ADK nodes ---------------------------------------------------------------------------


async def _tick(trip_id: str) -> None:
    await db().document(f"trips/{trip_id}").update({"pipeline.done": Increment(1)})


@node(name="extract_reel", parallel_worker=True, max_parallel_workers=4)
async def extract_reel(node_input: dict) -> dict:
    trip_id, reel = node_input["tripId"], node_input["reel"]
    reel_ref = db().document(f"trips/{trip_id}/reels/{reel['id']}")
    await reel_ref.update({"status": "processing"})
    try:
        candidates, from_cache = await extract_with_fallback(
            reel, node_input["destination"]["name"]
        )
        failed = False
    except Exception:
        logger.exception("Extraction failed for reel %s", reel["id"])
        candidates, from_cache, failed = [], False, True
    await _tick(trip_id)
    return {
        "reelId": reel["id"],
        "uploaderUid": reel["uploaderUid"],
        "candidates": [candidate.model_dump() for candidate in candidates],
        "failed": failed,
        "fromCache": from_cache,
    }


@node(name="verify_candidate", parallel_worker=True, max_parallel_workers=8)
async def verify_candidate(node_input: dict) -> dict:
    candidate = Candidate(**node_input["candidate"])
    try:
        outcome = await verifier.verify(candidate, node_input["destination"])
    except Exception:
        logger.exception("Verification failed for %r", candidate.name)
        outcome = DroppedPlace(name=candidate.name, reason="couldn't be checked on Google Maps")
    await _tick(node_input["tripId"])
    if isinstance(outcome, DroppedPlace):
        return {"dropped": outcome.model_dump()}
    return {
        "place": outcome.model_dump(),
        "category": candidate.category,
        "reelId": node_input["reelId"],
        "uploaderUid": node_input["uploaderUid"],
        "atSec": candidate.appears_at_sec,
        "evidence": candidate.evidence,
        "quote": candidate.quote,
    }


@node(name="summarize_place", parallel_worker=True, max_parallel_workers=6)
async def summarize_place(node_input: dict) -> dict:
    place = VerifiedPlace(**node_input["place"])
    try:
        summary, sources = await summarizer.summarize(place, node_input["destination"]["name"])
    except Exception:
        # The place is verified, so it still goes on the board without a summary.
        logger.exception("Summary failed for %r", place.name)
        summary, sources = PlaceSummary(), []
    await _tick(node_input["tripId"])
    return {"placeId": place.place_id, "summary": summary.model_dump(), "sources": sources}


async def _stage(trip_ref: AsyncDocumentReference, stage: str, total: int) -> None:
    await trip_ref.update({"pipeline.stage": stage, "pipeline.done": 0, "pipeline.total": total})


async def _fail(
    trip_ref: AsyncDocumentReference, message: str, dropped: list[dict] | None = None
) -> None:
    await trip_ref.update(
        {
            "status": "gathering",
            "pipeline.stage": "failed",
            "pipeline.error": message,
            "pipeline.dropped": dropped or [],
            "pipeline.finishedAt": SERVER_TIMESTAMP,
        }
    )


async def _ingest(ctx: Context, trip_id: str, trip_ref: AsyncDocumentReference) -> dict:
    trip = (await trip_ref.get()).to_dict() or {}
    if not get_settings().places_api_key:
        await _fail(trip_ref, "Place verification isn't set up yet. Ask the team to add the key.")
        return {"ok": False}

    destination = dict(trip["destination"])
    if destination.get("lat") is None:
        coords = await geocode(destination["name"])
        if coords:
            destination["lat"], destination["lng"] = coords
            await trip_ref.update({"destination": destination})

    reels_query = trip_ref.collection("reels").where(
        filter=FieldFilter("status", "in", READABLE_REEL_STATUSES)
    )
    reels = [
        {
            "id": snapshot.id,
            "uploaderUid": snapshot.get("uploaderUid"),
            "storagePath": (snapshot.to_dict() or {}).get("storagePath"),
            "sourceUrl": (snapshot.to_dict() or {}).get("sourceUrl"),
        }
        async for snapshot in reels_query.stream()
    ]

    await _stage(trip_ref, "extracting", len(reels))
    extracted = await ctx.run_node(
        extract_reel,
        [{"tripId": trip_id, "reel": reel, "destination": destination} for reel in reels],
    )

    jobs = [
        {
            "tripId": trip_id,
            "destination": destination,
            "candidate": candidate,
            "reelId": result["reelId"],
            "uploaderUid": result["uploaderUid"],
        }
        for result in extracted
        for candidate in result["candidates"]
    ]
    await _stage(trip_ref, "verifying", len(jobs))
    places, dropped = merge_verified(await ctx.run_node(verify_candidate, jobs))

    batch = db().batch()
    for result in extracted:
        found = sum(
            any(m["reelId"] == result["reelId"] for m in entry["mentions"]) for entry in places
        )
        update: dict[str, Any] = {"status": "failed" if result["failed"] else "done"}
        if result["failed"]:
            update["error"] = "The AI couldn't read this video."
        else:
            update["placesFound"] = found
        batch.update(trip_ref.collection("reels").document(result["reelId"]), update)
    await batch.commit()

    if not places:
        await _fail(
            trip_ref,
            "No real places could be verified from these Reels. Add Reels that name specific "
            "places, then try again.",
            dropped,
        )
        return {"ok": False}

    await _stage(trip_ref, "summarizing", len(places))
    summaries = await ctx.run_node(
        summarize_place,
        [
            {"tripId": trip_id, "destination": destination, "place": entry["place"]}
            for entry in places
        ],
    )

    batch = db().batch()
    for entry, summary in zip(places, summaries, strict=True):
        place_ref = trip_ref.collection("places").document(summary["placeId"])
        batch.set(place_ref, place_document(entry, summary["summary"], summary["sources"]))
    batch.update(
        trip_ref,
        {
            "status": "voting",
            "pipeline.stage": "done",
            "pipeline.dropped": dropped,
            "pipeline.usedFallback": any(result["fromCache"] for result in extracted),
            "pipeline.finishedAt": SERVER_TIMESTAMP,
        },
    )
    await batch.commit()

    count = len(places)
    found = f"{count} {'place' if count == 1 else 'places'}"
    for uid in trip["memberUids"]:
        await notify(
            uid,
            type="voting_open",
            text=f"{found} found in your Reels. Time to vote!",
            trip_id=trip_id,
            link=f"/trips/{trip_id}/places",
        )
    return {"ok": True, "places": count}


@node(name="ingest_trip", rerun_on_resume=True)
async def ingest_trip(ctx: Context, node_input: Any) -> dict:
    trip_id = trip_id_from(node_input)
    trip_ref = db().document(f"trips/{trip_id}")
    try:
        return await _ingest(ctx, trip_id, trip_ref)
    except Exception:
        logger.exception("Ingest failed for trip %s", trip_id)
        await _fail(trip_ref, GENERIC_FAILURE)
        return {"ok": False}


ingest_workflow = Workflow(name="travelin_ingest", edges=[("START", ingest_trip)])


async def run_ingest(trip_id: str) -> None:
    """Runs the ingest workflow for one trip. Progress and results land in Firestore."""
    try:
        await run_workflow(ingest_workflow, trip_id)
    except Exception:
        logger.exception("Ingest workflow crashed for trip %s", trip_id)
        await _fail(db().document(f"trips/{trip_id}"), GENERIC_FAILURE)
