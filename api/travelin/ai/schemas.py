"""Structured inputs and outputs of the AI steps. Gemini fills the response schemas."""

from typing import Any, Literal

from pydantic import BaseModel

Category = Literal[
    "food", "cafe", "attraction", "nature", "beach", "stay", "nightlife", "shopping", "activity",
    "other",
]  # fmt: skip
Evidence = Literal["on_screen_text", "caption", "speech", "visual"]


class Candidate(BaseModel):
    """A place the Extractor saw in a video, before verification."""

    name: str
    city_hint: str = ""
    category: Category = "other"
    appears_at_sec: int = 0
    evidence: Evidence = "visual"
    quote: str = ""
    confidence: float = 0.0


class ExtractResult(BaseModel):
    places: list[Candidate]


class MatchDecision(BaseModel):
    same_place: bool
    reason: str


class VerifiedPlace(BaseModel):
    """A candidate matched to a real Google Maps place."""

    place_id: str
    name: str
    address: str = ""
    lat: float
    lng: float
    google_maps_uri: str = ""
    types: list[str] = []
    rating: float | None = None
    user_rating_count: int | None = None
    price_level: str | None = None
    price_range: dict[str, Any] | None = None
    opening_hours: dict[str, Any] | None = None
    photo_name: str | None = None


class DroppedPlace(BaseModel):
    name: str
    reason: str


class PlaceSummary(BaseModel):
    highlights: list[str] = []
    best_time: str = ""
    price_note: str = ""
    dietary_note: str = ""
    crowd_note: str = ""
