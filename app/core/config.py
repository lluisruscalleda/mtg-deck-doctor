"""Application configuration loaded from environment variables."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings for API, workers, and integrations."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: Literal["development", "test", "production"] = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 55700
    log_level: str = "INFO"

    database_url: str = "postgresql+asyncpg://mtg:mtg@localhost:5432/mtg_deck_doctor"

    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"
    rabbitmq_queue: str = "mtg.analysis"
    rabbitmq_dlq: str = "mtg.analysis.dlq"

    llm_provider: str = "openai"
    llm_model: str = "gpt-4o-mini"
    llm_api_key: str | None = None
    llm_base_url: str | None = None

    scryfall_base_url: str = "https://api.scryfall.com"
    scryfall_user_agent: str = "MTGDeckDoctor/1.0"

    max_cards_per_deck: int = Field(default=100, ge=1)
    max_card_name_length: int = Field(default=120, ge=1)
    max_recommendations: int = Field(default=3, ge=1, le=10)

    sse_heartbeat_seconds: float = Field(default=15.0, gt=0)
    sse_poll_interval_seconds: float = Field(default=1.0, gt=0)

    outbox_poll_interval_seconds: float = Field(default=1.0, gt=0)
    outbox_batch_size: int = Field(default=20, ge=1)

    llm_timeout_seconds: float = Field(default=45.0, gt=0)
    llm_max_retries: int = Field(default=1, ge=0, le=5)

    @field_validator("llm_api_key", "llm_base_url", mode="before")
    @classmethod
    def empty_str_to_none(cls, value: object) -> object:
        if value == "":
            return None
        return value

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    def require_llm_config(self) -> None:
        """Raise if the configured LLM provider cannot run."""
        if self.llm_provider.lower() == "openai" and not self.llm_api_key:
            msg = (
                "LLM credentials are not configured for the selected provider. "
                "Set LLM credentials in the environment, or inject a fake model in tests."
            )
            raise RuntimeError(msg)


@lru_cache
def get_settings() -> Settings:
    return Settings()
