from typing import Annotated, Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from firebase_admin import auth as firebase_auth
from pydantic import BaseModel

from .db import db, firebase_app

bearer = HTTPBearer(auto_error=False)


class User(BaseModel):
    uid: str
    name: str | None = None
    email: str | None = None
    picture: str | None = None


# Sync on purpose: verify_id_token blocks on the certificate fetch, and FastAPI
# runs sync dependencies in its threadpool.
def current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> User:
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    try:
        claims = firebase_auth.verify_id_token(credentials.credentials, app=firebase_app())
    except (firebase_auth.InvalidIdTokenError, firebase_auth.CertificateFetchError, ValueError):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid ID token") from None
    return User(
        uid=claims["uid"],
        name=claims.get("name"),
        email=claims.get("email"),
        picture=claims.get("picture"),
    )


CurrentUser = Annotated[User, Depends(current_user)]


async def trip_for_member(trip_id: str, user: CurrentUser) -> dict[str, Any]:
    snapshot = await db().collection("trips").document(trip_id).get()
    if not snapshot.exists:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Trip not found")
    trip = snapshot.to_dict() or {}
    if user.uid not in trip.get("memberUids", []):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not a member of this trip")
    return {"id": snapshot.id, **trip}


MemberTrip = Annotated[dict[str, Any], Depends(trip_for_member)]
