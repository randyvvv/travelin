"""Demo merchant for Travelin group bookings.

It speaks AP2: it signs a CartMandate for each cart, and before charging it checks the
PaymentMandate's group authorization itself, so a payment the whole squad did not approve
is refused here even if the agent that sent it is wrong.
"""

import json
import logging
import secrets
from datetime import UTC, date, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import httpx
import jwt
from ap2.models.mandate import CartContents, CartMandate, IntentMandate, PaymentMandate
from ap2.models.payment_request import (
    PaymentCurrencyAmount,
    PaymentDetailsInit,
    PaymentItem,
    PaymentMethodData,
    PaymentRequest,
)
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field

from .config import get_settings
from .signing import digest, key_id, load_or_create_key, public_jwk

logger = logging.getLogger(__name__)

MOCK_METHOD = "https://travelin.app/pay/mock"


class CatalogItem(BaseModel):
    sku: str
    type: Literal["stay", "tour"]
    destination: str
    title: str
    description: str
    price_idr: int
    unit: Literal["night", "person"]
    capacity: int


class Catalog(BaseModel):
    merchant_id: str
    merchant_name: str
    items: list[CatalogItem]


class CartRequest(BaseModel):
    intent_mandate: IntentMandate
    sku: str
    guests: int = Field(ge=1, le=20)
    check_in: date
    check_out: date


class CartResponse(BaseModel):
    cart_mandate: CartMandate


class PaymentBody(BaseModel):
    cart_mandate: CartMandate
    payment_mandate: PaymentMandate


class Order(BaseModel):
    order_id: str
    cart_id: str
    amount_idr: int
    merchant_name: str
    paid_at: str


class PaymentRejected(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


CATALOG = Catalog.model_validate(
    json.loads((Path(__file__).parent / "catalog.json").read_text(encoding="utf-8"))
)
# Mock processor state. One Cloud Run instance (min-instances 1) is enough for the demo.
ORDERS: dict[str, Order] = {}
_travelin_keys: dict[str, Any] = {}

app = FastAPI(title="Travelin Demo Merchant", version="0.1.0")


@lru_cache
def merchant_key() -> ec.EllipticCurvePrivateKey:
    return load_or_create_key(get_settings().merchant_signing_key, "MERCHANT_SIGNING_KEY")


async def fetch_travelin_jwks() -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=5) as client:
        response = await client.get(get_settings().travelin_jwks_url)
        response.raise_for_status()
        return response.json()


async def travelin_keys(kid: str | None) -> dict[str, Any]:
    """Travelin's public keys by kid; refetched when an unknown kid shows up."""
    if kid and kid not in _travelin_keys:
        try:
            jwks = await fetch_travelin_jwks()
            _travelin_keys.update({k["kid"]: jwt.PyJWK(k).key for k in jwks["keys"]})
        except Exception:
            logger.warning("Could not fetch Travelin's JWKS", exc_info=True)
    return _travelin_keys


def unverified_kid(token: str | None) -> str | None:
    try:
        return jwt.get_unverified_header(token or "").get("kid")
    except jwt.InvalidTokenError:
        return None


def verify_payment(cart: CartMandate, payment: PaymentMandate, keys: dict[str, Any]) -> None:
    """Raises PaymentRejected unless this merchant signed the cart and every traveler approved."""
    try:
        signed = jwt.decode(
            cart.merchant_authorization or "", merchant_key().public_key(), algorithms=["ES256"]
        )
    except jwt.ExpiredSignatureError:
        raise PaymentRejected("The cart has expired. Ask for a new one.") from None
    except jwt.InvalidTokenError:
        raise PaymentRejected("The cart wasn't signed by this merchant.") from None
    if signed.get("cart_hash") != digest(cart.contents):
        raise PaymentRejected("The cart was changed after the merchant signed it.")

    token = payment.user_authorization
    if not token:
        raise PaymentRejected("The payment has no group authorization.")
    key = keys.get(unverified_kid(token) or "")
    if key is None:
        raise PaymentRejected("The group authorization isn't from Travelin.")
    try:
        approved = jwt.decode(token, key, algorithms=["ES256"], audience=CATALOG.merchant_id)
    except jwt.InvalidTokenError:
        raise PaymentRejected("The group authorization isn't valid.") from None
    if approved.get("cart_hash") != digest(cart.contents):
        raise PaymentRejected("The group approved a different cart.")
    if approved.get("mandate_hash") != digest(payment.payment_mandate_contents):
        raise PaymentRejected("The payment was changed after the group approved it.")

    guests = cart.contents.payment_request.method_data[0].data["guests"]
    approvals = len(approved.get("approvals", []))
    if approved.get("member_count") != guests:
        raise PaymentRejected("The group size doesn't match the booking.")
    if approvals < guests:
        raise PaymentRejected(f"Only {approvals} of {guests} travelers approved this booking.")

    contents = payment.payment_mandate_contents
    total = cart.contents.payment_request.details.total.amount
    paying = contents.payment_details_total.amount
    if contents.payment_details_id != cart.contents.id:
        raise PaymentRejected("The payment is for a different cart.")
    if (paying.currency, paying.value) != (total.currency, total.value):
        raise PaymentRejected("The payment total doesn't match the cart.")


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/.well-known/jwks.json")
async def jwks() -> dict[str, list[dict[str, Any]]]:
    return {"keys": [public_jwk(merchant_key())]}


@app.get("/catalog")
async def catalog(destination: str | None = None) -> Catalog:
    if destination is None:
        return CATALOG
    wanted = destination.strip().lower()
    items = [item for item in CATALOG.items if item.destination.lower() == wanted]
    return CATALOG.model_copy(update={"items": items})


@app.post("/carts")
async def create_cart(body: CartRequest) -> CartResponse:
    item = next((i for i in CATALOG.items if i.sku == body.sku), None)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "We don't sell that item.")
    if body.sku not in (body.intent_mandate.skus or []):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "The cart doesn't match the intent."
        )
    if body.guests > item.capacity:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"{item.title} fits up to {item.capacity} guests."
        )

    if item.unit == "night":
        quantity = max(1, (body.check_out - body.check_in).days)
        label = f"{item.title}, {quantity} {'night' if quantity == 1 else 'nights'}"
    else:
        quantity = body.guests
        label = f"{item.title}, {quantity} {'person' if quantity == 1 else 'people'}"
    amount = PaymentCurrencyAmount(currency="IDR", value=float(item.price_idr * quantity))
    cart_id = f"cart_{secrets.token_hex(8)}"
    expires = datetime.now(UTC) + timedelta(minutes=get_settings().cart_ttl_minutes)

    contents = CartContents(
        id=cart_id,
        user_cart_confirmation_required=True,
        payment_request=PaymentRequest(
            method_data=[
                PaymentMethodData(
                    supported_methods=MOCK_METHOD, data={"guests": body.guests, "sku": item.sku}
                )
            ],
            details=PaymentDetailsInit(
                id=cart_id,
                display_items=[PaymentItem(label=label, amount=amount)],
                total=PaymentItem(label="Total", amount=amount),
            ),
        ),
        cart_expiry=expires.isoformat(),
        merchant_name=CATALOG.merchant_name,
    )
    signature = jwt.encode(
        {
            "iss": CATALOG.merchant_id,
            "cart_id": cart_id,
            "cart_hash": digest(contents),
            "iat": int(datetime.now(UTC).timestamp()),
            "exp": int(expires.timestamp()),
        },
        merchant_key(),
        algorithm="ES256",
        headers={"kid": key_id(merchant_key())},
    )
    return CartResponse(
        cart_mandate=CartMandate(contents=contents, merchant_authorization=signature)
    )


@app.post("/payments")
async def pay(body: PaymentBody) -> Order:
    cart = body.cart_mandate
    if cart.contents.id in ORDERS:
        raise HTTPException(status.HTTP_409_CONFLICT, "This cart is already paid.")
    keys = await travelin_keys(unverified_kid(body.payment_mandate.user_authorization))
    try:
        verify_payment(cart, body.payment_mandate, keys)
    except PaymentRejected as rejection:
        logger.info("Payment for %s refused: %s", cart.contents.id, rejection.reason)
        raise HTTPException(status.HTTP_403_FORBIDDEN, rejection.reason) from None

    # Mock payment processor: the charge always succeeds once the mandate checks out.
    order = Order(
        order_id=f"ord_{secrets.token_hex(6)}",
        cart_id=cart.contents.id,
        amount_idr=int(cart.contents.payment_request.details.total.amount.value),
        merchant_name=cart.contents.merchant_name,
        paid_at=datetime.now(UTC).isoformat(),
    )
    ORDERS[cart.contents.id] = order
    return order
