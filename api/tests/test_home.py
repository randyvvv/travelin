"""Daily Google Places recommendations for the Home dashboard."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime
from threading import Event, Lock
from uuid import uuid4

from travelin.ai.schemas import VerifiedPlace
from travelin.ai.suggester import Suggestion
from travelin.auth import User, current_user
from travelin.main import app
from travelin.routes import home

from .emulator import firestore_client, requires_emulators, sign_up


def maps_place(place_id: str, name: str, review_count: int) -> dict:
    return {
        "id": place_id,
        "displayName": {"text": name},
        "formattedAddress": f"{name}, Southeast Asia",
        "location": {"latitude": 1.2, "longitude": 103.8},
        "types": ["tourist_attraction"],
        "googleMapsUri": f"https://maps.google.com/?q={place_id}",
        "rating": 4.7,
        "userRatingCount": review_count,
    }


def verified_place(place_id: str, name: str) -> VerifiedPlace:
    return VerifiedPlace(
        place_id=place_id,
        name=name,
        address=f"{name}, Southeast Asia",
        lat=1.2,
        lng=103.8,
        google_maps_uri=f"https://maps.google.com/?q={place_id}",
        types=["tourist_attraction"],
        rating=4.7,
        user_rating_count=500,
    )


def test_daily_key_uses_jakarta_date_at_utc_rollover():
    assert home.jakarta_day_key(datetime(2026, 10, 16, 16, 59, tzinfo=UTC)) == "2026-10-16"
    assert home.jakarta_day_key(datetime(2026, 10, 16, 17, 0, tzinfo=UTC)) == "2026-10-17"


def test_concurrent_daily_cache_claims_only_one_generation(monkeypatch):
    class Snapshot:
        def __init__(self, value):
            self.value = value

        def to_dict(self):
            return dict(self.value)

    class CacheReference:
        def __init__(self):
            self.value = {}

        async def get(self, transaction=None):
            return Snapshot(self.value)

        def set(self, value):
            self.value = dict(value)

        def update(self, value):
            self.value.update(value)

    class Transaction:
        def __init__(self, lock):
            self.lock = lock

        def set(self, ref, value):
            ref.set(value)

        def update(self, ref, value):
            ref.update(value)

    class Database:
        def __init__(self):
            self.lock = asyncio.Lock()

        def transaction(self):
            return Transaction(self.lock)

    def transactional(function):
        async def run(transaction):
            async with transaction.lock:
                return await function(transaction)

        return run

    monkeypatch.setattr(home, "async_transactional", transactional)
    database = Database()
    monkeypatch.setattr(home, "db", lambda: database)
    ref = CacheReference()

    async def claim_many():
        return await asyncio.gather(
            *(home._claim_daily_cache(ref, "2026-10-17") for _ in range(8))
        )

    results = asyncio.run(claim_many())
    claimed = [result for result in results if result[0] == "claimed"]
    assert len(claimed) == 1
    assert sum(result[0] == "generating" for result in results) == 7
    claim_id = claimed[0][2]
    assert all(result[1]["generationId"] == claim_id for result in results)

    next_day = asyncio.run(home._claim_daily_cache(ref, "2026-10-18"))
    assert next_day[0] == "claimed"
    assert next_day[2] != claim_id


def test_home_trip_prefers_gathering_underway_then_nearest_future():
    trips = [
        {"id": "past", "status": "gathering", "startDate": "2026-10-10", "endDate": "2026-10-12"},
        {"id": "near", "status": "gathering", "startDate": "2026-10-20", "endDate": "2026-10-22"},
        {"id": "far", "status": "planned", "startDate": "2026-11-01", "endDate": "2026-11-03"},
        {"id": "settled", "status": "settled", "startDate": "2026-10-17", "endDate": "2026-10-19"},
        {"id": "now", "status": "gathering", "startDate": "2026-10-16", "endDate": "2026-10-18"},
    ]
    assert home.select_home_trip(trips, date(2026, 10, 17))["id"] == "now"
    assert home.select_home_trip(trips[:4], date(2026, 10, 17))["id"] == "near"
    assert home.select_home_trip([trips[0], trips[3]], date(2026, 10, 17)) is None


def test_personal_preferences_require_a_non_empty_preference():
    assert not home.has_personal_preferences(None)
    assert not home.has_personal_preferences({"prefs": {"interests": [], "skip": []}})
    assert home.has_personal_preferences({"prefs": {"interests": ["food"]}})
    assert home.has_personal_preferences({"prefs": {"budgetIdr": 250000}})


def test_popular_candidates_are_deduplicated_and_sorted_by_review_count():
    places = [
        maps_place("low", "Low", 300),
        maps_place("high", "High", 2500),
        maps_place("mid", "Mid", 900),
        maps_place("high", "High duplicate", 2500),
    ]
    ranked = home.ranked_popular_places(places)
    assert [place["id"] for place in ranked] == ["high", "mid", "low"]


def test_ideas_endpoint_claims_daily_ids_and_returns_fresh_details(client, monkeypatch):
    uid = f"home-ideas-{uuid4().hex}"
    app.dependency_overrides[current_user] = lambda: User(uid=uid)
    cache = {"dayKey": "2026-10-17", "state": "generating"}
    details_calls = []

    async def claim(ref, day_key):
        assert day_key == "2026-10-17"
        return "claimed", cache, "claim-id"

    async def generate(user_id):
        assert user_id == uid
        return None, [], [f"popular-{index}" for index in range(5)], {}

    async def finish(ref, claim_id, *, trip_id, personal_place_ids, popular_place_ids):
        assert claim_id == "claim-id"
        assert trip_id is None
        assert personal_place_ids == []
        cache.update(
            {
                "state": "ready",
                "tripId": trip_id,
                "personalPlaceIds": personal_place_ids,
                "popularPlaceIds": popular_place_ids,
            }
        )
        return True

    async def load_context(trip_id, user_id):
        return None, set()

    async def details(place_id):
        details_calls.append(place_id)
        return maps_place(place_id, f"Fresh {place_id}", 1000)

    monkeypatch.setattr(home, "_cache_ref", lambda user_id: object())
    monkeypatch.setattr(home, "jakarta_day_key", lambda: "2026-10-17")
    monkeypatch.setattr(home, "_claim_daily_cache", claim)
    monkeypatch.setattr(home, "_generate_daily_ideas", generate)
    monkeypatch.setattr(home, "_finish_daily_cache", finish)
    monkeypatch.setattr(home, "_load_context", load_context)
    monkeypatch.setattr(home, "fresh_home_idea_details", details)
    try:
        response = client.get("/v1/home/ideas")
        assert response.status_code == 200, response.text
        assert response.headers["cache-control"] == "no-store"
        result = response.json()
        assert result["state"] == "ready"
        assert [idea["placeId"] for idea in result["ideas"]] == [f"popular-{index}" for index in range(5)]
        assert result["ideas"][0]["name"] == "Fresh popular-0"
        assert details_calls == [f"popular-{index}" for index in range(5)]
        assert set(cache) <= {"dayKey", "state", "tripId", "personalPlaceIds", "popularPlaceIds"}
    finally:
        app.dependency_overrides.pop(current_user, None)


def test_daily_photo_endpoint_returns_attribution_without_caching_photo_data(client, monkeypatch):
    uid = f"home-photo-{uuid4().hex}"
    app.dependency_overrides[current_user] = lambda: User(uid=uid)
    cache = {
        "dayKey": "2026-10-17",
        "state": "ready",
        "personalPlaceIds": ["photo-id"],
        "popularPlaceIds": [],
    }

    class Snapshot:
        def to_dict(self):
            return cache

    class CacheReference:
        async def get(self):
            return Snapshot()

    monkeypatch.setattr(home, "_cache_ref", lambda cached_uid: CacheReference())
    monkeypatch.setattr(home, "jakarta_day_key", lambda: "2026-10-17")

    async def fresh_photo(place_id):
        return {
            "photoUri": "https://images.example/transient.jpg",
            "authorAttributions": [
                {"displayName": "Photo author", "uri": "https://example.com/author"}
            ],
            "googleMapsUri": "https://maps.google.com/?q=photo-id",
        }

    monkeypatch.setattr(home, "fresh_place_photo", fresh_photo)
    try:
        response = client.get("/v1/home/ideas/photo-id/photo")
        assert response.status_code == 200
        assert response.json()["authorAttributions"][0]["displayName"] == "Photo author"
        assert response.headers["cache-control"] == "no-store"
        assert client.get("/v1/home/ideas/not-in-set/photo").status_code == 404
    finally:
        app.dependency_overrides.pop(current_user, None)


def test_daily_photo_endpoint_handles_missing_photo_and_provider_failure(client, monkeypatch):
    app.dependency_overrides[current_user] = lambda: User(uid=f"home-photo-{uuid4().hex}")
    cache = {
        "dayKey": "2026-10-17",
        "state": "ready",
        "personalPlaceIds": [],
        "popularPlaceIds": ["photo-id"],
    }

    class Snapshot:
        def to_dict(self):
            return cache

    class CacheReference:
        async def get(self):
            return Snapshot()

    monkeypatch.setattr(home, "_cache_ref", lambda uid: CacheReference())
    monkeypatch.setattr(home, "jakarta_day_key", lambda: "2026-10-17")

    async def no_photo(place_id):
        return {"photoUri": None, "authorAttributions": [], "googleMapsUri": "https://maps.google.com/"}

    async def unavailable(place_id):
        from travelin.places import PlacesUnavailableError

        raise PlacesUnavailableError("not configured")

    try:
        monkeypatch.setattr(home, "fresh_place_photo", no_photo)
        missing = client.get("/v1/home/ideas/photo-id/photo")
        assert missing.status_code == 200
        assert missing.json()["photoUri"] is None

        monkeypatch.setattr(home, "fresh_place_photo", unavailable)
        failed = client.get("/v1/home/ideas/photo-id/photo")
        assert failed.status_code == 503
        assert failed.headers["cache-control"] == "no-store"
    finally:
        app.dependency_overrides.pop(current_user, None)


def test_resolve_uses_three_personal_and_two_popular_then_fills_missing_slots(monkeypatch):
    async def load_context(trip_id, uid):
        if trip_id is None:
            return None, set()
        return {"id": "trip-1", "destination": {"name": "Singapore"}, "status": "gathering"}, set()

    monkeypatch.setattr(home, "_load_context", load_context)

    async def resolve(cache, uid, *, transient=None):
        return await home._resolve_daily_ideas(cache, uid, transient=transient)

    transient = {
        f"personal-{index}": verified_place(f"personal-{index}", f"Personal {index}")
        for index in range(3)
    }
    transient.update(
        {
            f"popular-{index}": verified_place(f"popular-{index}", f"Popular {index}")
            for index in range(5)
        }
    )
    cache = {
        "dayKey": "2026-10-17",
        "tripId": "trip-1",
        "personalPlaceIds": ["personal-0", "personal-1", "personal-2"],
        "popularPlaceIds": [f"popular-{index}" for index in range(5)],
    }
    response = asyncio.run(resolve(cache, "uid", transient=transient))
    assert [idea.source for idea in response.ideas] == ["personal"] * 3 + ["popular"] * 2

    cache["personalPlaceIds"] = ["personal-0"]
    response = asyncio.run(resolve(cache, "uid", transient=transient))
    assert len(response.ideas) == 5
    assert [idea.source for idea in response.ideas] == ["personal"] + ["popular"] * 4

    cache["tripId"] = None
    response = asyncio.run(resolve(cache, "uid", transient=transient))
    assert response.trip_id is None
    assert [idea.place_id for idea in response.ideas] == [f"popular-{index}" for index in range(5)]


@requires_emulators
def test_daily_ids_are_per_user_stable_until_jakarta_day_changes(client, monkeypatch):
    uid = f"daily-ideas-{uuid4().hex}"
    other_uid = f"daily-ideas-other-{uuid4().hex}"
    current_uid = uid
    app.dependency_overrides[current_user] = lambda: User(uid=current_uid, name="Daily ideas")
    store = firestore_client()
    generation_count = 0

    async def search_text(*args, **kwargs):
        nonlocal generation_count
        generation_count += 1
        suffix = "first" if generation_count == 1 else "second"
        return [maps_place(f"{suffix}-{index}", f"{suffix.title()} {index}", 1000 - index) for index in range(8)]

    async def fresh_details(place_id):
        return maps_place(place_id, f"Fresh {place_id}", 600)

    monkeypatch.setattr(home, "search_text", search_text)
    monkeypatch.setattr(home, "fresh_home_idea_details", fresh_details)
    monkeypatch.setattr(home, "jakarta_day_key", lambda: "2026-10-17")

    try:
        first = client.get("/v1/home/ideas")
        assert first.status_code == 200, first.text
        first_ids = [idea["placeId"] for idea in first.json()["ideas"]]
        assert first_ids == [f"first-{index}" for index in range(5)]

        again = client.get("/v1/home/ideas")
        assert again.status_code == 200, again.text
        assert [idea["placeId"] for idea in again.json()["ideas"]] == first_ids
        assert again.json()["ideas"][0]["name"] == f"Fresh {first_ids[0]}"
        assert generation_count == 1

        cached = store.document(f"users/{uid}/homeIdeas/current").get().to_dict()
        assert cached["dayKey"] == "2026-10-17"
        assert cached["popularPlaceIds"] == [f"first-{index}" for index in range(8)]
        assert not {"name", "photoName", "photoUri", "googleMapsUri"} & set(cached)

        current_uid = other_uid
        other = client.get("/v1/home/ideas")
        assert other.status_code == 200, other.text
        assert [idea["placeId"] for idea in other.json()["ideas"]] == [
            f"second-{index}" for index in range(5)
        ]
        assert generation_count == 2

        current_uid = uid
        monkeypatch.setattr(home, "jakarta_day_key", lambda: "2026-10-18")
        next_day = client.get("/v1/home/ideas")
        assert next_day.status_code == 200, next_day.text
        assert [idea["placeId"] for idea in next_day.json()["ideas"]] == [
            f"third-{index}" for index in range(5)
        ]
        assert generation_count == 3
    finally:
        app.dependency_overrides.pop(current_user, None)


@requires_emulators
def test_home_idea_photos_are_fresh_attributed_and_limited_to_cached_ids(client, monkeypatch):
    user = sign_up("Photo ideas")
    # The response itself grants access only to IDs placed in this account's daily cache.
    monkeypatch.setattr(home, "jakarta_day_key", lambda: "2026-10-17")

    async def search_text(*args, **kwargs):
        return [maps_place(f"photo-{index}", f"Photo {index}", 800 - index) for index in range(6)]

    payload = {
        "photoUri": "https://images.example/fresh.jpg",
        "authorAttributions": [{"displayName": "A travel photographer", "uri": "https://example.com"}],
        "googleMapsUri": "https://maps.google.com/?q=photo-0",
    }
    calls = []

    async def fresh_photo(place_id):
        calls.append(place_id)
        return payload

    monkeypatch.setattr(home, "search_text", search_text)
    monkeypatch.setattr(home, "fresh_place_photo", fresh_photo)
    response = client.get("/v1/home/ideas", headers=user)
    assert response.status_code == 200, response.text
    place_id = response.json()["ideas"][0]["placeId"]

    photo = client.get(f"/v1/home/ideas/{place_id}/photo", headers=user)
    assert photo.status_code == 200
    assert photo.json() == payload
    assert photo.headers["cache-control"] == "no-store"
    assert calls == [place_id]

    async def no_photo(place_id):
        return {"photoUri": None, "authorAttributions": [], "googleMapsUri": payload["googleMapsUri"]}

    monkeypatch.setattr(home, "fresh_place_photo", no_photo)
    missing_photo = client.get(f"/v1/home/ideas/{place_id}/photo", headers=user)
    assert missing_photo.status_code == 200
    assert missing_photo.json()["photoUri"] is None
    assert missing_photo.json()["googleMapsUri"] == payload["googleMapsUri"]

    async def unavailable(place_id):
        from travelin.places import PlacesUnavailableError

        raise PlacesUnavailableError("test")

    monkeypatch.setattr(home, "fresh_place_photo", unavailable)
    failed_photo = client.get(f"/v1/home/ideas/{place_id}/photo", headers=user)
    assert failed_photo.status_code == 503
    assert failed_photo.headers["cache-control"] == "no-store"
    assert client.get("/v1/home/ideas/not-cached/photo", headers=user).status_code == 404


@requires_emulators
def test_concurrent_home_opens_claim_only_one_generation(client, monkeypatch):
    user = sign_up("Concurrent ideas")
    started = Event()
    release = Event()
    calls = 0
    calls_lock = Lock()
    monkeypatch.setattr(home, "jakarta_day_key", lambda: "2026-10-17")

    async def search_text(*args, **kwargs):
        nonlocal calls
        with calls_lock:
            calls += 1
        started.set()
        await asyncio.to_thread(release.wait, 5)
        return [maps_place(f"concurrent-{index}", f"Concurrent {index}", 1000 - index) for index in range(7)]

    monkeypatch.setattr(home, "search_text", search_text)
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(client.get, "/v1/home/ideas", headers=user)
        assert started.wait(5)
        second = executor.submit(client.get, "/v1/home/ideas", headers=user)
        second_result = second.result(timeout=5)
        release.set()
        first_result = first.result(timeout=10)

    assert calls == 1
    assert first_result.status_code == 200
    assert second_result.status_code == 200
    assert second_result.json()["state"] in {"generating", "ready"}


@requires_emulators
def test_trip_personal_suggestions_exclude_board_and_fill_popular_slots(client, monkeypatch):
    store = firestore_client()
    uid = f"home-test-{uuid4().hex}"
    trip_id = f"home-ideas-personal-{uuid4().hex}"
    app.dependency_overrides[current_user] = lambda: User(uid=uid, name="Preference owner")
    trip_ref = store.document(f"trips/{trip_id}")
    trip_ref.set(
        {
            "name": "Singapore weekend",
            "destination": {"name": "Singapore", "lat": 1.29, "lng": 103.85},
            "origin": {"name": "Jakarta", "lat": -6.2, "lng": 106.8},
            "startDate": "2026-10-20",
            "endDate": "2026-10-22",
            "status": "gathering",
            "memberUids": [uid],
        }
    )
    trip_ref.collection("members").document(uid).set(
        {"prefs": {"interests": ["local food"], "dietary": [], "skip": [], "budgetIdr": 300000}}
    )
    trip_ref.collection("places").document("already-on-board").set({"name": "Garden by the Bay"})
    store.document(f"users/{uid}/homeIdeas/current").delete()
    monkeypatch.setattr(home, "jakarta_day_key", lambda: "2026-10-17")

    async def suggest(trip, members, existing, count=8):
        assert members[0]["prefs"]["interests"] == ["local food"]
        assert existing == ["Garden by the Bay"]
        return [
            Suggestion(name="Garden by the Bay"),
            Suggestion(name="Personal 1"),
            Suggestion(name="Personal 2"),
            Suggestion(name="Personal 3"),
        ]

    async def verify(candidate, destination):
        if candidate.name == "Garden by the Bay":
            return verified_place("already-on-board", candidate.name)
        return verified_place(candidate.name.lower().replace(" ", "-"), candidate.name)

    async def search_text(*args, **kwargs):
        assert args[0] == "popular tourist attractions and places to visit in Singapore"
        assert kwargs["bias"] == (1.29, 103.85, home.SEARCH_RADIUS_M)
        return [maps_place(f"popular-{index}", f"Popular {index}", 3000 - index) for index in range(8)]

    monkeypatch.setattr(home.suggester, "suggest", suggest)
    monkeypatch.setattr(home.verifier, "verify", verify)
    monkeypatch.setattr(home, "search_text", search_text)

    try:
        response = client.get("/v1/home/ideas")
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["tripId"] == trip_id
        assert result["tripStatus"] == "gathering"
        assert [idea["source"] for idea in result["ideas"]] == ["personal"] * 3 + ["popular"] * 2
        assert "already-on-board" not in [idea["placeId"] for idea in result["ideas"]]
    finally:
        app.dependency_overrides.pop(current_user, None)


@requires_emulators
def test_trip_without_preferences_uses_only_popular_recommendations(client, monkeypatch):
    store = firestore_client()
    uid = f"home-no-prefs-{uuid4().hex}"
    trip_id = f"home-ideas-no-prefs-{uuid4().hex}"
    app.dependency_overrides[current_user] = lambda: User(uid=uid, name="No preferences")
    store.document(f"trips/{trip_id}").set(
        {
            "name": "Bangkok weekend",
            "destination": {"name": "Bangkok", "lat": 13.75, "lng": 100.5},
            "startDate": "2026-10-20",
            "endDate": "2026-10-22",
            "status": "gathering",
            "memberUids": [uid],
        }
    )
    store.document(f"trips/{trip_id}/members/{uid}").set({"prefs": {}})
    monkeypatch.setattr(home, "jakarta_day_key", lambda: "2026-10-17")

    async def unexpected_suggest(*args, **kwargs):
        raise AssertionError("the suggester must not run without a personal preference")

    async def search_text(*args, **kwargs):
        assert args[0] == "popular tourist attractions and places to visit in Bangkok"
        assert kwargs["bias"] == (13.75, 100.5, home.SEARCH_RADIUS_M)
        return [maps_place(f"fallback-{index}", f"Fallback {index}", 2000 - index) for index in range(7)]

    monkeypatch.setattr(home.suggester, "suggest", unexpected_suggest)
    monkeypatch.setattr(home, "search_text", search_text)
    try:
        response = client.get("/v1/home/ideas")
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["tripId"] == trip_id
        assert len(result["ideas"]) == 5
        assert {idea["source"] for idea in result["ideas"]} == {"popular"}
    finally:
        app.dependency_overrides.pop(current_user, None)
