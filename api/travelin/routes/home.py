"""Authenticated Home recommendations with a per-user daily Place ID cache."""

import logging
import uuid
from datetime import UTC, date, datetime, timedelta, timezone
from typing import Any, Literal

import httpx
from fastapi import APIRouter, HTTPException, Response, status
from fastapi.responses import JSONResponse
from google.cloud.firestore import (
    SERVER_TIMESTAMP,
    AsyncTransaction,
    FieldFilter,
    async_transactional,
)

from ..ai import suggester, verifier
from ..ai.schemas import Candidate, DroppedPlace, VerifiedPlace
from ..ai.suggester import category_from_types
from ..ai.verifier import SEARCH_RADIUS_M
from ..auth import CurrentUser
from ..db import db
from ..places import (
    HOME_IDEA_FIELD_MASK,
    PlacesUnavailableError,
    fresh_home_idea_details,
    fresh_place_photo,
    search_text,
)
from ..schemas import CamelModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/home", tags=["home"])

# Jakarta has a fixed UTC+7 offset and no daylight-saving transitions. Using a
# fixed offset also keeps this correct on Windows systems without tzdata.
JAKARTA = timezone(timedelta(hours=7), name="Asia/Jakarta")
GENERATION_LEASE = timedelta(minutes=5)
PERSONAL_LIMIT = 3
IDEA_LIMIT = 5
POPULAR_POOL_LIMIT = 20
POPULAR_QUERY = "popular tourist attractions and places to visit in Southeast Asia"
HOME_PHOTO_HEADERS = {"Cache-Control": "no-store", "Pragma": "no-cache"}


class HomeIdea(CamelModel):
    place_id: str
    name: str
    category: str
    address: str
    rating: float | None = None
    user_rating_count: int | None = None
    google_maps_uri: str
    source: Literal["personal", "popular"]


class HomeIdeasResponse(CamelModel):
    state: Literal["ready", "generating", "failed"]
    day_key: str
    trip_id: str | None = None
    destination: str | None = None
    trip_status: str | None = None
    ideas: list[HomeIdea] = []


def jakarta_day_key(now: datetime | None = None) -> str:
    """Return the app's daily refresh key in the Travelin home timezone."""
    local_now = (now or datetime.now(UTC)).astimezone(JAKARTA)
    return local_now.date().isoformat()


def select_home_trip(
    trips: list[dict[str, Any]], today: date | None = None
) -> dict[str, Any] | None:
    """Prefer a gathering trip in progress, otherwise the soonest upcoming one."""
    today = today or datetime.now(JAKARTA).date()
    day_key = today.isoformat()
    active = [trip for trip in trips if trip.get("status") == "gathering"]
    underway = [
        trip
        for trip in active
        if trip.get("startDate", "") <= day_key and trip.get("endDate", "") >= day_key
    ]
    if underway:
        return min(underway, key=lambda trip: (trip.get("endDate", ""), trip.get("startDate", "")))
    upcoming = [trip for trip in active if trip.get("startDate", "") > day_key]
    return min(upcoming, key=lambda trip: trip.get("startDate", ""), default=None)


def has_personal_preferences(member: dict[str, Any] | None) -> bool:
    prefs = (member or {}).get("prefs") or {}
    return bool(
        prefs.get("budgetIdr")
        or prefs.get("interests")
        or prefs.get("dietary")
        or prefs.get("skip")
    )


def ranked_popular_places(places: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rank the Google search candidates by review volume, with stable ties."""
    unique: dict[str, dict[str, Any]] = {}
    for place in places:
        place_id = place.get("id")
        if place_id:
            unique.setdefault(place_id, place)
    return sorted(
        unique.values(),
        key=lambda place: (
            -(place.get("userRatingCount") or 0),
            -(place.get("rating") or 0),
            place.get("id", ""),
        ),
    )


def _cache_ref(uid: str):
    return db().collection("users").document(uid).collection("homeIdeas").document("current")


async def _claim_daily_cache(ref: Any, day_key: str) -> tuple[str, dict[str, Any], str | None]:
    claim_id = uuid.uuid4().hex
    now = datetime.now(UTC)

    @async_transactional
    async def claim(transaction: AsyncTransaction) -> tuple[str, dict[str, Any], str | None]:
        snapshot = await ref.get(transaction=transaction)
        cached = snapshot.to_dict() or {}
        if cached.get("dayKey") == day_key:
            if cached.get("state") in {"ready", "failed"}:
                return cached["state"], cached, None
            if cached.get("state") == "generating":
                lease_expires = cached.get("leaseExpiresAt")
                if lease_expires and lease_expires > now:
                    return "generating", cached, None
                transaction.update(
                    ref,
                    {"state": "failed", "failureCode": "generation_timed_out"},
                )
                return "failed", {**cached, "state": "failed"}, None

        new_cache = {
            "dayKey": day_key,
            "state": "generating",
            "generationId": claim_id,
            "leaseExpiresAt": now + GENERATION_LEASE,
            "createdAt": SERVER_TIMESTAMP,
            "personalPlaceIds": [],
            "popularPlaceIds": [],
            "tripId": None,
        }
        transaction.set(ref, new_cache)
        return "claimed", new_cache, claim_id

    return await claim(db().transaction())


async def _finish_daily_cache(
    ref: Any,
    claim_id: str,
    *,
    trip_id: str | None,
    personal_place_ids: list[str],
    popular_place_ids: list[str],
) -> bool:
    @async_transactional
    async def finish(transaction: AsyncTransaction) -> bool:
        snapshot = await ref.get(transaction=transaction)
        cached = snapshot.to_dict() or {}
        if cached.get("state") != "generating" or cached.get("generationId") != claim_id:
            return False
        transaction.update(
            ref,
            {
                "state": "ready",
                "tripId": trip_id,
                "personalPlaceIds": personal_place_ids,
                "popularPlaceIds": popular_place_ids,
                "finishedAt": SERVER_TIMESTAMP,
                "generationId": None,
                "leaseExpiresAt": None,
            },
        )
        return True

    return await finish(db().transaction())


async def _fail_daily_cache(ref: Any, claim_id: str, failure_code: str) -> None:
    @async_transactional
    async def fail(transaction: AsyncTransaction) -> None:
        snapshot = await ref.get(transaction=transaction)
        cached = snapshot.to_dict() or {}
        if cached.get("state") == "generating" and cached.get("generationId") == claim_id:
            transaction.update(
                ref,
                {
                    "state": "failed",
                    "failureCode": failure_code,
                    "generationId": None,
                    "leaseExpiresAt": None,
                    "finishedAt": SERVER_TIMESTAMP,
                },
            )

    await fail(db().transaction())


async def _load_trips_for_user(uid: str) -> list[dict[str, Any]]:
    query = db().collection("trips").where(
        filter=FieldFilter("memberUids", "array_contains", uid)
    )
    return [
        {"id": snapshot.id, **(snapshot.to_dict() or {})}
        async for snapshot in query.stream()
    ]


async def _board_places(trip_id: str) -> tuple[set[str], list[str]]:
    place_ids: set[str] = set()
    names: list[str] = []
    trip_ref = db().collection("trips").document(trip_id)
    for collection_name in ("places", "suggestions"):
        async for snapshot in trip_ref.collection(collection_name).stream():
            place_ids.add(snapshot.id)
            name = (snapshot.to_dict() or {}).get("name")
            if name:
                names.append(name)
    return place_ids, names


async def _personal_ideas(
    trip: dict[str, Any],
    member: dict[str, Any],
    board_names: list[str],
    board_ids: set[str],
) -> tuple[list[str], dict[str, VerifiedPlace]]:
    suggestions = await suggester.suggest(trip, [member], board_names, count=8)
    destination = trip["destination"]
    found: list[str] = []
    transient: dict[str, VerifiedPlace] = {}
    for suggestion in suggestions:
        candidate = Candidate(
            name=suggestion.name,
            city_hint=destination["name"],
            category=suggestion.category,
            confidence=1.0,
        )
        result = await verifier.verify(candidate, destination)
        if (
            isinstance(result, DroppedPlace)
            or result.place_id in board_ids
            or result.place_id in transient
        ):
            continue
        found.append(result.place_id)
        transient[result.place_id] = result
        if len(found) == PERSONAL_LIMIT:
            break
    return found, transient


async def _popular_ideas(
    excluded_ids: set[str], trip: dict[str, Any] | None = None
) -> tuple[list[str], dict[str, dict[str, Any]]]:
    query = POPULAR_QUERY
    bias = None
    if trip:
        destination = trip.get("destination") or {}
        query = f"popular tourist attractions and places to visit in {destination['name']}"
        if destination.get("lat") is not None and destination.get("lng") is not None:
            bias = (destination["lat"], destination["lng"], SEARCH_RADIUS_M)
    places = await search_text(
        query,
        field_mask=",".join(f"places.{field}" for field in HOME_IDEA_FIELD_MASK.split(",")),
        bias=bias,
        page_size=POPULAR_POOL_LIMIT,
    )
    ranked = ranked_popular_places(places)
    transient = {
        place["id"]: place for place in ranked if place["id"] not in excluded_ids
    }
    return list(transient), transient


async def _generate_daily_ideas(
    uid: str,
) -> tuple[str | None, list[str], list[str], dict[str, Any]]:
    trip = select_home_trip(await _load_trips_for_user(uid))
    trip_id = trip["id"] if trip else None
    personal_ids: list[str] = []
    transient: dict[str, Any] = {}
    board_ids: set[str] = set()

    if trip:
        board_ids, board_names = await _board_places(trip_id)
        member_snapshot = await (
            db().collection("trips").document(trip_id).collection("members").document(uid).get()
        )
        member = member_snapshot.to_dict() if member_snapshot.exists else None
        if has_personal_preferences(member):
            try:
                personal_ids, personal = await _personal_ideas(
                    trip, member or {}, board_names, board_ids
                )
                transient.update(personal)
            except Exception:
                # Personalization is an enhancement; keep the Home ideas useful
                # with the general popular set if the AI lookup is unavailable.
                logger.exception("Personal Home ideas lookup failed for %s", uid)

    popular_ids, popular = await _popular_ideas(board_ids | set(personal_ids), trip)
    transient.update(popular)
    return trip_id, personal_ids, popular_ids, transient


async def _load_context(trip_id: str | None, uid: str) -> tuple[dict[str, Any] | None, set[str]]:
    if not trip_id:
        return None, set()
    snapshot = await db().collection("trips").document(trip_id).get()
    if not snapshot.exists:
        return None, set()
    trip = {"id": snapshot.id, **(snapshot.to_dict() or {})}
    if uid not in trip.get("memberUids", []):
        return None, set()
    if trip.get("status") != "gathering":
        return None, set()
    board_ids, _ = await _board_places(trip_id)
    return trip, board_ids


def _as_home_idea(place: VerifiedPlace, source: Literal["personal", "popular"]) -> HomeIdea:
    return HomeIdea(
        place_id=place.place_id,
        name=place.name,
        category=category_from_types(place.types),
        address=place.address,
        rating=place.rating,
        user_rating_count=place.user_rating_count,
        google_maps_uri=place.google_maps_uri,
        source=source,
    )


async def _fresh_verified_place(place_id: str) -> VerifiedPlace | None:
    details = await fresh_home_idea_details(place_id)
    if details is None or not details.get("location"):
        return None
    return verifier.to_verified(details)


async def _resolve_daily_ideas(
    cache: dict[str, Any],
    uid: str,
    *,
    transient: dict[str, Any] | None = None,
) -> HomeIdeasResponse:
    trip, board_ids = await _load_context(cache.get("tripId"), uid)
    transient = transient or {}
    personal_ids = cache.get("personalPlaceIds", []) if trip else []
    popular_ids = cache.get("popularPlaceIds", [])
    selected: list[tuple[str, Literal["personal", "popular"]]] = []
    selected_ids: set[str] = set()

    async def add_candidates(
        ids: list[str], source: Literal["personal", "popular"], limit: int
    ) -> None:
        for place_id in ids:
            if len([item for item in selected if item[1] == source]) >= limit:
                break
            if place_id in board_ids or place_id in selected_ids:
                continue
            place = transient.get(place_id)
            if place is None:
                place = await _fresh_verified_place(place_id)
            elif isinstance(place, dict):
                if not place.get("location"):
                    continue
                place = verifier.to_verified(place)
            if place is None:
                continue
            selected.append((place_id, source))
            selected_ids.add(place_id)
            transient[place_id] = place

    await add_candidates(personal_ids, "personal", PERSONAL_LIMIT)
    await add_candidates(popular_ids, "popular", IDEA_LIMIT - len(selected))

    ideas = [
        _as_home_idea(transient[place_id], source)
        for place_id, source in selected[:IDEA_LIMIT]
    ]
    return HomeIdeasResponse(
        state="ready",
        day_key=cache["dayKey"],
        trip_id=trip["id"] if trip else None,
        destination=trip.get("destination", {}).get("name") if trip else None,
        trip_status=trip.get("status") if trip else None,
        ideas=ideas,
    )


def _response_from_cache_state(
    state: str, day_key: str, cache: dict[str, Any]
) -> HomeIdeasResponse:
    return HomeIdeasResponse(
        state=state,  # type: ignore[arg-type]
        day_key=day_key,
        trip_id=cache.get("tripId"),
        ideas=[],
    )


@router.get("/ideas", response_model=HomeIdeasResponse)
async def daily_home_ideas(user: CurrentUser, response: Response) -> HomeIdeasResponse:
    """Choose ideas on first Home open of the Jakarta calendar day, then reuse IDs."""
    day_key = jakarta_day_key()
    response.headers.update(HOME_PHOTO_HEADERS)
    ref = _cache_ref(user.uid)
    state, cache, claim_id = await _claim_daily_cache(ref, day_key)

    if state == "ready":
        return await _resolve_daily_ideas(cache, user.uid)
    if state in {"generating", "failed"}:
        return _response_from_cache_state(state, day_key, cache)

    try:
        trip_id, personal_ids, popular_ids, transient = await _generate_daily_ideas(user.uid)
        if not claim_id or not await _finish_daily_cache(
            ref,
            claim_id,
            trip_id=trip_id,
            personal_place_ids=personal_ids,
            popular_place_ids=popular_ids,
        ):
            latest = await ref.get()
            return _response_from_cache_state("generating", day_key, latest.to_dict() or {})
        cache = {
            "dayKey": day_key,
            "state": "ready",
            "tripId": trip_id,
            "personalPlaceIds": personal_ids,
            "popularPlaceIds": popular_ids,
        }
        return await _resolve_daily_ideas(cache, user.uid, transient=transient)
    except (PlacesUnavailableError, httpx.HTTPError):
        logger.exception("Home ideas lookup failed for %s", user.uid)
        if claim_id:
            await _fail_daily_cache(ref, claim_id, "places_unavailable")
        return _response_from_cache_state("failed", day_key, cache)
    except Exception:
        logger.exception("Home ideas generation failed for %s", user.uid)
        if claim_id:
            await _fail_daily_cache(ref, claim_id, "generation_failed")
        return _response_from_cache_state("failed", day_key, cache)


@router.get("/ideas/{place_id}/photo")
async def daily_home_idea_photo(place_id: str, user: CurrentUser) -> Response:
    """Resolve a fresh photo only for a Place ID in this user's daily idea set."""
    day_key = jakarta_day_key()
    snapshot = await _cache_ref(user.uid).get()
    cached = snapshot.to_dict() or {}
    cached_ids = set(cached.get("personalPlaceIds", [])) | set(cached.get("popularPlaceIds", []))
    if (
        cached.get("dayKey") != day_key
        or cached.get("state") != "ready"
        or place_id not in cached_ids
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Place is not in today's ideas.")
    try:
        payload = await fresh_place_photo(place_id)
    except PlacesUnavailableError:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"detail": "Place photos aren't available right now."},
            headers=HOME_PHOTO_HEADERS,
        )
    except httpx.HTTPError:
        logger.exception("Home idea photo lookup failed for %s", place_id)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"detail": "Place photos aren't available right now."},
            headers=HOME_PHOTO_HEADERS,
        )
    return JSONResponse(content=payload, headers=HOME_PHOTO_HEADERS)
