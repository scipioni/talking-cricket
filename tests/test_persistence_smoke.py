from __future__ import annotations

from calobot.persistence.repository import create_user, get_user_by_telegram_id


async def test_create_and_fetch_user(db_session):
    user = await create_user(db_session, telegram_user_id=12345)
    await db_session.commit()

    fetched = await get_user_by_telegram_id(db_session, 12345)
    assert fetched is not None
    assert fetched.id == user.id
    assert fetched.onboarding_complete is False
