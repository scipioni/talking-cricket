from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

from calobot.persistence.models import WeightEntry
from calobot.persistence.repository import create_user
from calobot.weight.normalizer import WeightNormalization
from calobot.weight.service import NeedsConfirmation, Rejected, Stored, apply_weight

TZ = ZoneInfo("Europe/Rome")


async def test_absolute_weight_stored(db_session):
    user = await create_user(db_session, telegram_user_id=1)
    result = await apply_weight(
        db_session, user, WeightNormalization(kg_absolute=78.0), None, TZ
    )
    assert isinstance(result, Stored)
    assert result.entry.kg == 78.0
    assert result.replaced_previous is False


async def test_relative_change_uses_last_weight(db_session):
    user = await create_user(db_session, telegram_user_id=2)
    yesterday = dt.date.today() - dt.timedelta(days=5)
    db_session.add(WeightEntry(user_id=user.id, kg=80.0, day=yesterday))
    await db_session.flush()

    result = await apply_weight(
        db_session,
        user,
        WeightNormalization(delta_kg=0.5, direction="loss"),
        None,
        TZ,
    )
    assert isinstance(result, Stored)
    assert result.entry.kg == 79.5


async def test_relative_change_without_previous_weight_rejected(db_session):
    user = await create_user(db_session, telegram_user_id=3)
    result = await apply_weight(
        db_session, user, WeightNormalization(delta_kg=0.5, direction="loss"), None, TZ
    )
    assert isinstance(result, Rejected)
    assert result.reason == "no_previous_weight"


async def test_out_of_range_rejected(db_session):
    user = await create_user(db_session, telegram_user_id=4)
    result = await apply_weight(db_session, user, WeightNormalization(kg_absolute=15.0), None, TZ)
    assert isinstance(result, Rejected)
    assert result.reason == "out_of_range"


async def test_implausible_jump_needs_confirmation(db_session):
    user = await create_user(db_session, telegram_user_id=5)
    today = dt.date.today()
    db_session.add(WeightEntry(user_id=user.id, kg=80.0, day=today - dt.timedelta(days=1)))
    await db_session.flush()

    result = await apply_weight(
        db_session, user, WeightNormalization(kg_absolute=95.0), None, TZ
    )
    assert isinstance(result, NeedsConfirmation)

    # once confirmed, it stores despite the jump
    confirmed_result = await apply_weight(
        db_session, user, WeightNormalization(kg_absolute=95.0), None, TZ, confirmed=True
    )
    assert isinstance(confirmed_result, Stored)


async def test_second_weighing_same_day_replaces(db_session):
    user = await create_user(db_session, telegram_user_id=6)
    first = await apply_weight(db_session, user, WeightNormalization(kg_absolute=78.0), None, TZ)
    second = await apply_weight(db_session, user, WeightNormalization(kg_absolute=77.5), None, TZ)
    assert isinstance(first, Stored) and not first.replaced_previous
    assert isinstance(second, Stored) and second.replaced_previous
    assert second.entry.id == first.entry.id
    assert second.entry.kg == 77.5


async def test_goal_reached_detected(db_session):
    user = await create_user(db_session, telegram_user_id=7)
    user.peso_obiettivo_kg = 75.0
    today = dt.date.today()
    db_session.add(WeightEntry(user_id=user.id, kg=76.0, day=today - dt.timedelta(days=1)))
    await db_session.flush()

    result = await apply_weight(db_session, user, WeightNormalization(kg_absolute=75.0), None, TZ)
    assert isinstance(result, Stored)
    assert result.goal_reached is True
