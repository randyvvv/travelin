"""Adding places without Reels: search Google Maps, or ask the AI for suggestions."""

import logging
from typing import Any

import httpx
from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Response, status
from fastapi.responses import JSONResponse
from google.cloud.firestore import ArrayUnion, AsyncTransaction, async_transactional

from ..ai import summarizer
from ..ai.ingest import place_document, summary_fields
from ..ai.schemas import PlaceSummary, VerifiedPlace
from ..ai.suggest import claim_suggesting, run_suggest
from ..ai.suggester import category_from_types
from ..ai.verifier import SEARCH_RADIUS_M, to_verified
from ..auth import CurrentUser, MemberTrip
from ..db import db
from ..places import (
    SEARCH_FIELD_MASK,
    PlacesUnavailableError,
    fresh_curated_photo,
    fresh_place_photo,
    get_place,
    search_text,
)
from ..schemas import CamelModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1", tags=["places"])

CURATED_DESTINATIONS = {
    "bali": "Bali, Indonesia",
    "yogyakarta": "Yogyakarta, Indonesia",
    "singapore": "Singapore",
    "bangkok": "Bangkok, Thailand",
    "kuala-lumpur": "Kuala Lumpur, Malaysia",
    "ho-chi-minh-city": "Ho Chi Minh City, Vietnam",
}
NO_STORE_HEADERS = {"Cache-Control": "no-store", "Pragma": "no-cache"}


class PlaceHit(CamelModel):
    place_id: str
    name: str
    address: str
    rating: float | None
    user_rating_count: int | None
    category: str
    on_board: bool


class AddPlace(CamelModel):
    place_id: str


class PlaceAdded(CamelModel):
    place_id: str
    already_added: bool


class SuggestStarted(CamelModel):
    status: str


def require_gathering(trip: dict[str, Any]) -> None:
    if trip["status"] != "gathering":
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Places can only be changed before voting starts."
        )


def places_unavailable() -> HTTPException:
    return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Place search isn't set up yet.")


def photo_unavailable() -> HTTPException:
    return HTTPException(
        status.HTTP_503_SERVICE_UNAVAILABLE,
        "Place photos aren't available right now.",
        headers=NO_STORE_HEADERS,
    )


def photo_response(payload: dict[str, Any] | None) -> Response:
    return JSONResponse(content=payload, headers=NO_STORE_HEADERS)


async def summarize_added_place(trip_id: str, destination: str, place: VerifiedPlace) -> None:
    try:
        summary, sources = await summarizer.summarize(place, destination)
    except Exception:
        logger.exception("Summary failed for %r", place.name)
        summary, sources = PlaceSummary(), []
    await (
        db()
        .document(f"trips/{trip_id}/places/{place.place_id}")
        .update(
            {
                "summary": summary_fields(summary.model_dump()),
                "mapsSources": sources,
                "summaryPending": False,
            }
        )
    )


@router.get("/trips/{trip_id}/places:search")
async def search_places(
    trip: MemberTrip, q: str = Query(min_length=2, max_length=100)
) -> list[PlaceHit]:
    require_gathering(trip)
    destination = trip["destination"]
    has_coords = destination.get("lat") is not None
    try:
        results = await search_text(
            q if destination["name"].lower() in q.lower() else f"{q}, {destination['name']}",
            field_mask=SEARCH_FIELD_MASK,
            bias=(destination["lat"], destination["lng"], SEARCH_RADIUS_M) if has_coords else None,
            page_size=6,
        )
    except PlacesUnavailableError:
        raise places_unavailable() from None
    on_board = {
        snapshot.id async for snapshot in db().collection(f"trips/{trip['id']}/places").stream()
    }
    hits = []
    for result in results:
        if not result.get("location"):
            continue
        place = to_verified(result)
        hits.append(
            PlaceHit(
                place_id=place.place_id,
                name=place.name,
                address=place.address,
                rating=place.rating,
                user_rating_count=place.user_rating_count,
                category=category_from_types(place.types),
                on_board=place.place_id in on_board,
            )
        )
    return hits


@router.get("/trips/{trip_id}/places/{place_id}/photo")
async def trip_place_photo(trip: MemberTrip, place_id: str) -> Response:
    """Return an uncached, freshly resolved photo for a place on this trip's board."""
    place_ref = db().document(f"trips/{trip['id']}/places/{place_id}")
    if not (await place_ref.get()).exists:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Place not found on this trip.")
    try:
        payload = await fresh_place_photo(place_id)
    except PlacesUnavailableError:
        raise photo_unavailable() from None
    except httpx.HTTPError:
        logger.exception("Place photo lookup failed for %s", place_id)
        raise photo_unavailable() from None
    return photo_response(payload)


@router.get("/home/destinations/{slug}/photo")
async def curated_destination_photo(slug: str, user: CurrentUser) -> Response:
    """Resolve a fresh photo for one allowlisted Home inspiration destination."""
    query = CURATED_DESTINATIONS.get(slug)
    if query is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Destination not found.")
    try:
        payload = await fresh_curated_photo(query)
    except PlacesUnavailableError:
        raise photo_unavailable() from None
    except httpx.HTTPError:
        logger.exception("Curated destination photo lookup failed for %s", slug)
        raise photo_unavailable() from None
    return photo_response(payload)


@router.post("/trips/{trip_id}/places", status_code=status.HTTP_201_CREATED)
async def add_place(
    body: AddPlace, trip: MemberTrip, user: CurrentUser, background_tasks: BackgroundTasks
) -> PlaceAdded:
    require_gathering(trip)
    place_ref = db().document(f"trips/{trip['id']}/places/{body.place_id}")
    if (await place_ref.get()).exists:
        await place_ref.update({"savedBy": ArrayUnion([user.uid])})
        return PlaceAdded(place_id=body.place_id, already_added=True)

    try:
        details = await get_place(body.place_id)
    except PlacesUnavailableError:
        raise places_unavailable() from None
    if details is None or not details.get("location"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Google Maps doesn't know that place.")

    place = to_verified(details)
    # Added from Google Maps itself, so it is verified by construction; the summary follows.
    await place_ref.set(
        place_document(
            place,
            category_from_types(place.types),
            None,
            [],
            saved_by=[user.uid],
            added_by=user.uid,
        )
    )
    background_tasks.add_task(summarize_added_place, trip["id"], trip["destination"]["name"], place)
    return PlaceAdded(place_id=place.place_id, already_added=False)


@router.delete("/trips/{trip_id}/places/{place_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_place(trip: MemberTrip, user: CurrentUser, place_id: str) -> Response:
    trip_ref = db().collection("trips").document(trip["id"])
    place_ref = trip_ref.collection("places").document(place_id)

    @async_transactional
    async def remove(transaction: AsyncTransaction) -> None:
        current_snapshot = await trip_ref.get(transaction=transaction)
        if not current_snapshot.exists:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Trip not found.")
        current_trip = current_snapshot.to_dict() or {}
        if user.uid not in current_trip.get("memberUids", []):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Not a member of this trip.")
        require_gathering(current_trip)
        place_snapshot = await place_ref.get(transaction=transaction)
        if not place_snapshot.exists:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Place not found on this trip.")
        transaction.delete(place_ref)

    await remove(db().transaction())
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/trips/{trip_id}/places:suggest", status_code=status.HTTP_202_ACCEPTED)
async def suggest_places(trip: MemberTrip, background_tasks: BackgroundTasks) -> SuggestStarted:
    require_gathering(trip)
    if not await claim_suggesting(db().document(f"trips/{trip['id']}")):
        raise HTTPException(status.HTTP_409_CONFLICT, "Suggestions are already on their way.")
    background_tasks.add_task(run_suggest, trip["id"])
    return SuggestStarted(status="suggesting")
