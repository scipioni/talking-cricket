"""Typed LLM errors. See specs/message-ingestion - Language model invocation contract:
no raw model output, exception text or stack trace may ever reach a chat reply, so the
bot layer matches on these types and picks a fixed, pre-written user-facing message."""

from __future__ import annotations


class LLMError(Exception):
    """Base class for all gateway failures. Never str()'d into a user-facing message."""


class LLMUnavailableError(LLMError):
    """The endpoint could not be reached or timed out."""


class LLMValidationExhaustedError(LLMError):
    """The model never produced schema-valid output within the retry limit."""
