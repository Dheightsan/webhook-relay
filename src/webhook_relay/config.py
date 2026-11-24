from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    admin_api_key: str = Field(min_length=16)

    # Incoming webhooks
    signature_tolerance_seconds: int = 300
    max_body_bytes: int = 1_048_576

    # Outgoing deliveries
    delivery_max_attempts: int = 3
    delivery_backoff_seconds: float = 1.0
    delivery_timeout_seconds: float = 5.0
    # Off by default so a source cannot point the relay at internal addresses.
    allow_private_targets: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
