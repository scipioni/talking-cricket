"""Logs every Telegram update pulled in and every Bot API call pushed out, at the
framework boundary rather than scattered across handlers - so no send/receive path
can silently go unlogged, including ones added later.

Registered once in main.py: IncomingLoggingMiddleware on the dispatcher's update
observer (before routing), OutgoingLoggingMiddleware on the bot's session (wraps
every outbound API call: send_message, send_photo, answer_callback_query, ...).
"""

from __future__ import annotations

import datetime as dt
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware, Bot
from aiogram.client.session.middlewares.base import BaseRequestMiddleware, NextRequestMiddlewareType
from aiogram.methods import TelegramMethod
from aiogram.methods.base import TelegramType
from aiogram.types import TelegramObject, Update

from calobot.telemetry.bus import event_bus
from calobot.telemetry.context import bind_telemetry_context

logger = logging.getLogger("calobot.telegram.messages")

PREVIEW_LENGTH = 200


def _truncate(text: str | None) -> str:
    if not text:
        return ""
    text = text.replace("\n", " ")
    return text if len(text) <= PREVIEW_LENGTH else text[:PREVIEW_LENGTH] + "…"


def _extract_chat_id(update: Update) -> int | None:
    if update.message is not None:
        return update.message.chat.id
    if update.callback_query is not None:
        if update.callback_query.message is not None:
            return update.callback_query.message.chat.id
        return update.callback_query.from_user.id
    if update.edited_message is not None:
        return update.edited_message.chat.id
    return None


class IncomingLoggingMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if isinstance(event, Update):
            self._log_update(event)
            chat_id = _extract_chat_id(event)
            if chat_id is not None:
                # Build telemetry event payload
                payload: dict[str, Any] = {
                    "type": "incoming_update",
                    "chat_id": chat_id,
                    "timestamp": dt.datetime.now(dt.UTC).isoformat(),
                    "update_id": event.update_id,
                }
                if event.message is not None:
                    payload["text"] = event.message.text or ""
                    payload["has_image"] = bool(event.message.photo)
                    payload["username"] = (
                        event.message.from_user.username if event.message.from_user else None
                    )
                elif event.callback_query is not None:
                    payload["callback_data"] = event.callback_query.data
                    payload["username"] = (
                        event.callback_query.from_user.username if event.callback_query.from_user else None
                    )

                event_bus.publish(payload)

                with bind_telemetry_context(chat_id):
                    return await handler(event, data)

        return await handler(event, data)

    @staticmethod
    def _log_update(update: Update) -> None:
        if update.message is not None:
            msg = update.message
            user_id = msg.from_user.id if msg.from_user else None
            if msg.text:
                content = f'text="{_truncate(msg.text)}"'
            elif msg.photo:
                content = "photo"
            else:
                content = "other"
            logger.info(
                "IN  update=%s chat=%s user=%s %s", update.update_id, msg.chat.id, user_id, content
            )
        elif update.callback_query is not None:
            cq = update.callback_query
            chat_id = cq.message.chat.id if cq.message else None
            logger.info(
                "IN  update=%s chat=%s user=%s callback_data=%r",
                update.update_id,
                chat_id,
                cq.from_user.id,
                cq.data,
            )
        else:
            logger.info("IN  update=%s type=%s", update.update_id, update.event_type)


class OutgoingLoggingMiddleware(BaseRequestMiddleware):
    async def __call__(
        self,
        make_request: NextRequestMiddlewareType[TelegramType],
        bot: Bot,
        method: TelegramMethod[TelegramType],
    ) -> Any:
        self._log_request(method)

        chat_id = getattr(method, "chat_id", None)
        try:
            if chat_id is not None:
                chat_id = int(chat_id)
        except (ValueError, TypeError):
            pass

        if chat_id is None:
            from calobot.telemetry.context import active_chat_id

            chat_id = active_chat_id.get(None)

        if chat_id is not None:
            options: dict[str, str] = {}
            reply_markup = getattr(method, "reply_markup", None)
            from aiogram.types import InlineKeyboardMarkup

            if isinstance(reply_markup, InlineKeyboardMarkup):
                options = {
                    button.text: button.callback_data
                    for row in reply_markup.inline_keyboard
                    for button in row
                    if button.callback_data is not None
                }

            text = getattr(method, "text", None) or getattr(method, "caption", None) or ""
            api_method = getattr(method, "__api_method__", type(method).__name__)

            payload: dict[str, Any] = {
                "type": "outgoing_response",
                "chat_id": chat_id,
                "timestamp": dt.datetime.now(dt.UTC).isoformat(),
                "method": api_method,
                "text": text,
                "options": options,
                "has_image": "Photo" in api_method,
            }
            event_bus.publish(payload)

        return await make_request(bot, method)

    @staticmethod
    def _log_request(method: TelegramMethod[Any]) -> None:
        api_method = getattr(method, "__api_method__", type(method).__name__)
        chat_id = getattr(method, "chat_id", None)
        content = _truncate(getattr(method, "text", None) or getattr(method, "caption", None))
        logger.info("OUT method=%s chat=%s %s", api_method, chat_id, f'text="{content}"' if content else "")
