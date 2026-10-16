"""AP2 mandates Travelin creates on behalf of the squad."""

import hashlib
import secrets
import time
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Any

import jwt
from ap2.models.mandate import (
    CartMandate,
    IntentMandate,
    PaymentMandate,
    PaymentMandateContents,
)
from ap2.models.payment_request import PaymentResponse
from cryptography.hazmat.primitives.asymmetric import ec

from ..config import get_settings
from .signing import digest, key_id, load_or_create_key

AUTHORIZATION_TTL_SECONDS = 600


@lru_cache
def travelin_key() -> ec.EllipticCurvePrivateKey:
    return load_or_create_key(get_settings().travelin_signing_key, "TRAVELIN_SIGNING_KEY")


def anonymize(uid: str) -> str:
    """The merchant needs to count approvals, not to know who the travelers are."""
    return hashlib.sha256(uid.encode()).hexdigest()[:16]


def build_intent(stay: dict[str, Any], trip: dict[str, Any], guests: int) -> IntentMandate:
    return IntentMandate(
        user_cart_confirmation_required=True,
        natural_language_description=(
            f"{stay['title']} for {guests} people in {trip['destination']['name']}, "
            f"{trip['startDate']} to {trip['endDate']}"
        ),
        merchants=[get_settings().merchant_id],
        skus=[stay["sku"]],
        requires_refundability=False,
        intent_expiry=(datetime.now(UTC) + timedelta(days=1)).isoformat(),
    )


def build_payment(
    cart: CartMandate, approvals: dict[str, datetime], member_count: int, payer_uid: str
) -> PaymentMandate:
    """A PaymentMandate whose user_authorization is the squad's signed group approval.

    `approvals` maps member UID to when they approved. Callers pass every member's
    approval; the merchant re-checks the count and refuses anything less.
    """
    request = cart.contents.payment_request
    contents = PaymentMandateContents(
        payment_mandate_id=f"pm_{secrets.token_hex(8)}",
        payment_details_id=cart.contents.id,
        payment_details_total=request.details.total.model_copy(deep=True),
        payment_response=PaymentResponse(
            request_id=cart.contents.id,
            method_name=request.method_data[0].supported_methods,
            details={"payer": anonymize(payer_uid), "token": "mock-wallet-token"},
        ),
        merchant_agent=get_settings().merchant_id,
    )
    now = int(time.time())
    authorization = jwt.encode(
        {
            "iss": "travelin-api",
            "aud": get_settings().merchant_id,
            "cart_hash": digest(cart.contents),
            "mandate_hash": digest(contents),
            "member_count": member_count,
            "approvals": [
                {"member": anonymize(uid), "at": at.isoformat()}
                for uid, at in sorted(approvals.items())
            ],
            "iat": now,
            "exp": now + AUTHORIZATION_TTL_SECONDS,
        },
        travelin_key(),
        algorithm="ES256",
        headers={"kid": key_id(travelin_key())},
    )
    return PaymentMandate(payment_mandate_contents=contents, user_authorization=authorization)
