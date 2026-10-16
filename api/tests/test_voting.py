from fastapi.testclient import TestClient

from .emulator import firestore_client, requires_emulators, sign_up
from .test_trips import TRIP


def voting_trip(client: TestClient) -> tuple[str, dict, dict, str, str]:
    """A two-member trip in voting with two places."""
    host, friend = sign_up("Hana Host"), sign_up("Raka")
    created = client.post("/v1/trips", json=TRIP, headers=host).json()
    client.post(f"/v1/join/{created['inviteCode']}", headers=friend)

    store = firestore_client()
    trip_ref = store.document(f"trips/{created['tripId']}")
    trip_ref.update({"status": "voting"})
    for place_id in ("p1", "p2"):
        trip_ref.collection("places").document(place_id).set(
            {"name": place_id, "tally": {"must": 0, "maybe": 0, "skip": 0}}
        )
    trip = trip_ref.get().to_dict()
    host_uid = trip["hostUid"]
    friend_uid = next(uid for uid in trip["memberUids"] if uid != host_uid)
    return created["tripId"], host, friend, host_uid, friend_uid


@requires_emulators
def test_submitting_votes_updates_tallies_and_locks_votes(client: TestClient):
    trip_id, host, friend, host_uid, friend_uid = voting_trip(client)
    store = firestore_client()
    members = store.collection(f"trips/{trip_id}/members")
    members.document(host_uid).update({"votes": {"p1": "must", "p2": "skip", "gone": "must"}})
    members.document(friend_uid).update({"votes": {"p1": "maybe"}})

    first = client.post(f"/v1/trips/{trip_id}/votes:submit", headers=host)
    assert first.status_code == 200, first.text
    assert first.json() == {"allSubmitted": False}
    assert client.post(f"/v1/trips/{trip_id}/votes:submit", headers=host).status_code == 409

    assert client.post(f"/v1/trips/{trip_id}/votes:submit", headers=friend).json() == {
        "allSubmitted": True
    }

    places = {
        doc.id: doc.to_dict()["tally"]
        for doc in store.collection(f"trips/{trip_id}/places").stream()
    }
    assert places["p1"] == {"must": 1, "maybe": 1, "skip": 0}
    assert places["p2"] == {"must": 0, "maybe": 0, "skip": 1}

    texts = [
        doc.to_dict()["text"]
        for doc in store.collection(f"users/{host_uid}/notifications").stream()
    ]
    assert "Everyone has voted on Jogja long weekend." in texts


@requires_emulators
def test_votes_cannot_be_submitted_outside_voting(client: TestClient):
    host = sign_up("Hana Host")
    trip_id = client.post("/v1/trips", json=TRIP, headers=host).json()["tripId"]
    assert client.post(f"/v1/trips/{trip_id}/votes:submit", headers=host).status_code == 409
