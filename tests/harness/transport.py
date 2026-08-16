"""The outgoing half of the transport double: a Bot whose every API call is recorded
instead of sent (specs/test-transport - Faithful message identity, Observable
transcript, Options are addressed by their visible label).

Interception happens at `Bot.__call__`, which is the single funnel every outbound
call passes through - `bot.send_message(...)`, `message.answer(...)` and
`callback.answer()` all build a TelegramMethod and await it, and awaiting it calls
`bot(method)`. Overriding one method therefore catches all of them, with real
(pydantic-validated) method objects rather than mock recordings.

Deliberately a written class and not an AsyncMock: two behaviours here are
load-bearing and a mock cannot supply them - assigning identifiers that behave like
real message identifiers (production writes `sent.message_id` into the database as
the link between a confirmation and its entry), and reflecting a later keyboard
replacement onto the message it replaced (design.md - 'Drive the real handlers
through a written double').
"""

from __future__ import annotations

import datetime as dt
import io
from dataclasses import dataclass, field

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.methods import (
    AnswerCallbackQuery,
    EditMessageReplyMarkup,
    GetFile,
    SendChatAction,
    SendMessage,
    SendPhoto,
)
from aiogram.methods.base import TelegramMethod
from aiogram.types import Chat, File, InlineKeyboardMarkup, Message

# A syntactically valid token that could never be a real one. Nothing here ever
# reaches the network: Bot.__call__ is overridden below, and AiohttpSession creates
# its underlying connection lazily, so none is ever opened.
FAKE_TOKEN = "42:CALOBOT-TEST-TOKEN"

# Returned Message objects need a date. Production never reads it, so it is a
# constant rather than the wall clock, to keep transcripts byte-comparable.
_EPOCH = dt.datetime(2026, 1, 1, tzinfo=dt.UTC)


class UnsupportedApiCall(NotImplementedError):
    """The bot called a Telegram method the double does not emulate.

    Raised rather than silently returning a plausible value: the fidelity boundary
    is declared (specs/test-transport - Declared fidelity boundary), and a double
    that quietly fakes something outside it turns a passing run into a false one.
    """


@dataclass
class SentMessage:
    """One outgoing message as the user would perceive it.

    `text` carries the caption for messages that carried an image, which is what a
    user reads in both cases.
    """

    message_id: int
    chat_id: int
    text: str
    options: dict[str, str] = field(default_factory=dict)
    has_image: bool = False

    @property
    def labels(self) -> list[str]:
        return list(self.options)


def decode_options(reply_markup: object) -> dict[str, str]:
    """Turn an outgoing keyboard back into the label -> action data pairs a real
    client would hold, preserving the order the buttons were offered in."""
    if not isinstance(reply_markup, InlineKeyboardMarkup):
        return {}
    return {
        button.text: button.callback_data
        for row in reply_markup.inline_keyboard
        for button in row
        if button.callback_data is not None
    }


class FakeBot(Bot):
    def __init__(self) -> None:
        # Mirrors production's construction (main.py) so that anything depending on
        # default bot properties behaves the same here.
        super().__init__(
            token=FAKE_TOKEN,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        )
        self.sent: list[SentMessage] = []
        self.chat_actions: list[str] = []
        self.answered_callbacks: list[str | None] = []
        self._staged_files: dict[str, bytes] = {}
        self._last_message_id = 1000

    # -- identity ---------------------------------------------------------

    def next_message_id(self) -> int:
        """Message identifiers are unique across the whole chat, incoming and
        outgoing alike, exactly as Telegram numbers them - so a reply can target
        either and no two ever collide."""
        self._last_message_id += 1
        return self._last_message_id

    # -- transcript -------------------------------------------------------

    @property
    def last(self) -> SentMessage:
        if not self.sent:
            raise AssertionError("the bot has sent nothing")
        return self.sent[-1]

    def message(self, message_id: int) -> SentMessage:
        for sent in self.sent:
            if sent.message_id == message_id:
                return sent
        raise AssertionError(f"no message with id {message_id} was sent")

    def find_option(self, label: str, *, on: int | None = None) -> tuple[SentMessage, str] | None:
        """Locate an offered option by the label a user would read.

        Searches most recent first, so a scenario that just taps a label gets the
        current keyboard. `on` pins the search to one message, which is how a
        scenario deliberately taps a superseded keyboard.
        """
        candidates = self.sent if on is None else [self.message(on)]
        for sent in reversed(candidates):
            if label in sent.options:
                return sent, sent.options[label]
        return None

    def staged_file_bytes(self, file_id: str) -> bytes:
        return self._staged_files[file_id]

    def stage_file(self, file_id: str, data: bytes) -> None:
        """Make bytes retrievable through the get-file / download-file pair, which is
        how the photo handler obtains an image."""
        self._staged_files[file_id] = data

    # -- interception -----------------------------------------------------

    async def __call__(self, method: TelegramMethod, request_timeout: int | None = None):  # type: ignore[override]
        if isinstance(method, SendMessage):
            return self._record(method.chat_id, method.text, method.reply_markup, has_image=False)

        if isinstance(method, SendPhoto):
            return self._record(
                method.chat_id, method.caption or "", method.reply_markup, has_image=True
            )

        if isinstance(method, EditMessageReplyMarkup):
            return self._replace_options(method.message_id, method.reply_markup)

        if isinstance(method, SendChatAction):
            self.chat_actions.append(method.action)
            return True

        if isinstance(method, AnswerCallbackQuery):
            self.answered_callbacks.append(method.text)
            return True

        if isinstance(method, GetFile):
            return File(
                file_id=method.file_id,
                file_unique_id=method.file_id,
                file_path=f"staged/{method.file_id}",
            )

        raise UnsupportedApiCall(
            f"{type(method).__name__} is outside the transport double's fidelity boundary"
        )

    async def download_file(self, file_path: str, *args, **kwargs) -> io.BytesIO:  # type: ignore[override]
        """Not a TelegramMethod - Bot.download_file reaches for the session directly,
        so it needs its own override rather than being caught by __call__."""
        file_id = file_path.removeprefix("staged/")
        if file_id not in self._staged_files:
            raise UnsupportedApiCall(f"no file staged for {file_path!r}")
        return io.BytesIO(self._staged_files[file_id])

    # -- recording --------------------------------------------------------

    def _record(self, chat_id, text: str, reply_markup, *, has_image: bool) -> Message:
        message_id = self.next_message_id()
        self.sent.append(
            SentMessage(
                message_id=message_id,
                chat_id=int(chat_id),
                text=text,
                options=decode_options(reply_markup),
                has_image=has_image,
            )
        )
        return Message(
            message_id=message_id,
            date=_EPOCH,
            chat=Chat(id=int(chat_id), type="private"),
            caption=text if has_image else None,
            text=None if has_image else text,
        ).as_(self)

    def _replace_options(self, message_id: int | None, reply_markup) -> bool:
        """A keyboard swapped onto an already-sent message replaces what that message
        offers, so the transcript shows what the user is looking at now rather than
        what was first sent (specs/test-transport - Observable transcript)."""
        if message_id is None:
            raise UnsupportedApiCall("editing a message without an identifier is not emulated")
        self.message(message_id).options = decode_options(reply_markup)
        return True
