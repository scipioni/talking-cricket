"""Tests for advice-memory (openspec/changes/advice-memory): recording, outcome
resolution, repetition suppression, the read-only tool, no-retention and
/cancellami."""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

from harness.state import create_onboarded_user

from calobot.advice.memory import (
    classify_topic,
    previous_unresolved_tip,
    record_advice,
    resolve_pending_outcomes,
)
from calobot.advice.tools import NoArgs, build_tool_registry
from calobot.persistence.models import (
    AdviceOutcome,
    AdviceRecord,
    AdviceSurface,
    AdviceTopic,
    FoodEntry,
    Provenance,
)
from calobot.persistence.repository import get_recent_advice_records, hard_delete_user
from calobot.persistence.seed import seed_all

TZ = ZoneInfo("Europe/Rome")


def _food(user_id: int, grams: float, kcal: float, when: dt.datetime) -> FoodEntry:
    return FoodEntry(
        user_id=user_id,
        description="pasto",
        grams=grams,
        kcal_per_100g=kcal / grams * 100,
        kcal=kcal,
        provenance=Provenance.tabella,
        consumed_at=when,
    )


def test_classify_topic_meal_timing():
    assert classify_topic("Prova a mangiare qualcosa prima la sera, per non arrivare a cena troppo tardi.") \
        == AdviceTopic.meal_timing


def test_classify_topic_logging_consistency():
    topic = classify_topic("Prova a registrare i pasti ogni giorno, anche gli spuntini.")
    assert topic == AdviceTopic.logging_consistency


def test_classify_topic_no_match():
    assert classify_topic("Aggiungi piu' verdure ai tuoi pasti per varieta'.") is None


async def test_record_advice_from_dietician_review(db_session):
    user = await create_onboarded_user(db_session, 201)
    record = await record_advice(
        db_session, user, AdviceSurface.dietician_review, "dietician_tip_week",
        "Registra i pasti ogni giorno questa settimana.", situation="period=week",
    )
    await db_session.flush()

    assert record.surface == AdviceSurface.dietician_review
    assert record.topic == AdviceTopic.logging_consistency
    assert record.outcome == AdviceOutcome.undetermined

    records = await get_recent_advice_records(db_session, user.id)
    assert len(records) == 1
    assert records[0].id == record.id


async def test_record_advice_from_daily_advice_and_advice_agent(db_session):
    user = await create_onboarded_user(db_session, 202)
    await record_advice(
        db_session, user, AdviceSurface.daily_advice, "daily_rest_of_day", "Bevi piu' acqua oggi.",
        situation="daily_report",
    )
    await record_advice(
        db_session, user, AdviceSurface.advice_agent, "meal_suggestion", "Prova un'insalata di ceci.",
        situation="suggestion_mode=within_budget",
    )
    await db_session.flush()

    records = await get_recent_advice_records(db_session, user.id)
    surfaces = {r.surface for r in records}
    assert surfaces == {AdviceSurface.daily_advice, AdviceSurface.advice_agent}


async def test_previous_unresolved_tip_returns_text_while_undetermined(db_session):
    user = await create_onboarded_user(db_session, 203)
    await record_advice(
        db_session, user, AdviceSurface.dietician_review, "dietician_tip_week", "Consiglio numero uno.",
        situation="period=week",
    )
    await db_session.flush()

    assert await previous_unresolved_tip(db_session, user, "dietician_tip_week") == "Consiglio numero uno."
    assert await previous_unresolved_tip(db_session, user, "dietician_tip_general") is None


async def test_previous_unresolved_tip_none_once_resolved(db_session):
    user = await create_onboarded_user(db_session, 204)
    record = await record_advice(
        db_session, user, AdviceSurface.dietician_review, "dietician_tip_week", "Consiglio numero uno.",
        situation="period=week",
    )
    record.outcome = AdviceOutcome.followed
    await db_session.flush()

    assert await previous_unresolved_tip(db_session, user, "dietician_tip_week") is None


async def test_resolve_pending_outcomes_marks_logging_consistency_followed(db_session):
    user = await create_onboarded_user(db_session, 205)
    advice_day = dt.date(2026, 8, 3)  # a Monday, long enough in the past
    record = await record_advice(
        db_session, user, AdviceSurface.dietician_review, "dietician_tip_week",
        "Registra i pasti con piu' costanza questa settimana.", situation="period=week",
    )
    record.created_at = dt.datetime.combine(advice_day, dt.time(12), tzinfo=dt.UTC)
    await db_session.flush()

    # Before window: 1 day logged out of 7. After window: 6 days logged out of 7.
    before_day = advice_day - dt.timedelta(days=6)
    db_session.add(_food(user.id, 100, 200, dt.datetime.combine(before_day, dt.time(12), tzinfo=TZ)))
    for offset in range(6):
        day = advice_day + dt.timedelta(days=offset)
        db_session.add(_food(user.id, 100, 200, dt.datetime.combine(day, dt.time(12), tzinfo=TZ)))
    await db_session.flush()

    await resolve_pending_outcomes(db_session, user, TZ)
    await db_session.refresh(record)

    assert record.outcome == AdviceOutcome.followed


async def test_resolve_pending_outcomes_marks_logging_consistency_not_followed(db_session):
    user = await create_onboarded_user(db_session, 206)
    advice_day = dt.date(2026, 8, 3)
    record = await record_advice(
        db_session, user, AdviceSurface.dietician_review, "dietician_tip_week",
        "Registra i pasti con piu' costanza questa settimana.", situation="period=week",
    )
    record.created_at = dt.datetime.combine(advice_day, dt.time(12), tzinfo=dt.UTC)
    await db_session.flush()

    # Before window: 3 days logged. After window: still only 3 days, no improvement.
    for offset in (6, 5, 4):
        day = advice_day - dt.timedelta(days=offset - 3)
        db_session.add(_food(user.id, 100, 200, dt.datetime.combine(day, dt.time(12), tzinfo=TZ)))
    for offset in (0, 1, 2):
        day = advice_day + dt.timedelta(days=offset)
        db_session.add(_food(user.id, 100, 200, dt.datetime.combine(day, dt.time(12), tzinfo=TZ)))
    await db_session.flush()

    await resolve_pending_outcomes(db_session, user, TZ)
    await db_session.refresh(record)

    assert record.outcome == AdviceOutcome.not_followed


async def test_resolve_pending_outcomes_leaves_recent_advice_undetermined(db_session):
    user = await create_onboarded_user(db_session, 207)
    record = await record_advice(
        db_session, user, AdviceSurface.dietician_review, "dietician_tip_week",
        "Registra i pasti con piu' costanza questa settimana.", situation="period=week",
    )
    await db_session.flush()

    await resolve_pending_outcomes(db_session, user, TZ)
    await db_session.refresh(record)

    assert record.outcome == AdviceOutcome.undetermined


async def test_advice_with_no_matching_topic_stays_undetermined_forever(db_session):
    user = await create_onboarded_user(db_session, 208)
    advice_day = dt.date(2026, 1, 1)
    record = await record_advice(
        db_session, user, AdviceSurface.dietician_review, "dietician_tip_general",
        "Aggiungi piu' verdure ai tuoi pasti per varieta'.", situation="period=month",
    )
    record.created_at = dt.datetime.combine(advice_day, dt.time(12), tzinfo=dt.UTC)
    await db_session.flush()
    assert record.topic is None

    await resolve_pending_outcomes(db_session, user, TZ)
    await db_session.refresh(record)

    assert record.outcome == AdviceOutcome.undetermined


async def test_get_advice_history_tool_returns_recorded_advice(db_session, settings, llm):
    await seed_all(db_session)
    user = await create_onboarded_user(db_session, 209)
    await record_advice(
        db_session, user, AdviceSurface.daily_advice, "daily_rest_of_day", "Bevi piu' acqua oggi.",
        situation="daily_report",
    )
    await db_session.flush()

    tools = {t.name: t for t in await build_tool_registry(db_session, llm.gateway, user, settings.timezone)}
    result = await tools["get_advice_history"].handler(NoArgs())

    assert result["no_data"] is False
    assert result["records"][0]["content"] == "Bevi piu' acqua oggi."
    assert result["records"][0]["outcome"] == "undetermined"


async def test_get_advice_history_tool_reports_no_data(db_session, settings, llm):
    await seed_all(db_session)
    user = await create_onboarded_user(db_session, 210)

    tools = {t.name: t for t in await build_tool_registry(db_session, llm.gateway, user, settings.timezone)}
    result = await tools["get_advice_history"].handler(NoArgs())

    assert result["no_data"] is True


async def test_no_retention_mode_discards_advice_records(db_session):
    from calobot.persistence.engine import get_session_factory
    from calobot.telemetry.context import active_no_retention

    user = await create_onboarded_user(db_session, 212)

    # Mirrors how a real request-scoped session records advice while no-retention
    # mode is active: the session's own `commit()` is bypassed by
    # `NonRetentiveAsyncSession`, so closing the `async with` block without a real
    # commit rolls the write back (design.md - Decisions).
    token = active_no_retention.set(True)
    try:
        session_factory = get_session_factory()
        async with session_factory() as session:
            await record_advice(
                session, user, AdviceSurface.daily_advice, "daily_rest_of_day", "Consiglio non salvato.",
                situation="daily_report",
            )
            await session.commit()
    finally:
        active_no_retention.reset(token)

    records = await get_recent_advice_records(db_session, user.id)
    assert records == []


async def test_cancellami_removes_advice_records(db_session):
    user = await create_onboarded_user(db_session, 211)
    await record_advice(
        db_session, user, AdviceSurface.daily_advice, "daily_rest_of_day", "Consiglio da cancellare.",
        situation="daily_report",
    )
    await db_session.flush()

    await hard_delete_user(db_session, user.id)
    await db_session.flush()

    from sqlalchemy import select

    result = await db_session.execute(select(AdviceRecord).where(AdviceRecord.user_id == user.id))
    assert result.scalars().all() == []
