"""Helpers for tests that run against the Firebase emulators.

Run them from the repo root with:

    npx firebase-tools emulators:exec --only firestore,auth --project demo-travelin \
        "cd api && uv run pytest"
"""

import os
import uuid

import httpx
import pytest
from google.cloud import firestore

AUTH_HOST = os.environ.get("FIREBASE_AUTH_EMULATOR_HOST")
FIRESTORE_HOST = os.environ.get("FIRESTORE_EMULATOR_HOST")

requires_emulators = pytest.mark.skipif(
    not (AUTH_HOST and FIRESTORE_HOST), reason="needs the Firebase emulators"
)


def sign_up(display_name: str) -> dict[str, str]:
    """Creates an emulator user and returns an Authorization header for it."""
    response = httpx.post(
        f"http://{AUTH_HOST}/identitytoolkit.googleapis.com/v1/accounts:signUp?key=emulator",
        json={
            "email": f"{uuid.uuid4().hex[:10]}@example.com",
            "password": "emulator-password",
            "displayName": display_name,
            "returnSecureToken": True,
        },
    )
    response.raise_for_status()
    return {"Authorization": f"Bearer {response.json()['idToken']}"}


def firestore_client() -> firestore.Client:
    return firestore.Client(project=os.environ["GOOGLE_CLOUD_PROJECT"])
