from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, status

from ..ai.plan import claim_planning, run_plan
from ..auth import CurrentUser, MemberTrip, User
from ..db import db, notify
from ..schemas import CamelModel

router = APIRouter(prefix="/v1", tags=["planning"])

DEADLINE_STATUSES = {"gathering", "extracting", "voting"}


class VotingUpdate(CamelModel):
    deadline: datetime | None


class PlanResponse(CamelModel):
    status: str


def require_host(trip: dict[str, Any], user: User, action: str) -> None:
    if trip["hostUid"] != user.uid:
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"Only the host can {action}.")


@router.patch("/trips/{trip_id}/voting", status_code=status.HTTP_204_NO_CONTENT)
async def update_voting(body: VotingUpdate, trip: MemberTrip, user: CurrentUser) -> None:
    require_host(trip, user, "set the voting deadline")
    if trip["status"] not in DEADLINE_STATUSES:
        raise HTTPException(status.HTTP_409_CONFLICT, "Voting is already over for this trip.")
    deadline = body.deadline
    if deadline is not None:
        if deadline.tzinfo is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Include a time zone.")
        if deadline <= datetime.now(UTC):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Pick a time in the future.")

    await db().document(f"trips/{trip['id']}").update({"votingDeadline": deadline})
    if deadline is not None:
        for uid in trip["memberUids"]:
            if uid != user.uid:
                await notify(
                    uid,
                    type="voting_deadline",
                    text=f"The host set a voting deadline for {trip['name']}.",
                    trip_id=trip["id"],
                    link=f"/trips/{trip['id']}/places",
                )


@router.post("/trips/{trip_id}/plan", status_code=status.HTTP_202_ACCEPTED)
async def start_plan(
    trip: MemberTrip, user: CurrentUser, background_tasks: BackgroundTasks
) -> PlanResponse:
    require_host(trip, user, "close voting")
    if not await claim_planning(db().document(f"trips/{trip['id']}")):
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Voting isn't open, so there's nothing to plan."
        )
    background_tasks.add_task(run_plan, trip["id"])
    return PlanResponse(status="planning")
