"""A scripted stand-in for the language model, shared by every test that drives the
bot through the transport double.

Responses are held in a queue that can be appended to at any point, rather than
fixed as an ordered `side_effect` list at construction time. The queue is still
consumed in order - the model is genuinely called in a fixed sequence - but a test
can stage the next leg of a conversation after reading what the bot just asked,
which is what driving a multi-turn scenario requires.

Interception is at the OpenAI client, not at the gateway, so the real gateway runs:
schema validation, the retry-with-error-fed-back loop, and the mapping of transport
failures onto the two typed errors are all exercised rather than bypassed.
"""

from __future__ import annotations

import json
from collections import deque
from types import SimpleNamespace
from typing import Any

from calobot.llm.gateway import LLMGateway
from calobot.settings import Settings


class NoScriptedResponse(AssertionError):
    """The bot made a model call the test did not stage.

    Surfaced as a failure rather than an empty response, because an unexpected extra
    call is exactly the kind of change that matters in this pipeline.
    """


class ScriptedLLM:
    def __init__(self, settings: Settings) -> None:
        self.gateway = LLMGateway(settings)
        self.pending: deque[Any] = deque()
        self.calls: list[dict[str, Any]] = []
        self.gateway._client.chat.completions.create = self._create  # type: ignore[method-assign]

    def push(self, *payloads: Any) -> ScriptedLLM:
        """Stage one or more responses. A dict is returned as JSON; an exception
        instance is raised instead, which is how transport failures are staged."""
        self.pending.extend(payloads)
        return self

    async def _create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if not self.pending:
            raise NoScriptedResponse(
                f"the bot made an unstaged model call (call #{len(self.calls)}); "
                f"{len(self.calls) - 1} were staged"
            )
        payload = self.pending.popleft()
        if isinstance(payload, BaseException):
            raise payload
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))]
        )

    def install(self, monkeypatch) -> ScriptedLLM:
        """Make the handlers use this gateway. They construct one per message from
        settings, so the factory is the injection point."""
        monkeypatch.setattr("calobot.telegram.handlers._gateway", lambda _settings: self.gateway)
        return self
