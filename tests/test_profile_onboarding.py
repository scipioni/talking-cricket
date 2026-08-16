from __future__ import annotations

from calobot.profile.onboarding import OnboardingExtraction, parse_and_validate
from calobot.profile.service import (
    apply_onboarding_field,
    current_budget,
    maybe_complete_onboarding,
    next_onboarding_question,
    register_or_get_user,
)


async def test_multiple_fields_in_one_message_are_all_recorded():
    extraction = OnboardingExtraction(
        data_nascita_text="41 anni",
        altezza_text="1.78",
        peso_attuale_text="78kg",
        peso_obiettivo_text="72",
    )
    parsed, errors = parse_and_validate(extraction)
    assert errors == []
    assert parsed["altezza_cm"] == 178.0
    assert parsed["peso_attuale_kg"] == 78.0
    assert parsed["peso_obiettivo_kg"] == 72.0
    assert "data_nascita" in parsed


async def test_onboarding_completes_and_budget_available(db_session):
    reg = await register_or_get_user(db_session, telegram_user_id=1)
    user = reg.user

    for field, value in [
        ("sesso", "maschio"),
        ("data_nascita", __import__("datetime").date(1990, 1, 1)),
        ("altezza_cm", 178.0),
        ("peso_attuale_kg", 90.0),
        ("peso_obiettivo_kg", 80.0),
        ("livello_attivita", "moderato"),
        ("ritmo", "moderato"),
    ]:
        error = await apply_onboarding_field(db_session, user, field, value)
        assert error is None

    assert await next_onboarding_question(db_session, user) is None
    completed_now = await maybe_complete_onboarding(db_session, user)
    assert completed_now is True

    budget = await current_budget(db_session, user)
    assert budget is not None
    assert budget.direction == "deficit"


async def test_unsafe_goal_weight_rejected(db_session):
    reg = await register_or_get_user(db_session, telegram_user_id=2)
    user = reg.user
    user.altezza_cm = 175
    await db_session.flush()

    error = await apply_onboarding_field(db_session, user, "peso_obiettivo_kg", 45)
    assert error is not None
    assert user.peso_obiettivo_kg is None


async def test_peso_attuale_applied_twice_same_day_replaces_not_crashes(db_session):
    """Regression test for a real crash seen in production: applying
    peso_attuale_kg twice for the same day (e.g. the user re-answers during
    onboarding) used to raise sqlite3.IntegrityError on the (user_id, day)
    unique constraint instead of replacing the value, per specs/weight-logging
    - One weight per day."""
    reg = await register_or_get_user(db_session, telegram_user_id=4)
    user = reg.user

    error1 = await apply_onboarding_field(db_session, user, "peso_attuale_kg", 78.0)
    error2 = await apply_onboarding_field(db_session, user, "peso_attuale_kg", 77.0)
    assert error1 is None
    assert error2 is None

    from calobot.persistence.repository import get_latest_weight

    weight = await get_latest_weight(db_session, user.id)
    assert weight.kg == 77.0


async def test_resume_after_restart_keeps_supplied_fields(db_session):
    reg = await register_or_get_user(db_session, telegram_user_id=3)
    user = reg.user
    await apply_onboarding_field(db_session, user, "sesso", "femmina")
    await apply_onboarding_field(db_session, user, "altezza_cm", 165.0)

    # Simulate a restart: fetch a fresh User row the way a new process would.
    from calobot.persistence.repository import get_user_by_telegram_id

    reloaded = await get_user_by_telegram_id(db_session, 3)
    assert reloaded.sesso.value == "femmina"
    assert reloaded.altezza_cm == 165.0
    next_field = await next_onboarding_question(db_session, reloaded)
    assert next_field == "data_nascita"
