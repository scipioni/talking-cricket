"""Recording and replay (group 8).

The property under test is not "replay returns the recorded answers" - that is easy
and useless on its own. It is that replay *refuses* when the code has moved on, so a
fixing agent can never be told a stale recording still passes.
"""

from __future__ import annotations

import pytest
from harness.cassette import CallCapReached, Cassette, Divergence, Player, Recorder, fingerprint
from harness.state import create_onboarded_user, food_extraction

from calobot.llm.gateway import LLMGateway
from calobot.persistence.seed import seed_all


async def _log_walnuts(client, description="noci"):
    return await client.say(f"ho mangiato 10g di {description}")


def _stage(llm, description="noci"):
    llm.push(
        {"intent": "food", "ignored_text": None},
        food_extraction(description=description, quantity_grams=10),
        {"selected_candidate_id": 1},
    )


# -- fingerprinting -------------------------------------------------------


def test_the_same_request_fingerprints_the_same():
    request = {
        "model": "m",
        "messages": [{"role": "user", "content": "ciao"}],
        "response_format": {"json_schema": {"name": "Classification"}},
    }

    assert fingerprint(request) == fingerprint(dict(request))


def test_a_changed_prompt_changes_the_fingerprint():
    """Which is why a recording cannot verify a fix that rewrites a prompt - the
    limitation is a property of the design, so it is asserted rather than assumed."""
    base = {
        "model": "m",
        "messages": [{"role": "system", "content": "vecchio prompt"}],
        "response_format": {"json_schema": {"name": "Classification"}},
    }
    changed = {**base, "messages": [{"role": "system", "content": "nuovo prompt"}]}

    assert fingerprint(base) != fingerprint(changed)


# -- recording ------------------------------------------------------------


async def test_a_run_records_every_exchange_in_order(db_session, client, llm, settings):
    await seed_all(db_session)
    await create_onboarded_user(db_session, 42)
    recorder = Recorder(llm.gateway)
    _stage(llm)

    await _log_walnuts(client)

    assert len(recorder.cassette) == 3  # classify, extract, table selection
    assert [e.step for e in recorder.cassette.exchanges] == [
        "Classification",
        "FoodExtraction",
        "RowSelection",
    ]


async def test_a_recording_round_trips_through_a_file(db_session, client, llm, tmp_path):
    await seed_all(db_session)
    await create_onboarded_user(db_session, 42)
    recorder = Recorder(llm.gateway)
    _stage(llm)
    await _log_walnuts(client)

    path = recorder.cassette.save(tmp_path / "run.jsonl")
    reloaded = Cassette.load(path)

    assert len(reloaded) == len(recorder.cassette)
    assert reloaded.exchanges[0].fingerprint == recorder.cassette.exchanges[0].fingerprint


# -- replay ---------------------------------------------------------------


async def test_a_replay_reproduces_the_conversation_without_the_endpoint(
    db_session, client, llm, settings
):
    await seed_all(db_session)
    await create_onboarded_user(db_session, 42)
    recorder = Recorder(llm.gateway)
    _stage(llm)
    live = await _log_walnuts(client)

    # A fresh gateway with nothing behind it but the recording.
    replay_gateway = LLMGateway(settings)
    player = Player(replay_gateway, recorder.cassette)
    llm.gateway._client.chat.completions.create = replay_gateway._client.chat.completions.create

    replayed = await _log_walnuts(client)

    assert [m.text for m in replayed] == [m.text for m in live]
    # Not fully consumed, and correctly so: the live run populated the resolution
    # cache, so the replay resolves "noci" without the table-selection call. A clean
    # replay needs the starting state the recording was made against - which is why
    # the run report carries the seeded state alongside the recording.
    assert player.position == 2


async def test_a_changed_call_sequence_is_reported_as_a_divergence(
    db_session, client, llm, settings
):
    """The failure that matters: the code now calls the model differently, and the
    replay must say so rather than hand back an unrelated recorded answer."""
    await seed_all(db_session)
    await create_onboarded_user(db_session, 42)
    recorder = Recorder(llm.gateway)
    _stage(llm)
    await _log_walnuts(client, "noci")

    replay_gateway = LLMGateway(settings)
    Player(replay_gateway, recorder.cassette)
    llm.gateway._client.chat.completions.create = replay_gateway._client.chat.completions.create

    with pytest.raises(Divergence, match="diverges from the recording"):
        await _log_walnuts(client, "mele")  # a different message -> a different first call


async def test_more_calls_than_recorded_is_a_divergence(db_session, client, llm, settings):
    await seed_all(db_session)
    await create_onboarded_user(db_session, 42)

    cassette = Cassette()
    replay_gateway = LLMGateway(settings)
    Player(replay_gateway, cassette)
    llm.gateway._client.chat.completions.create = replay_gateway._client.chat.completions.create

    with pytest.raises(Divergence, match="only 0"):
        await _log_walnuts(client)


async def test_fewer_calls_than_recorded_is_a_divergence(db_session, client, llm, settings):
    await seed_all(db_session)
    await create_onboarded_user(db_session, 42)
    recorder = Recorder(llm.gateway)
    _stage(llm)
    await _log_walnuts(client)

    player = Player(LLMGateway(settings), recorder.cassette)
    player.position = 1

    with pytest.raises(Divergence, match="used 1 of 3"):
        player.assert_fully_consumed()


# -- budget ---------------------------------------------------------------


async def test_the_model_call_cap_stops_the_run_and_keeps_the_recording(
    db_session, client, llm
):
    await seed_all(db_session)
    await create_onboarded_user(db_session, 42)
    recorder = Recorder(llm.gateway, call_cap=2)
    _stage(llm)

    with pytest.raises(CallCapReached, match="cap of 2 model calls"):
        await _log_walnuts(client)

    # Whatever was learned before the budget ran out is still worth replaying.
    assert len(recorder.cassette) == 2


# -- the offline guard ----------------------------------------------------


async def test_an_unmarked_test_cannot_reach_the_endpoint(settings):
    """The `offline` fixture is autouse; this asserts it actually bites, rather than
    trusting that every future test remembers to stub the model."""
    gateway = LLMGateway(settings)

    with pytest.raises(AssertionError, match="tried to contact"):
        await gateway._client.chat.completions.create(
            model="m", messages=[{"role": "user", "content": "ciao"}]
        )


def test_live_runs_are_excluded_from_the_default_suite():
    import tomllib
    from pathlib import Path

    config = tomllib.loads(
        (Path(__file__).resolve().parent.parent / "pyproject.toml").read_text()
    )
    options = config["tool"]["pytest"]["ini_options"]

    assert "not live" in options["addopts"]
    assert any(marker.startswith("live:") for marker in options["markers"])
