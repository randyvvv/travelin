"""The merchant's own guardrail: it only charges carts that every traveler approved."""

import time
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from ap2.models.mandate import (
    CartMandate,
    IntentMandate,
    PaymentMandate,
    PaymentMandateContents,
)
from ap2.models.payment_request import PaymentResponse
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient

from merchant import main
from merchant.signing import digest, key_id, public_jwk

TRAVELIN_KEY = ec.generate_private_key(ec.SECP256R1())
client = TestClient(main.app)


@pytest.fixture(autouse=True)
def travelin_jwks(monkeypatch):
    async def fetch():
        return {"keys": [public_jwk(TRAVELIN_KEY)]}

    monkeypatch.setattr(main, "fetch_travelin_jwks", fetch)
    main._travelin_keys.clear()
    main.ORDERS.clear()


def intent(sku: str = "yog-stay-courtyard") -> dict:
    expiry = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    return IntentMandate(
        natural_language_description="Homestay in Yogyakarta for 3, 24-26 Oct",
        merchants=["travelin-demo-merchant"],
        skus=[sku],
        intent_expiry=expiry,
    ).model_dump(mode="json")


def new_cart(guests: int = 3, sku: str = "yog-stay-courtyard") -> CartMandate:
    response = client.post(
        "/carts",
        json={
            "intent_mandate": intent(sku),
            "sku": sku,
            "guests": guests,
            "check_in": "2026-10-24",
            "check_out": "2026-10-26",
        },
    )
    assert response.status_code == 200, response.text
    return CartMandate.model_validate(response.json()["cart_mandate"])


def payment_for(
    cart: CartMandate, approvals: int, member_count: int, key=TRAVELIN_KEY
) -> PaymentMandate:
    contents = PaymentMandateContents(
        payment_mandate_id="pm_1",
        payment_details_id=cart.contents.id,
        payment_details_total=cart.contents.payment_request.details.total.model_copy(deep=True),
        payment_response=PaymentResponse(request_id=cart.contents.id, method_name=main.MOCK_METHOD),
        merchant_agent="travelin-demo-merchant",
    )
    token = jwt.encode(
        {
            "aud": "travelin-demo-merchant",
            "cart_hash": digest(cart.contents),
            "mandate_hash": digest(contents),
            "member_count": member_count,
            "approvals": [{"member": f"m{i}"} for i in range(approvals)],
            "exp": int(time.time()) + 600,
        },
        key,
        algorithm="ES256",
        headers={"kid": key_id(key)},
    )
    return PaymentMandate(payment_mandate_contents=contents, user_authorization=token)


def pay(cart: CartMandate, payment: PaymentMandate):
    return client.post(
        "/payments",
        json={
            "cart_mandate": cart.model_dump(mode="json"),
            "payment_mandate": payment.model_dump(mode="json"),
        },
    )


def test_cart_is_priced_and_signed():
    cart = new_cart()
    assert cart.contents.payment_request.details.total.amount.value == 1_700_000  # 2 nights
    claims = jwt.decode(
        cart.merchant_authorization, main.merchant_key().public_key(), algorithms=["ES256"]
    )
    assert claims["cart_hash"] == digest(cart.contents)


def test_jwks_publishes_the_signing_key():
    key = client.get("/.well-known/jwks.json").json()["keys"][0]
    assert key["kid"] == key_id(main.merchant_key())


def test_payment_with_every_approval_goes_through_once():
    cart = new_cart()
    first = pay(cart, payment_for(cart, approvals=3, member_count=3))
    assert first.status_code == 200, first.text
    assert first.json()["amount_idr"] == 1_700_000
    assert pay(cart, payment_for(cart, approvals=3, member_count=3)).status_code == 409


def test_missing_approval_is_refused():
    cart = new_cart()
    response = pay(cart, payment_for(cart, approvals=2, member_count=3))
    assert response.status_code == 403
    assert response.json()["detail"] == "Only 2 of 3 travelers approved this booking."


def test_tampered_cart_is_refused():
    cart = new_cart()
    payment = payment_for(cart, approvals=3, member_count=3)
    cheaper = cart.model_copy(deep=True)
    cheaper.contents.payment_request.details.total.amount.value = 1.0
    assert pay(cheaper, payment).json()["detail"] == (
        "The cart was changed after the merchant signed it."
    )


def test_tampered_payment_is_refused():
    cart = new_cart()
    payment = payment_for(cart, approvals=3, member_count=3)
    payment.payment_mandate_contents.payment_details_total.amount.value = 1.0
    assert pay(cart, payment).json()["detail"] == (
        "The payment was changed after the group approved it."
    )


def test_authorization_from_another_signer_is_refused():
    cart = new_cart()
    stranger = ec.generate_private_key(ec.SECP256R1())
    response = pay(cart, payment_for(cart, approvals=3, member_count=3, key=stranger))
    assert response.json()["detail"] == "The group authorization isn't from Travelin."


def test_group_size_must_match_cart():
    cart = new_cart(guests=3)
    response = pay(cart, payment_for(cart, approvals=2, member_count=2))
    assert response.json()["detail"] == "The group size doesn't match the booking."


def test_cart_checks():
    assert client.post("/carts", json={"intent_mandate": intent(), "sku": "nope", "guests": 2,
                                       "check_in": "2026-10-24", "check_out": "2026-10-25"}).status_code == 404  # fmt: skip
    mismatch = client.post("/carts", json={"intent_mandate": intent("yog-tour-merapi-jeep"), "sku": "yog-stay-courtyard",
                                           "guests": 2, "check_in": "2026-10-24", "check_out": "2026-10-25"})  # fmt: skip
    assert mismatch.status_code == 422
    too_many = client.post("/carts", json={"intent_mandate": intent(), "sku": "yog-stay-courtyard", "guests": 7,
                                           "check_in": "2026-10-24", "check_out": "2026-10-25"})  # fmt: skip
    assert too_many.status_code == 409
