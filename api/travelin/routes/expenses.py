import logging
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, status
from google.cloud.firestore import SERVER_TIMESTAMP
from pydantic import Field

from ..ai import receipt
from ..auth import CurrentUser, MemberTrip
from ..db import db
from ..money.split import Item, SplitError, compute_shares
from ..schemas import CamelModel
from .settlement import split_changed

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1", tags=["expenses"])

EDITABLE_STATUSES = {"planned", "splitting"}


class ItemIn(CamelModel):
    name: str = Field(min_length=1, max_length=80)
    unit_price_idr: int = Field(ge=0)
    qty: int = Field(ge=1, le=99)
    portions: dict[str, int] = {}


class SplitIn(CamelModel):
    mode: Literal["equal", "shares", "exact", "items"]
    participants: list[str] = []
    shares: dict[str, int] | None = None
    exact: dict[str, int] | None = None


class ExpenseIn(CamelModel):
    title: str = Field(min_length=1, max_length=80)
    amount_idr: int = Field(default=0, ge=0)
    paid_by: str
    split: SplitIn
    items: list[ItemIn] = []
    tax_idr: int = Field(default=0, ge=0)
    service_idr: int = Field(default=0, ge=0)
    discount_idr: int = Field(default=0, ge=0)
    receipt_path: str | None = None


class ExpenseSaved(CamelModel):
    expense_id: str
    amount_idr: int


class ScanRequest(CamelModel):
    storage_path: str


class ScannedItem(CamelModel):
    name: str
    unit_price_idr: int
    qty: int


class ScanResult(CamelModel):
    merchant: str
    items: list[ScannedItem]
    subtotal_idr: int
    tax_idr: int
    service_idr: int
    discount_idr: int
    total_idr: int
    warnings: list[str]


def require_editable(trip: dict[str, Any]) -> None:
    if trip["status"] not in EDITABLE_STATUSES:
        message = (
            "Expenses open once the itinerary is ready."
            if trip["status"] not in {"settling", "settled"}
            else "Payments have started. Tap Adjust split before changing expenses."
        )
        raise HTTPException(status.HTTP_409_CONFLICT, message)


def expense_document(body: ExpenseIn, trip: dict[str, Any]) -> dict[str, Any]:
    involved = {body.paid_by, *body.split.participants}
    involved |= {uid for item in body.items for uid in item.portions}
    if involved - set(trip["memberUids"]):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Everyone on an expense must be in the squad."
        )
    if body.receipt_path and not body.receipt_path.startswith(f"trips/{trip['id']}/receipts/"):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "That receipt isn't from this trip."
        )

    participants = list(dict.fromkeys(body.split.participants))
    try:
        amount, shares = compute_shares(
            mode=body.split.mode,
            amount=body.amount_idr,
            participants=participants,
            shares=body.split.shares,
            exact=body.split.exact,
            items=[Item(i.name, i.unit_price_idr, i.qty, i.portions) for i in body.items],
            tax=body.tax_idr,
            service=body.service_idr,
            discount=body.discount_idr,
        )
    except SplitError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from None

    return {
        "title": body.title,
        "amountIdr": amount,
        "paidBy": body.paid_by,
        "split": {
            "mode": body.split.mode,
            "participants": sorted(shares) if body.split.mode == "items" else participants,
            "shares": body.split.shares,
            "exact": body.split.exact,
        },
        "items": [
            {
                "name": item.name,
                "unitPriceIdr": item.unit_price_idr,
                "qty": item.qty,
                "portions": {uid: n for uid, n in item.portions.items() if n > 0},
            }
            for item in body.items
        ],
        "taxIdr": body.tax_idr,
        "serviceIdr": body.service_idr,
        "discountIdr": body.discount_idr,
        "computedShares": shares,
        "receiptPath": body.receipt_path,
        "source": "receipt" if body.split.mode == "items" else "manual",
        "updatedAt": SERVER_TIMESTAMP,
    }


@router.post("/trips/{trip_id}/expenses", status_code=status.HTTP_201_CREATED)
async def create_expense(body: ExpenseIn, trip: MemberTrip, user: CurrentUser) -> ExpenseSaved:
    require_editable(trip)
    document = expense_document(body, trip)
    expense_ref = db().collection(f"trips/{trip['id']}/expenses").document()
    await expense_ref.set({**document, "createdBy": user.uid, "createdAt": SERVER_TIMESTAMP})
    await split_changed(trip, user)
    return ExpenseSaved(expense_id=expense_ref.id, amount_idr=document["amountIdr"])


@router.patch("/trips/{trip_id}/expenses/{expense_id}")
async def update_expense(
    expense_id: str, body: ExpenseIn, trip: MemberTrip, user: CurrentUser
) -> ExpenseSaved:
    require_editable(trip)
    expense_ref = db().document(f"trips/{trip['id']}/expenses/{expense_id}")
    existing = await expense_ref.get()
    if not existing.exists:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That expense no longer exists.")
    if existing.get("source") == "booking":
        raise HTTPException(status.HTTP_409_CONFLICT, "Group bookings can't be edited.")
    document = expense_document(body, trip)
    await expense_ref.update(document)
    await split_changed(trip, user)
    return ExpenseSaved(expense_id=expense_id, amount_idr=document["amountIdr"])


@router.delete("/trips/{trip_id}/expenses/{expense_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_expense(expense_id: str, trip: MemberTrip, user: CurrentUser) -> None:
    require_editable(trip)
    expense_ref = db().document(f"trips/{trip['id']}/expenses/{expense_id}")
    existing = await expense_ref.get()
    if not existing.exists:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That expense no longer exists.")
    if existing.get("source") == "booking":
        raise HTTPException(status.HTTP_409_CONFLICT, "Group bookings can't be deleted.")
    await expense_ref.delete()
    await split_changed(trip, user)


@router.post("/trips/{trip_id}/receipts:scan")
async def scan_receipt(body: ScanRequest, trip: MemberTrip, user: CurrentUser) -> ScanResult:
    prefix = f"trips/{trip['id']}/receipts/{user.uid}/"
    if not body.storage_path.startswith(prefix) or ".." in body.storage_path:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Upload the receipt photo first."
        )
    try:
        result = await receipt.scan(body.storage_path)
    except Exception:
        logger.exception("Receipt scan failed for %s", body.storage_path)
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "Couldn't read that receipt. Try a sharper photo, or enter the expense by hand.",
        ) from None
    return ScanResult(
        merchant=result.merchant,
        items=[
            ScannedItem(name=item.name, unit_price_idr=item.unit_price, qty=max(item.qty, 1))
            for item in result.items
        ],
        subtotal_idr=result.subtotal,
        tax_idr=result.tax,
        service_idr=result.service,
        discount_idr=result.discount,
        total_idr=result.total,
        warnings=receipt.check(result),
    )
