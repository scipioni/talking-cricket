"""Logs every Telegram update pulled in and every Bot API call pushed out, at the
framework boundary rather than scattered across handlers - so no send/receive path
can silently go unlogged, including ones added later.

Registered once in main.py: IncomingLoggingMiddleware on the dispatcher's update
observer (before routing), OutgoingLoggingMiddleware on the bot's session (wraps
every outbound API call: send_message, send_photo, answer_callback_query, ...).
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware, Bot
from aiogram.client.session.middlewares.base import BaseRequestMiddleware, NextRequestMiddlewareType
from aiogram.methods import TelegramMethod
from aiogram.methods.base import TelegramType
from aiogram.types import TelegramObject, Update

logger = logging.getLogger("calobot.telegram.messages")

PREVIEW_LENGTH = 200


def _truncate(text: str | None) -> str:
    if not text:
        return ""
    text = text.replace("\n", " ")
    return text if len(text) <= PREVIEW_LENGTH else text[:PREVIEW_LENGTH] + "…"


class IncomingLoggingMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if isinstance(event, Update):
            self._log_update(event)
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
        return await make_request(bot, method)

    @staticmethod
    def _log_request(method: TelegramMethod[Any]) -> None:
        api_method = getattr(method, "__api_method__", type(method).__name__)
        chat_id = getattr(method, "chat_id", None)
        content = _truncate(getattr(method, "text", None) or getattr(method, "caption", None))
        logger.info("OUT method=%s chat=%s %s", api_method, chat_id, f'text="{content}"' if content else "")
