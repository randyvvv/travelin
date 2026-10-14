import json
from pathlib import Path
from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel


class CatalogItem(BaseModel):
    sku: str
    type: Literal["stay", "tour"]
    destination: str
    title: str
    description: str
    price_idr: int
    unit: Literal["night", "person"]
    capacity: int


class Catalog(BaseModel):
    merchant_id: str
    merchant_name: str
    items: list[CatalogItem]


CATALOG = Catalog.model_validate(
    json.loads((Path(__file__).parent / "catalog.json").read_text(encoding="utf-8"))
)

app = FastAPI(title="Travelin Demo Merchant", version="0.1.0")


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/catalog")
async def catalog(destination: str | None = None) -> Catalog:
    if destination is None:
        return CATALOG
    wanted = destination.strip().lower()
    items = [item for item in CATALOG.items if item.destination.lower() == wanted]
    return CATALOG.model_copy(update={"items": items})
