import os
from functools import lru_cache

import firebase_admin
from firebase_admin import firestore_async
from google.cloud.firestore import SERVER_TIMESTAMP, AsyncClient

from .config import get_settings


def firebase_app() -> firebase_admin.App:
    try:
        return firebase_admin.get_app()
    except ValueError:
        settings = get_settings()
        return firebase_admin.initialize_app(
            options={
                "projectId": settings.google_cloud_project,
                "storageBucket": settings.storage_bucket,
            }
        )


@lru_cache
def db() -> AsyncClient:
    if os.environ.get("FIRESTORE_EMULATOR_HOST"):
        # The emulator takes no credentials, but firebase_admin would still demand ADC.
        return AsyncClient(project=get_settings().google_cloud_project)
    return firestore_async.client(firebase_app())


async def notify(uid: str, *, type: str, text: str, trip_id: str, link: str) -> None:
    await (
        db()
        .collection("users")
        .document(uid)
        .collection("notifications")
        .add(
            {
                "type": type,
                "text": text,
                "tripId": trip_id,
                "link": link,
                "read": False,
                "createdAt": SERVER_TIMESTAMP,
            }
        )
    )
