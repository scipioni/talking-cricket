"""Tests for proactive-nudges: signals, content, the cycle's gates, commands and
the stop callback."""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

from harness.state import create_onboarded_user

from calobot.advice.memory import record_advice
from calobot.nudges.messages import STOP_INSTRUCTION, compose
from calobot.nudges.service import _in_quiet_hours, _rate_limited, run_nudge_cycle
from calobot.nudges.signals import (
    NudgeCandidate,
    broken_logging_streak,
    find_candidate,
    goal_reached_recently,
    unresolved_suggestion,
)
from calobot.persistence.models import AdviceSurface, FoodEntry, Provenance, WeightEntry

TZ = ZoneInfo("Europe/Rome")


def _food(user_id: int, when: dt.datetime) -> FoodEntry:
    return FoodEntry(
        user_id=user_id,
        description="pasto",
        grams=100,
        kcal_per_100g=200,
        kcal=200,
        provenance=Provenance.tabella,
        consumed_at=when,
    )


async def test_goal_reached_recently_true_within_tolerance_and_window(db_session, settings):
    user = await create_onboarded_user(db_session, 301, weight_kg=70.2)
    user.peso_obiettivo_kg = 70.0
    await db_session.flush()

    assert await goal_reached_recently(db_session, user, TZ, settings) is True


async def test_goal_reached_recently_false_when_too_old(db_session, settings):
    user = await create_onboarded_user(db_session, 302, weight_kg=80.0)
    user.peso_obiettivo_kg = 70.0
    old_day = dt.date.today() - dt.timedelta(days=30)
    db_session.add(WeightEntry(user_id=user.id, day=old_day, kg=70.0))
    await db_session.flush()

    assert await goal_reached_recently(db_session, user, TZ, settings) is False


async def test_goal_reached_recently_false_when_far_off(db_session, settings):
    user = await create_onboarded_user(db_session, 303, weight_kg=75.0)
    user.peso_obiettivo_kg = 70.0
    await db_session.flush()

    assert await goal_reached_recently(db_session, user, TZ, settings) is False


async def test_broken_streak_requires_prior_engagement(db_session, settings):
    user = await create_onboarded_user(db_session, 304)
    # No food logged at all, ever - not a "break" since there's nothing to break.
    assert await broken_logging_streak(db_session, user, TZ, settings) is False


async def test_broken_streak_fires_after_prior_engagement(db_session, settings):
    user = await create_onboarded_user(db_session, 305)
    today = dt.datetime.now(TZ)
    old_meal = today - dt.timedelta(days=settings.nudge_streak_break_days + 5)
    db_session.add(_food(user.id, old_meal))
    await db_session.flush()

    assert await broken_logging_streak(db_session, user, TZ, settings) is True


async def test_broken_streak_does_not_fire_with_recent_logging(db_session, settings):
    user = await create_onboarded_user(db_session, 306)
    today = dt.datetime.now(TZ)
    db_session.add(_food(user.id, today))
    await db_session.flush()

    assert await broken_logging_streak(db_session, user, TZ, settings) is False


async def test_unresolved_suggestion_requires_minimum_age(db_session, settings):
    user = await create_onboarded_user(db_session, 307)
    record = await record_advice(
        db_session, user, AdviceSurface.dietician_review, "dietician_tip_week",
        "Registra i pasti ogni giorno questa settimana.", situation="period=week",
    )
    await db_session.flush()
    assert await unresolved_suggestion(db_session, user, TZ, settings) is None

    record.created_at = dt.datetime.now(dt.UTC) - dt.timedelta(days=settings.nudge_suggestion_min_age_days + 1)
    await db_session.flush()
    found = await unresolved_suggestion(db_session, user, TZ, settings)
    assert found is not None
    assert found.id == record.id


async def test_find_candidate_priority_goal_over_streak(db_session, settings):
    user = await create_onboarded_user(db_session, 308, weight_kg=70.0)
    user.peso_obiettivo_kg = 70.0
    old_meal = dt.datetime.now(TZ) - dt.timedelta(days=settings.nudge_streak_break_days + 5)
    db_session.add(_food(user.id, old_meal))
    await db_session.flush()

    candidate = await find_candidate(db_session, user, TZ, settings)
    assert candidate is not None
    assert candidate.kind == "goal_reached"


async def test_find_candidate_none_when_nothing_fires(db_session, settings):
    user = await create_onboarded_user(db_session, 309)
    assert await find_candidate(db_session, user, TZ, settings) is None


def test_compose_includes_stop_instruction_and_no_forbidden_framing():
    for kind in ("goal_reached", "broken_streak"):
        text = compose(NudgeCandidate(kind=kind))
        assert STOP_INSTRUCTION.strip() in text
        assert "fallito" not in text.lower()
        assert "dovresti mangiare meno" not in text.lower()
        assert "grasso" not in text.lower()
        assert "peso corporeo" not in text.lower()


def test_in_quiet_hours_wraps_midnight(settings):
    assert _in_quiet_hours(dt.datetime(2026, 1, 1, 23, 0), settings) is True
    assert _in_quiet_hours(dt.datetime(2026, 1, 1, 3, 0), settings) is True
    assert _in_quiet_hours(dt.datetime(2026, 1, 1, 12, 0), settings) is False


def test_rate_limited(settings):
    user_recent = type("U", (), {"last_nudge_sent_at": dt.datetime.now(dt.UTC)})()
    user_old = type(
        "U", (), {"last_nudge_sent_at": dt.datetime.now(dt.UTC) - dt.timedelta(days=30)}
    )()
    user_never = type("U", (), {"last_nudge_sent_at": None})()

    now = dt.datetime.now(dt.UTC)
    assert _rate_limited(user_recent, now, settings) is True
    assert _rate_limited(user_old, now, settings) is False
    assert _rate_limited(user_never, now, settings) is False


class _FakeBot:
    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []

    async def send_message(self, chat_id, text, **kwargs):
        self.sent.append((chat_id, text))


class _NonClosingSessionContext:
    """Wraps the test's live `db_session` so `run_nudge_cycle`'s `async with
    session_factory() as session:` reuses it without closing it on exit - the
    fixture, not this helper, owns the session's lifecycle."""

    def __init__(self, session) -> None:
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *exc_info) -> None:
        return None


def _patch_session_factory(monkeypatch, db_session) -> None:
    monkeypatch.setattr(
        "calobot.nudges.service.get_session_factory",
        lambda: (lambda: _NonClosingSessionContext(db_session)),
    )


async def test_run_nudge_cycle_sends_when_opted_in_and_signal_fires(db_session, settings, monkeypatch):
    user = await create_onboarded_user(db_session, 310, weight_kg=70.0)
    user.nudges_enabled = True
    user.peso_obiettivo_kg = 70.0
    await db_session.flush()
    await db_session.commit()

    _patch_session_factory(monkeypatch, db_session)
    bot = _FakeBot()

    await run_nudge_cycle(bot, settings)

    assert len(bot.sent) == 1
    assert bot.sent[0][0] == user.telegram_user_id


async def test_run_nudge_cycle_skips_when_not_opted_in(db_session, settings, monkeypatch):
    user = await create_onboarded_user(db_session, 311, weight_kg=70.0)
    # nudges_enabled stays default False
    user.peso_obiettivo_kg = 70.0
    await db_session.flush()
    await db_session.commit()

    _patch_session_factory(monkeypatch, db_session)
    bot = _FakeBot()

    await run_nudge_cycle(bot, settings)

    assert bot.sent == []


async def test_run_nudge_cycle_respects_rate_limit(db_session, settings, monkeypatch):
    user = await create_onboarded_user(db_session, 312, weight_kg=70.0)
    user.nudges_enabled = True
    user.peso_obiettivo_kg = 70.0
    user.last_nudge_sent_at = dt.datetime.now(dt.UTC)
    await db_session.flush()
    await db_session.commit()

    _patch_session_factory(monkeypatch, db_session)
    bot = _FakeBot()

    await run_nudge_cycle(bot, settings)

    assert bot.sent == []


async def test_run_nudge_cycle_skips_no_retention_chat(db_session, settings, monkeypatch):
    from calobot.telemetry.context import no_retention_chats

    user = await create_onboarded_user(db_session, 313, weight_kg=70.0)
    user.nudges_enabled = True
    user.peso_obiettivo_kg = 70.0
    await db_session.flush()
    await db_session.commit()

    no_retention_chats.add(user.telegram_user_id)
    try:
        _patch_session_factory(monkeypatch, db_session)
        bot = _FakeBot()
        await run_nudge_cycle(bot, settings)
        assert bot.sent == []
    finally:
        no_retention_chats.discard(user.telegram_user_id)


async def test_nudges_on_off_commands(client):
    from calobot.persistence.repository import get_user_by_telegram_id

    await client.say("/start")

    async def _get_user(session):
        return await get_user_by_telegram_id(session, client.telegram_user_id)

    replies_on = await client.say("/notifiche_on")
    assert "attivate" in replies_on[0].text

    replies_off = await client.say("/notifiche_off")
    assert "disattivate" in replies_off[0].text


async def test_hard_delete_removes_nudge_preference(db_session):
    from calobot.persistence.repository import hard_delete_user

    user = await create_onboarded_user(db_session, 314)
    user.nudges_enabled = True
    await db_session.flush()

    await hard_delete_user(db_session, user.id)
    await db_session.flush()

    from calobot.persistence.repository import get_user_by_telegram_id

    assert await get_user_by_telegram_id(db_session, 314) is None
