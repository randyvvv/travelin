from typing import Any

from fastapi import APIRouter, HTTPException, status
from google.cloud.firestore import (
    SERVER_TIMESTAMP,
    AsyncTransaction,
    Increment,
    async_transactional,
)

from ..auth import CurrentUser, MemberTrip
from ..db import db, notify
from ..schemas import CamelModel

router = APIRouter(prefix="/v1", tags=["voting"])

VOTES = {"must", "maybe", "skip"}


class SubmitVotesResponse(CamelModel):
    all_submitted: bool


@router.post("/trips/{trip_id}/votes:submit")
async def submit_votes(trip: MemberTrip, user: CurrentUser) -> SubmitVotesResponse:
    trip_ref = db().document(f"trips/{trip['id']}")
    members_ref = trip_ref.collection("members")

    @async_transactional
    async def submit(transaction: AsyncTransaction) -> bool:
        current = (await trip_ref.get(transaction=transaction)).to_dict() or {}
        if current.get("status") != "voting":
            raise HTTPException(status.HTTP_409_CONFLICT, "Voting isn't open for this trip.")
        members = {
            snapshot.id: snapshot.to_dict() or {}
            async for snapshot in members_ref.stream(transaction=transaction)
        }
        me = members[user.uid]
        if me.get("votesSubmittedAt") is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, "You've already submitted your votes.")

        place_ids = {
            snapshot.id
            async for snapshot in trip_ref.collection("places").stream(transaction=transaction)
        }
        votes: dict[str, Any] = me.get("votes") or {}
        for place_id, vote in votes.items():
            if place_id in place_ids and vote in VOTES:
                transaction.update(
                    trip_ref.collection("places").document(place_id),
                    {f"tally.{vote}": Increment(1)},
                )
        transaction.update(members_ref.document(user.uid), {"votesSubmittedAt": SERVER_TIMESTAMP})
        return all(
            uid == user.uid or member.get("votesSubmittedAt") is not None
            for uid, member in members.items()
        )

    all_submitted = await submit(db().transaction())
    if all_submitted:
        await notify(
            trip["hostUid"],
            type="voting_deadline",
            text=f"Everyone has voted on {trip['name']}.",
            trip_id=trip["id"],
            link=f"/trips/{trip['id']}",
        )
    return SubmitVotesResponse(all_submitted=all_submitted)
