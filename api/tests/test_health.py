from fastapi.testclient import TestClient

from travelin.main import app

client = TestClient(app)


def test_healthz():
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_me_requires_token():
    assert client.get("/v1/me").status_code == 401
