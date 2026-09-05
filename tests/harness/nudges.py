"""Nudges inside a time-lapse run: recognising what the cycle originated, driving it
at the execution points a scenario's timeline crosses, keeping the run's timeline of
sends and preference changes, and checking the temporal invariants over them
(specs/conversation-simulation - Scheduled jobs run as simulated time advances,
Temporal invariants over originated messages).

Design decisions this implements (time-lapse-simulation/design.md): execution points
are computed arithmetically and the job body is invoked directly (the scheduler loop
has no clock seam); nudges are identified only by their observable surface - the
stop keyboard and the fixed template wording - never by plumbing added to product
code; the two invariants that need history the database does not keep are checked
over the timeline the run records itself.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from typing import Literal
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from calobot.nudges.messages import _TEMPLATES
from calobot.nudges.service import run_nudge_cycle
from calobot.persistence.models import AdviceOutcome, AdviceRecord, User
from calobot.settings import Settings
from calobot.telegram.keyboards import CALLBACK_NUDGE_STOP
from calobot.telemetry.context import no_retention_chats

from .invariants import Violation
from .transport import SentMessage

JOB_NAME = "proactive_nudges"

# The stop keyboard is what makes an outgoing message a nudge as far as a user can
# tell; any message offering it is one, whatever its text.
def _is_nudge(message: SentMessage, *, chat_id: int) -> bool:
    return message.chat_id == chat_id and CALLBACK_NUDGE_STOP in message.options.values()


def _kind_prefixes() -> dict[str, str]:
    """Kind -> the stable prefix of its template, cut at the first placeholder so a
    composed tip (interpolated into unresolved_suggestion) still matches. The
    coupling to template wording is deliberate and loud: a wording change makes
    recognition fail into 'unrecognised', which fails expectations visibly rather
    than misclassifying silently (design.md - Decisions)."""
    return {kind: template.split("{")[0] for kind, template in _TEMPLATES.items()}


def recognise_nudge(message: SentMessage, *, chat_id: int) -> str | None:
    """The nudge's kind, or None when the message is not a nudge at all. A message
    carrying the stop keyboard whose text matches no known template comes back as
    'unrecognised' - a template changed and this file did not follow."""
    if not _is_nudge(message, chat_id=chat_id):
        return None
    for kind, prefix in _kind_prefixes().items():
        if message.text.startswith(prefix):
            return kind
    return "unrecognised"


def execution_points(
    origin: dt.datetime, to: dt.datetime, interval_seconds: float
) -> list[dt.datetime]:
    """The job's execution instants in (origin, to], on the grid the run's origin
    defines - the same instants the real scheduler would fire on, minus the origin
    itself, since a job is first due one interval after it starts."""
    points: list[dt.datetime] = []
    moment = origin + dt.timedelta(seconds=interval_seconds)
    step = dt.timedelta(seconds=interval_seconds)
    while moment <= to:
        points.append(moment)
        moment += step
    return points


# -- the run's timeline ---------------------------------------------------


@dataclass(frozen=True)
class NudgeSend:
    instant: dt.datetime
    kind: str
    text: str


@dataclass(frozen=True)
class FlagChange:
    """A preference the user (or no-retention mode) turned over at some point in the
    run. Recorded by diffing state, so the instant is when the run observed the
    change, not necessarily the exact transition - close enough to order it against
    sends, which is all the invariants need."""

    instant: dt.datetime
    name: Literal["nudges", "no_retention"]
    value: bool


@dataclass(frozen=True)
class CycleExecution:
    instant: dt.datetime
    job: str
    messages: tuple[SentMessage, ...]


TimelineEvent = NudgeSend | FlagChange


class NudgeWatch:
    """Drives the cycle as simulated time advances and remembers everything it and
    the conversation did to the nudge state."""

    def __init__(self, bot, settings: Settings, *, chat_id: int) -> None:
        self.bot = bot
        self.settings = settings
        self.chat_id = chat_id
        self.interval = dt.timedelta(seconds=settings.nudge_check_interval_seconds)
        self._next: dt.datetime | None = None
        self.executions: list[CycleExecution] = []
        self.events: list[TimelineEvent] = []
        self._enabled: bool | None = None
        self._no_retention: bool | None = None

    # -- driving ----------------------------------------------------------

    async def mark_origin(self, session: AsyncSession, user_id: int, origin: dt.datetime) -> None:
        """Anchor the execution grid to the run's start and record the preferences
        the user has before anything runs, so a send can be judged against the state
        that preceded it."""
        self._next = origin + self.interval
        await self.observe(session, user_id, origin)

    async def run_due(
        self,
        to: dt.datetime,
        *,
        clock,
        restore_to: dt.datetime,
        session: AsyncSession,
        user_id: int,
    ) -> list[CycleExecution]:
        """Run every execution point up to `to`, each at its own instant so every
        read of 'now' inside the cycle observes it, then put the clock back where the
        scenario is. Returns the executions that ran (possibly none)."""
        if self._next is None:
            raise AssertionError("mark_origin was never called")
        executed: list[CycleExecution] = []
        while self._next <= to:
            point = self._next
            clock.set(point)
            before = len(self.bot.sent)
            await run_nudge_cycle(self.bot, self.settings)
            messages = tuple(self.bot.sent[before:])
            execution = CycleExecution(instant=point, job=JOB_NAME, messages=messages)
            self.executions.append(execution)
            executed.append(execution)
            for message in messages:
                kind = recognise_nudge(message, chat_id=self.chat_id) or "unrecognised"
                self.events.append(NudgeSend(instant=point, kind=kind, text=message.text))
            await self.observe(session, user_id, point)
            self._next += self.interval
        clock.set(restore_to)
        return executed

    # -- observation ------------------------------------------------------

    async def observe(self, session: AsyncSession, user_id: int, instant: dt.datetime) -> None:
        """Diff the user's nudge preference and the no-retention set into the
        timeline, so enable/opt-out/no-retention events and sends share one
        ordering. The first observation is recorded too: a send is judged against
        the state the run started with, which must be visible in the timeline
        rather than implicit."""
        session.expire_all()
        user = await session.get(User, user_id)
        if user is None:
            return
        enabled = bool(user.nudges_enabled)
        if self._enabled is None or enabled != self._enabled:
            self.events.append(FlagChange(instant=instant, name="nudges", value=enabled))
            self._enabled = enabled
        no_retention = user.telegram_user_id in no_retention_chats
        if self._no_retention is None or no_retention != self._no_retention:
            self.events.append(
                FlagChange(instant=instant, name="no_retention", value=no_retention)
            )
            self._no_retention = no_retention

    # -- querying ---------------------------------------------------------

    @property
    def sends(self) -> list[NudgeSend]:
        return [event for event in self.events if isinstance(event, NudgeSend)]

    def state_at(self, instant: dt.datetime, name: Literal["nudges", "no_retention"]) -> bool:
        """The last value a flag of this name held at `instant`, from the timeline.
        False when nothing had been observed yet - the safe reading, since a send
        before any observation is unexplained by definition."""
        value: bool | None = None
        for event in self.events:
            if isinstance(event, FlagChange) and event.name == name and event.instant <= instant:
                value = event.value
        return value if value is not None else False

    # -- invariants -------------------------------------------------------

    async def check(self, session: AsyncSession, user_id: int, tz: ZoneInfo) -> list[Violation]:
        """The temporal invariants (specs/conversation-simulation - Temporal
        invariants over originated messages). Deliberately independent of the
        production guards: the quiet-hours window is re-implemented here, as the
        existing invariants re-implement the claim detection, so a shared blind spot
        cannot silence both."""
        sends = self.sends
        violations: list[Violation] = []

        window = dt.timedelta(days=self.settings.nudge_min_interval_days)
        # a sliding pairwise window, so a lone send is simply not compared
        for earlier, later in zip(sends, sends[1:], strict=False):
            if later.instant - earlier.instant < window:
                violations.append(
                    Violation(
                        "nudge rate window violated",
                        f"a {earlier.kind} nudge at {earlier.instant.isoformat()} and a "
                        f"{later.kind} nudge at {later.instant.isoformat()} are less than "
                        f"{self.settings.nudge_min_interval_days} days apart",
                    )
                )

        start, end = (
            self.settings.nudge_quiet_hours_start,
            self.settings.nudge_quiet_hours_end,
        )
        for send in sends:
            hour = send.instant.astimezone(tz).hour
            in_quiet = (start <= hour < end) if start <= end else (hour >= start or hour < end)
            if in_quiet:
                violations.append(
                    Violation(
                        "nudge sent during quiet hours",
                        f"the {send.kind} nudge at {send.instant.astimezone(tz).isoformat()} "
                        f"({tz.key}) falls inside the quiet-hours window "
                        f"{start:02d}:00-{end:02d}:00",
                    )
                )

        for send in sends:
            if not self.state_at(send.instant, "nudges"):
                violations.append(
                    Violation(
                        "nudge sent while nudges were disabled",
                        f"the {send.kind} nudge at {send.instant.isoformat()} reached a "
                        "user whose nudges were not enabled at that point in the run",
                    )
                )
            if self.state_at(send.instant, "no_retention"):
                violations.append(
                    Violation(
                        "nudge sent while no-retention was on",
                        f"the {send.kind} nudge at {send.instant.isoformat()} was sent "
                        "while the chat was in no-retention mode",
                    )
                )

        violations.extend(await self._resolved_suggestion_violations(session, user_id, sends))
        return violations

    _TIP = re.compile(r'Qualche giorno fa ti avevo dato un consiglio: "(.+)"\.')

    async def _resolved_suggestion_violations(
        self, session: AsyncSession, user_id: int, sends: list[NudgeSend]
    ) -> list[Violation]:
        """A nudge may reference prior advice only while that advice is unresolved
        (specs/proactive-nudges, via advice-memory's outcome states)."""
        from sqlalchemy import select

        violations: list[Violation] = []
        for send in sends:
            if send.kind != "unresolved_suggestion":
                continue
            match = self._TIP.search(send.text)
            if match is None:
                continue
            result = await session.execute(
                select(AdviceRecord).where(
                    AdviceRecord.user_id == user_id,
                    AdviceRecord.content == match.group(1),
                )
            )
            records = list(result.scalars())
            if records and all(record.outcome != AdviceOutcome.undetermined for record in records):
                violations.append(
                    Violation(
                        "nudge about a resolved suggestion",
                        f"the nudge at {send.instant.isoformat()} quotes advice whose "
                        "recorded outcome is "
                        f"{records[0].outcome.value}, not undetermined",
                    )
                )
        return violations
