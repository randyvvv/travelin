"""Group booking with AP2: the merchant signs a cart, every member approves that exact cart,
and only then does Travelin sign the payment mandate the merchant will accept."""

import logging
from typing import Any

from ap2.models.mandate import CartMandate
from fastapi import APIRouter, HTTPException, status
from google.cloud.firestore import (
    SERVER_TIMESTAMP,
    AsyncDocumentReference,
    AsyncTransaction,
    FieldFilter,
    async_transactional,
)

from ..auth import CurrentUser, MemberTrip
from ..booking import merchant_client
from ..booking.mandates import build_intent, build_payment
from ..booking.merchant_client import MerchantError
from ..booking.signing import digest
from ..db import db
from ..money.split import compute_shares
from ..schemas import CamelModel
from .settlement import notify_squad, rupiah
from .trips import display_name

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1", tags=["booking"])

ACTIVE_STATUSES = ["approving", "paying", "paid"]


class BookingCreated(CamelModel):
    booking_id: str


class BookingState(CamelModel):
    status: str


class GuardrailResult(CamelModel):
    rejected: bool
    reason: str


def _booking_ref(trip_id: str, booking_id: str) -> AsyncDocumentReference:
    return db().document(f"trips/{trip_id}/bookings/{booking_id}")


def _approved(booking: dict[str, Any]) -> dict[str, Any]:
    """Approvals of the cart as it stands; an approval of an older cart doesn't count."""
    return {
        uid: approval["at"]
        for uid, approval in booking["approvals"].items()
        if approval.get("cartHash") == booking["cartHash"]
    }


def booking_expense(trip: dict[str, Any], booking: dict[str, Any], booking_id: str) -> dict:
    members = trip["memberUids"]
    amount, shares = compute_shares(mode="equal", amount=booking["amountIdr"], participants=members)
    return {
        "title": booking["title"],
        "amountIdr": amount,
        "paidBy": booking["payerUid"],
        "split": {"mode": "equal", "participants": members, "shares": None, "exact": None},
        "items": [],
        "taxIdr": 0,
        "serviceIdr": 0,
        "discountIdr": 0,
        "computedShares": shares,
        "receiptPath": None,
        "source": "booking",
        "bookingId": booking_id,
        "createdBy": booking["payerUid"],
        "createdAt": SERVER_TIMESTAMP,
        "updatedAt": SERVER_TIMESTAMP,
    }


async def complete_booking(trip: dict[str, Any], booking_ref: AsyncDocumentReference) -> None:
    """Pays the merchant once every member approved, then adds the cost to Split bill."""
    booking = (await booking_ref.get()).to_dict() or {}
    cart = CartMandate.model_validate(booking["cartMandate"])
    payment = build_payment(cart, _approved(booking), booking["guests"], booking["payerUid"])
    link = f"/trips/{trip['id']}/booking/{booking_ref.id}"
    try:
        order = await merchant_client.pay(cart, payment)
    except MerchantError as error:
        await booking_ref.update({"status": "failed", "failureReason": error.reason})
        await notify_squad(
            trip,
            skip=None,
            type="booking_paid",
            text=f"The booking for {booking['title']} didn't go through: {error.reason}",
            link=link,
        )
        return

    batch = db().batch()
    batch.update(
        booking_ref,
        {
            "status": "paid",
            "paymentMandate": payment.model_dump(mode="json"),
            "receipt": order,
            "paidAt": SERVER_TIMESTAMP,
        },
    )
    expense_ref = db().collection(f"trips/{trip['id']}/expenses").document()
    batch.set(expense_ref, booking_expense(trip, booking, booking_ref.id))
    await batch.commit()
    await notify_squad(
        trip,
        skip=None,
        type="booking_paid",
        text=f"{booking['title']} is booked for {rupiah(booking['amountIdr'])}. "
        "It's in Split bill.",
        link=link,
    )


@router.post("/trips/{trip_id}/bookings", status_code=status.HTTP_201_CREATED)
async def propose_booking(trip: MemberTrip, user: CurrentUser) -> BookingCreated:
    if trip["status"] != "planned":
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Bookings are open after planning and before settling up."
        )
    trip_ref = db().document(f"trips/{trip['id']}")
    plan = (await trip_ref.collection("plan").document("current").get()).to_dict() or {}
    stay = plan.get("stay")
    if not stay:
        raise HTTPException(status.HTTP_409_CONFLICT, "The plan doesn't suggest anything to book.")
    active = trip_ref.collection("bookings").where(
        filter=FieldFilter("status", "in", ACTIVE_STATUSES)
    )
    if [snapshot async for snapshot in active.limit(1).stream()]:
        raise HTTPException(status.HTTP_409_CONFLICT, "This trip already has a booking.")

    guests = len(trip["memberUids"])
    try:
        cart = await merchant_client.create_cart(
            build_intent(stay, trip, guests),
            stay["sku"],
            guests,
            trip["startDate"],
            trip["endDate"],
        )
    except MerchantError as error:
        code = status.HTTP_409_CONFLICT if error.status_code else status.HTTP_502_BAD_GATEWAY
        raise HTTPException(code, error.reason) from None

    cart_hash = digest(cart.contents)
    booking_ref = trip_ref.collection("bookings").document()
    everyone_approved = guests == 1  # a solo trip needs no one else's approval
    await booking_ref.set(
        {
            "sku": stay["sku"],
            "type": stay["type"],
            "title": stay["title"],
            "amountIdr": int(cart.contents.payment_request.details.total.amount.value),
            "guests": guests,
            "payerUid": user.uid,
            "intentMandate": build_intent(stay, trip, guests).model_dump(mode="json"),
            "cartMandate": cart.model_dump(mode="json"),
            "cartHash": cart_hash,
            "approvals": {user.uid: {"at": SERVER_TIMESTAMP, "cartHash": cart_hash}},
            "status": "paying" if everyone_approved else "approving",
            "createdBy": user.uid,
            "createdAt": SERVER_TIMESTAMP,
        }
    )
    if everyone_approved:
        await complete_booking(trip, booking_ref)
    else:
        await notify_squad(
            trip,
            skip=user.uid,
            type="booking_proposed",
            text=f"{display_name(user)} wants to book {stay['title']}. Approve it to pay.",
            link=f"/trips/{trip['id']}/booking/{booking_ref.id}",
        )
    return BookingCreated(booking_id=booking_ref.id)


@router.post("/trips/{trip_id}/bookings/{booking_id}:approve")
async def approve_booking(booking_id: str, trip: MemberTrip, user: CurrentUser) -> BookingState:
    trip_ref = db().document(f"trips/{trip['id']}")
    booking_ref = _booking_ref(trip["id"], booking_id)

    @async_transactional
    async def approve(transaction: AsyncTransaction) -> bool:
        snapshot = await booking_ref.get(transaction=transaction)
        if not snapshot.exists:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "That booking no longer exists.")
        booking = snapshot.to_dict() or {}
        current = (await trip_ref.get(transaction=transaction)).to_dict() or {}
        if booking["status"] != "approving":
            raise HTTPException(
                status.HTTP_409_CONFLICT, "This booking isn't waiting for approvals."
            )
        if current.get("status") != "planned":
            raise HTTPException(
                status.HTTP_409_CONFLICT, "Settling up has started, so this booking can't go ahead."
            )
        if user.uid in _approved(booking):
            raise HTTPException(status.HTTP_409_CONFLICT, "You've already approved this booking.")
        approved = {*_approved(booking), user.uid}
        everyone = approved >= set(current["memberUids"])
        transaction.update(
            booking_ref,
            {
                f"approvals.{user.uid}": {"at": SERVER_TIMESTAMP, "cartHash": booking["cartHash"]},
                **({"status": "paying"} if everyone else {}),
            },
        )
        return everyone

    if await approve(db().transaction()):
        await complete_booking(trip, booking_ref)
    return BookingState(status=(await booking_ref.get()).get("status"))


@router.post("/trips/{trip_id}/bookings/{booking_id}:test-guardrail")
async def test_guardrail(booking_id: str, trip: MemberTrip) -> GuardrailResult:
    """Sends the merchant a payment with only the approvals so far, to show it is refused."""
    snapshot = await _booking_ref(trip["id"], booking_id).get()
    if not snapshot.exists:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That booking no longer exists.")
    booking = snapshot.to_dict() or {}
    approved = _approved(booking)
    if booking["status"] != "approving" or len(approved) >= booking["guests"]:
        raise HTTPException(status.HTTP_409_CONFLICT, "There are no missing approvals to test.")

    cart = CartMandate.model_validate(booking["cartMandate"])
    try:
        await merchant_client.pay(
            cart, build_payment(cart, approved, booking["guests"], booking["payerUid"])
        )
    except MerchantError as error:
        return GuardrailResult(rejected=True, reason=error.reason)
    logger.error("Merchant accepted booking %s without every approval", booking_id)
    return GuardrailResult(rejected=False, reason="The merchant accepted the payment.")
