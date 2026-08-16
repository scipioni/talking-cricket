"""Recording and replay (specs/conversation-simulation - Recording and replay).

A live run is expensive and non-deterministic, which makes it terrible input for an
agent trying to fix what it found: the agent cannot tell whether its change worked or
the dice rolled differently. So a live run records every model exchange, and the same
conversation replays against that recording for free and identically.

Responses are keyed by *position and request fingerprint*, not by request hash alone.
Order-independent lookup would hide a change in the number of model calls, which is
one of the most consequential things that can happen in this pipeline - the existing
suite is brittle for exactly that reason, and the fix is to make the divergence loud
rather than to make it invisible.

The honest limitation, stated here because it decides how a recording may be used: a
recording verifies fixes to *code*, not to *prompts*. Changing a prompt changes the
fingerprint and invalidates the recording, because the recorded reply was produced by
the old one.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from calobot.llm.gateway import LLMGateway


class Divergence(AssertionError):
    """The code under test made a different model call than the one recorded."""


class CallCapReached(AssertionError):
    """The scenario exhausted its model call budget and was stopped."""


def fingerprint(kwargs: dict[str, Any]) -> str:
    """Identifies a request by what actually determines the answer: the model, the
    conversation sent to it, and the schema demanded back."""
    schema = kwargs.get("response_format", {}).get("json_schema", {}).get("name")
    payload = json.dumps(
        {"model": kwargs.get("model"), "messages": kwargs.get("messages"), "schema": schema},
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


@dataclass
class Exchange:
    index: int
    fingerprint: str
    step: str | None
    response: str

    def to_json(self) -> str:
        return json.dumps(
            {
                "index": self.index,
                "fingerprint": self.fingerprint,
                "step": self.step,
                "response": self.response,
            },
            ensure_ascii=False,
        )

    @classmethod
    def from_json(cls, line: str) -> Exchange:
        data = json.loads(line)
        return cls(
            index=data["index"],
            fingerprint=data["fingerprint"],
            step=data.get("step"),
            response=data["response"],
        )


def _as_response(content: str) -> Any:
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


class Cassette:
    def __init__(self, exchanges: list[Exchange] | None = None) -> None:
        self.exchanges: list[Exchange] = exchanges or []

    def save(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(exchange.to_json() for exchange in self.exchanges))
        return path

    @classmethod
    def load(cls, path: Path) -> Cassette:
        lines = [line for line in path.read_text().splitlines() if line.strip()]
        return cls([Exchange.from_json(line) for line in lines])

    def __len__(self) -> int:
        return len(self.exchanges)


class Recorder:
    """Wraps a gateway so every exchange is captured on its way past."""

    def __init__(self, gateway: LLMGateway, *, call_cap: int = 400) -> None:
        self.gateway = gateway
        self.cassette = Cassette()
        self.call_cap = call_cap
        self._original = gateway._client.chat.completions.create
        gateway._client.chat.completions.create = self._create  # type: ignore[method-assign]

    async def _create(self, **kwargs: Any) -> Any:
        if len(self.cassette) >= self.call_cap:
            # The partial recording is kept: whatever was learned before the budget
            # ran out is still worth replaying.
            raise CallCapReached(
                f"the scenario reached its cap of {self.call_cap} model calls; "
                f"{len(self.cassette)} exchanges recorded"
            )
        response = await self._original(**kwargs)
        content = response.choices[0].message.content or ""
        self.cassette.exchanges.append(
            Exchange(
                index=len(self.cassette),
                fingerprint=fingerprint(kwargs),
                step=_step_name(kwargs),
                response=content,
            )
        )
        return response


class Player:
    """Replays a recording, refusing to guess when the code has moved on."""

    def __init__(self, gateway: LLMGateway, cassette: Cassette) -> None:
        self.gateway = gateway
        self.cassette = cassette
        self.position = 0
        gateway._client.chat.completions.create = self._create  # type: ignore[method-assign]

    async def _create(self, **kwargs: Any) -> Any:
        if self.position >= len(self.cassette):
            raise Divergence(
                f"the code made model call #{self.position + 1}, but the recording holds "
                f"only {len(self.cassette)}: the call sequence has changed"
            )
        recorded = self.cassette.exchanges[self.position]
        actual = fingerprint(kwargs)
        if actual != recorded.fingerprint:
            raise Divergence(
                f"model call #{self.position + 1} diverges from the recording: recorded "
                f"{recorded.step or 'unknown step'} ({recorded.fingerprint}), got "
                f"{_step_name(kwargs) or 'unknown step'} ({actual}). A recording cannot "
                "verify a change that alters how the model is called."
            )
        self.position += 1
        return _as_response(recorded.response)

    def assert_fully_consumed(self) -> None:
        if self.position != len(self.cassette):
            raise Divergence(
                f"the replay used {self.position} of {len(self.cassette)} recorded "
                "exchanges: the code made fewer model calls than the recording holds"
            )


def _step_name(kwargs: dict[str, Any]) -> str | None:
    return kwargs.get("response_format", {}).get("json_schema", {}).get("name")
