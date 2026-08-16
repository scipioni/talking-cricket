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
