from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .auth import CurrentUser, User
from .config import get_settings
from .routes import ingest, planning, trips, voting

app = FastAPI(title="Travelin API", version="0.1.0")
app.include_router(trips.router)
app.include_router(ingest.router)
app.include_router(voting.router)
app.include_router(planning.router)

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
