"""Reproducing a finding from its artefacts alone (task 9.5).

The claim under test: given the repository, a saved run report and its recording, an
agent can reproduce the same failure with no access to the machine that found it and
no contact with the model. If this does not hold, every live finding is a story
rather than a bug report.
"""

from __future__ import annotations

import datetime as dt
import json

from harness.cassette import Cassette, Player, Recorder
from harness.run import CheckedRun
from harness.scenario import COOPERATIVE, Scenario, Step, StoredFood
from harness.simulation import run_scenario
from harness.state import create_onboarded_user, food_extraction
from harness.user_agent import RecordedUser, SimulatedUser

from calobot.llm.gateway import LLMGateway
from calobot.persistence.seed import seed_all

SCENARIO = Scenario(
    name="wrong-quantity",
    persona=COOPERATIVE,
    starts_at=dt.datetime(2026, 3, 2, 13, 0),
    steps=[
        Step(intent="log 100 g of rice", expect=StoredFood("riso", 100)),
        Step(intent="log 50 g of bread", expect=StoredFood("pane", 50)),
    ],
)


async def _fresh_user(db_session):
    await seed_all(db_session)
    user = await create_onboarded_user(db_session, 42)
    return user.id


def _stage_bot(llm, description: str, grams: int):
    llm.push(
        {"intent": "food", "ignored_text": None},
        food_extraction(description=description, quantity_grams=grams),
        {"selected_candidate_id": None},
        {"kcal_per_100g": 100, "display_name_it": description},
    )


async def test_a_failure_reproduces_from_the_report_and_the_recording(
    db_session, run, client, llm, agent_llm, settings, tmp_path
):
    user_id = await _fresh_user(db_session)

    # --- the expensive run: the model is live as far as the harness is concerned,
    #     and everything it says is recorded on the way past.
    recorder = Recorder(llm.gateway)
    agent_llm.push({"message": "100g di riso"}, {"message": "50 grammi di pane"})
    _stage_bot(llm, "riso", 100)
    _stage_bot(llm, "pane", 5)  # the bot got this one wrong

    report = await run_scenario(
        SCENARIO,
        run=run,
        user=SimulatedUser(agent_llm.gateway, SCENARIO.persona),
        session=db_session,
        user_id=user_id,
        tz=settings.timezone,
        cassette=recorder.cassette,
        cassette_path=tmp_path / "run.jsonl",
    )

    assert not report.passed
    failing_step = next(v for v in report.verdicts if not v.passed)
    assert failing_step.step_index == 2

    report_path = report.save(tmp_path / "report.json")

    # --- everything after this point uses only what was written to disk, plus the
    #     repository. Nothing from the run above is referenced.
    saved = json.loads(report_path.read_text())
    cassette = Cassette.load(tmp_path / saved["cassette"].rsplit("/", 1)[-1])

    assert saved["seed"]  # how to rebuild the starting state
    assert saved["utterances"] == ["100g di riso", "50 grammi di pane"]

    # Rebuild the starting state the seed describes, in a clean database.
    from calobot.persistence.engine import get_session_factory

    session_factory = get_session_factory()
    async with session_factory() as fresh_session:
        from sqlalchemy import delete

        from calobot.persistence.models import FoodEntry, ResolutionCache

        await fresh_session.execute(delete(FoodEntry))
        await fresh_session.execute(delete(ResolutionCache))
        await fresh_session.commit()

    db_session.expire_all()

    # A gateway with nothing behind it but the recording, and a user that repeats
    # what it said rather than inventing it again. No model is contacted.
    replay_gateway = LLMGateway(settings)
    Player(replay_gateway, cassette)
    llm.gateway._client.chat.completions.create = replay_gateway._client.chat.completions.create

    from harness.client import Client
    from harness.transport import FakeBot

    replay_bot = FakeBot()
    replay_client = Client(replay_bot, settings, telegram_user_id=42)
    replay_run = CheckedRun(client=replay_client, session=db_session, tz=settings.timezone)

    reproduced = await run_scenario(
        SCENARIO,
        run=replay_run,
        user=RecordedUser(SCENARIO.persona, saved["utterances"]),
        session=db_session,
        user_id=user_id,
        tz=settings.timezone,
    )

    # The same step fails, the same way.
    assert not reproduced.passed
    reproduced_failure = next(v for v in reproduced.verdicts if not v.passed)
    assert reproduced_failure.step_index == failing_step.step_index
    assert reproduced_failure.detail == failing_step.detail
    assert reproduced_failure.said == failing_step.said


async def test_a_replay_needs_no_model_and_no_agent(db_session, settings):
    """The two things a live run needs and a replay must not: the endpoint, and a
    model call to generate the user's words."""
    user = RecordedUser(COOPERATIVE, ["ho mangiato una mela"])

    said = await user.utterance(intent="log an apple", behaviour="straight", replies=[])

    assert said == "ho mangiato una mela"
    assert user.consumed == ["ho mangiato una mela"]


async def test_a_replay_short_of_utterances_says_so(db_session, settings):
    user = RecordedUser(COOPERATIVE, [])

    try:
        await user.utterance(intent="log an apple", behaviour="straight", replies=[])
    except AssertionError as error:
        assert "the recording holds only 0" in str(error)
    else:
        raise AssertionError("a replay with no utterances left should have failed")
