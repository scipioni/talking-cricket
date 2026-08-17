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
    # A separately-downscaled, typically higher-resolution rendering of the same
    # photo, used only for label reading (tasks.md 1.2 - the resolution is
    # "separately configurable for labels"): small print needs more legibility
    # headroom than classification or dish recognition do. Falls back to
    # base64_data when absent, e.g. in tests that construct ImageContent directly.
    label_base64_data: str | None = None


MessageContent = TextContent | ImageContent
