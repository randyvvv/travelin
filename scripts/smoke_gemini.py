"""Check the Gemini setup on Vertex AI before building features on top of it.

Reads api/.env. Run from the repo root after `gcloud auth application-default login`:

    uv run --project api python scripts/smoke_gemini.py
    uv run --project api python scripts/smoke_gemini.py --video gs://<bucket>/samples/reels/reel-1.mp4
"""

import argparse
import os
import sys
import time
from collections.abc import Callable
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel

load_dotenv(Path(__file__).resolve().parents[1] / "api" / ".env")

# Taman Sari Water Castle, Yogyakarta
SAMPLE_LAT, SAMPLE_LNG = -7.8100, 110.3594


class Place(BaseModel):
    name: str
    city: str


class PlaceList(BaseModel):
    places: list[Place]


def run_check(label: str, fn: Callable[[], object]) -> bool:
    started = time.perf_counter()
    try:
        detail = fn()
    except Exception as error:  # report every failure and keep going
        print(f"FAIL  {label}: {type(error).__name__}: {error}")
        return False
    print(f"PASS  {label} ({time.perf_counter() - started:.1f}s): {detail}")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--video", help="gs:// URI of a sample reel (video/mp4)")
    args = parser.parse_args()

    project = os.environ.get("GOOGLE_CLOUD_PROJECT")
    if not project:
        sys.exit("GOOGLE_CLOUD_PROJECT is not set (api/.env)")
    location = os.environ.get("GOOGLE_CLOUD_LOCATION", "global")
    fast_model = os.environ.get("FAST_MODEL", "gemini-3.8-flash")
    planner_model = os.environ.get("PLANNER_MODEL", "gemini-4-argon")

    client = genai.Client(vertexai=True, project=project, location=location)
    print(f"project={project} location={location} fast={fast_model} planner={planner_model}\n")

    def structured_output() -> object:
        response = client.models.generate_content(
            model=fast_model,
            contents="Name two well-known places to visit in Yogyakarta, Indonesia.",
            config=types.GenerateContentConfig(
                response_mime_type="application/json", response_schema=PlaceList
            ),
        )
        return [place.name for place in response.parsed.places]

    def video_extraction() -> object:
        response = client.models.generate_content(
            model=fast_model,
            contents=[
                types.Part.from_uri(file_uri=args.video, mime_type="video/mp4"),
                "List every specific, named place that is shown, spoken, or written in this video.",
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json", response_schema=PlaceList
            ),
        )
        return [place.name for place in response.parsed.places]

    def maps_grounding() -> object:
        response = client.models.generate_content(
            model=fast_model,
            contents="What do visitors say about Taman Sari Water Castle, "
            "and when is the best time to visit?",
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_maps=types.GoogleMaps())],
                tool_config=types.ToolConfig(
                    retrieval_config=types.RetrievalConfig(
                        lat_lng=types.LatLng(latitude=SAMPLE_LAT, longitude=SAMPLE_LNG)
                    )
                ),
            ),
        )
        metadata = response.candidates[0].grounding_metadata
        chunks = (metadata.grounding_chunks if metadata else None) or []
        sources = [(chunk.maps.title, chunk.maps.place_id) for chunk in chunks if chunk.maps]
        if not sources:
            raise RuntimeError("response has no Google Maps sources")
        return sources[:3]

    def planner() -> object:
        response = client.models.generate_content(
            model=planner_model, contents="Reply with the single word: ready"
        )
        return response.text.strip()

    checks: list[tuple[str, Callable[[], object]]] = [
        ("structured output", structured_output),
        ("maps grounding", maps_grounding),
        ("planner model", planner),
    ]
    if args.video:
        checks.insert(1, ("video extraction", video_extraction))
    else:
        print("SKIP  video extraction (pass --video gs://...)")

    results = [run_check(label, fn) for label, fn in checks]
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
