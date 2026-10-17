"""Places without Reels: search and add, AI suggestions, and voting with no Reels at all."""

import asyncio

import pytest
from fastapi.testclient import TestClient

from travelin import places as places_client
from travelin.ai import ingest, suggest, suggester, summarizer, verifier
from travelin.ai.schemas import DroppedPlace, PlaceSummary
from travelin.ai.suggester import Suggestion, category_from_types, describe, parse_suggestions
from travelin.auth import User, current_user, trip_for_member
from travelin.config import get_settings
from travelin.main import app
from travelin.routes import places as places_routes
from travelin.routes import trips

from .emulator import firestore_client, requires_emulators, sign_up
from .test_trips import TRIP


class FakePlacesResponse:
    def __init__(self, payload: dict, status_code: int = 200):
        self.payload = payload
        self.status_code = status_code

    def json(self):
        return self.payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise AssertionError(f"unexpected fake Places status: {self.status_code}")


class FakePlacesHttp:
    def __init__(self, *responses: FakePlacesResponse):
        self.responses = list(responses)
        self.calls = []

    async def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.responses.pop(0)


class FakePlaceSnapshot:
    exists = True


class FakePlaceDocument:
    async def get(self):
        return FakePlaceSnapshot()


class FakePlaceDatabase:
    def document(self, path):
        assert path == "trips/trip-1/places/place-1"
        return FakePlaceDocument()


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


def test_fresh_place_photo_returns_photo_uri_attribution_and_maps_source(monkeypatch):
    attribution = {
        "displayName": "Google Maps contributor",
        "uri": "https://maps.google.com/contributor",
    }
    client = FakePlacesHttp(
        FakePlacesResponse(
            {
                "googleMapsUri": "https://maps.google.com/place/taman-sari",
                "photos": [
                    {
                        "name": "places/place-taman-sari/photos/current",
                        "authorAttributions": [attribution],
                        "googleMapsUri": "https://maps.google.com/photo/taman-sari",
                    }
                ],
            }
        ),
        FakePlacesResponse({"photoUri": "https://lh3.googleusercontent.com/fresh-photo"}),
    )
    monkeypatch.setattr(places_client, "_http", lambda: client)
    monkeypatch.setattr(places_client, "_api_key", lambda: "test-key")

    result = asyncio.run(places_client.fresh_place_photo("place-taman-sari"))

    assert result == {
        "photoUri": "https://lh3.googleusercontent.com/fresh-photo",
        "authorAttributions": [attribution],
        "googleMapsUri": "https://maps.google.com/photo/taman-sari",
    }
    detail_headers = client.calls[0][1]["headers"]
    assert detail_headers["X-Goog-FieldMask"] == (
        "id,photos.name,photos.authorAttributions,photos.googleMapsUri,googleMapsUri"
    )
    assert client.calls[1][1]["params"] == {"maxWidthPx": 960, "skipHttpRedirect": "true"}
    assert "current" in client.calls[1][0]


def test_fresh_place_photo_gracefully_returns_when_photo_is_missing(monkeypatch):
    client = FakePlacesHttp(
        FakePlacesResponse(
            {
                "googleMapsUri": "https://maps.google.com/place/no-photo",
                "photos": [],
            }
        )
    )
    monkeypatch.setattr(places_client, "_http", lambda: client)
    monkeypatch.setattr(places_client, "_api_key", lambda: "test-key")

    result = asyncio.run(places_client.fresh_place_photo("place-without-photo"))

    assert result == {
        "photoUri": None,
        "authorAttributions": [],
        "googleMapsUri": "https://maps.google.com/place/no-photo",
    }
    assert len(client.calls) == 1


def test_fresh_place_photo_handles_expired_or_unavailable_photo_reference(monkeypatch):
    attribution = {"displayName": "Contributor", "uri": "https://maps.google.com/contributor"}
    client = FakePlacesHttp(
        FakePlacesResponse(
            {
                "googleMapsUri": "https://maps.google.com/place/no-photo",
                "photos": [
                    {"name": "places/place/photos/expired", "authorAttributions": [attribution]}
                ],
            }
        ),
        FakePlacesResponse({}, status_code=404),
    )
    monkeypatch.setattr(places_client, "_http", lambda: client)
    monkeypatch.setattr(places_client, "_api_key", lambda: "test-key")

    result = asyncio.run(places_client.fresh_place_photo("place-with-expired-photo"))

    assert result == {
        "photoUri": None,
        "authorAttributions": [attribution],
        "googleMapsUri": "https://maps.google.com/place/no-photo",
    }


def test_fresh_curated_photo_uses_place_search_and_returns_source(monkeypatch):
    async def search_text(query, *, field_mask, page_size):
        assert query == "Bali, Indonesia"
        assert "places.photos.authorAttributions" in field_mask
        assert "places.photos.googleMapsUri" in field_mask
        assert "places.googleMapsUri" in field_mask
        assert page_size == 1
        return [
            {
                "id": "bali-place",
                "displayName": {"text": "Bali"},
                "googleMapsUri": "https://maps.google.com/place/bali",
                "photos": [
                    {
                        "name": "places/bali/photos/current",
                        "authorAttributions": [],
                        "googleMapsUri": "https://maps.google.com/photo/bali",
                    }
                ],
            }
        ]

    client = FakePlacesHttp(
        FakePlacesResponse({"photoUri": "https://lh3.googleusercontent.com/bali"})
    )
    monkeypatch.setattr(places_client, "search_text", search_text)
    monkeypatch.setattr(places_client, "_http", lambda: client)
    monkeypatch.setattr(places_client, "_api_key", lambda: "test-key")

    result = asyncio.run(places_client.fresh_curated_photo("Bali, Indonesia"))

    assert result == {
        "photoUri": "https://lh3.googleusercontent.com/bali",
        "authorAttributions": [],
        "googleMapsUri": "https://maps.google.com/photo/bali",
        "placeName": "Bali",
    }


def test_authenticated_photo_routes_return_attribution_and_fallback_source(client, monkeypatch):
    async def member_trip(trip_id):
        return {"id": trip_id, "memberUids": ["test-user"]}

    async def place_photo(place_id):
        return {
            "photoUri": "https://lh3.googleusercontent.com/transient",
            "authorAttributions": [
                {"displayName": "Contributor", "uri": "https://maps.google.com/contributor"}
            ],
            "googleMapsUri": "https://maps.google.com/photo/place-1",
        }

    async def curated_photo(query):
        return {
            "photoUri": None,
            "authorAttributions": [],
            "googleMapsUri": "https://maps.google.com/place/bali",
        }

    monkeypatch.setattr(places_routes, "db", lambda: FakePlaceDatabase())
    monkeypatch.setattr(places_routes, "fresh_place_photo", place_photo)
    monkeypatch.setattr(places_routes, "fresh_curated_photo", curated_photo)
    app.dependency_overrides[current_user] = lambda: User(uid="test-user")
    app.dependency_overrides[trip_for_member] = member_trip
    try:
        place_response = client.get("/v1/trips/trip-1/places/place-1/photo")
        curated_response = client.get("/v1/home/destinations/bali/photo")
        invalid_curated = client.get("/v1/home/destinations/not-allowed/photo")
    finally:
        app.dependency_overrides.pop(current_user, None)
        app.dependency_overrides.pop(trip_for_member, None)

    assert place_response.status_code == 200
    assert place_response.headers["cache-control"] == "no-store"
    assert place_response.json()["authorAttributions"] == [
        {"displayName": "Contributor", "uri": "https://maps.google.com/contributor"}
    ]
    assert place_response.json()["googleMapsUri"] == "https://maps.google.com/photo/place-1"
    assert curated_response.status_code == 200
    assert curated_response.json() == {
        "photoUri": None,
        "authorAttributions": [],
        "googleMapsUri": "https://maps.google.com/place/bali",
    }
    assert invalid_curated.status_code == 404


@requires_emulators
def test_authenticated_home_photo_routes_are_uncached_and_allow_no_photo(
    client, fakes, monkeypatch
):
    trip_id, host, _, _, _ = new_trip(client)
    firestore_client().document(f"trips/{trip_id}/places/place-taman-sari").set(
        {"name": "Taman Sari"}
    )
    attribution = {"displayName": "Contributor", "uri": "https://maps.google.com/contributor"}

    async def fresh_place_photo(place_id):
        return {
            "photoUri": "https://lh3.googleusercontent.com/transient",
            "authorAttributions": [attribution],
            "googleMapsUri": "https://maps.google.com/place/taman-sari",
        }

    async def missing_curated_photo(query):
        return {
            "photoUri": None,
            "authorAttributions": [],
            "googleMapsUri": "https://maps.google.com/place/bali",
        }

    monkeypatch.setattr(places_routes, "fresh_place_photo", fresh_place_photo)
    monkeypatch.setattr(places_routes, "fresh_curated_photo", missing_curated_photo)

    assert client.get(f"/v1/trips/{trip_id}/places/place-taman-sari/photo").status_code == 401
    place_response = client.get(f"/v1/trips/{trip_id}/places/place-taman-sari/photo", headers=host)
    assert place_response.status_code == 200
    assert place_response.headers["cache-control"] == "no-store"
    assert place_response.json() == {
        "photoUri": "https://lh3.googleusercontent.com/transient",
        "authorAttributions": [attribution],
        "googleMapsUri": "https://maps.google.com/place/taman-sari",
    }

    curated_response = client.get("/v1/home/destinations/bali/photo", headers=host)
    assert curated_response.status_code == 200
    assert curated_response.headers["cache-control"] == "no-store"
    assert curated_response.json() == {
        "photoUri": None,
        "authorAttributions": [],
        "googleMapsUri": "https://maps.google.com/place/bali",
    }
    assert client.get("/v1/home/destinations/not-allowed/photo", headers=host).status_code == 404


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

    kopi_ref = store.document(f"trips/{trip_id}/suggestions/place-kopi")
    kopi = kopi_ref.get().to_dict()
    assert kopi["suggestion"] == {"reason": "A slow breakfast by the rice fields."}
    assert kopi["category"] == "cafe"  # "other" from Gemini, refined from Maps types
    assert kopi["savedBy"] == []
    assert "photoName" not in kopi
    assert not store.document(f"trips/{trip_id}/places/place-kopi").get().exists
    taman_sari = store.document(f"trips/{trip_id}/places/place-taman-sari").get().to_dict()
    assert taman_sari["suggestion"] is None  # still the member's own pick


@requires_emulators
def test_suggest_more_appends_only_new_places(client: TestClient, fakes, monkeypatch):
    trip_id, host, _, _, _ = new_trip(client)
    suggestions = [
        Suggestion(name="Kopi Klotok", category="cafe", reason="First idea"),
    ]
    calls = 0

    async def suggest_places(trip, members, existing, count=8):
        nonlocal calls
        assert existing == ([] if calls == 0 else ["Kopi Klotok"])
        calls += 1
        return list(suggestions)

    monkeypatch.setattr(suggester, "suggest", suggest_places)
    first = client.post(f"/v1/trips/{trip_id}/places:suggest", headers=host)
    assert first.status_code == 202
    suggestions.append(Suggestion(name="Taman Sari", category="attraction", reason="A classic"))

    second = client.post(f"/v1/trips/{trip_id}/places:suggest", headers=host)
    assert second.status_code == 202
    store = firestore_client()
    docs = list(store.collection(f"trips/{trip_id}/suggestions").stream())
    assert {doc.id for doc in docs} == {"place-kopi", "place-taman-sari"}
    assert list(store.collection(f"trips/{trip_id}/places").stream()) == []


@requires_emulators
def test_any_member_can_remove_a_place_only_while_gathering(client: TestClient, fakes):
    trip_id, host, friend, _, _ = new_trip(client)
    added = client.post(
        f"/v1/trips/{trip_id}/places", json={"placeId": "place-taman-sari"}, headers=host
    )
    assert added.status_code == 201

    removed = client.delete(f"/v1/trips/{trip_id}/places/place-taman-sari", headers=friend)
    assert removed.status_code == 204
    assert not firestore_client().document(
        f"trips/{trip_id}/places/place-taman-sari"
    ).get().exists
    assert client.delete(
        f"/v1/trips/{trip_id}/places/place-taman-sari", headers=friend
    ).status_code == 404

    client.post(
        f"/v1/trips/{trip_id}/places", json={"placeId": "place-taman-sari"}, headers=host
    )
    firestore_client().document(f"trips/{trip_id}").update({"status": "voting"})
    refused = client.delete(f"/v1/trips/{trip_id}/places/place-taman-sari", headers=friend)
    assert refused.status_code == 409
    assert firestore_client().document(
        f"trips/{trip_id}/places/place-taman-sari"
    ).get().exists


@requires_emulators
def test_removed_place_can_be_added_again_from_a_reel(client: TestClient, fakes, monkeypatch):
    from travelin.ai import extractor
    from travelin.ai.schemas import Candidate

    async def extract(reel, destination):
        return [Candidate(name="Taman Sari", category="attraction", confidence=0.9)]

    async def no_cache_key(reel):
        return None

    monkeypatch.setattr(extractor, "extract", extract)
    monkeypatch.setattr(ingest, "cache_key", no_cache_key)
    trip_id, host, friend, _, friend_uid = new_trip(client)
    assert client.post(
        f"/v1/trips/{trip_id}/places", json={"placeId": "place-taman-sari"}, headers=host
    ).status_code == 201
    assert client.delete(
        f"/v1/trips/{trip_id}/places/place-taman-sari", headers=friend
    ).status_code == 204

    store = firestore_client()
    store.document(f"trips/{trip_id}/reels/reel-after-removal").set(
        {
            "uploaderUid": friend_uid,
            "source": "upload",
            "storagePath": f"trips/{trip_id}/reels/{friend_uid}/reel-after-removal.mp4",
            "status": "queued",
            "platform": "other",
        }
    )
    assert client.post(f"/v1/trips/{trip_id}/ingest", headers=host).status_code == 202
    assert store.document(f"trips/{trip_id}/places/place-taman-sari").get().exists


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
