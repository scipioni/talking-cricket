from __future__ import annotations

from calobot.settings import Settings


def test_blank_optional_env_values_are_treated_as_unset(monkeypatch):
    """A .env copied from .env.example has blank per-step overrides
    (CALOBOT_LLM_CLASSIFY_TEMPERATURE=) - these must not fail validation."""
    monkeypatch.setenv("CALOBOT_TELEGRAM_BOT_TOKEN", "x")
    monkeypatch.setenv("CALOBOT_LLM_CLASSIFY_MODEL", "")
    monkeypatch.setenv("CALOBOT_LLM_CLASSIFY_TEMPERATURE", "")
    monkeypatch.setenv("CALOBOT_LLM_EXTRACT_MODEL", "")
    monkeypatch.setenv("CALOBOT_LLM_EXTRACT_TEMPERATURE", "")

    settings = Settings()  # type: ignore[call-arg]

    assert settings.llm_classify_model is None
    assert settings.llm_classify_temperature is None
    assert settings.model_for_step("classify") == settings.llm_model
    assert settings.temperature_for_step("classify") == settings.llm_temperature


def test_explicit_override_still_applies(monkeypatch):
    monkeypatch.setenv("CALOBOT_TELEGRAM_BOT_TOKEN", "x")
    monkeypatch.setenv("CALOBOT_LLM_CLASSIFY_MODEL", "some-small-model")
    monkeypatch.setenv("CALOBOT_LLM_CLASSIFY_TEMPERATURE", "0.0")

    settings = Settings()  # type: ignore[call-arg]

    assert settings.model_for_step("classify") == "some-small-model"
    assert settings.temperature_for_step("classify") == 0.0


def test_google_oauth_settings_and_admin_parsing(monkeypatch):
    monkeypatch.setenv("CALOBOT_TELEGRAM_BOT_TOKEN", "x")
    monkeypatch.setenv("CALOBOT_GOOGLE_CLIENT_ID", "my-client-id")
    monkeypatch.setenv("CALOBOT_GOOGLE_CLIENT_SECRET", "my-client-secret")
    monkeypatch.setenv("CALOBOT_ALLOWED_ADMIN_EMAILS", '["a@b.com", "scipio.it@gmail.com"]')

    settings = Settings()  # type: ignore[call-arg]

    assert settings.google_client_id == "my-client-id"
    assert settings.google_client_secret == "my-client-secret"
    assert settings.allowed_admin_emails == ["a@b.com", "scipio.it@gmail.com"]

    # Test comma-separated parsing fallback
    monkeypatch.setenv("CALOBOT_ALLOWED_ADMIN_EMAILS", "test@test.com, scipio.it@gmail.com ")
    settings_csv = Settings()  # type: ignore[call-arg]
    assert settings_csv.allowed_admin_emails == ["test@test.com", "scipio.it@gmail.com"]
