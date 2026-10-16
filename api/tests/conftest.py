from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from travelin import places
from travelin.db import db
from travelin.main import app


@pytest.fixture
def client() -> Iterator[TestClient]:
    # Cached async clients are bound to one TestClient's event loop.
    db.cache_clear()
    places._client = None
    with TestClient(app) as test_client:
        yield test_client
