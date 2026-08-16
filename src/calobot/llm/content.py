"""Message content types. A union from day one so image input needs no restructuring
later (design.md - 'The extraction interface takes text | image from day one')."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TextContent:
    text: str


@dataclass(frozen=True)
class ImageContent:
    base64_data: str
    mime_type: str = "image/jpeg"
    caption: str | None = None


MessageContent = TextContent | ImageContent
