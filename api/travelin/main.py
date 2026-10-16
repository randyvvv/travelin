from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .auth import CurrentUser, User
from .booking.mandates import travelin_key
from .booking.signing import public_jwk
from .config import get_settings
from .routes import booking, expenses, ingest, places, planning, settlement, trips, voting

app = FastAPI(title="Travelin API", version="0.1.0")
app.include_router(trips.router)
app.include_router(ingest.router)
app.include_router(places.router)
app.include_router(voting.router)
app.include_router(planning.router)
app.include_router(expenses.router)
app.include_router(settlement.router)
app.include_router(booking.router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/v1/me")
async def me(user: CurrentUser) -> User:
    return user


@app.get("/.well-known/jwks.json")
async def jwks() -> dict[str, list[dict[str, Any]]]:
    """Public key the merchant uses to verify the squad's group authorization."""
    return {"keys": [public_jwk(travelin_key())]}
