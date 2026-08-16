"""Regression test for a real bug reported from a live conversation: tapping an
onboarding button (sesso/livello di attività/ritmo) never applied the answer to
the profile, because on_answer_callback routed straight into the general message
pipeline regardless of onboarding state, which correctly-but-uselessly classified
the bare button label (e.g. "maschio") as unrelated chat."""

from __future__ import annotations

from unittest.mock import AsyncMock

from aiogram.types import Chat
from aiogram.types import User as TgUser

from calobot.persistence.models import Sesso
from calobot.persistence.repository import create_user, get_user_by_telegram_id
from calobot.telegram.handlers import on_answer_callback


def _make_callback(data: str, telegram_user_id: int, chat_id: int):
    chat = Chat(id=chat_id, type="private")
    tg_user = TgUser(id=telegram_user_id, is_bot=False, first_name="Stefano")
    message = AsyncMock()
    message.chat = chat
    callback = AsyncMock()
    callback.data = data
    callback.message = message
    callback.from_user = tg_user
    return callback


async def test_onboarding_button_answer_is_applied_to_profile(db_session, settings):
    await create_user(db_session, telegram_user_id=555)
    await db_session.commit()

    bot = AsyncMock()
    callback = _make_callback("ans:maschio", telegram_user_id=555, chat_id=555)

    await on_answer_callback(callback, bot, settings)

    reloaded = await get_user_by_telegram_id(db_session, 555)
    assert reloaded.sesso == Sesso.maschio

    # It must advance to the *next* onboarding question, not a generic chat reply.
    bot.send_message.assert_awaited_once()
    sent_text = bot.send_message.call_args.args[1]
    assert "nato" in sent_text.lower() or "età" in sent_text.lower()


async def test_stale_button_tap_does_not_corrupt_a_later_field(db_session, settings):
    """If the user taps an old keyboard from an already-answered question (e.g.
    sesso), the tapped label must not be forced onto whatever field onboarding has
    since moved on to."""
    user = await create_user(db_session, telegram_user_id=556)
    user.sesso = Sesso.maschio
    await db_session.commit()

    bot = AsyncMock()
    callback = _make_callback("ans:maschio", telegram_user_id=556, chat_id=556)

    await on_answer_callback(callback, bot, settings)

    reloaded = await get_user_by_telegram_id(db_session, 556)
    assert reloaded.data_nascita is None  # untouched, not corrupted by the stale tap
    bot.send_message.assert_awaited_once()
