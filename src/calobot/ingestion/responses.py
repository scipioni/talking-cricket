"""What a pipeline step wants to say back. The telegram layer translates this into
actual Bot API calls (message + optional inline keyboard + optional photo + optional
entry reference for attaching modify/delete controls)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

EntryKind = Literal["food", "activity", "weight"]


@dataclass(frozen=True)
class OutgoingMessage:
    text: str
    buttons: list[str] = field(default_factory=list)
    photo_png: bytes | None = None
    # Set when this message confirms a stored entry, so the telegram layer can
    # attach modify/delete controls and record confirmation_message_id
    # (specs/entry-correction - Deterministic targeting of an entry).
    entry_ref: tuple[EntryKind, int] | None = None
