from fastapi.testclient import TestClient

from merchant.main import app

client = TestClient(app)


def test_healthz():
    assert client.get("/healthz").json() == {"status": "ok"}


def test_catalog_filters_by_destination_case_insensitively():
    items = client.get("/catalog", params={"destination": "yogyakarta"}).json()["items"]
    assert items
    assert all(item["destination"] == "Yogyakarta" for item in items)


def test_catalog_unknown_destination_is_empty():
    assert client.get("/catalog", params={"destination": "Atlantis"}).json()["items"] == []
