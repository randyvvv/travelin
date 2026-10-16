from functools import lru_cache
from typing import Any

from google import genai
from google.genai import types

from ..config import get_settings


@lru_cache
def client() -> genai.Client:
    settings = get_settings()
    return genai.Client(
        vertexai=True,
        project=settings.google_cloud_project,
        location=settings.google_cloud_location,
    )


def fast_config(**kwargs: Any) -> types.GenerateContentConfig:
    """Config for FAST_MODEL calls. Low thinking keeps simple, schema-bound tasks quick."""
    return types.GenerateContentConfig(
        thinking_config=types.ThinkingConfig(thinking_level=types.ThinkingLevel.LOW),
        **kwargs,
    )
