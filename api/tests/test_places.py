"""Places without Reels: search and add, AI suggestions, and voting with no Reels at all."""

import pytest
from fastapi.testclient import TestClient

from travelin.ai import ingest, suggest, suggester, summarizer, verifier
from travelin.ai.schemas import DroppedPlace, PlaceSummary
from travelin.ai.suggester import Suggestion, category_from_types, describe, parse_suggestions
from travelin.config import get_settings
from travelin.routes import places as places_routes
from travelin.routes import trips

from .emulator import firestore_client, requires_emulators, sign_up
from .test_trips import TRIP


def maps_result(place_id: str, name: str, types: list[str]) -> dict:
    return {
        "id": place_id,
        "displayName": {"text": name},
        "formattedAddress": f"{name}, Yogyakarta",
        "location": {"latitude": -7.8, "longitude": 110.37},
        "types": types,
        "rating": 4.6,
        "userRatingCount": 1200,
    }


TAMAN_SARI = maps_result("place-taman-sari", "Taman Sari", ["tourist_attraction"])
KOPI = maps_result("place-kopi", "Kopi Klotok", ["cafe", "restaurant"])
KNOWN = {"Taman Sari": TAMAN_SARI, "Kopi Klotok": KOPI}


@pytest.fixture
def fakes(monkeypatch):
    async def search_text(query, *, field_mask, bias=None, page_size=3):
        return [TAMAN_SARI, KOPI]

    async def get_place(place_id):
        return next((r for r in KNOWN.values() if r["id"] == place_id), None)

    async def summarize(place, destination):
        return PlaceSummary(highlights=[f"{place.name} is lovely"]), [
            {"title": place.name, "uri": "https://maps.google.com/x"}
        ]

    async def verify(candidate, destination):
        result = KNOWN.get(candidate.name)
        if result is None:
            return DroppedPlace(name=candidate.name, reason="not found on Google Maps")
        return verifier.to_verified(result)

    async def suggest_places(trip, members, existing, count=8):
        return [
            Suggestion(name="Taman Sari", category="attraction", reason="Already saved"),
            Suggestion(
                name="Kopi Klotok", category="other", reason="A slow breakfast by the rice fields."
            ),
            Suggestion(name="Imaginary Cafe", category="cafe", reason="Doesn't exist"),
        ]

    async def no_geocode(query):
        return None

    monkeypatch.setattr(places_routes, "search_text", search_text)
    monkeypatch.setattr(places_routes, "get_place", get_place)
    monkeypatch.setattr(summarizer, "summarize", summarize)
    monkeypatch.setattr(verifier, "verify", verify)
    monkeypatch.setattr(suggester, "suggest", suggest_places)
    monkeypatch.setattr(trips, "geocode", no_geocode)
    monkeypatch.setattr(suggest, "geocode", no_geocode)
    monkeypatch.setattr(ingest, "geocode", no_geocode)
    monkeypatch.setattr(get_settings(), "places_api_key", "test-key")


def test_category_from_place_types():
    assert category_from_types(["cafe", "restaurant", "food"]) == "cafe"
    assert category_from_types(["tourist_attraction", "museum"]) == "attraction"
    assert category_from_types(["point_of_interest"]) == "other"


def test_parse_suggestions_and_describe_preferences():
    text = 'Sure!\n```json\n{"places": [{"name": "Kopi Klotok", "category": "cafe", "reason": "Breakfast"}]}\n```'
    assert parse_suggestions(text)[0].name == "Kopi Klotok"
    assert parse_suggestions("no json here") is None
    assert describe(["Nature", "Local food", "Nature"], "none") == "Nature (2), Local food (1)"
    assert describe([], "none") == "none"


def new_trip(client: TestClient) -> tuple[str, dict, dict, str, str]:
    host, friend = sign_up("Hana"), sign_up("Raka")
    created = client.post("/v1/trips", json=TRIP, headers=host).json()
    client.post(f"/v1/join/{created['inviteCode']}", headers=friend)
    trip = firestore_client().document(f"trips/{created['tripId']}").get().to_dict()
    friend_uid = next(uid for uid in trip["memberUids"] if uid != trip["hostUid"])
    return created["tripId"], host, friend, trip["hostUid"], friend_uid


@requires_emulators
def test_search_and_add_places(client: TestClient, fakes):
    trip_id, host, friend, host_uid, friend_uid = new_trip(client)

    hits = client.get(
        f"/v1/trips/{trip_id}/places:search", params={"q": "taman"}, headers=host
    ).json()
    assert [(h["name"], h["category"], h["onBoard"]) for h in hits] == [
        ("Taman Sari", "attraction", False),
        ("Kopi Klotok", "cafe", False),
    ]

    added = client.post(
        f"/v1/trips/{trip_id}/places", json={"placeId": "place-taman-sari"}, headers=host
    )
    assert added.status_code == 201, added.text
    assert added.json() == {"placeId": "place-taman-sari", "alreadyAdded": False}
    again = client.post(
        f"/v1/trips/{trip_id}/places", json={"placeId": "place-taman-sari"}, headers=friend
    ).json()
    assert again["alreadyAdded"] is True

    place = firestore_client().document(f"trips/{trip_id}/places/place-taman-sari").get().to_dict()
    assert place["addedBy"] == host_uid
    assert sorted(place["savedBy"]) == sorted([host_uid, friend_uid])
    assert place["summaryPending"] is False  # the background summary has run
    assert place["summary"]["highlights"] == ["Taman Sari is lovely"]

    hits = client.get(
        f"/v1/trips/{trip_id}/places:search", params={"q": "taman"}, headers=host
    ).json()
    assert hits[0]["onBoard"] is True
    missing = client.post(f"/v1/trips/{trip_id}/places", json={"placeId": "nope"}, headers=host)
    assert missing.status_code == 404


@requires_emulators
def test_ai_suggestions_skip_known_and_unverified_places(client: TestClient, fakes):
    trip_id, host, _, _, _ = new_trip(client)
    client.post(f"/v1/trips/{trip_id}/places", json={"placeId": "place-taman-sari"}, headers=host)

    assert client.post(f"/v1/trips/{trip_id}/places:suggest", headers=host).status_code == 202
    store = firestore_client()
    trip = store.document(f"trips/{trip_id}").get().to_dict()
    assert trip["suggesting"]["stage"] == "done"
    assert trip["suggesting"]["added"] == 1
    assert trip["status"] == "gathering"

    kopi = store.document(f"trips/{trip_id}/places/place-kopi").get().to_dict()
    assert kopi["suggestion"] == {"reason": "A slow breakfast by the rice fields."}
    assert kopi["category"] == "cafe"  # "other" from Gemini, refined from Maps types
    assert kopi["savedBy"] == []
    taman_sari = store.document(f"trips/{trip_id}/places/place-taman-sari").get().to_dict()
    assert taman_sari["suggestion"] is None  # still the member's own pick


@requires_emulators
def test_voting_starts_without_reels(client: TestClient, fakes):
    trip_id, host, _, _, _ = new_trip(client)
    assert client.post(f"/v1/trips/{trip_id}/ingest", headers=host).status_code == 409

    client.post(f"/v1/trips/{trip_id}/places", json={"placeId": "place-kopi"}, headers=host)
    assert client.post(f"/v1/trips/{trip_id}/ingest", headers=host).status_code == 202
    trip = firestore_client().document(f"trips/{trip_id}").get().to_dict()
    assert trip["status"] == "voting"

    late = client.post(
        f"/v1/trips/{trip_id}/places", json={"placeId": "place-taman-sari"}, headers=host
    )
    assert late.status_code == 409


@requires_emulators
def test_reels_add_to_places_already_on_the_board(client: TestClient, fakes, monkeypatch):
    from travelin.ai import extractor
    from travelin.ai.schemas import Candidate

    async def extract(reel, destination):
        return [
            Candidate(name="Taman Sari", category="attraction", appears_at_sec=4, confidence=0.9)
        ]

    async def no_cache_key(reel):
        return None

    monkeypatch.setattr(extractor, "extract", extract)
    monkeypatch.setattr(ingest, "cache_key", no_cache_key)

    trip_id, host, friend, host_uid, friend_uid = new_trip(client)
    client.post(f"/v1/trips/{trip_id}/places", json={"placeId": "place-taman-sari"}, headers=host)
    firestore_client().document(f"trips/{trip_id}/reels/reel-1").set(
        {
            "uploaderUid": friend_uid,
            "source": "upload",
            "storagePath": f"trips/{trip_id}/reels/{friend_uid}/reel-1.mp4",
            "status": "queued",
            "platform": "other",
        }
    )

    assert client.post(f"/v1/trips/{trip_id}/ingest", headers=host).status_code == 202
    place = firestore_client().document(f"trips/{trip_id}/places/place-taman-sari").get().to_dict()
    assert sorted(place["savedBy"]) == sorted([host_uid, friend_uid])
    assert [m["reelId"] for m in place["mentions"]] == ["reel-1"]
    assert place["summary"]["highlights"] == ["Taman Sari is lovely"]  # kept, not redone
