from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from google.cloud.firestore import (
    SERVER_TIMESTAMP,
    AsyncTransaction,
    FieldFilter,
    async_transactional,
)

from ..ai.ingest import READABLE_REEL_STATUSES, run_ingest
from ..auth import CurrentUser, MemberTrip
from ..db import db
from ..schemas import CamelModel

router = APIRouter(prefix="/v1", tags=["ingest"])


class IngestResponse(CamelModel):
    status: str


@router.post("/trips/{trip_id}/ingest", status_code=status.HTTP_202_ACCEPTED)
async def start_ingest(
    trip: MemberTrip, user: CurrentUser, background_tasks: BackgroundTasks
) -> IngestResponse:
    if trip["hostUid"] != user.uid:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the host can start finding places.")

    trip_ref = db().document(f"trips/{trip['id']}")
    readable = (
        trip_ref.collection("reels")
        .where(filter=FieldFilter("status", "in", READABLE_REEL_STATUSES))
        .limit(1)
    )
    if not [snapshot async for snapshot in readable.stream()]:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Add at least one Reel video before finding places."
        )

    @async_transactional
    async def claim(transaction: AsyncTransaction) -> None:
        current = (await trip_ref.get(transaction=transaction)).to_dict() or {}
        if current.get("status") != "gathering":
            raise HTTPException(
                status.HTTP_409_CONFLICT, "Places are already being found for this trip."
            )
        transaction.update(
            trip_ref,
            {
                "status": "extracting",
                "pipeline": {
                    "stage": "starting",
                    "done": 0,
                    "total": 0,
                    "dropped": [],
                    "startedAt": SERVER_TIMESTAMP,
                },
            },
        )

    await claim(db().transaction())
    background_tasks.add_task(run_ingest, trip["id"])
    return IngestResponse(status="extracting")
