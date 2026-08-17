"""Every invariant is tested by breaking it on purpose (task 5.6).

An invariant that has never been seen to fire is an assertion nobody has checked -
it might be querying the wrong thing and reporting "all clear" forever.
"""

from __future__ import annotations

import datetime as dt

import pytest
from harness.invariants import check_all
from harness.llm import NoMoreToolCalls
from harness.run import RunStopped
from harness.state import create_onboarded_user, food_extraction

from calobot.persistence.models import (
    ActivityEntry,
    DraftIntent,
    FoodEntry,
    PendingDraft,
    Provenance,
    WeightEntry,
)
from calobot.persistence.seed import seed_all
from calobot.persistence.timeutil import utcnow


async def _check(db_session, user, settings):
    # Read the id before expiring: an attribute read on an expired object would
    # lazy-load inside the event loop, which the async session cannot do.
    user_id = user.id
    db_session.expire_all()
    return await check_all(db_session, user_id, settings.timezone)


def _food(user_id: int, **overrides) -> FoodEntry:
    defaults = dict(
        user_id=user_id,
        description="riso",
        grams=100.0,
        kcal_per_100g=130.0,
        kcal=130.0,
        provenance=Provenance.tabella,
        consumed_at=utcnow(),
    )
    return FoodEntry(**{**defaults, **overrides})


# -- a clean state is clean -----------------------------------------------


async def test_a_normal_conversation_violates_nothing(db_session, run, llm, settings):
    await seed_all(db_session)
    await create_onboarded_user(db_session, 42)

    llm.push(
        {"intent": "food", "ignored_text": None},
        food_extraction(description="noci", quantity_grams=10),
        {"selected_candidate_id": 1},
    )
    await run.say("ho mangiato 10g di noci")

    run.assert_clean()


# -- each invariant, broken on purpose ------------------------------------


async def test_an_entry_without_a_quantity_is_caught(db_session, settings):
    user = await create_onboarded_user(db_session, 42)
    db_session.add(_food(user.id, grams=0.0, kcal=0.0))
    await db_session.flush()

    violations = await _check(db_session, user, settings)

    assert any(v.invariant == "entry without a quantity" for v in violations)


async def test_an_activity_without_a_duration_is_caught(db_session, settings):
    user = await create_onboarded_user(db_session, 42)
    db_session.add(
        ActivityEntry(
            user_id=user.id,
            activity="corsa",
            duration_minutes=0.0,
            met=8.0,
            kcal=0.0,
            provenance=Provenance.tabella,
            performed_at=utcnow(),
        )
    )
    await db_session.flush()

    violations = await _check(db_session, user, settings)

    assert any(v.invariant == "entry without a quantity" for v in violations)


async def test_a_deleted_entry_that_still_counts_is_caught(db_session, settings, monkeypatch):
    """Simulates the read path forgetting the soft-delete filter, which is the bug
    this invariant exists to catch."""
    user = await create_onboarded_user(db_session, 42)
    deleted = _food(user.id, deleted_at=utcnow())
    db_session.add(deleted)
    await db_session.flush()

    import calobot.persistence.repository as repository

    original = repository.get_entries_in_range

    async def leaky(session, kind, user_id, start, end):
        entries = await original(session, kind, user_id, start, end)
        if kind == "food":
            return [*entries, deleted]  # the deleted one leaks back in
        return entries

    monkeypatch.setattr("calobot.reporting.aggregation.get_entries_in_range", leaky)

    violations = await _check(db_session, user, settings)

    assert any(v.invariant == "day total disagrees with its entries" for v in violations)


async def test_a_day_total_that_drifts_is_caught(db_session, settings, monkeypatch):
    user = await create_onboarded_user(db_session, 42)
    db_session.add(_food(user.id))
    await db_session.flush()

    import calobot.reporting.aggregation as aggregation

    original = aggregation.build_food_report

    async def inflated(session, user_id, period, day, tz, budget):
        report = await original(session, user_id, period, day, tz, budget)
        return type(report)(
            total_kcal=report.total_kcal + 999,
            daily_average_kcal=report.daily_average_kcal,
            budget_kcal=report.budget_kcal,
            difference_kcal=report.difference_kcal,
            days_with_no_data=report.days_with_no_data,
            has_data=report.has_data,
        )

    monkeypatch.setattr("harness.invariants.build_food_report", inflated)

    violations = await _check(db_session, user, settings)

    assert any(v.invariant == "day total disagrees with its entries" for v in violations)


async def test_an_entry_counted_on_the_wrong_day_is_caught(db_session, settings, monkeypatch):
    user = await create_onboarded_user(db_session, 42)
    db_session.add(_food(user.id))
    await db_session.flush()

    async def misbucketed(session, user_id, period, day, tz):
        return {day + dt.timedelta(days=1): 130.0}

    monkeypatch.setattr("harness.invariants.build_daily_kcal_breakdown", misbucketed)

    violations = await _check(db_session, user, settings)

    assert any(v.invariant == "entry counted on the wrong local day" for v in violations)


async def test_a_draft_with_no_question_outstanding_is_caught(db_session, settings):
    user = await create_onboarded_user(db_session, 42)
    db_session.add(
        PendingDraft(
            user_id=user.id,
            intent=DraftIntent.food,
            payload={"items": [{"description": "riso", "resolved": {}}], "current_index": 0},
            awaiting_field=None,
        )
    )
    await db_session.flush()

    violations = await _check(db_session, user, settings)

    assert any(v.invariant == "draft open with no question outstanding" for v in violations)


async def test_an_implausible_stored_weight_is_caught(db_session, settings):
    user = await create_onboarded_user(db_session, 42)
    db_session.add(
        WeightEntry(user_id=user.id, kg=800.0, day=dt.date(2026, 3, 2), recorded_at=utcnow())
    )
    await db_session.flush()

    violations = await _check(db_session, user, settings)

    assert any(v.invariant == "implausible stored value" for v in violations)


# -- attribution ----------------------------------------------------------


async def test_a_violation_names_the_action_that_caused_it(db_session, run, llm):
    """Attribution is the point of checking after every action: the report has to say
    which message broke it, not merely that something did."""
    await seed_all(db_session)
    user = await create_onboarded_user(db_session, 42)

    llm.push(
        {"intent": "food", "ignored_text": None},
        food_extraction(description="noci", quantity_grams=10),
        {"selected_candidate_id": 1},
    )
    await run.say("primo messaggio innocuo")

    # Corrupt the state as if the next message had done it.
    db_session.add(_food(user.id, grams=0.0, kcal=0.0))
    await db_session.flush()

    llm.push(
        {"intent": "other", "ignored_text": None},
        NoMoreToolCalls(),
        {"answer_text": "ciao", "used_data": False, "declined_reason": None},
    )
    with pytest.raises(RunStopped) as caught:
        await run.say("secondo messaggio")

    failure = caught.value.failure
    assert failure.kind == "invariant"
    assert failure.action_index == 2
    assert "secondo messaggio" in failure.action


async def test_a_violation_fails_the_run_even_when_the_step_succeeded(db_session, run, llm):
    await seed_all(db_session)
    user = await create_onboarded_user(db_session, 42)

    db_session.add(_food(user.id, grams=0.0, kcal=0.0))
    await db_session.flush()

    llm.push(
        {"intent": "food", "ignored_text": None},
        food_extraction(description="noci", quantity_grams=10),
        {"selected_candidate_id": 1},
    )

    # The step itself does exactly what it should - and the run still fails.
    with pytest.raises(RunStopped):
        await run.say("ho mangiato 10g di noci")


# -- bounds ---------------------------------------------------------------


async def test_a_conversation_that_stops_advancing_is_caught(db_session, run, llm):
    """The bot re-asks for a missing field with no attempt counter; the only exit is
    draft expiry. A cooperative user never sees it. A user who answers "boh" does,
    immediately - which is precisely the class of bug this harness exists to surface.
    """
    await seed_all(db_session)
    await create_onboarded_user(db_session, 42)
    run.progress_limit = 2

    llm.push(
        {"intent": "food", "ignored_text": None},
        food_extraction(
            description="pasta al pesto", quantity_grams=None, household_measure="un piatto"
        ),
    )
    asked = await run.say("un piatto di pasta al pesto")
    assert asked[0].options  # a portion question is outstanding

    llm.push({"intent": "other", "ignored_text": None})
    await run.say("boh")

    llm.push({"intent": "other", "ignored_text": None})
    await run.say("boh")

    # Recorded, not raised: a stuck conversation is an observation about one turn, so
    # the run continues and a single run surfaces every finding rather than the first.
    failure = run.failures[-1]
    assert failure.kind == "no-progress"
    assert "portion_grams" in failure.detail
    # The attempt count must be the real one. It read "0 times in a row" in two live
    # reports, because the counter was reset before the message was formatted.
    assert "3 times in a row" in failure.detail
    assert run.actions[-1].index == 3


async def test_answering_the_question_clears_the_stall_counter(db_session, run, llm):
    await seed_all(db_session)
    await create_onboarded_user(db_session, 42)
    run.progress_limit = 2

    llm.push(
        {"intent": "food", "ignored_text": None},
        food_extraction(
            description="pasta al pesto", quantity_grams=None, household_measure="un piatto"
        ),
    )
    asked = await run.say("un piatto di pasta al pesto")

    llm.push({"intent": "other", "ignored_text": None})
    await run.say("boh")

    # A real answer resolves the draft, so the run is clean rather than stalled.
    llm.push(
        {"selected_candidate_id": None},
        {"kcal_per_100g": 200, "display_name_it": "pasta al pesto"},
    )
    await run.tap(asked[0].labels[1])

    run.assert_clean()


async def test_a_corrupting_violation_stops_the_run_but_a_turn_level_one_does_not(
    db_session, run, llm
):
    """Which failures end a run is a deliberate split. A corrupt database poisons
    everything computed after it. A stuck conversation or a false confirmation are
    observations about one turn, and stopping on them means a run reports only its
    earliest finding - run 2 of marco-three-days never reached day three."""
    assert "invariant" in run.stopping_kinds
    assert "action-cap" in run.stopping_kinds
    assert "no-progress" not in run.stopping_kinds
    assert "false-confirmation" not in run.stopping_kinds


async def test_the_action_cap_stops_the_run(db_session, run, llm):
    await create_onboarded_user(db_session, 42)
    run.action_cap = 2

    llm.push(
        {"intent": "other", "ignored_text": None},
        NoMoreToolCalls(),
        {"answer_text": "ciao", "used_data": False, "declined_reason": None},
    )
    await run.say("uno")
    llm.push(
        {"intent": "other", "ignored_text": None},
        NoMoreToolCalls(),
        {"answer_text": "ciao", "used_data": False, "declined_reason": None},
    )
    await run.say("due")

    with pytest.raises(RunStopped, match="cap of 2 actions"):
        await run.say("tre")
