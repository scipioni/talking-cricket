"""Environment-driven configuration. See openspec design.md - Decisions - Per-step model configuration."""

from __future__ import annotations

from functools import lru_cache
from zoneinfo import ZoneInfo

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CALOBOT_", env_nested_delimiter="__")

    telegram_bot_token: str

    llm_base_url: str = "https://ingegno.csgalileo.org/ollama/v1"
    llm_api_key: str = "ollama"
    llm_model: str = "qwen3-vl:30b-a3b-instruct"
    llm_temperature: float = 0.2
    llm_timeout_seconds: float = 30.0
    llm_retry_limit: int = 2

    # Per-step overrides. Unset fields fall back to the values above. A blank
    # value in .env (e.g. `CALOBOT_LLM_CLASSIFY_TEMPERATURE=`) must also mean
    # "unset", not a parse error - see the validator below.
    llm_classify_model: str | None = None
    llm_classify_temperature: float | None = None
    llm_extract_model: str | None = None
    llm_extract_temperature: float | None = None

    @field_validator(
        "llm_classify_model",
        "llm_classify_temperature",
        "llm_extract_model",
        "llm_extract_temperature",
        mode="before",
    )
    @classmethod
    def _blank_env_value_means_unset(cls, value: object) -> object:
        return None if value == "" else value

    database_path: str = "/data/calobot.db"

    timezone_name: str = "Europe/Rome"

    draft_expiry_minutes: int = 30

    log_level: str = "INFO"

    @property
    def timezone(self) -> ZoneInfo:
        return ZoneInfo(self.timezone_name)

    @property
    def database_url(self) -> str:
        return f"sqlite+aiosqlite:///{self.database_path}"

    def model_for_step(self, step: str) -> str:
        overrides = {"classify": self.llm_classify_model, "extract": self.llm_extract_model}
        return overrides.get(step) or self.llm_model

    def temperature_for_step(self, step: str) -> float:
        overrides = {
            "classify": self.llm_classify_temperature,
            "extract": self.llm_extract_temperature,
        }
        value = overrides.get(step)
        return value if value is not None else self.llm_temperature


@lru_cache
def get_settings() -> Settings:
    return Settings()
