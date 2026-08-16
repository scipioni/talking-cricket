"""Running a scenario, and the report a fixing agent consumes
(specs/conversation-simulation - Findings are reported for another agent to act on).

Ties together the pieces: the scenario supplies intents and behaviours, the simulated
user turns them into Italian, the checked run performs them with the invariants
watching, and the oracle scores each step against what the user meant.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from calobot.persistence.models import FoodEntry, Provenance

from .cassette import Cassette
from .oracle import Verdict, score, snapshot
from .run import CheckedRun, Failure, RunStopped
from .scenario import Behaviour, Scenario
from .transport import SentMessage
from .user_agent import SimulatedUser


@dataclass(frozen=True)
class Metrics:
    """Described as trends, never as pass/fail: a single misclassification means
    nothing, and gating on one would make the suite reject correct behaviour."""

    steps: int
    entries_stored: int
    clarification_turns: int
    clarification_turns_per_entry: float
    off_intent_replies: int
    from_food_table: int
    from_model_estimate: int

    @property
    def table_share(self) -> float:
        total = self.from_food_table + self.from_model_estimate
        return self.from_food_table / total if total else 0.0


@dataclass
class RunReport:
    scenario: str
    persona: str
    behaviours: list[Behaviour]
    verdicts: list[Verdict] = field(default_factory=list)
    failures: list[Failure] = field(default_factory=list)
    conversation: list[str] = field(default_factory=list)
    # Everything the user said, verbatim and in order. A replay feeds these back
    # rather than re-generating them, which is what makes reproduction free and
    # deterministic (specs/conversation-simulation - Recording and replay).
    utterances: list[str] = field(default_factory=list)
    seed: str = ""
    # Persisted rather than only printed: the caps in a scenario are set from these,
    # so a later run can see whether the cost of a run has moved.
    model_calls: int = 0
    duration_seconds: float = 0.0
    metrics: Metrics | None = None
    stopped_early: bool = False
    cassette_path: str | None = None

    @property
    def passed(self) -> bool:
        return not self.failures and all(verdict.passed for verdict in self.verdicts)

    def attribution(self, failure_or_verdict) -> str:
        """Triage hint, not a proof. Invariant, progress and budget failures are
        properties of the code and replay deterministically. A step whose expectation
        was missed is usually the model's judgement, and a recording cannot verify a
        fix that changes how the model is prompted."""
        return "code" if isinstance(failure_or_verdict, Failure) else "model"

    def render(self) -> str:
        lines = [
            f"scenario: {self.scenario}",
            f"persona: {self.persona} ({'hostile' if self.behaviours else 'cooperative'})",
            f"behaviours: {', '.join(self.behaviours) or 'none'}",
            f"seed: {self.seed}",
            f"result: {'PASSED' if self.passed else 'FAILED'}"
            + (" (stopped early)" if self.stopped_early else ""),
            "",
        ]
        for verdict in self.verdicts:
            lines.append(str(verdict))
            if not verdict.passed:
                lines.append(f"    meant: {verdict.intent}")
                lines.append(f"    said:  {verdict.said}")
                for reply in verdict.replies:
                    lines.append(f"    bot:   {reply}")
                lines.append("    attribution: model")
        for failure in self.failures:
            lines.append(str(failure))
            lines.append("    attribution: code")
        if self.metrics:
            lines += [
                "",
                "metrics (reported, not gated):",
                f"  entries stored: {self.metrics.entries_stored}",
                f"  clarification turns per entry: "
                f"{self.metrics.clarification_turns_per_entry:.2f}",
                f"  replies off the intended intent: {self.metrics.off_intent_replies}",
                f"  resolved from the food table: {self.metrics.table_share:.0%}",
            ]
        if self.model_calls or self.duration_seconds:
            lines += [
                f"  model calls: {self.model_calls}"
                + (f" in {self.duration_seconds:.0f}s" if self.duration_seconds else ""),
            ]
        if self.cassette_path:
            lines += ["", f"recording: {self.cassette_path}"]
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "scenario": self.scenario,
            "persona": self.persona,
            "behaviours": list(self.behaviours),
            "passed": self.passed,
            "stopped_early": self.stopped_early,
            "verdicts": [asdict(v) for v in self.verdicts],
            "failures": [asdict(f) for f in self.failures],
            "conversation": self.conversation,
            "utterances": list(self.utterances),
            "seed": self.seed,
            "model_calls": self.model_calls,
            "duration_seconds": round(self.duration_seconds, 1),
            "metrics": asdict(self.metrics) if self.metrics else None,
            "cassette": self.cassette_path,
        }

    def save(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False))
        return path


async def _metrics(
    session: AsyncSession, user_id: int, *, steps: int, clarification_turns: int, off_intent: int
) -> Metrics:
    session.expire_all()
    result = await session.execute(
        select(FoodEntry).where(FoodEntry.user_id == user_id, FoodEntry.deleted_at.is_(None))
    )
    entries = list(result.scalars())
    from_table = sum(1 for e in entries if e.provenance == Provenance.tabella)
    return Metrics(
        steps=steps,
        entries_stored=len(entries),
        clarification_turns=clarification_turns,
        clarification_turns_per_entry=(clarification_turns / len(entries)) if entries else 0.0,
        off_intent_replies=off_intent,
        from_food_table=from_table,
        from_model_estimate=len(entries) - from_table,
    )


def _is_clarification(replies: list[SentMessage]) -> bool:
    return any(reply.options for reply in replies)


def _is_off_intent(replies: list[SentMessage]) -> bool:
    """A reply that neither asks anything nor confirms anything - the shape of a
    message that was classified as ordinary conversation when it was meant as a log."""
    return bool(replies) and not any(reply.options for reply in replies)


async def run_scenario(
    scenario: Scenario,
    *,
    run: CheckedRun,
    user: SimulatedUser,
    session: AsyncSession,
    user_id: int,
    tz: ZoneInfo,
    clock=None,
    cassette: Cassette | None = None,
    cassette_path: Path | None = None,
    seed: str = "seed_all + one onboarded user",
) -> RunReport:
    report = RunReport(
        scenario=scenario.name,
        persona=scenario.persona.name,
        behaviours=list(scenario.persona.repertoire),
        seed=seed,
        cassette_path=str(cassette_path) if cassette_path else None,
    )
    run.action_cap = scenario.action_cap

    clarification_turns = 0
    off_intent = 0

    if clock is not None:
        clock.set_local(scenario.starts_at, tz)

    for index, step in enumerate(scenario.steps, start=1):
        if clock is not None and step.at is not None:
            clock.set_local(step.at, tz)

        before = await snapshot(session, user_id)

        said: str | None = None
        try:
            if step.tap is not None:
                said = f"(tap: {step.tap})"
                target = run.client.inbox[-2] if step.tap_on_previous else None
                replies = await run.tap(step.tap, on=target)
            else:
                said = await user.utterance(
                    intent=step.intent, behaviour=step.behaviour, replies=run.client.inbox
                )
                replies = await run.say(said)
        except RunStopped as stopped:
            report.failures.append(stopped.failure)
            report.stopped_early = True
            break
        finally:
            # Recorded even when the action failed: a replay must be able to reach
            # the message that broke the run, and utterances repeat (a hostile user
            # says "boh" more than once), so this appends unconditionally.
            if said is not None:
                report.utterances.append(said)

        report.conversation.append(f"USER: {said}")
        report.conversation += [f"BOT: {reply.text}" for reply in replies]

        if _is_clarification(replies):
            clarification_turns += 1
        if _is_off_intent(replies):
            off_intent += 1

        after = await snapshot(session, user_id)
        report.verdicts.append(
            await score(
                session,
                user_id,
                tz,
                step_index=index,
                step=step,
                said=said,
                replies=replies,
                before=before,
                after=after,
            )
        )

    report.failures.extend(f for f in run.failures if f not in report.failures)
    report.metrics = await _metrics(
        session,
        user_id,
        steps=len(report.verdicts),
        clarification_turns=clarification_turns,
        off_intent=off_intent,
    )
    if cassette is not None:
        report.model_calls = len(cassette)
        if cassette_path is not None:
            cassette.save(cassette_path)
    return report
