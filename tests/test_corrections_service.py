from __future__ import annotations

import pytest

from calobot.corrections.service import (
    AlreadyDeleted,
    Deleted,
    NoEntry,
    amend_food_quantity,
    delete_by_target,
    find_entry_by_confirmation_message,
    set_confirmation_message_id,
    undo_last,
)
from calobot.persistence.models import FoodEntry, Provenance
from calobot.persistence.repository import create_user
from calobot.persistence.timeutil import utcnow


async def test_undo_with_no_entries(db_session):
    user = await create_user(db_session, telegram_user_id=1)
    result = await undo_last(db_session, user.id)
    assert isinstance(result, NoEntry)


async def test_undo_deletes_most_recent_entry(db_session):
    user = await create_user(db_session, telegram_user_id=2)
    entry = FoodEntry(
        user_id=user.id,
        description="noci",
        grams=10,
        kcal_per_100g=654,
        kcal=65.4,
        provenance=Provenance.tabella,
        consumed_at=utcnow(),
    )
    db_session.add(entry)
    await db_session.flush()

    result = await undo_last(db_session, user.id)
    assert isinstance(result, Deleted)
    assert result.kind == "food"

    await db_session.refresh(entry)
    assert entry.deleted_at is not None


async def test_targeting_by_confirmation_message(db_session):
    user = await create_user(db_session, telegram_user_id=3)
    entry = FoodEntry(
        user_id=user.id,
        description="mela",
        grams=180,
        kcal_per_100g=52,
        kcal=93.6,
        provenance=Provenance.tabella,
        consumed_at=utcnow(),
    )
    db_session.add(entry)
    await db_session.flush()
    await set_confirmation_message_id(db_session, "food", entry.id, message_id=999)

    found = await find_entry_by_confirmation_message(db_session, 999)
    assert found is not None
    kind, found_entry = found
    assert kind == "food"
    assert found_entry.id == entry.id


async def test_delete_already_deleted_entry(db_session):
    user = await create_user(db_session, telegram_user_id=4)
    entry = FoodEntry(
        user_id=user.id,
        description="pane",
        grams=50,
        kcal_per_100g=265,
        kcal=132.5,
        provenance=Provenance.tabella,
        consumed_at=utcnow(),
        deleted_at=utcnow(),
    )
    db_session.add(entry)
    await db_session.flush()

    result = await delete_by_target(db_session, "food", entry.id)
    assert isinstance(result, AlreadyDeleted)


async def test_amend_food_quantity_recomputes_kcal(db_session):
    user = await create_user(db_session, telegram_user_id=5)
    entry = FoodEntry(
        user_id=user.id,
        description="noci",
        grams=10,
        kcal_per_100g=654,
        kcal=65.4,
        provenance=Provenance.tabella,
        consumed_at=utcnow(),
    )
    db_session.add(entry)
    await db_session.flush()

    updated = await amend_food_quantity(db_session, entry, 20.0)
    assert updated.grams == 20.0
    assert updated.kcal == 130.8


async def test_amend_food_quantity_rescales_macros(db_session):
    user = await create_user(db_session, telegram_user_id=6)
    entry = FoodEntry(
        user_id=user.id,
        description="noci",
        grams=10,
        kcal_per_100g=654,
        kcal=65.4,
        protein_g=1.52,
        fat_g=6.52,
        carbs_g=1.37,
        fiber_g=0.67,
        provenance=Provenance.tabella,
        consumed_at=utcnow(),
    )
    db_session.add(entry)
    await db_session.flush()

    updated = await amend_food_quantity(db_session, entry, 20.0)
    assert updated.protein_g == pytest.approx(3.04)
    assert updated.fat_g == pytest.approx(13.04)
    assert updated.carbs_g == pytest.approx(2.74)
    assert updated.fiber_g == pytest.approx(1.34)


async def test_amend_food_quantity_leaves_null_macros_null(db_session):
    user = await create_user(db_session, telegram_user_id=7)
    entry = FoodEntry(
        user_id=user.id,
        description="alimento senza macro",
        grams=10,
        kcal_per_100g=100,
        kcal=10,
        provenance=Provenance.llm,
        consumed_at=utcnow(),
    )
    db_session.add(entry)
    await db_session.flush()

    updated = await amend_food_quantity(db_session, entry, 20.0)
    assert updated.protein_g is None
    assert updated.fat_g is None
    assert updated.carbs_g is None
    assert updated.fiber_g is None
