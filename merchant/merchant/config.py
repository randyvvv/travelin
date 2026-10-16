from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    merchant_signing_key: str = ""  # ES256 private key, PEM
    travelin_jwks_url: str = "http://localhost:8000/.well-known/jwks.json"
    cart_ttl_minutes: int = 60


@lru_cache
def get_settings() -> Settings:
    return Settings()
