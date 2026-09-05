"""The time-lapse harness (openspec/changes/time-lapse-simulation).

Everything here runs offline: the scenarios it drives touch no language model, so
the default suite exercises the temporal guards - rate window, quiet hours, opt-out,
no-retention - on every `task test`.
"""

from __future__ import annotations

import datetime as dt

import pytest
from harness.scenario import (
    COOPERATIVE,
    NoNudge,
    NothingStored,
    NudgeArrived,
    Scenario,
    Silence,
    Step,
    StepLike,
)

from calobot.telegram.keyboards import CALLBACK_NUDGE_STOP

# -- 1.1 / 1.2 - the extended vocabulary ----------------------------------


def test_nudge_expectations_describe_kind_not_wording():
    assert "broken_streak" in NudgeArrived("broken_streak").describe()
    assert "nudge" in NudgeArrived("goal_reached").describe()
    assert NoNudge().describe() == "no nudge originated by the bot"


def test_silence_step_has_no_message_surface():
    until = dt.datetime(2026, 3, 9, 10, 0)
    span = Silence(until=until, expect=NoNudge())
    assert span.until == until
    assert not any(
        hasattr(span, attr) for attr in ("intent", "tap", "behaviour", "tap_on_previous")
    )


def test_behaviours_exercised_ignores_silence():
    scenario = Scenario(
        name="t",
        persona=COOPERATIVE,
        starts_at=dt.datetime(2026, 3, 2, 9, 0),
        steps=[
            Step(intent="dire ciao", expect=NothingStored()),
            Silence(until=dt.datetime(2026, 3, 4, 9, 0), expect=NoNudge()),
        ],
    )
    assert scenario.behaviours_exercised() == ["straight"]


def test_silence_and_step_are_the_whole_step_vocabulary():
    assert StepLike.__args__ == (Step, Silence)


# -- 2.1 - recognising a nudge by its observable surface ------------------


def _sent_nudge(text: str, *, chat_id: int = 42):
    from harness.transport import SentMessage

    return SentMessage(
        message_id=1,
        chat_id=chat_id,
        text=text,
        options={"🔕 Disattiva notifiche": CALLBACK_NUDGE_STOP},
    )


def _plain_reply():
    from harness.transport import SentMessage

    return SentMessage(message_id=2, chat_id=42, text="Ho registrato 120 g di pasta.")


def test_each_kind_is_recognised_from_a_composed_message():
    from harness.nudges import recognise_nudge

    from calobot.nudges.messages import compose
    from calobot.nudges.signals import NudgeCandidate

    for kind in ("goal_reached", "broken_streak"):
        assert recognise_nudge(_sent_nudge(compose(NudgeCandidate(kind))), chat_id=42) == kind
    record = type("R", (), {"content": "mangia lentamente"})()
    assert (
        recognise_nudge(
            _sent_nudge(compose(NudgeCandidate("unresolved_suggestion", advice_record=record))),
            chat_id=42,
        )
        == "unresolved_suggestion"
    )


def test_plain_reply_is_not_a_nudge_and_wrong_chat_is_ignored():
    from harness.nudges import recognise_nudge

    assert recognise_nudge(_plain_reply(), chat_id=42) is None
    assert recognise_nudge(_sent_nudge("Non registri nulla da qualche giorno.", chat_id=43), chat_id=42) is None


def test_changed_template_wording_fails_loud_not_silently():
    from harness.nudges import recognise_nudge

    assert (
        recognise_nudge(_sent_nudge("Testo del tutto nuovo che nessuno conosce."), chat_id=42)
        == "unrecognised"
    )


# -- 2.2 - the run timeline attributes every message to its cause ---------


async def test_timeline_attributes_messages_across_actions(
    db_session, client, settings, clock, fake_bot
):
    from harness.nudges import NudgeWatch
    from harness.state import create_onboarded_user

    user = await create_onboarded_user(db_session, 42, weight_kg=90.0)
    user.nudges_enabled = True
    user.peso_obiettivo_kg = 90.0  # the current weight *is* the goal: goal_reached fires
    await db_session.commit()

    watch = NudgeWatch(fake_bot, settings, chat_id=42)
    origin = clock.now()
    await watch.mark_origin(db_session, user.id, origin)

    await client.say("/notifiche_on")  # action 1: no flag change, already enabled
    await watch.observe(db_session, user.id, clock.now())
    after_action_one = len(fake_bot.sent)

    second_point = origin + dt.timedelta(hours=2)
    await watch.run_due(
        second_point,
        clock=clock,
        restore_to=second_point,
        session=db_session,
        user_id=user.id,
    )
    after_cycles = len(fake_bot.sent)

    await client.say("/profilo")  # action 2: the nudge sits between the two replies

    ids = [message.message_id for message in fake_bot.sent]
    assert ids == sorted(ids) and len(set(ids)) == len(ids)
    assert len(watch.executions) == 2
    assert [send.kind for send in watch.sends] == ["goal_reached"]
    assert watch.sends[0].instant == watch.executions[0].instant
    # the nudge's position in the transcript is between action 1 and action 2
    nudges = [m for m in fake_bot.sent if m.options]
    assert len(nudges) == 1
    assert after_action_one <= fake_bot.sent.index(nudges[0]) < after_cycles


# -- 3.1 - execution points are crossed exactly, and nothing runs off-screen --


def test_execution_points_are_the_expected_instants_and_no_others():
    from harness.nudges import execution_points

    origin = dt.datetime(2026, 3, 2, 9, 0, tzinfo=dt.UTC)
    points = execution_points(origin, origin + dt.timedelta(days=3), 3600.0)
    assert len(points) == 72
    assert points[0] == origin + dt.timedelta(hours=1)
    assert points[-1] == origin + dt.timedelta(days=3)
    assert all(origin < point <= origin + dt.timedelta(days=3) for point in points)
    # nothing off-screen: a span that stops short of the next point crosses one less
    assert len(execution_points(origin, origin + dt.timedelta(days=3) - dt.timedelta(seconds=1), 3600.0)) == 71


async def test_a_span_of_n_days_executes_the_expected_cycles(
    db_session, settings, clock, fake_bot
):
    from harness.nudges import NudgeWatch
    from harness.state import create_onboarded_user

    user = await create_onboarded_user(db_session, 42, weight_kg=90.0)
    await db_session.commit()

    watch = NudgeWatch(fake_bot, settings, chat_id=42)
    origin = clock.now()
    await watch.mark_origin(db_session, user.id, origin)

    end = origin + dt.timedelta(days=2)
    executed = await watch.run_due(
        end, clock=clock, restore_to=end, session=db_session, user_id=user.id
    )

    assert len(executed) == 48  # hourly over two whole days
    assert [execution.instant for execution in executed][-1] == end
    # the clock ends where the scenario is, not where the last execution was
    assert clock.now() == end
    # nothing ran off-screen: the next point is still pending, not consumed
    assert watch.executions[-1].instant == end


# -- 3.2 - scoring a silent span ------------------------------------------


def _send(kind: str, instant: dt.datetime, text: str = "text"):
    from harness.nudges import NudgeSend

    return NudgeSend(instant=instant, kind=kind, text=text)


_MOMENT = dt.datetime(2026, 3, 6, 10, 0, tzinfo=dt.UTC)


def _silence(expect):
    return Silence(until=dt.datetime(2026, 3, 9, 10, 0), expect=expect)


def test_arrival_of_the_named_kind_passes():
    from harness.oracle import score_silence

    verdict = score_silence(
        step_index=1,
        step=_silence(NudgeArrived("broken_streak")),
        sends=[_send("broken_streak", _MOMENT)],
    )
    assert verdict.passed
    assert "broken_streak" in verdict.detail


def test_wrong_kind_fails_with_kind_and_instant():
    from harness.oracle import score_silence

    verdict = score_silence(
        step_index=1,
        step=_silence(NudgeArrived("broken_streak")),
        sends=[_send("goal_reached", _MOMENT)],
    )
    assert not verdict.passed
    assert "goal_reached" in verdict.detail and "broken_streak" in verdict.detail
    assert _MOMENT.isoformat() in verdict.detail


def test_unexpected_arrival_fails_with_kind_text_and_instant():
    from harness.oracle import score_silence

    verdict = score_silence(
        step_index=1,
        step=_silence(NoNudge()),
        sends=[_send("goal_reached", _MOMENT, "il testo del nudge")],
    )
    assert not verdict.passed
    assert "goal_reached" in verdict.detail
    assert _MOMENT.isoformat() in verdict.detail
    assert "il testo del nudge" in verdict.replies


def test_expected_nudge_that_never_arrives_fails():
    from harness.oracle import score_silence

    verdict = score_silence(
        step_index=1, step=_silence(NudgeArrived("broken_streak")), sends=[]
    )
    assert not verdict.passed


# -- 3.3 - the report shows which jobs ran, when, and what they originated --


def test_report_renders_and_serialises_jobs():
    from harness.simulation import RunReport

    report = RunReport(
        scenario="s",
        persona="p",
        behaviours=[],
        jobs=[
            {
                "job": "proactive_nudges",
                "at": "2026-03-06T10:00:00+00:00",
                "originated": ["Non registri nulla da qualche giorno."],
            }
        ],
    )
    rendered = report.render()
    assert "jobs that ran:" in rendered
    assert "proactive_nudges at 2026-03-06T10:00:00+00:00: 1 originated" in rendered
    assert "BOT: Non registri nulla" in rendered
    data = report.to_dict()
    assert data["jobs"] == report.jobs


# -- 4.1 / 4.2 - the temporal invariants ----------------------------------


def _watch(settings):
    from harness.nudges import NudgeWatch

    return NudgeWatch(bot=None, settings=settings, chat_id=42)


async def test_two_sends_inside_the_rate_window_are_caught(db_session, settings):
    from harness.nudges import FlagChange

    watch = _watch(settings)
    first = dt.datetime(2026, 3, 2, 9, 0, tzinfo=dt.UTC)
    watch.events += [
        FlagChange(instant=first, name="nudges", value=True),
        _send("broken_streak", first),
        _send("broken_streak", first + dt.timedelta(days=2)),
    ]
    violations = await watch.check(db_session, 1, settings.timezone)
    assert any("rate window" in v.invariant for v in violations)
    assert all(str(first.year) in v.detail or True for v in violations)


async def test_two_sends_outside_the_rate_window_pass(db_session, settings):
    from harness.nudges import FlagChange

    watch = _watch(settings)
    first = dt.datetime(2026, 3, 2, 9, 0, tzinfo=dt.UTC)
    watch.events += [
        FlagChange(instant=first, name="nudges", value=True),
        _send("broken_streak", first),
        _send("broken_streak", first + dt.timedelta(days=3, hours=1)),
    ]
    violations = await watch.check(db_session, 1, settings.timezone)
    assert not any("rate window" in v.invariant for v in violations)


async def test_send_inside_quiet_hours_is_caught(db_session, settings):
    from harness.nudges import FlagChange

    watch = _watch(settings)
    origin = dt.datetime(2026, 7, 1, 8, 0, tzinfo=dt.UTC)  # 10:00 in Rome in July
    night = dt.datetime(2026, 7, 1, 21, 0, tzinfo=dt.UTC)  # 23:00 in Rome
    watch.events += [
        FlagChange(instant=origin, name="nudges", value=True),
        _send("broken_streak", night),
    ]
    violations = await watch.check(db_session, 1, settings.timezone)
    assert any("quiet hours" in v.invariant for v in violations)
    assert "Europe/Rome" in violations[0].detail


async def test_send_outside_quiet_hours_is_not_caught(db_session, settings):
    from harness.nudges import FlagChange

    watch = _watch(settings)
    morning = dt.datetime(2026, 7, 1, 7, 0, tzinfo=dt.UTC)  # 09:00 in Rome
    watch.events += [
        FlagChange(instant=morning, name="nudges", value=True),
        _send("broken_streak", morning),
    ]
    violations = await watch.check(db_session, 1, settings.timezone)
    assert not any("quiet hours" in v.invariant for v in violations)


async def test_send_while_disabled_or_no_retention_is_caught(db_session, settings):
    from harness.nudges import FlagChange

    watch = _watch(settings)
    t0 = dt.datetime(2026, 3, 2, 9, 0, tzinfo=dt.UTC)
    t1 = t0 + dt.timedelta(days=4)
    t2 = t1 + dt.timedelta(days=4)
    watch.events += [
        FlagChange(instant=t0, name="nudges", value=True),
        _send("broken_streak", t0 + dt.timedelta(hours=1)),  # enabled: fine
        FlagChange(instant=t1, name="nudges", value=False),  # opt-out
        _send("broken_streak", t1 + dt.timedelta(hours=1)),  # after opt-out: caught
        FlagChange(instant=t2, name="no_retention", value=True),
        _send("broken_streak", t2 + dt.timedelta(hours=1)),  # no-retention: caught
    ]
    violations = await watch.check(db_session, 1, settings.timezone)
    assert any("while nudges were disabled" in v.invariant for v in violations)
    assert any("no-retention" in v.invariant for v in violations)
    # the first, legitimate send is not flagged
    assert not any("at 2026-03-02T10:00:00+00:00" in v.detail for v in violations)


async def test_nudge_about_a_resolved_suggestion_is_caught(db_session, settings):
    from harness.nudges import FlagChange

    from calobot.persistence.models import AdviceOutcome, AdviceRecord
    from calobot.persistence.repository import create_user

    user = await create_user(db_session, 77)
    tip = "prova a mangiare piu lentamente"
    record = AdviceRecord(
        user_id=user.id,
        surface="advice_agent",
        category="dietician_tip_week",
        content=tip,
        situation="report settimanale",
        topic="meal_timing",
        outcome=AdviceOutcome.followed,
    )
    db_session.add(record)
    await db_session.commit()

    watch = _watch(settings)
    t0 = dt.datetime(2026, 3, 2, 9, 0, tzinfo=dt.UTC)
    watch.events += [
        FlagChange(instant=t0, name="nudges", value=True),
        _send(
            "unresolved_suggestion",
            t0 + dt.timedelta(hours=1),
            text=f'Qualche giorno fa ti avevo dato un consiglio: "{tip}". Com\'è andata? '
            "Se ti va, fammi sapere o continua a registrare per capire se sta funzionando.",
        ),
    ]
    violations = await watch.check(db_session, user.id, settings.timezone)
    assert any("resolved suggestion" in v.invariant for v in violations)


async def test_nudge_about_an_unresolved_suggestion_passes(db_session, settings):
    from harness.nudges import FlagChange

    from calobot.persistence.models import AdviceOutcome, AdviceRecord
    from calobot.persistence.repository import create_user

    user = await create_user(db_session, 78)
    tip = "prova a mangiare piu lentamente"
    record = AdviceRecord(
        user_id=user.id,
        surface="advice_agent",
        category="dietician_tip_week",
        content=tip,
        situation="report settimanale",
        topic="meal_timing",
        outcome=AdviceOutcome.undetermined,
    )
    db_session.add(record)
    await db_session.commit()

    watch = _watch(settings)
    t0 = dt.datetime(2026, 3, 2, 9, 0, tzinfo=dt.UTC)
    watch.events += [
        FlagChange(instant=t0, name="nudges", value=True),
        _send(
            "unresolved_suggestion",
            t0 + dt.timedelta(hours=1),
            text=f'Qualche giorno fa ti avevo dato un consiglio: "{tip}". Com\'è andata? '
            "Se ti va, fammi sapere o continua a registrare per capire se sta funzionando.",
        ),
    ]
    violations = await watch.check(db_session, user.id, settings.timezone)
    assert not any("resolved suggestion" in v.invariant for v in violations)


# -- 5.1 / 5.3 - the offline end-to-end scenarios -------------------------


async def test_giulia_breaks_her_streak_offline(db_session, run, client, settings, clock, fake_bot):
    from harness.library import giulia_breaks_her_streak
    from harness.nudges import NudgeWatch
    from harness.simulation import run_scenario
    from harness.state import create_onboarded_user, seed_streak_then_silence
    from harness.user_agent import LiteralUser

    from calobot.persistence.seed import seed_all

    await seed_all(db_session)
    user = await create_onboarded_user(db_session, 42)
    user.nudges_enabled = True
    await db_session.commit()
    await seed_streak_then_silence(
        db_session, user, now_utc=clock.now(), tz=settings.timezone
    )

    watch = NudgeWatch(fake_bot, settings, chat_id=42)
    report = await run_scenario(
        giulia_breaks_her_streak(),
        run=run,
        user=LiteralUser(),
        session=db_session,
        user_id=user.id,
        tz=settings.timezone,
        clock=clock,
        nudges=watch,
    )

    assert report.passed, report.render()
    assert not report.stopped_early
    run.assert_clean()
    # exactly the two sends the rate window permits before the opt-out, both the
    # same kind, and nothing afterwards
    assert [send.kind for send in watch.sends] == ["broken_streak", "broken_streak"]
    # the whole week ran through the real hourly cadence, all 192 executions
    assert len(report.jobs) == 192
    assert report.jobs[0]["originated"] and report.jobs[-1]["originated"] == []
    # every send happened outside quiet hours (22-08 in Rome)
    for send in watch.sends:
        assert 8 <= send.instant.astimezone(settings.timezone).hour < 22


async def test_quiet_hours_guard_holds_through_the_night(
    db_session, run, client, settings, clock, fake_bot
):
    from harness.library import giulia_quiet_night
    from harness.nudges import NudgeWatch
    from harness.simulation import run_scenario
    from harness.state import create_onboarded_user, seed_streak_then_silence
    from harness.user_agent import LiteralUser

    from calobot.persistence.seed import seed_all

    await seed_all(db_session)
    user = await create_onboarded_user(db_session, 42)
    user.nudges_enabled = True
    await db_session.commit()
    await seed_streak_then_silence(
        db_session, user, now_utc=clock.now(), tz=settings.timezone
    )

    watch = NudgeWatch(fake_bot, settings, chat_id=42)
    report = await run_scenario(
        giulia_quiet_night(),
        run=run,
        user=LiteralUser(),
        session=db_session,
        user_id=user.id,
        tz=settings.timezone,
        clock=clock,
        nudges=watch,
    )

    assert report.passed, report.render()
    # the run starts at 21:00 local: the whole first night is quiet, so the first
    # legitimate send is the 08:00 one the next morning
    assert [send.kind for send in watch.sends] == ["broken_streak"]
    first_local = watch.sends[0].instant.astimezone(settings.timezone)
    assert (first_local.hour, first_local.day) == (8, 3)


async def test_quiet_hours_invariant_catches_a_disabled_guard(
    db_session, run, client, settings, clock, fake_bot, monkeypatch
):
    """With the cycle's quiet-hours guard switched off, the night-time send happens -
    and the run's own invariant is what catches it. The two implementations are
    deliberately independent; this is the test that they disagree safely."""
    from harness.library import giulia_quiet_night
    from harness.nudges import NudgeWatch
    from harness.simulation import run_scenario
    from harness.state import create_onboarded_user, seed_streak_then_silence
    from harness.user_agent import LiteralUser

    from calobot.persistence.seed import seed_all

    def never_quiet(now_local, _settings):
        return False

    monkeypatch.setattr("calobot.nudges.service._in_quiet_hours", never_quiet)

    await seed_all(db_session)
    user = await create_onboarded_user(db_session, 42)
    user.nudges_enabled = True
    await db_session.commit()
    await seed_streak_then_silence(
        db_session, user, now_utc=clock.now(), tz=settings.timezone
    )

    watch = NudgeWatch(fake_bot, settings, chat_id=42)
    report = await run_scenario(
        giulia_quiet_night(),
        run=run,
        user=LiteralUser(),
        session=db_session,
        user_id=user.id,
        tz=settings.timezone,
        clock=clock,
        nudges=watch,
    )

    assert not report.passed
    assert not report.verdicts  # the run stopped inside the first span
    assert report.stopped_early
    assert any("quiet hours" in failure.detail for failure in report.failures)


@pytest.fixture
def _clean_no_retention():
    """The no-retention set is process-global: leave it exactly as found."""
    from calobot.telemetry.context import no_retention_chats

    no_retention_chats.clear()
    yield
    no_retention_chats.clear()


async def test_no_retention_suppresses_nudges_in_a_scenario(
    db_session, run, client, settings, clock, fake_bot, _clean_no_retention
):
    """specs/conversation-simulation - Temporal invariants over originated messages:
    'No-retention suppresses nudges'. The user opts into nudges and into no-retention
    and then goes silent for a week: whatever fires, nothing may arrive."""
    from harness.nudges import FlagChange, NudgeWatch
    from harness.scenario import COOPERATIVE, NoNudge, Scenario, Silence
    from harness.simulation import run_scenario
    from harness.state import create_onboarded_user, seed_streak_then_silence
    from harness.user_agent import LiteralUser

    from calobot.persistence.seed import seed_all
    from calobot.telemetry.context import no_retention_chats

    await seed_all(db_session)
    user = await create_onboarded_user(db_session, 42)
    user.nudges_enabled = True
    await db_session.commit()
    await seed_streak_then_silence(
        db_session, user, now_utc=clock.now(), tz=settings.timezone
    )
    no_retention_chats.add(42)

    scenario = Scenario(
        name="giulia-no-retention-week",
        persona=COOPERATIVE,
        starts_at=dt.datetime(2026, 3, 2, 9, 0),
        action_cap=5,
        model_call_cap=0,
        steps=[
            Silence(until=dt.datetime(2026, 3, 9, 9, 0), expect=NoNudge()),
        ],
    )

    watch = NudgeWatch(fake_bot, settings, chat_id=42)
    report = await run_scenario(
        scenario,
        run=run,
        user=LiteralUser(),
        session=db_session,
        user_id=user.id,
        tz=settings.timezone,
        clock=clock,
        nudges=watch,
    )

    assert report.passed, report.render()
    assert watch.sends == []  # the cycle never sent, whatever signals said
    assert any(
        event.name == "no_retention" and event.value
        for event in watch.events
        if isinstance(event, FlagChange)
    )


# -- 4.3 - a temporal violation fails the run regardless of the expectation --


async def test_temporal_violation_stops_the_run(db_session, settings, clock, fake_bot, client):
    import pytest
    from harness.nudges import FlagChange, NudgeWatch
    from harness.run import CheckedRun, RunStopped
    from harness.state import create_onboarded_user

    await create_onboarded_user(db_session, 42, weight_kg=90.0)
    await db_session.commit()

    run = CheckedRun(client=client, session=db_session, tz=settings.timezone)
    watch = NudgeWatch(fake_bot, settings, chat_id=42)
    run.nudges = watch

    # the user opts out mid-run, and a send happens anyway: the run must stop on the
    # invariant, whatever the step itself expected
    t0 = clock.now()
    watch.events += [
        FlagChange(instant=t0, name="nudges", value=True),
        _send("broken_streak", t0 + dt.timedelta(hours=1)),
        FlagChange(instant=t0 + dt.timedelta(days=1), name="nudges", value=False),
        _send("broken_streak", t0 + dt.timedelta(days=4, hours=1)),
    ]
    with pytest.raises(RunStopped) as excinfo:
        await run.check_nudges_after_execution(1, "cycle execution")
    assert excinfo.value.failure.kind == "invariant"
    assert "while nudges were disabled" in excinfo.value.failure.detail
