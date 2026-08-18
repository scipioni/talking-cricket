from __future__ import annotations

import logging

import pytest
from aiogram.methods import AnswerCallbackQuery, GetUpdates, SendMessage, SendPhoto
from aiogram.types import Chat, Message, Update, User

from calobot.telegram.logging_middleware import (
    IncomingLoggingMiddleware,
    OutgoingLoggingMiddleware,
)


def _make_update(text: str) -> Update:
    chat = Chat(id=42, type="private")
    user = User(id=7, is_bot=False, first_name="Stefano")
    message = Message(
        message_id=1,
        date=0,
        chat=chat,
        from_user=user,
        text=text,
    )
    return Update(update_id=100, message=message)


async def test_incoming_middleware_logs_and_calls_handler(caplog):
    middleware = IncomingLoggingMiddleware()
    update = _make_update("ho mangiato 10g di noci")

    called = {}

    async def handler(event, data):
        called["event"] = event
        return "handled"

    with caplog.at_level(logging.INFO, logger="calobot.telegram.messages"):
        result = await middleware(handler, update, {})

    assert result == "handled"
    assert called["event"] is update
    assert "ho mangiato 10g di noci" in caplog.text
    assert "chat=42" in caplog.text
    assert "user=7" in caplog.text


async def test_incoming_middleware_truncates_long_text(caplog):
    middleware = IncomingLoggingMiddleware()
    update = _make_update("a" * 500)

    async def handler(event, data):
        return None

    with caplog.at_level(logging.INFO, logger="calobot.telegram.messages"):
        await middleware(handler, update, {})

    logged_line = [line for line in caplog.text.splitlines() if "text=" in line][0]
    assert len(logged_line) < 500 + 50


async def test_outgoing_middleware_logs_send_message(caplog):
    middleware = OutgoingLoggingMiddleware()
    method = SendMessage(chat_id=42, text="Registrato: noci 10g - 65 kcal")

    async def make_request(bot, method):
        return "sent"

    with caplog.at_level(logging.INFO, logger="calobot.telegram.messages"):
        result = await middleware(make_request, bot=None, method=method)

    assert result == "sent"
    assert "method=sendMessage" in caplog.text
    assert "chat=42" in caplog.text
    assert "Registrato" in caplog.text


async def test_outgoing_middleware_logs_send_photo_without_binary_content(caplog):
    from aiogram.types import BufferedInputFile

    middleware = OutgoingLoggingMiddleware()
    photo = BufferedInputFile(b"\x89PNG", filename="report.png")
    method = SendPhoto(chat_id=42, photo=photo, caption="Report settimanale")

    async def make_request(bot, method):
        return "sent"

    with caplog.at_level(logging.INFO, logger="calobot.telegram.messages"):
        await middleware(make_request, bot=None, method=method)

    assert "method=sendPhoto" in caplog.text
    assert "Report settimanale" in caplog.text
    assert "PNG" not in caplog.text  # binary content itself is never logged


async def test_outgoing_middleware_handles_methods_without_chat_id(caplog):
    middleware = OutgoingLoggingMiddleware()
    method = AnswerCallbackQuery(callback_query_id="abc", text="Eliminata.")

    async def make_request(bot, method):
        return "ok"

    with caplog.at_level(logging.INFO, logger="calobot.telegram.messages"):
        await middleware(make_request, bot=None, method=method)

    assert "method=answerCallbackQuery" in caplog.text


async def test_outgoing_middleware_does_not_log_a_successful_poll(caplog):
    """getUpdates is long polling's own request, reissued continuously with nothing
    chat-specific to say - logging it on every successful poll is pure noise."""
    middleware = OutgoingLoggingMiddleware()
    method = GetUpdates()

    async def make_request(bot, method):
        return []

    with caplog.at_level(logging.INFO, logger="calobot.telegram.messages"):
        result = await middleware(make_request, bot=None, method=method)

    assert result == []
    assert caplog.text == ""


async def test_outgoing_middleware_logs_a_failed_poll(caplog):
    middleware = OutgoingLoggingMiddleware()
    method = GetUpdates()

    async def make_request(bot, method):
        raise RuntimeError("network unreachable")

    with caplog.at_level(logging.INFO, logger="calobot.telegram.messages"):
        with pytest.raises(RuntimeError, match="network unreachable"):
            await middleware(make_request, bot=None, method=method)

    assert "method=getUpdates" in caplog.text
    assert "failed" in caplog.text
