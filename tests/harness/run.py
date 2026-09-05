"""A conversation with the invariants watching it.

Wraps a Client so that every action is followed by an invariant sweep, a progress
check and a budget check, each attributed to the action that triggered it
(specs/conversation-simulation - Hard invariants are checked after every action,
Conversations must make progress).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from calobot.persistence.models import ActivityEntry, FoodEntry, PendingDraft, WeightEntry
from calobot.persistence.repository import get_user_by_telegram_id
from calobot.persistence.timeutil import utcnow

from .client import Client
from .invariants import Violation, check_all, claims_something_was_recorded
from .transport import SentMessage

if TYPE_CHECKING:
    from .nudges import NudgeWatch

FailureKind = Literal["invariant", "false-confirmation", "no-progress", "action-cap"]

# How many consecutive actions may leave the conversation in exactly the same state
# before it counts as stuck. Two is a real retry; a third with nothing moving means
# the user has no way forward.
DEFAULT_PROGRESS_LIMIT = 3
DEFAULT_ACTION_CAP = 60

# Which failures end the run rather than being recorded and moved past.
#
# A corrupt database poisons everything computed after it, so the run stops and the
# report says where. A stuck conversation or a false confirmation are observations
# about one turn: continuing costs nothing and one run then surfaces every finding
# instead of only the earliest. Run 2 of marco-three-days stopped on day two and
# never reached the day-three steps, which is the cost of stopping on everything.
STOPPING_KINDS: frozenset[str] = frozenset({"invariant", "action-cap"})


@dataclass(frozen=True)
class Action:
    index: int
    description: str
    replies: list[SentMessage]


@dataclass(frozen=True)
class Failure:
    kind: FailureKind
    detail: str
    action_index: int
    action: str

    def __str__(self) -> str:
        return f"[{self.kind}] after action {self.action_index} ({self.action}): {self.detail}"


class RunStopped(AssertionError):
    """The run was stopped rather than allowed to continue: a hard invariant broke, the
    conversation stopped making progress, or the action budget ran out."""

    def __init__(self, failure: Failure) -> None:
        super().__init__(str(failure))
        self.failure = failure


@dataclass
class CheckedRun:
    client: Client
    session: AsyncSession
    tz: ZoneInfo
    progress_limit: int = DEFAULT_PROGRESS_LIMIT
    action_cap: int = DEFAULT_ACTION_CAP
    stopping_kinds: frozenset[str] = STOPPING_KINDS
    # Present when the scenario spans time: the watch drives the nudge cycle at
    # execution points and the temporal invariants run alongside the hard ones.
    nudges: NudgeWatch | None = None

    actions: list[Action] = field(default_factory=list)
    failures: list[Failure] = field(default_factory=list)
    _stalled_state: tuple | None = field(default=None, repr=False)
    _stalled_count: int = field(default=0, repr=False)

    # -- actions ----------------------------------------------------------

    # The action is passed as a factory, not as a coroutine: the budget is checked
    # before anything is created, so a run stopped at the cap does not leave an
    # un-awaited action behind.

    async def say(self, text: str, **kwargs) -> list[SentMessage]:
        return await self._perform(f"say {text!r}", lambda: self.client.say(text, **kwargs))

    async def tap(self, label: str, **kwargs) -> list[SentMessage]:
        return await self._perform(f"tap {label!r}", lambda: self.client.tap(label, **kwargs))

    async def reply_to(self, target, text: str) -> list[SentMessage]:
        return await self._perform(
            f"reply {text!r}", lambda: self.client.reply_to(target, text)
        )

    async def send_photo(self, data: bytes = b"fake", **kwargs) -> list[SentMessage]:
        return await self._perform(
            "send photo", lambda: self.client.send_photo(data, **kwargs)
        )

    async def start(self) -> list[SentMessage]:
        return await self._perform("/start", self.client.start)

    # -- checking ---------------------------------------------------------

    async def _perform(self, description: str, action) -> list[SentMessage]:
        index = len(self.actions) + 1
        if index > self.action_cap:
            self._fail(
                Failure(
                    "action-cap",
                    f"the scenario reached its cap of {self.action_cap} actions without completing",
                    index,
                    description,
                )
            )
            return []

        before = await self._entry_count()
        replies = await action()
        self.actions.append(Action(index=index, description=description, replies=list(replies)))

        await self._check_invariants(index, description)
        await self._check_confirmation_is_truthful(index, description, replies, before)
        await self._check_progress(index, description)
        return replies

    async def _check_confirmation_is_truthful(
        self, index: int, description: str, replies: list[SentMessage], before: int
    ) -> None:
        """A reply must not tell the user something was recorded when nothing was.

        Found by the first live run: a multi-intent message was classified as ordinary
        conversation, and the conversational reply invented "Ho registrato: cena, peso
        e attivita" while storing none of it - in the same turn as a notice saying part
        of the message had *not* been registered. Nothing downstream can detect this;
        the user simply believes their day is logged.
        """
        if await self._entry_count() > before:
            return
        for reply in replies:
            if claims_something_was_recorded(reply.text):
                self._fail(
                    Failure(
                        "false-confirmation",
                        f"the reply claims a record was made but nothing was stored: "
                        f"{reply.text!r}",
                        index,
                        description,
                    )
                )
                return

    async def _entry_count(self) -> int:
        user_id = await self._user_id()
        if user_id is None:
            return 0
        total = 0
        for model, when in (
            (FoodEntry, FoodEntry.deleted_at),
            (ActivityEntry, ActivityEntry.deleted_at),
            (WeightEntry, WeightEntry.deleted_at),
        ):
            result = await self.session.execute(
                select(func.count()).select_from(model).where(
                    model.user_id == user_id, when.is_(None)
                )
            )
            total += result.scalar_one()
        return total

    async def _check_invariants(self, index: int, description: str) -> None:
        user_id = await self._user_id()
        if user_id is None:
            return
        for violation in await check_all(self.session, user_id, self.tz):
            self._fail(Failure("invariant", str(violation), index, description))
        if self.nudges is not None:
            await self.nudges.observe(self.session, user_id, utcnow())
            await self.check_nudges_after_execution(index, description)

    async def check_nudges_after_execution(self, index: int, description: str) -> None:
        """The temporal invariants over originated messages, attributed to the action
        that just ran or the cycle execution that just ran - a violation fails the
        run regardless of what the step itself expected
        (specs/conversation-simulation - Temporal invariants over originated
        messages)."""
        if self.nudges is None:
            return
        user_id = await self._user_id()
        if user_id is None:
            return
        for violation in await self.nudges.check(self.session, user_id, self.tz):
            self._fail(Failure("invariant", str(violation), index, description))

    async def _check_progress(self, index: int, description: str) -> None:
        """A conversation that leaves the draft in exactly the same state, action after
        action, is asking the user for something they cannot supply. The bot will
        happily do this forever - the clarification loop re-asks with no attempt
        counter, and only draft expiry ends it."""
        state = await self._draft_state()
        if state is None:
            self._stalled_state, self._stalled_count = None, 0
            return
        if state == self._stalled_state:
            self._stalled_count += 1
        else:
            self._stalled_state, self._stalled_count = state, 1

        if self._stalled_count > self.progress_limit:
            # Read the count before resetting it. Resetting first reported "asked 0
            # times in a row", which is how this appeared in two real run reports
            # before anyone noticed the number was the one thing it could not be.
            attempts = self._stalled_count
            # Reported once per stall, not once per turn after it: the run continues,
            # and a second report for the same stuck draft adds nothing.
            self._stalled_count = 0
            _draft_id, _index, awaiting = state
            self._fail(
                Failure(
                    "no-progress",
                    f"the bot has asked for {awaiting!r} {attempts} times in a row "
                    "with nothing advancing",
                    index,
                    description,
                )
            )

    async def _draft_state(self) -> tuple | None:
        user_id = await self._user_id()
        if user_id is None:
            return None
        result = await self.session.execute(
            select(PendingDraft).where(PendingDraft.user_id == user_id)
        )
        draft = result.scalar_one_or_none()
        if draft is None:
            return None
        return (draft.id, draft.payload.get("current_index"), draft.awaiting_field)

    async def _user_id(self) -> int | None:
        """Expire first, then read: the handlers wrote through their own sessions, and
        an attribute read on a stale object would lazy-load inside the event loop,
        which SQLAlchemy's async session cannot do."""
        self.session.expire_all()
        user = await get_user_by_telegram_id(self.session, self.client.telegram_user_id)
        return None if user is None else user.id

    def _fail(self, failure: Failure) -> None:
        self.failures.append(failure)
        if failure.kind in self.stopping_kinds:
            raise RunStopped(failure)

    # -- reporting --------------------------------------------------------

    def assert_clean(self) -> None:
        if self.failures:
            raise AssertionError(
                "the run failed:\n  " + "\n  ".join(str(f) for f in self.failures)
            )

    @property
    def violations(self) -> list[Violation]:
        return [Violation("run", f.detail) for f in self.failures]
