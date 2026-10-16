"""Planning on the emulators, with the Gemini planner and the merchant catalog faked."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from google.cloud import firestore

from travelin.ai import plan_context, planner

from .emulator import firestore_client, requires_emulators, sign_up
from .plan_fixtures import CATALOG, MEMBERS, PLACES, stop, valid_plan
from .test_trips import TRIP
from .test_validator import SUNDAY_MARKET, day

TWO_DAY_TRIP = {**TRIP, "endDate": "2026-10-25"}
TOO_EARLY = valid_plan(
    days=[
        day(
            "2026-10-24",
            stop("P1", "08:00", "10:00", ["M1", "M2"]),
            stop("P2", "12:00", "13:00", ["M1", "M2"]),
            stop("P3", "19:00", "21:00", ["M2"]),
        ),
        SUNDAY_MARKET,
    ]
)


def voting_trip(client: TestClient) -> dict:
    """Hana (host, M1) and Raka (M2) have both voted on the four fixture places."""
    host, friend = sign_up("Hana"), sign_up("Raka")
    created = client.post("/v1/trips", json=TWO_DAY_TRIP, headers=host).json()
    client.post(f"/v1/join/{created['inviteCode']}", headers=friend)

    store = firestore_client()
    trip_ref = store.document(f"trips/{created['tripId']}")
    trip_ref.update(
        {
            "status": "voting",
            "destination": {"name": "Yogyakarta", "lat": -7.7956, "lng": 110.3695},
        }
    )
    for place in PLACES:
        trip_ref.collection("places").document(place["id"]).set(
            {k: v for k, v in place.items() if k != "id"}
            | {"tally": {"must": 0, "maybe": 0, "skip": 0}}
        )
    trip = trip_ref.get().to_dict()
    host_uid = trip["hostUid"]
    friend_uid = next(uid for uid in trip["memberUids"] if uid != host_uid)
    for uid, fixture in ((host_uid, MEMBERS[0]), (friend_uid, MEMBERS[1])):
        trip_ref.collection("members").document(uid).update(
            {
                "prefs": fixture["prefs"],
                "votes": fixture["votes"],
                "votesSubmittedAt": firestore.SERVER_TIMESTAMP,
            }
        )
    return {
        "id": created["tripId"],
        "host": host,
        "friend": friend,
        "hostUid": host_uid,
        "friendUid": friend_uid,
    }


@pytest.fixture
def fake_catalog(monkeypatch):
    async def catalog(destination: str):
        return CATALOG

    monkeypatch.setattr(plan_context, "fetch_catalog", catalog)


@requires_emulators
def test_plan_is_revised_until_it_passes_then_saved(client: TestClient, fake_catalog, monkeypatch):
    calls: list[list[str]] = []

    async def generate(context, previous=None, errors=()):
        calls.append(list(errors))
        return TOO_EARLY if previous is None else valid_plan()

    monkeypatch.setattr(planner, "generate", generate)
    trip = voting_trip(client)

    assert client.post(f"/v1/trips/{trip['id']}/plan", headers=trip["friend"]).status_code == 403
    response = client.post(f"/v1/trips/{trip['id']}/plan", headers=trip["host"])
    assert response.status_code == 202, response.text

    assert calls[0] == []
    assert any("Taman Sari" in error and "not open" in error for error in calls[1])
    assert len(calls) == 2

    store = firestore_client()
    saved_trip = store.document(f"trips/{trip['id']}").get().to_dict()
    assert saved_trip["status"] == "planned"
    assert saved_trip["planning"]["stage"] == "done"

    days = [
        doc.to_dict()
        for doc in store.collection(f"trips/{trip['id']}/itinerary").order_by("date").stream()
    ]
    assert [d["date"] for d in days] == ["2026-10-24", "2026-10-25"]
    assert [s["placeId"] for s in days[0]["stops"]] == ["pl-a", "pl-b", "pl-c"]
    assert days[0]["stops"][2]["attendees"] == [trip["friendUid"]]

    plan = store.document(f"trips/{trip['id']}/plan/current").get().to_dict()
    assert plan["attempts"] == 2
    assert plan["stay"]["title"] == "Courtyard Homestay (demo)"
    assert plan["compromises"][0]["uid"] == trip["hostUid"]
    assert {e["uid"] for e in plan["estimates"]} == {trip["hostUid"], trip["friendUid"]}
    assert plan["warnings"] == [
        "Opening hours for Beringharjo Market are unknown; check before you go."
    ]

    texts = [
        doc.to_dict()["text"]
        for doc in store.collection(f"users/{trip['friendUid']}/notifications").stream()
    ]
    assert "Your itinerary for Jogja long weekend is ready." in texts

    assert client.post(f"/v1/trips/{trip['id']}/plan", headers=trip["host"]).status_code == 409


@requires_emulators
def test_plan_that_never_passes_is_saved_with_heads_ups(
    client: TestClient, fake_catalog, monkeypatch
):
    async def generate(context, previous=None, errors=()):
        return TOO_EARLY

    monkeypatch.setattr(planner, "generate", generate)
    trip = voting_trip(client)
    client.post(f"/v1/trips/{trip['id']}/plan", headers=trip["host"])

    plan = firestore_client().document(f"trips/{trip['id']}/plan/current").get().to_dict()
    assert plan["attempts"] == 3
    assert (
        "Taman Sari is not open 08:00-10:00 on Saturday 2026-10-24 (hours: 09:00-17:00)."
        in plan["warnings"]
    )


@requires_emulators
def test_planner_failure_reopens_voting(client: TestClient, fake_catalog, monkeypatch):
    async def generate(context, previous=None, errors=()):
        raise RuntimeError("model unavailable")

    monkeypatch.setattr(planner, "generate", generate)
    trip = voting_trip(client)
    client.post(f"/v1/trips/{trip['id']}/plan", headers=trip["host"])

    saved = firestore_client().document(f"trips/{trip['id']}").get().to_dict()
    assert saved["status"] == "voting"
    assert saved["planning"]["stage"] == "failed"
    assert "Please try again" in saved["planning"]["error"]


@requires_emulators
def test_host_sets_a_voting_deadline(client: TestClient):
    trip = voting_trip(client)
    url = f"/v1/trips/{trip['id']}/voting"
    soon = (datetime.now(UTC) + timedelta(hours=3)).isoformat()
    past = (datetime.now(UTC) - timedelta(hours=1)).isoformat()

    assert client.patch(url, json={"deadline": soon}, headers=trip["friend"]).status_code == 403
    assert client.patch(url, json={"deadline": past}, headers=trip["host"]).status_code == 422
    assert client.patch(url, json={"deadline": soon}, headers=trip["host"]).status_code == 204

    store = firestore_client()
    assert store.document(f"trips/{trip['id']}").get().get("votingDeadline") is not None
    texts = [
        doc.to_dict()["text"]
        for doc in store.collection(f"users/{trip['friendUid']}/notifications").stream()
    ]
    assert "The host set a voting deadline for Jogja long weekend." in texts

    assert client.patch(url, json={"deadline": None}, headers=trip["host"]).status_code == 204
    assert store.document(f"trips/{trip['id']}").get().get("votingDeadline") is None
