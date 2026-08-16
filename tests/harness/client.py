"""The inbound half of the transport double: everything a user can do, delivered
through the production dispatcher (specs/test-transport - Every inbound user action
is reachable).

Actions are fed to a real `Dispatcher` holding the real `router`, so aiogram's own
filters decide which handler serves each one - a command is recognised as a command
and a tap is routed by its action data, rather than the harness deciding on the
bot's behalf. `Dispatcher.feed_update` propagates handler exceptions (the swallowing
happens in `_process_update`, which only long polling uses), so a handler that
raises fails the test loudly.
"""

from __future__ import annotations

import datetime as dt

from aiogram import Dispatcher
from aiogram.types import CallbackQuery, Chat, Message, PhotoSize, Update
from aiogram.types import User as TgUser

from calobot.settings import Settings
from calobot.telegram.handlers import router

from .transport import FakeBot, SentMessage

_EPOCH = dt.datetime(2026, 1, 1, tzinfo=dt.UTC)

_dispatcher: Dispatcher | None = None


def _shared_dispatcher() -> Dispatcher:
    """One dispatcher per process. `router` is a module-level singleton and aiogram
    refuses to attach an already-attached router, so a dispatcher per Client would
    fail on the second one. Nothing is retained between updates - `settings` is
    passed per call - so sharing is safe."""
    global _dispatcher
    if _dispatcher is None:
        dispatcher = Dispatcher()
        dispatcher.include_router(router)
        _dispatcher = dispatcher
    return _dispatcher


class ScenarioError(AssertionError):
    """The scenario asked for something the user could not have done - for example
    tapping a label no message offers. A scenario error, not a bot failure."""


class Client:
    """One user in one private chat."""

    def __init__(
        self,
        bot: FakeBot,
        settings: Settings,
        *,
        telegram_user_id: int = 42,
        chat_id: int | None = None,
        first_name: str = "Utente",
    ) -> None:
        self.bot = bot
        self.settings = settings
        self.telegram_user_id = telegram_user_id
        self.chat_id = telegram_user_id if chat_id is None else chat_id
        self.first_name = first_name
        self._update_id = 0

    # -- transcript -------------------------------------------------------

    @property
    def inbox(self) -> list[SentMessage]:
        return self.bot.sent

    @property
    def last(self) -> SentMessage:
        return self.bot.last

    # -- actions ----------------------------------------------------------

    async def say(self, text: str, *, reply_to: SentMessage | int | None = None) -> list[SentMessage]:
        """Send a text message. A message whose text is a command is routed to the
        command handler by aiogram's own filters, exactly as in production."""
        return await self._feed_message(self._message(text=text, reply_to=reply_to))

    async def reply_to(self, target: SentMessage | int, text: str) -> list[SentMessage]:
        return await self.say(text, reply_to=target)

    async def send_photo(
        self, data: bytes = b"\x89PNG-fake", *, caption: str | None = None
    ) -> list[SentMessage]:
        file_id = f"photo-{self.bot.next_message_id()}"
        self.bot.stage_file(file_id, data)
        photo = [
            PhotoSize(file_id=f"{file_id}-small", file_unique_id=f"{file_id}-small", width=90, height=90),
            PhotoSize(file_id=file_id, file_unique_id=file_id, width=1280, height=1280),
        ]
        # Production takes the largest size, which is the last element.
        self.bot.stage_file(f"{file_id}-small", data)
        return await self._feed_message(self._message(photo=photo, caption=caption))

    async def tap(self, label: str, *, on: SentMessage | int | None = None) -> list[SentMessage]:
        """Tap an offered option by the label a user would read.

        `on` pins the tap to one message, which is how a scenario deliberately taps a
        superseded keyboard: the action is then delivered faithfully, and how the bot
        copes with a stale tap is what is being observed.
        """
        pinned = on.message_id if isinstance(on, SentMessage) else on
        found = self.bot.find_option(label, on=pinned)
        if found is None:
            offered = sorted({lbl for sent in self.bot.sent for lbl in sent.options})
            raise ScenarioError(
                f"no message offers the option {label!r}; currently offered: {offered}"
            )
        origin, action_data = found
        callback = CallbackQuery(
            id=str(self._next_update_id()),
            from_user=self._from_user(),
            chat_instance=f"chat-{self.chat_id}",
            data=action_data,
            message=Message(
                message_id=origin.message_id,
                date=_EPOCH,
                chat=Chat(id=self.chat_id, type="private"),
                text=origin.text or None,
            ).as_(self.bot),
        ).as_(self.bot)
        return await self._feed(Update(update_id=self._next_update_id(), callback_query=callback))

    # -- named commands ---------------------------------------------------

    async def start(self) -> list[SentMessage]:
        return await self.say("/start")

    async def undo(self) -> list[SentMessage]:
        return await self.say("/annulla")

    async def profile(self) -> list[SentMessage]:
        return await self.say("/profilo")

    async def delete_me(self) -> list[SentMessage]:
        return await self.say("/cancellami")

    # -- plumbing ---------------------------------------------------------

    def _next_update_id(self) -> int:
        self._update_id += 1
        return self._update_id

    def _from_user(self) -> TgUser:
        return TgUser(id=self.telegram_user_id, is_bot=False, first_name=self.first_name)

    def _message(
        self,
        *,
        text: str | None = None,
        photo: list[PhotoSize] | None = None,
        caption: str | None = None,
        reply_to: SentMessage | int | None = None,
    ) -> Message:
        replied_to = None
        if reply_to is not None:
            target_id = reply_to.message_id if isinstance(reply_to, SentMessage) else reply_to
            replied_to = Message(
                message_id=target_id,
                date=_EPOCH,
                chat=Chat(id=self.chat_id, type="private"),
            ).as_(self.bot)
        return Message(
            message_id=self.bot.next_message_id(),
            date=_EPOCH,
            chat=Chat(id=self.chat_id, type="private"),
            from_user=self._from_user(),
            text=text,
            photo=photo,
            caption=caption,
            reply_to_message=replied_to,
        ).as_(self.bot)

    async def _feed_message(self, message: Message) -> list[SentMessage]:
        return await self._feed(Update(update_id=self._next_update_id(), message=message))

    async def _feed(self, update: Update) -> list[SentMessage]:
        before = len(self.bot.sent)
        # Mounting the update to the bot avoids aiogram's JSON round-trip re-creation
        # of the whole update, which would drop the bot binding on nested objects.
        await _shared_dispatcher().feed_update(self.bot, update.as_(self.bot), settings=self.settings)
        return self.bot.sent[before:]
