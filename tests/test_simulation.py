"""A whole scenario, end to end, offline (groups 7 and 9).

Both actors are scripted here - the simulated user and the bot - so the test is about
the *machinery*: that a scenario runs, that the oracle scores it, that the report
carries what an agent would need to reproduce a failure. The live version of this is
task 10.1, and it is the only part that needs a real endpoint.
"""

from __future__ import annotations

import datetime as dt

from harness.library import marco_three_days
from harness.llm import NoMoreToolCalls
from harness.scenario import (
    COOPERATIVE,
    HOSTILE,
    NothingStored,
    Scenario,
    Step,
    StoredFood,
)
from harness.simulation import run_scenario
from harness.state import create_onboarded_user, food_extraction
from harness.user_agent import SimulatedUser

from calobot.persistence.seed import seed_all


async def _setup(db_session):
    await seed_all(db_session)
    user = await create_onboarded_user(db_session, 42)
    return user.id


def _food_exchange(llm, description: str, grams: int):
    llm.push(
        {"intent": "food", "ignored_text": None},
        food_extraction(description=description, quantity_grams=grams),
        {"selected_candidate_id": None},
        {"kcal_per_100g": 100, "display_name_it": description},
    )


async def _run(scenario, *, db_session, run, agent_llm, settings, clock=None):
    user_id = await _setup(db_session)
    return await run_scenario(
        scenario,
        run=run,
        user=SimulatedUser(agent_llm.gateway, scenario.persona),
        session=db_session,
        user_id=user_id,
        tz=settings.timezone,
        clock=clock,
    )


# -- a passing scenario ---------------------------------------------------


async def test_a_scenario_that_goes_well_passes(db_session, run, llm, agent_llm, settings):
    scenario = Scenario(
        name="one-good-meal",
        persona=COOPERATIVE,
        starts_at=dt.datetime(2026, 3, 2, 13, 0),
        steps=[Step(intent="log 100 g of rice", expect=StoredFood("riso", 100))],
    )
    agent_llm.push({"message": "ho mangiato 100g di riso"})
    _food_exchange(llm, "riso", 100)

    report = await _run(scenario, db_session=db_session, run=run, agent_llm=agent_llm, settings=settings)

    assert report.passed, report.render()
    assert report.verdicts[0].said == "ho mangiato 100g di riso"


async def test_the_words_vary_but_the_intent_is_what_is_scored(
    db_session, run, llm, agent_llm, settings
):
    """The agent phrased it differently than the scenario would have. The step still
    passes, because the intent is the contract."""
    scenario = Scenario(
        name="one-good-meal",
        persona=COOPERATIVE,
        starts_at=dt.datetime(2026, 3, 2, 13, 0),
        steps=[Step(intent="log 100 g of rice", expect=StoredFood("riso", 100))],
    )
    agent_llm.push({"message": "stasera un etto di riso, niente di che"})
    _food_exchange(llm, "riso", 100)

    report = await _run(scenario, db_session=db_session, run=run, agent_llm=agent_llm, settings=settings)

    assert report.passed
    assert "etto" in report.verdicts[0].said


# -- a failing scenario ---------------------------------------------------


async def test_a_step_whose_expectation_is_missed_fails_the_run(
    db_session, run, llm, agent_llm, settings
):
    scenario = Scenario(
        name="wrong-quantity",
        persona=COOPERATIVE,
        starts_at=dt.datetime(2026, 3, 2, 13, 0),
        steps=[Step(intent="log 100 g of rice", expect=StoredFood("riso", 100))],
    )
    agent_llm.push({"message": "100g di riso"})
    _food_exchange(llm, "riso", 10)  # the bot stored a tenth of it

    report = await _run(scenario, db_session=db_session, run=run, agent_llm=agent_llm, settings=settings)

    assert not report.passed
    assert not report.verdicts[0].passed
    assert report.attribution(report.verdicts[0]) == "model"


async def test_an_invariant_violation_stops_the_run_and_is_attributed_to_the_code(
    db_session, run, llm, agent_llm, settings
):
    """The corrupt entry is inserted directly rather than coaxed out of the bot.

    It used to be produced by staging an extraction of 0 g, which the bot dutifully
    stored - that was the injection defect, and calobot-false-confirmation closed it.
    The harness must still catch a bad entry whatever put it there, so the test now
    manufactures the state instead of relying on a route that no longer exists.
    """
    from calobot.persistence.models import FoodEntry, Provenance
    from calobot.persistence.timeutil import utcnow

    scenario = Scenario(
        name="broken-entry",
        persona=COOPERATIVE,
        starts_at=dt.datetime(2026, 3, 2, 13, 0),
        steps=[
            Step(intent="log 100 g of rice", expect=StoredFood("riso", 100)),
            Step(intent="log 50 g of bread", expect=StoredFood("pane", 50)),
        ],
    )
    user_id = await _setup(db_session)
    db_session.add(
        FoodEntry(
            user_id=user_id,
            description="voce corrotta",
            grams=0.0,
            kcal_per_100g=0.0,
            kcal=0.0,
            provenance=Provenance.llm,
            consumed_at=utcnow(),
        )
    )
    await db_session.flush()

    agent_llm.push({"message": "100g di riso"})
    _food_exchange(llm, "riso", 100)

    report = await run_scenario(
        scenario,
        run=run,
        user=SimulatedUser(agent_llm.gateway, scenario.persona),
        session=db_session,
        user_id=user_id,
        tz=settings.timezone,
    )

    assert not report.passed
    assert report.stopped_early
    assert report.failures[0].kind == "invariant"
    assert report.attribution(report.failures[0]) == "code"


# -- the report -----------------------------------------------------------


async def test_the_report_carries_what_is_needed_to_reproduce_a_failure(
    db_session, run, llm, agent_llm, settings
):
    scenario = Scenario(
        name="wrong-quantity",
        persona=HOSTILE,
        starts_at=dt.datetime(2026, 3, 2, 13, 0),
        steps=[Step(intent="log 100 g of rice", expect=StoredFood("riso", 100))],
    )
    agent_llm.push({"message": "cento grammi di riso dai"})
    _food_exchange(llm, "riso", 10)

    report = await _run(scenario, db_session=db_session, run=run, agent_llm=agent_llm, settings=settings)
    rendered = report.render()

    assert "wrong-quantity" in rendered
    assert "Marco" in rendered
    assert "log 100 g of rice" in rendered  # what was meant
    assert "cento grammi di riso dai" in rendered  # what was said
    assert "Registrato" in rendered  # what the bot replied
    assert "attribution: model" in rendered
    assert report.to_dict()["behaviours"]  # which behaviours were in play


async def test_the_report_round_trips_through_a_file(
    db_session, run, llm, agent_llm, settings, tmp_path
):
    scenario = Scenario(
        name="one-good-meal",
        persona=COOPERATIVE,
        starts_at=dt.datetime(2026, 3, 2, 13, 0),
        steps=[Step(intent="log 100 g of rice", expect=StoredFood("riso", 100))],
    )
    agent_llm.push({"message": "100g di riso"})
    _food_exchange(llm, "riso", 100)

    report = await _run(scenario, db_session=db_session, run=run, agent_llm=agent_llm, settings=settings)
    path = report.save(tmp_path / "report.json")

    import json

    reloaded = json.loads(path.read_text())
    assert reloaded["passed"]
    assert reloaded["conversation"]


async def test_metrics_are_reported_and_do_not_fail_the_run(
    db_session, run, llm, agent_llm, settings
):
    """A misclassification is counted, not fatal: one means nothing, and gating on it
    would make the suite reject correct behaviour."""
    scenario = Scenario(
        name="off-intent",
        persona=COOPERATIVE,
        starts_at=dt.datetime(2026, 3, 2, 13, 0),
        steps=[Step(intent="say hello", expect=NothingStored())],
    )
    agent_llm.push({"message": "ciao come stai"})
    llm.push(
        {"intent": "other", "ignored_text": None},
        NoMoreToolCalls(),
        {"answer_text": "Ciao!", "used_data": False, "declined_reason": None},
    )

    report = await _run(scenario, db_session=db_session, run=run, agent_llm=agent_llm, settings=settings)

    assert report.passed
    assert report.metrics.off_intent_replies == 1
    assert "metrics (reported, not gated)" in report.render()


# -- simulated days -------------------------------------------------------


async def test_steps_are_attributed_to_their_own_local_days(
    db_session, run, llm, agent_llm, settings, clock
):
    scenario = Scenario(
        name="two-days",
        persona=COOPERATIVE,
        starts_at=dt.datetime(2026, 3, 2, 9, 0),
        steps=[
            Step(
                intent="log 100 g of rice",
                expect=StoredFood("riso", 100, on_local_day=dt.date(2026, 3, 2)),
                at=dt.datetime(2026, 3, 2, 13, 0),
            ),
            Step(
                intent="log 50 g of bread",
                expect=StoredFood("pane", 50, on_local_day=dt.date(2026, 3, 3)),
                at=dt.datetime(2026, 3, 3, 13, 0),
            ),
        ],
    )
    agent_llm.push({"message": "100g di riso"}, {"message": "50g di pane"})
    _food_exchange(llm, "riso", 100)
    _food_exchange(llm, "pane", 50)

    report = await _run(
        scenario, db_session=db_session, run=run, agent_llm=agent_llm, settings=settings, clock=clock
    )

    assert report.passed, report.render()


# -- the authored scenario ------------------------------------------------


def test_the_hostile_scenario_covers_three_days_and_every_declared_behaviour():
    scenario = marco_three_days()
    days = {step.at.date() for step in scenario.steps if step.at}

    assert len(days) == 3
    assert scenario.persona.is_hostile
    # Every day contains at least one step whose correct outcome is that nothing is
    # stored - the checks a cooperative scenario cannot make.
    for day in days:
        same_day = [s for s in scenario.steps if s.at and s.at.date() == day]
        assert any(not isinstance(s.expect, StoredFood) for s in same_day)


def test_every_behaviour_the_scenario_uses_is_in_the_persona_repertoire():
    scenario = marco_three_days()
    agent = SimulatedUser(gateway=None, persona=scenario.persona)  # type: ignore[arg-type]

    unsupported = [s.behaviour for s in scenario.steps if not agent.supports(s.behaviour)]

    assert not unsupported, f"the scenario asks for behaviours the persona lacks: {unsupported}"
