from datetime import date

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from travelin.routes.trips import INVITE_ALPHABET, CreateTripRequest, new_invite_code

from .emulator import firestore_client, requires_emulators, sign_up

TRIP = {
    "name": "Jogja long weekend",
    "destination": "Yogyakarta",
    "origin": "Jakarta",
    "startDate": "2026-10-24",
    "endDate": "2026-10-26",
}


def test_create_trip_request_rejects_end_before_start():
    with pytest.raises(ValidationError):
        CreateTripRequest.model_validate({**TRIP, "endDate": "2026-10-23"})


def test_create_trip_request_rejects_long_trips():
    with pytest.raises(ValidationError):
        CreateTripRequest.model_validate({**TRIP, "endDate": "2026-11-24"})


def test_create_trip_request_strips_whitespace():
    request = CreateTripRequest.model_validate({**TRIP, "name": "  Jogja  "})
    assert request.name == "Jogja"
    assert request.start_date == date(2026, 10, 24)


def test_invite_codes_use_unambiguous_characters():
    code = new_invite_code()
    assert len(code) == 8
    assert set(code) <= set(INVITE_ALPHABET)


@requires_emulators
def test_create_preview_and_join_trip(client: TestClient):
    host = sign_up("Hana Host")
    friend = sign_up("Raka")

    created = client.post("/v1/trips", json=TRIP, headers=host)
    assert created.status_code == 201, created.text
    trip_id = created.json()["tripId"]
    code = created.json()["inviteCode"]

    preview = client.get(f"/v1/join/{code.lower()}", headers=friend).json()
    assert preview["tripId"] == trip_id
    assert preview["hostName"] == "Hana Host"
    assert preview["memberCount"] == 1
    assert preview["alreadyMember"] is False
    assert preview["joinable"] is True

    assert client.post(f"/v1/join/{code}", headers=friend).json() == {"tripId": trip_id}
    # Joining twice is a no-op.
    assert client.post(f"/v1/join/{code}", headers=friend).status_code == 200

    assert client.get("/v1/join/NOPE2345", headers=friend).status_code == 404

    store = firestore_client()
    trip = store.document(f"trips/{trip_id}").get().to_dict()
    assert trip["status"] == "gathering"
    assert len(trip["memberUids"]) == 2
    members = [doc.to_dict() for doc in store.collection(f"trips/{trip_id}/members").stream()]
    assert sorted(member["role"] for member in members) == ["host", "member"]

    notifications = list(store.collection(f"users/{trip['hostUid']}/notifications").stream())
    assert [n.to_dict()["text"] for n in notifications] == ["Raka joined Jogja long weekend"]


@requires_emulators
def test_join_is_refused_once_trip_is_past_voting(client: TestClient):
    created = client.post("/v1/trips", json=TRIP, headers=sign_up("Hana Host")).json()
    firestore_client().document(f"trips/{created['tripId']}").update({"status": "planned"})

    response = client.post(f"/v1/join/{created['inviteCode']}", headers=sign_up("Late Larry"))
    assert response.status_code == 409


def test_requests_without_token_are_rejected(client: TestClient):
    assert client.post("/v1/trips", json=TRIP).status_code == 401
