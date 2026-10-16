from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    google_cloud_project: str = ""
    google_cloud_location: str = "global"
    storage_bucket: str = ""

    fast_model: str = "gemini-3.8-flash"
    planner_model: str = "gemini-4-argon"

    places_api_key: str = ""
    merchant_url: str = "http://localhost:8001"
    merchant_id: str = "travelin-demo-merchant"
    travelin_signing_key: str = ""  # ES256 private key, PEM

    allowed_origins: str = "http://localhost:5173"  # comma-separated

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
