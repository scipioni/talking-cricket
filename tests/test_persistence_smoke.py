from __future__ import annotations

from calobot.persistence.repository import create_user, get_user_by_telegram_id


async def test_create_and_fetch_user(db_session):
    user = await create_user(db_session, telegram_user_id=12345)
    await db_session.commit()

    fetched = await get_user_by_telegram_id(db_session, 12345)
    assert fetched is not None
    assert fetched.id == user.id
    assert fetched.onboarding_complete is False


async def test_seed_backfills_reference_portions(db_session):
    """Rows seeded before the portion columns existed (food-table-reference-portions)
    must fill from the CSV on the next seed, exactly like the macro backfill."""
    from sqlalchemy import select

    from calobot.persistence.models import FoodDataRow
    from calobot.persistence.seed import seed_food_data

    await seed_food_data(db_session)
    # Simulate pre-existing rows by wiping the portion columns and seeding again.
    rows = (await db_session.execute(select(FoodDataRow))).scalars().all()
    for row in rows:
        row.portion_small_g = None
    await db_session.commit()

    await seed_food_data(db_session)

    db_session.expire_all()
    onion = next(
        row
        for row in (await db_session.execute(select(FoodDataRow))).scalars()
        if row.source_name_en == "Onions, raw"
    )
    assert (onion.portion_small_g, onion.portion_medium_g, onion.portion_generous_g) == (
        40.0,
        60.0,
        100.0,
    )
