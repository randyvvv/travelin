import logging
import secrets
from datetime import date
from typing import Any

from fastapi import APIRouter, HTTPException, status
from google.cloud.firestore import (
    SERVER_TIMESTAMP,
    ArrayUnion,
    AsyncTransaction,
    DocumentSnapshot,
    FieldFilter,
    async_transactional,
)
from pydantic import Field, model_validator

from ..auth import CurrentUser, User
from ..db import db, notify
from ..places import PlacesUnavailableError, geocode
from ..schemas import CamelModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1", tags=["trips"])

MAX_MEMBERS = 8
MAX_TRIP_DAYS = 14
JOINABLE_STATUSES = {"gathering", "extracting", "voting"}
# No 0/O or 1/I/L, so codes survive being read aloud or retyped.
INVITE_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
INVITE_LENGTH = 8


class CreateTripRequest(CamelModel):
    name: str = Field(min_length=1, max_length=80)
    destination: str = Field(min_length=1, max_length=120)
    origin: str = Field(min_length=1, max_length=120)
    start_date: date
    end_date: date

    @model_validator(mode="after")
    def check_dates(self) -> "CreateTripRequest":
        if self.end_date < self.start_date:
            raise ValueError("The trip must end on or after its start date")
        if (self.end_date - self.start_date).days >= MAX_TRIP_DAYS:
            raise ValueError(f"A trip can be at most {MAX_TRIP_DAYS} days long")
        return self


class CreateTripResponse(CamelModel):
    trip_id: str
    invite_code: str


class InvitePreview(CamelModel):
    trip_id: str
    name: str
    destination: str
    start_date: str
    end_date: str
    host_name: str
    member_count: int
    already_member: bool
    joinable: bool


class JoinResponse(CamelModel):
    trip_id: str


def new_invite_code() -> str:
    return "".join(secrets.choice(INVITE_ALPHABET) for _ in range(INVITE_LENGTH))


def display_name(user: User) -> str:
    return user.name or (user.email or "Traveler").split("@")[0]


def new_member(user: User, role: str) -> dict[str, Any]:
    return {
        "displayName": display_name(user),
        "photoURL": user.picture or "",
        "role": role,
        "isBot": False,
        "prefs": {"budgetIdr": 0, "interests": [], "dietary": [], "skip": []},
        "prefsDone": False,
        "votes": {},
        "votesSubmittedAt": None,
        "splitApprovedVersion": None,
        "joinedAt": SERVER_TIMESTAMP,
    }


def is_joinable(trip: dict[str, Any]) -> bool:
    return trip["status"] in JOINABLE_STATUSES and len(trip["memberUids"]) < MAX_MEMBERS


async def trip_by_invite(invite_code: str) -> DocumentSnapshot:
    query = (
        db()
        .collection("trips")
        .where(filter=FieldFilter("inviteCode", "==", invite_code.strip().upper()))
        .limit(1)
    )
    async for snapshot in query.stream():
        return snapshot
    raise HTTPException(status.HTTP_404_NOT_FOUND, "This invite link isn't valid.")


@router.post("/trips", status_code=status.HTTP_201_CREATED)
async def create_trip(body: CreateTripRequest, user: CurrentUser) -> CreateTripResponse:
    try:
        coords = await geocode(body.destination)
    except PlacesUnavailableError:
        coords = None
    except Exception:
        # Best effort only: ingest geocodes again before it verifies places.
        logger.warning("Could not geocode %r", body.destination, exc_info=True)
        coords = None

    trip_ref = db().collection("trips").document()
    invite_code = new_invite_code()
    batch = db().batch()
    batch.set(
        trip_ref,
        {
            "name": body.name,
            "startDate": body.start_date.isoformat(),
            "endDate": body.end_date.isoformat(),
            "origin": body.origin,
            "destination": {
                "name": body.destination,
                "lat": coords[0] if coords else None,
                "lng": coords[1] if coords else None,
            },
            "hostUid": user.uid,
            "memberUids": [user.uid],
            "inviteCode": invite_code,
            "status": "gathering",
            "votingDeadline": None,
            "split": {"version": 0},
            "isDemo": False,
            "createdAt": SERVER_TIMESTAMP,
        },
    )
    batch.set(trip_ref.collection("members").document(user.uid), new_member(user, "host"))
    await batch.commit()
    return CreateTripResponse(trip_id=trip_ref.id, invite_code=invite_code)


@router.get("/join/{invite_code}")
async def preview_invite(invite_code: str, user: CurrentUser) -> InvitePreview:
    snapshot = await trip_by_invite(invite_code)
    trip = snapshot.to_dict() or {}
    host = await snapshot.reference.collection("members").document(trip["hostUid"]).get()
    return InvitePreview(
        trip_id=snapshot.id,
        name=trip["name"],
        destination=trip["destination"]["name"],
        start_date=trip["startDate"],
        end_date=trip["endDate"],
        host_name=(host.to_dict() or {}).get("displayName", "Your friend"),
        member_count=len(trip["memberUids"]),
        already_member=user.uid in trip["memberUids"],
        joinable=is_joinable(trip),
    )


@router.post("/join/{invite_code}")
async def join_trip(invite_code: str, user: CurrentUser) -> JoinResponse:
    trip_ref = (await trip_by_invite(invite_code)).reference

    @async_transactional
    async def add_member(transaction: AsyncTransaction) -> dict[str, Any] | None:
        trip = (await trip_ref.get(transaction=transaction)).to_dict() or {}
        if user.uid in trip["memberUids"]:
            return None
        if trip["status"] not in JOINABLE_STATUSES:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "This trip has moved past voting, so it can't take new members.",
            )
        if len(trip["memberUids"]) >= MAX_MEMBERS:
            raise HTTPException(
                status.HTTP_409_CONFLICT, f"This trip is full ({MAX_MEMBERS} members)."
            )
        transaction.update(trip_ref, {"memberUids": ArrayUnion([user.uid])})
        transaction.set(
            trip_ref.collection("members").document(user.uid), new_member(user, "member")
        )
        return trip

    trip = await add_member(db().transaction())
    if trip is not None:
        await notify(
            trip["hostUid"],
            type="joined",
            text=f"{display_name(user)} joined {trip['name']}",
            trip_id=trip_ref.id,
            link=f"/trips/{trip_ref.id}",
        )
    return JoinResponse(trip_id=trip_ref.id)
