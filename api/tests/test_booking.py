"""Group booking end to end: Travelin API and the real merchant app, both in-process.

The merchant verifies Travelin's signatures with the JWKS the API publishes, so these
tests catch any mismatch in how the two services build and hash AP2 mandates.
"""

import sys
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from travelin.booking import merchant_client
from travelin.booking.mandates import travelin_key
from travelin.booking.signing import public_jwk

from .emulator import firestore_client, requires_emulators
from .test_settlement import planned_trip

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "merchant"))
from merchant import main as merchant_main  # noqa: E402

STAY = {
    "sku": "yog-stay-courtyard",
    "type": "stay",
    "title": "Courtyard Homestay (demo)",
    "priceIdr": 850_000,
    "unit": "night",
    "reason": "Fits all three budgets.",
}


@pytest.fixture
def merchant(monkeypatch):
    async def travelin_jwks():
        return {"keys": [public_jwk(travelin_key())]}

    monkeypatch.setattr(merchant_main, "fetch_travelin_jwks", travelin_jwks)
    monkeypatch.setattr(merchant_client, "TRANSPORT", httpx.ASGITransport(app=merchant_main.app))
    merchant_main._travelin_keys.clear()
    merchant_main.ORDERS.clear()


def bookable_trip(client: TestClient) -> dict:
    trip = planned_trip(client)  # Hana, Raka, Sari; 24-26 Oct, so 2 nights
    firestore_client().document(f"trips/{trip['id']}/plan/current").set({"stay": STAY})
    return trip


@requires_emulators
def test_booking_is_paid_only_after_everyone_approves(client: TestClient, merchant):
    trip = bookable_trip(client)
    tid, h, u = trip["id"], trip["headers"], trip["uids"]

    created = client.post(f"/v1/trips/{tid}/bookings", headers=h["Raka"])
    assert created.status_code == 201, created.text
    booking_id = created.json()["bookingId"]
    url = f"/v1/trips/{tid}/bookings/{booking_id}"
    store = firestore_client()
    booking = store.document(f"trips/{tid}/bookings/{booking_id}").get().to_dict()
    assert booking["status"] == "approving"
    assert booking["amountIdr"] == 1_700_000
    assert list(booking["approvals"]) == [u["Raka"]]
    assert booking["cartMandate"]["merchant_authorization"]

    # The merchant refuses a payment that's missing approvals, on its own.
    guardrail = client.post(f"{url}:test-guardrail", headers=h["Sari"]).json()
    assert guardrail == {"rejected": True, "reason": "Only 1 of 3 travelers approved this booking."}

    assert client.post(f"{url}:approve", headers=h["Raka"]).status_code == 409
    assert client.post(f"{url}:approve", headers=h["Hana"]).json() == {"status": "approving"}
    assert client.post(f"{url}:approve", headers=h["Sari"]).json() == {"status": "paid"}

    booking = store.document(f"trips/{tid}/bookings/{booking_id}").get().to_dict()
    assert booking["receipt"]["amount_idr"] == 1_700_000
    assert booking["paymentMandate"]["user_authorization"]

    expenses = [doc.to_dict() for doc in store.collection(f"trips/{tid}/expenses").stream()]
    assert len(expenses) == 1
    assert expenses[0]["source"] == "booking"
    assert expenses[0]["paidBy"] == u["Raka"]
    assert sorted(expenses[0]["computedShares"].values()) == [566_666, 566_667, 566_667]

    hana_texts = [
        d.to_dict()["text"] for d in store.collection(f"users/{u['Hana']}/notifications").stream()
    ]
    assert "Courtyard Homestay (demo) is booked for Rp1.700.000. It's in Split bill." in hana_texts

    # Booking expenses can't be edited by hand, and there's only one booking per trip.
    expense_id = next(store.collection(f"trips/{tid}/expenses").stream()).id
    assert (
        client.delete(f"/v1/trips/{tid}/expenses/{expense_id}", headers=h["Raka"]).status_code
        == 409
    )
    assert client.post(f"/v1/trips/{tid}/bookings", headers=h["Hana"]).status_code == 409


@requires_emulators
def test_solo_trip_books_immediately(client: TestClient, merchant):
    from .emulator import sign_up
    from .test_trips import TRIP

    solo = sign_up("Solo Sam")
    trip_id = client.post("/v1/trips", json=TRIP, headers=solo).json()["tripId"]
    store = firestore_client()
    store.document(f"trips/{trip_id}").update({"status": "planned"})
    store.document(f"trips/{trip_id}/plan/current").set({"stay": STAY})

    booking_id = client.post(f"/v1/trips/{trip_id}/bookings", headers=solo).json()["bookingId"]
    assert store.document(f"trips/{trip_id}/bookings/{booking_id}").get().get("status") == "paid"


@requires_emulators
def test_booking_needs_a_planned_trip_with_a_stay(client: TestClient, merchant):
    trip = planned_trip(client)
    tid, h = trip["id"], trip["headers"]
    assert client.post(f"/v1/trips/{tid}/bookings", headers=h["Hana"]).status_code == 409
    firestore_client().document(f"trips/{tid}/plan/current").set({"stay": STAY})
    firestore_client().document(f"trips/{tid}").update({"status": "splitting"})
    assert client.post(f"/v1/trips/{tid}/bookings", headers=h["Hana"]).status_code == 409


def test_jwks_publishes_the_group_authorization_key(client: TestClient):
    key = client.get("/.well-known/jwks.json").json()["keys"][0]
    assert key["kty"] == "EC" and key["alg"] == "ES256"
