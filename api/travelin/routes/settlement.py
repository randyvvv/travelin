"""Settling up: everyone approves the same split, then each person pays who they owe."""

from typing import Any

from fastapi import APIRouter, HTTPException, status
from google.cloud.firestore import (
    DELETE_FIELD,
    SERVER_TIMESTAMP,
    AsyncDocumentReference,
    AsyncTransaction,
    Increment,
    async_transactional,
)
from pydantic import Field

from ..auth import CurrentUser, MemberTrip, User
from ..db import db, notify
from ..money.settle import net_balances, payment_status, simplify
from ..schemas import CamelModel
from .trips import display_name

router = APIRouter(prefix="/v1", tags=["settlement"])


class SplitVersion(CamelModel):
    version: int


class PlannedTransfer(CamelModel):
    from_uid: str = Field(alias="from")
    to_uid: str = Field(alias="to")
    amount_idr: int


class SplitPreview(CamelModel):
    balances: dict[str, int]
    transfers: list[PlannedTransfer]


class ApprovalResult(CamelModel):
    complete: bool
    transfers: int


def rupiah(amount: int) -> str:
    return f"Rp{amount:,}".replace(",", ".")


def trip_ref_of(trip: dict[str, Any]) -> AsyncDocumentReference:
    return db().document(f"trips/{trip['id']}")


async def _read_money(
    trip_ref: AsyncDocumentReference, transaction: AsyncTransaction | None = None
) -> tuple[list[dict], list[dict]]:
    expenses = [
        snapshot.to_dict() or {}
        async for snapshot in trip_ref.collection("expenses").stream(transaction=transaction)
    ]
    transfers = [
        {"id": snapshot.id, **(snapshot.to_dict() or {})}
        async for snapshot in trip_ref.collection("transfers").stream(transaction=transaction)
    ]
    return expenses, transfers


async def notify_squad(
    trip: dict[str, Any], *, skip: str | None, type: str, text: str, link: str
) -> None:
    for uid in trip["memberUids"]:
        if uid != skip:
            await notify(uid, type=type, text=text, trip_id=trip["id"], link=link)


async def split_changed(trip: dict[str, Any], user: User) -> None:
    """After an expense edit: if the squad was approving, everyone approves again."""
    if trip["status"] != "splitting":
        return
    await trip_ref_of(trip).update({"split.version": Increment(1)})
    await notify_squad(
        trip,
        skip=user.uid,
        type="split_reopened",
        text=f"{display_name(user)} changed an expense in {trip['name']}. Approve the split again.",
        link=f"/trips/{trip['id']}/split",
    )


@router.get("/trips/{trip_id}/split:preview")
async def preview_split(trip: MemberTrip) -> SplitPreview:
    expenses, transfers = await _read_money(trip_ref_of(trip))
    balances = net_balances(expenses, [t for t in transfers if t["status"] == "confirmed"])
    return SplitPreview(
        balances={uid: balances.get(uid, 0) for uid in trip["memberUids"]},
        transfers=[
            PlannedTransfer(from_uid=payer, to_uid=payee, amount_idr=amount)
            for payer, payee, amount in simplify(balances)
        ],
    )


@router.post("/trips/{trip_id}/split:open", status_code=status.HTTP_204_NO_CONTENT)
async def open_split(trip: MemberTrip, user: CurrentUser) -> None:
    trip_ref = trip_ref_of(trip)
    if not [s async for s in trip_ref.collection("expenses").limit(1).stream()]:
        raise HTTPException(status.HTTP_409_CONFLICT, "Add at least one expense first.")

    @async_transactional
    async def start(transaction: AsyncTransaction) -> None:
        current = (await trip_ref.get(transaction=transaction)).to_dict() or {}
        if current.get("status") != "planned":
            raise HTTPException(status.HTTP_409_CONFLICT, "The split is already open.")
        transaction.update(trip_ref, {"status": "splitting", "split.version": Increment(1)})

    await start(db().transaction())
    await notify_squad(
        trip,
        skip=user.uid,
        type="approval_needed",
        text=f"{display_name(user)} is settling up {trip['name']}. Review and approve the split.",
        link=f"/trips/{trip['id']}/split",
    )


@router.post("/trips/{trip_id}/split:approve")
async def approve_split(body: SplitVersion, trip: MemberTrip, user: CurrentUser) -> ApprovalResult:
    trip_ref = trip_ref_of(trip)
    members_ref = trip_ref.collection("members")

    @async_transactional
    async def approve(transaction: AsyncTransaction) -> tuple[list, dict[str, str]] | None:
        current = (await trip_ref.get(transaction=transaction)).to_dict() or {}
        if current.get("status") != "splitting":
            raise HTTPException(status.HTTP_409_CONFLICT, "The split isn't waiting for approval.")
        version = current["split"]["version"]
        if body.version != version:
            raise HTTPException(
                status.HTTP_409_CONFLICT, "The split changed since you looked. Review it again."
            )
        members = {
            snapshot.id: snapshot.to_dict() or {}
            async for snapshot in members_ref.stream(transaction=transaction)
        }
        expenses, transfers = await _read_money(trip_ref, transaction)

        transaction.update(members_ref.document(user.uid), {"splitApprovedVersion": version})
        others_done = all(
            member.get("splitApprovedVersion") == version
            for uid, member in members.items()
            if uid != user.uid
        )
        if not others_done:
            return None

        confirmed = [t for t in transfers if t["status"] == "confirmed"]
        for stale in (t for t in transfers if t["status"] != "confirmed"):
            transaction.delete(trip_ref.collection("transfers").document(stale["id"]))
        plan = simplify(net_balances(expenses, confirmed))
        new_transfers = []
        for payer, payee, amount in plan:
            record = {"from": payer, "to": payee, "amountIdr": amount, "status": "unpaid"}
            new_transfers.append(record)
            transaction.set(
                trip_ref.collection("transfers").document(),
                {**record, "splitVersion": version, "createdAt": SERVER_TIMESTAMP},
            )
        transaction.update(
            trip_ref,
            {
                "status": "settling" if plan else "settled",
                "paymentStatus": payment_status(members, [*confirmed, *new_transfers]),
            },
        )
        names = {uid: member.get("displayName", "a friend") for uid, member in members.items()}
        return plan, names

    outcome = await approve(db().transaction())
    if outcome is None:
        return ApprovalResult(complete=False, transfers=0)
    plan, names = outcome
    for payer, payee, amount in plan:
        await notify(
            payer,
            type="bill",
            text=f"Pay {names[payee]} {rupiah(amount)} for {trip['name']}.",
            trip_id=trip["id"],
            link=f"/trips/{trip['id']}/pay",
        )
    return ApprovalResult(complete=True, transfers=len(plan))


@router.post("/trips/{trip_id}/split:adjust", status_code=status.HTTP_204_NO_CONTENT)
async def adjust_split(trip: MemberTrip, user: CurrentUser) -> None:
    trip_ref = trip_ref_of(trip)

    @async_transactional
    async def reopen(transaction: AsyncTransaction) -> None:
        current = (await trip_ref.get(transaction=transaction)).to_dict() or {}
        if current.get("status") not in {"splitting", "settling"}:
            raise HTTPException(status.HTTP_409_CONFLICT, "There's no split to adjust.")
        _, transfers = await _read_money(trip_ref, transaction)
        # Money that was already confirmed stays; everything else is recalculated.
        for transfer in transfers:
            if transfer["status"] != "confirmed":
                transaction.delete(trip_ref.collection("transfers").document(transfer["id"]))
        transaction.update(
            trip_ref,
            {"status": "splitting", "split.version": Increment(1), "paymentStatus": DELETE_FIELD},
        )

    await reopen(db().transaction())
    await notify_squad(
        trip,
        skip=user.uid,
        type="split_reopened",
        text=f"{display_name(user)} reopened the split for {trip['name']}. Review it again.",
        link=f"/trips/{trip['id']}/split",
    )


async def _advance_transfer(
    trip: dict[str, Any], transfer_id: str, user: User, *, role: str, before: str, after: str
) -> dict[str, Any]:
    """Moves one transfer forward a step. Only the payer sends; only the payee confirms."""
    trip_ref = trip_ref_of(trip)
    transfers_ref = trip_ref.collection("transfers")

    @async_transactional
    async def advance(transaction: AsyncTransaction) -> dict[str, Any]:
        current = (await trip_ref.get(transaction=transaction)).to_dict() or {}
        _, transfers = await _read_money(trip_ref, transaction)
        transfer = next((t for t in transfers if t["id"] == transfer_id), None)
        if transfer is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "That payment no longer exists.")
        if transfer[role] != user.uid:
            who = "the person paying" if role == "from" else "the person being paid"
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Only {who} can do this.")
        if current.get("status") != "settling" or transfer["status"] != before:
            raise HTTPException(status.HTTP_409_CONFLICT, "This payment has already moved on.")

        stamp = "sentAt" if after == "waiting" else "confirmedAt"
        transaction.update(
            transfers_ref.document(transfer_id), {"status": after, stamp: SERVER_TIMESTAMP}
        )
        transfer["status"] = after
        updates: dict[str, Any] = {
            "paymentStatus": payment_status(current["memberUids"], transfers)
        }
        if all(t["status"] == "confirmed" for t in transfers):
            updates["status"] = "settled"
        transaction.update(trip_ref, updates)
        return transfer

    return await advance(db().transaction())


@router.post(
    "/trips/{trip_id}/transfers/{transfer_id}:send", status_code=status.HTTP_204_NO_CONTENT
)
async def send_transfer(transfer_id: str, trip: MemberTrip, user: CurrentUser) -> None:
    transfer = await _advance_transfer(
        trip, transfer_id, user, role="from", before="unpaid", after="waiting"
    )
    amount = rupiah(transfer["amountIdr"])
    await notify(
        transfer["to"],
        type="payment_sent",
        text=f"{display_name(user)} sent you {amount}. Confirm once it arrives.",
        trip_id=trip["id"],
        link=f"/trips/{trip['id']}/pay",
    )


@router.post(
    "/trips/{trip_id}/transfers/{transfer_id}:confirm", status_code=status.HTTP_204_NO_CONTENT
)
async def confirm_transfer(transfer_id: str, trip: MemberTrip, user: CurrentUser) -> None:
    transfer = await _advance_transfer(
        trip, transfer_id, user, role="to", before="waiting", after="confirmed"
    )
    await notify(
        transfer["from"],
        type="payment_confirmed",
        text=f"{display_name(user)} confirmed your {rupiah(transfer['amountIdr'])} payment.",
        trip_id=trip["id"],
        link=f"/trips/{trip['id']}/pay",
    )
