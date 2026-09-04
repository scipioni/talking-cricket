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

    bot_label: str = "Grillo Parlante"

    database_path: str = "/data/calobot.db"

    timezone_name: str = "Europe/Rome"

    draft_expiry_minutes: int = 30

    # How many consecutive unusable answers to the same question before the system
    # stops asking, discards the draft and says so (specs/message-ingestion - Draft
    # completeness and the clarification loop). Before this existed the only exit was
    # draft expiry, which the user cannot see, predict or be told about.
    #
    # Must not exceed the simulation harness's progress bound: if the bot were allowed
    # more attempts than the harness tolerates, correct give-up behaviour would fail
    # every simulation run. See tests/test_clarification_give_up.py, which pins the
    # relationship so neither value can be changed alone.
    clarification_attempt_limit: int = 3

    log_level: str = "INFO"

    jsonl_log_enabled: bool = True
    jsonl_log_path: str = "/data/interactions.jsonl"

    web_port: int = 8083

    # Bounded resolution photos are downscaled to before inference (design.md -
    # image inference is much more expensive than text, so size is the main lever).
    # Labels get their own, typically higher, setting since legibility of small print
    # matters more than it does for a dish (open question in design.md, answerable
    # only against real photographs).
    photo_max_dimension_px: int = 1280
    photo_label_max_dimension_px: int = 2000

    off_base_url: str = "https://world.openfoodfacts.org"
    off_timeout_seconds: float = 5.0

    # Bound on retrieval rounds a single advice-agent question may trigger
    # (specs/advice-agent - The agent's work is bounded). Reaching it without an
    # answer ends the gather loop rather than looping indefinitely.
    llm_advice_max_rounds: int = 4

    # In-process periodic job scheduler (specs/background-scheduling). Off entirely
    # disables the background task; no job is registered by this setting alone.
    scheduler_enabled: bool = True
    scheduler_tick_interval_seconds: float = 60.0
    scheduler_shutdown_grace_seconds: float = 10.0

    # Proactive nudges (specs/proactive-nudges). All defaults are chosen to keep the
    # cadence low; nudges are off per-user regardless (nudges_enabled defaults False).
    nudge_check_interval_seconds: float = 3600.0
    nudge_min_interval_days: int = 3
    nudge_quiet_hours_start: int = 22
    nudge_quiet_hours_end: int = 8
    nudge_streak_break_days: int = 4
    nudge_goal_reached_recency_days: int = 3
    nudge_suggestion_min_age_days: int = 7

    google_client_id: str | None = None
    google_client_secret: str | None = None
    google_redirect_uri: str = "http://localhost:8083/api/auth/callback"
    allowed_admin_emails: list[str] | str = ["scipio.it@gmail.com"]
    session_secret_key: str | None = None

    @field_validator("allowed_admin_emails", mode="before")
    @classmethod
    def _parse_allowed_admin_emails(cls, value: object) -> object:
        if isinstance(value, str):
            if value.startswith("[") and value.endswith("]"):
                import json
                try:
                    return json.loads(value)
                except Exception:
                    pass
            return [email.strip() for email in value.split(",") if email.strip()]
        return value

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
