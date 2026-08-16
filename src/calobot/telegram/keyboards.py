"""Inline keyboard helpers. Buttons are how the clarification loop stays one-tap
in the common case while still accepting free text (design.md - 'every clarification
offers the common answers as inline keyboard buttons... free text is always accepted
as an alternative')."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

CALLBACK_ANSWER_PREFIX = "ans:"
CALLBACK_ENTRY_PREFIX = "entry:"


def options_keyboard(options: list[str]) -> InlineKeyboardMarkup | None:
    if not options:
        return None
    buttons = [
        [InlineKeyboardButton(text=opt, callback_data=f"{CALLBACK_ANSWER_PREFIX}{opt}")]
        for opt in options
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def entry_controls_keyboard(kind: str, entry_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✏️ modifica", callback_data=f"{CALLBACK_ENTRY_PREFIX}modifica:{kind}:{entry_id}"
                ),
                InlineKeyboardButton(
                    text="🗑 elimina", callback_data=f"{CALLBACK_ENTRY_PREFIX}elimina:{kind}:{entry_id}"
                ),
            ]
        ]
    )
