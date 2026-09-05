"""Seeded starting states, so a test that is about behaviour after onboarding does
not have to spend a conversation getting there."""

from __future__ import annotations

import datetime as dt

from sqlalchemy.ext.asyncio import AsyncSession

from calobot.persistence.models import User
from calobot.persistence.repository import create_user
from calobot.profile.service import apply_onboarding_field


async def create_onboarded_user(
    session: AsyncSession, telegram_user_id: int = 42, *, weight_kg: float = 90.0
) -> User:
    user = await create_user(session, telegram_user_id=telegram_user_id)
    await apply_onboarding_field(session, user, "sesso", "maschio")
    await apply_onboarding_field(session, user, "data_nascita", dt.date(1990, 1, 1))
    await apply_onboarding_field(session, user, "altezza_cm", 178.0)
    await apply_onboarding_field(session, user, "peso_attuale_kg", weight_kg)
    await apply_onboarding_field(session, user, "peso_obiettivo_kg", weight_kg - 10)
    await apply_onboarding_field(session, user, "livello_attivita", "moderato")
    await apply_onboarding_field(session, user, "ritmo", "moderato")
    user.onboarding_complete = True
    await session.flush()
    await session.commit()
    return user


FOOD_ITEM_TEMPLATE = {
    "description": "noci",
    "quantity_grams": 10,
    "quantity_count": None,
    "count_unit_hint": None,
    "household_measure": None,
    "preparation": None,
    "preparation_material_but_unstated": False,
}


def food_extraction(**overrides) -> dict:
    """The extract_food payload for a single item, with the fields a test cares about
    overridden and the rest left at their neutral values."""
    return {"items": [{**FOOD_ITEM_TEMPLATE, **overrides}], "when_text": None}


async def seed_streak_then_silence(
    session: AsyncSession, user: User, *, now_utc: dt.datetime, tz
) -> None:
    """The state a broken-streak nudge is earned by, and nothing else
    (specs/proactive-nudges - A nudge is sent only on an earned signal): food entries
    establishing a habit that stopped just over the streak window ago, and an old
    unresolved advice record that only wins if the streak signal does not.

    `now_utc` is the run's origin; entries land inside the prior-engagement window
    and outside the recent gap, whatever day the scenario starts on.
    """
    import zoneinfo

    from calobot.persistence.models import (
        AdviceOutcome,
        AdviceRecord,
        AdviceSurface,
        AdviceTopic,
        FoodEntry,
        Provenance,
    )

    assert isinstance(tz, zoneinfo.ZoneInfo)
    today = now_utc.astimezone(tz).date()
    for days_ago in (10, 8, 6):
        day = today - dt.timedelta(days=days_ago)
        consumed = dt.datetime.combine(day, dt.time(hour=13), tzinfo=tz).astimezone(dt.UTC)
        session.add(
            FoodEntry(
                user_id=user.id,
                description="pasto",
                grams=100,
                kcal_per_100g=200,
                kcal=200,
                provenance=Provenance.tabella,
                consumed_at=consumed,
            )
        )
    session.add(
        AdviceRecord(
            user_id=user.id,
            surface=AdviceSurface.daily_advice,
            category="meal_suggestion",
            content="Prova a registrare la colazione ogni giorno",
            situation="stato seed per lo scenario time-lapse",
            topic=AdviceTopic.meal_timing,
            outcome=AdviceOutcome.undetermined,
            created_at=now_utc - dt.timedelta(days=8),
        )
    )
    await session.commit()
