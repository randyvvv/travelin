"""Ingest workflow end to end on the emulators, with Gemini and Places replaced by fakes."""

import pytest
from fastapi.testclient import TestClient

from travelin.ai import extractor, ingest, summarizer, verifier
from travelin.ai.ingest import merge_verified
from travelin.ai.schemas import Candidate, DroppedPlace, PlaceSummary, VerifiedPlace
from travelin.config import get_settings
from travelin.routes import trips

from .emulator import firestore_client, requires_emulators, sign_up
from .test_trips import TRIP

EXTRACTED = {
    "reel-a": [
        Candidate(name="Taman Sari", category="attraction", appears_at_sec=3, confidence=0.9),
        Candidate(name="Warung Imaginary", category="food", appears_at_sec=9, confidence=0.7),
    ],
    "reel-b": [
        Candidate(name="Taman Sari Water Castle", category="attraction", confidence=0.95),
        Candidate(name="Gudeg Yu Djum", category="food", appears_at_sec=12, confidence=0.9),
    ],
}
KNOWN_PLACES = {
    "Taman Sari": "place-taman-sari",
    "Taman Sari Water Castle": "place-taman-sari",
    "Gudeg Yu Djum": "place-gudeg",
}


async def fake_extract(reel: dict, destination: str) -> list[Candidate]:
    if reel["id"] == "reel-broken":
        raise RuntimeError("video could not be decoded")
    return EXTRACTED[reel["id"]]


async def fake_verify(candidate: Candidate, destination: dict) -> VerifiedPlace | DroppedPlace:
    place_id = KNOWN_PLACES.get(candidate.name)
    if place_id is None:
        return DroppedPlace(name=candidate.name, reason="not found on Google Maps")
    return VerifiedPlace(place_id=place_id, name=candidate.name, lat=-7.81, lng=110.36)


async def fake_summarize(place: VerifiedPlace, destination: str):
    sources = [{"title": place.name, "uri": f"https://maps.google.com/?cid={place.place_id}"}]
    return PlaceSummary(highlights=[f"{place.name} is lovely"], best_time="Morning"), sources


async def fake_geocode(query: str):
    return (-7.7956, 110.3695)


async def no_geocode(query: str):
    return None


async def no_cache_key(reel: dict):
    return None


@pytest.fixture
def fakes(monkeypatch):
    monkeypatch.setattr(extractor, "extract", fake_extract)
    monkeypatch.setattr(verifier, "verify", fake_verify)
    monkeypatch.setattr(summarizer, "summarize", fake_summarize)
    monkeypatch.setattr(ingest, "geocode", fake_geocode)
    monkeypatch.setattr(trips, "geocode", no_geocode)
    monkeypatch.setattr(ingest, "cache_key", no_cache_key)
    monkeypatch.setattr(get_settings(), "places_api_key", "test-key")


def add_reel(trip_id: str, reel_id: str, uploader_uid: str, status: str = "queued") -> None:
    firestore_client().document(f"trips/{trip_id}/reels/{reel_id}").set(
        {
            "uploaderUid": uploader_uid,
            "source": "upload",
            "storagePath": f"trips/{trip_id}/reels/{uploader_uid}/{reel_id}.mp4",
            "platform": "other",
            "status": status,
        }
    )


def test_merge_verified_groups_by_place_and_dedupes_drops():
    def verified(place_id: str, reel: str, uid: str) -> dict:
        place = {"place_id": place_id, "name": place_id, "lat": 0, "lng": 0}
        return {
            "place": place,
            "category": "food",
            "reelId": reel,
            "uploaderUid": uid,
            "atSec": 1,
            "evidence": "speech",
            "quote": "",
        }

    places, dropped = merge_verified(
        [
            verified("p1", "r1", "hana"),
            verified("p1", "r2", "raka"),
            verified("p1", "r3", "hana"),
            {"dropped": {"name": "Fake", "reason": "x"}},
            {"dropped": {"name": "fake", "reason": "x"}},
        ]
    )
    assert len(places) == 1
    assert [m["reelId"] for m in places[0]["mentions"]] == ["r1", "r2", "r3"]
    assert places[0]["savedBy"] == ["hana", "raka"]
    assert len(dropped) == 1


@requires_emulators
def test_ingest_turns_reels_into_verified_places(client: TestClient, fakes):
    host, friend = sign_up("Hana Host"), sign_up("Raka")
    created = client.post("/v1/trips", json=TRIP, headers=host).json()
    trip_id = created["tripId"]
    client.post(f"/v1/join/{created['inviteCode']}", headers=friend)

    store = firestore_client()
    trip = store.document(f"trips/{trip_id}").get().to_dict()
    host_uid = trip["hostUid"]
    friend_uid = next(uid for uid in trip["memberUids"] if uid != host_uid)
    add_reel(trip_id, "reel-a", host_uid)
    add_reel(trip_id, "reel-b", friend_uid)
    add_reel(trip_id, "reel-broken", friend_uid)

    assert client.post(f"/v1/trips/{trip_id}/ingest", headers=friend).status_code == 403
    response = client.post(f"/v1/trips/{trip_id}/ingest", headers=host)
    assert response.status_code == 202, response.text
    # TestClient waits for background tasks, so the workflow has finished here.

    trip = store.document(f"trips/{trip_id}").get().to_dict()
    assert trip["status"] == "voting"
    assert trip["pipeline"]["stage"] == "done"
    assert trip["pipeline"]["dropped"] == [
        {"name": "Warung Imaginary", "reason": "not found on Google Maps"}
    ]
    assert trip["destination"]["lat"] == pytest.approx(-7.7956)

    places = {doc.id: doc.to_dict() for doc in store.collection(f"trips/{trip_id}/places").stream()}
    assert set(places) == {"place-taman-sari", "place-gudeg"}
    taman_sari = places["place-taman-sari"]
    assert sorted(taman_sari["savedBy"]) == sorted([host_uid, friend_uid])
    assert len(taman_sari["mentions"]) == 2
    assert taman_sari["summary"]["highlights"] == ["Taman Sari is lovely"]
    assert taman_sari["mapsSources"][0]["uri"].startswith("https://maps.google.com/")

    reels = {doc.id: doc.to_dict() for doc in store.collection(f"trips/{trip_id}/reels").stream()}
    assert reels["reel-a"]["status"] == "done" and reels["reel-a"]["placesFound"] == 1
    assert reels["reel-b"]["placesFound"] == 2
    assert reels["reel-broken"]["status"] == "failed"

    texts = [
        doc.to_dict()["text"]
        for doc in store.collection(f"users/{friend_uid}/notifications").stream()
    ]
    assert "2 places found in your Reels. Time to vote!" in texts

    # Starting again is refused once the trip has moved on.
    assert client.post(f"/v1/trips/{trip_id}/ingest", headers=host).status_code == 409


@requires_emulators
def test_ingest_with_no_verified_places_returns_to_gathering(
    client: TestClient, fakes, monkeypatch
):
    async def nothing_real(candidate, destination):
        return DroppedPlace(name=candidate.name, reason="not found on Google Maps")

    monkeypatch.setattr(verifier, "verify", nothing_real)
    host = sign_up("Hana Host")
    trip_id = client.post("/v1/trips", json=TRIP, headers=host).json()["tripId"]
    store = firestore_client()
    add_reel(trip_id, "reel-a", store.document(f"trips/{trip_id}").get().get("hostUid"))

    assert client.post(f"/v1/trips/{trip_id}/ingest", headers=host).status_code == 202
    trip = store.document(f"trips/{trip_id}").get().to_dict()
    assert trip["status"] == "gathering"
    assert trip["pipeline"]["stage"] == "failed"
    assert "No real places" in trip["pipeline"]["error"]
    assert len(trip["pipeline"]["dropped"]) == 2


@requires_emulators
def test_ingest_needs_a_reel(client: TestClient, fakes):
    host = sign_up("Hana Host")
    trip_id = client.post("/v1/trips", json=TRIP, headers=host).json()["tripId"]
    assert client.post(f"/v1/trips/{trip_id}/ingest", headers=host).status_code == 409
