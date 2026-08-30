"""specs/reporting - An unscoped report reports only the topics that have data.

A bare report request defaults to topic="all", so before this change every user who
did not log all three kinds of entry got their report followed by one bureaucratic
absence line per missing topic.
"""

from __future__ import annotations

import datetime as dt

from harness.state import create_onboarded_user

from calobot.persistence.models import ActivityEntry, FoodEntry, Provenance, WeightEntry
from calobot.persistence.seed import seed_all

_NO_WEIGHT = "non ci sono dati sul peso"
_NO_ACTIVITY = "non ci sono dati sull'attività"


def _food(user_id: int, when: dt.datetime) -> FoodEntry:
    return FoodEntry(
        user_id=user_id,
        description="mela",
        grams=150,
        kcal_per_100g=52,
        kcal=78.0,
        provenance=Provenance.tabella,
        consumed_at=when,
    )


async def _clear_weights(db_session, user):
    """Onboarding records a starting WeightEntry, so an onboarded user always has
    weight data. Soft-delete it to model a user who has never logged a weight since -
    every read path filters deleted_at."""
    from sqlalchemy import select

    rows = (await db_session.scalars(select(WeightEntry).where(WeightEntry.user_id == user.id))).all()
    for row in rows:
        row.deleted_at = dt.datetime.now(dt.UTC)
    await db_session.flush()
    await db_session.commit()


def _activity(user_id: int, when: dt.datetime) -> ActivityEntry:
    return ActivityEntry(
        user_id=user_id,
        activity="camminata",
        duration_minutes=30,
        met=3.0,
        kcal=120.0,
        provenance=Provenance.tabella,
        performed_at=when,
    )


def _all_text(sent) -> str:
    return "\n".join(m.text or "" for m in sent).lower()


async def test_unscoped_report_says_nothing_about_untracked_topics(db_session, client, llm):
    """Scenario: Unscoped report where only food was logged."""
    await seed_all(db_session)
    user = await create_onboarded_user(db_session, 42)
    await _clear_weights(db_session, user)
    db_session.add(_food(user.id, dt.datetime.now(dt.UTC)))
    await db_session.flush()
    await db_session.commit()

    llm.push(
        {"intent": "report", "ignored_text": None},
        {"period_text": None, "topic": "all"},
        {"advice": "Continua così!"},
    )
    sent = await client.say("report di oggi")

    text = _all_text(sent)
    assert "calorie" in text
    assert _NO_WEIGHT not in text
    assert _NO_ACTIVITY not in text


async def test_report_scoped_to_weight_still_reports_the_absence(db_session, client, llm):
    """Scenario: Report scoped to a topic with no data."""
    await seed_all(db_session)
    user = await create_onboarded_user(db_session, 42)
    await _clear_weights(db_session, user)

    llm.push(
        {"intent": "report", "ignored_text": None},
        {"period_text": None, "topic": "weight"},
    )
    sent = await client.say("come va il mio peso?")

    assert _NO_WEIGHT in _all_text(sent)


async def test_report_scoped_to_activity_still_reports_the_absence(db_session, client, llm):
    """Scenario: Report scoped to a topic with no data."""
    await seed_all(db_session)
    await create_onboarded_user(db_session, 42)

    llm.push(
        {"intent": "report", "ignored_text": None},
        {"period_text": None, "topic": "activity"},
    )
    sent = await client.say("quanta attività ho fatto oggi?")

    assert _NO_ACTIVITY in _all_text(sent)


async def test_unscoped_report_with_nothing_logged_gives_one_conversational_reply(
    db_session, client, llm
):
    """Scenario: Unscoped report over a period with nothing logged."""
    await seed_all(db_session)
    user = await create_onboarded_user(db_session, 42)
    await _clear_weights(db_session, user)

    llm.push(
        {"intent": "report", "ignored_text": None},
        {"period_text": None, "topic": "all"},
        {"message": "Il diario è ancora vuoto oggi: hai tutto il budget a disposizione!"},
    )
    sent = await client.say("report di oggi")

    assert len(sent) == 1
    text = _all_text(sent)
    assert "diario" in text
    assert _NO_WEIGHT not in text
    assert _NO_ACTIVITY not in text


async def test_unscoped_report_still_reports_every_topic_that_has_data(db_session, client, llm):
    """Scenario: Unscoped report where every topic has data."""
    await seed_all(db_session)
    user = await create_onboarded_user(db_session, 42)
    now = dt.datetime.now(dt.UTC)
    db_session.add(_food(user.id, now))
    db_session.add(_activity(user.id, now))
    await db_session.flush()
    await db_session.commit()

    llm.push(
        {"intent": "report", "ignored_text": None},
        {"period_text": None, "topic": "all"},
        {"advice": "Bella giornata!"},
    )
    sent = await client.say("report di oggi")

    text = _all_text(sent)
    assert "calorie" in text
    assert "peso" in text
    assert "attività" in text
