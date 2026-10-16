"""HTTP client for the demo merchant (AP2 objects over JSON)."""

from typing import Any

import httpx
from ap2.models.mandate import CartMandate, IntentMandate, PaymentMandate

from ..config import get_settings

# Tests point this at the merchant app in-process.
TRANSPORT: httpx.AsyncBaseTransport | None = None


class MerchantError(Exception):
    """The merchant refused, or couldn't be reached. `reason` is safe to show."""

    def __init__(self, reason: str, status_code: int | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.status_code = status_code


async def _post(path: str, body: dict[str, Any]) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=15, transport=TRANSPORT) as client:
            response = await client.post(f"{get_settings().merchant_url}{path}", json=body)
    except httpx.HTTPError:
        raise MerchantError("The merchant isn't reachable right now. Try again shortly.") from None
    if response.is_error:
        detail = (
            response.json().get("detail")
            if response.headers.get("content-type", "").startswith("application/json")
            else None
        )
        raise MerchantError(
            detail if isinstance(detail, str) else "The merchant refused the request.",
            response.status_code,
        )
    return response.json()


async def create_cart(
    intent: IntentMandate, sku: str, guests: int, check_in: str, check_out: str
) -> CartMandate:
    data = await _post(
        "/carts",
        {
            "intent_mandate": intent.model_dump(mode="json"),
            "sku": sku,
            "guests": guests,
            "check_in": check_in,
            "check_out": check_out,
        },
    )
    return CartMandate.model_validate(data["cart_mandate"])


async def pay(cart: CartMandate, payment: PaymentMandate) -> dict[str, Any]:
    return await _post(
        "/payments",
        {
            "cart_mandate": cart.model_dump(mode="json"),
            "payment_mandate": payment.model_dump(mode="json"),
        },
    )
