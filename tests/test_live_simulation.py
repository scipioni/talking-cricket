"""The live run (group 10).

Excluded from the default suite: it contacts the real endpoint, so it is slow, costs
compute and does not give the same answer twice. Run it deliberately:

    task simulate

Everything it finds is written to `simulation-runs/` as a report plus a recording,
and reproduces from those without the endpoint (see tests/test_reproduction.py).
Findings are filed as their own changes - this harness does not fix what it finds.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest
from harness.cassette import CallCapReached, Recorder
from harness.library import marco_three_days
from harness.simulation import run_scenario
from harness.state import create_onboarded_user
from harness.user_agent import SimulatedUser

from calobot.llm.gateway import LLMGateway
from calobot.persistence.seed import seed_all

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "simulation-runs"


@pytest.mark.live
async def test_marco_three_days_against_the_real_endpoint(
    db_session, run, client, settings, clock, monkeypatch
):
    await seed_all(db_session)
    user = await create_onboarded_user(db_session, 42)
    user_id = user.id

    scenario = marco_three_days()

    # One gateway for the bot, recorded; a separate one for the simulated user, so a
    # replay reproduces the bot's calls without also having to reproduce the agent's.
    bot_gateway = LLMGateway(settings)
    recorder = Recorder(bot_gateway, call_cap=scenario.model_call_cap)
    monkeypatch.setattr("calobot.telegram.handlers._gateway", lambda _s: bot_gateway)

    agent = SimulatedUser(LLMGateway(settings), scenario.persona)

    started = dt.datetime.now(dt.UTC)
    try:
        report = await run_scenario(
            scenario,
            run=run,
            user=agent,
            session=db_session,
            user_id=user_id,
            tz=settings.timezone,
            clock=clock,
            cassette=recorder.cassette,
            cassette_path=OUTPUT_DIR / f"{scenario.name}.jsonl",
        )
    except CallCapReached as exhausted:
        recorder.cassette.save(OUTPUT_DIR / f"{scenario.name}.partial.jsonl")
        pytest.fail(f"{exhausted}\nthe partial recording was kept")

    report.duration_seconds = (dt.datetime.now(dt.UTC) - started).total_seconds()
    report.save(OUTPUT_DIR / f"{scenario.name}.report.json")

    print(f"\n{report.render()}")


    # The run is an instrument, not a gate: it reports rather than asserting the bot
    # is perfect. What must hold is that the harness produced a usable finding set.
    assert report.verdicts, "the scenario produced no verdicts at all"
    assert (OUTPUT_DIR / f"{scenario.name}.jsonl").exists()
