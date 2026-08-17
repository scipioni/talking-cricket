"""Direct tests of the advice agent module (tasks.md group 4), before pipeline
wiring. End-to-end scenarios through the transport double live in
test_advice_behaviour.py (tasks.md group 7)."""

from __future__ import annotations

import datetime as dt

from harness.llm import ToolCall, ToolCallsResponse
from harness.state import create_onboarded_user

from calobot.advice.agent import COULD_NOT_ANSWER_TEXT, UNFOUNDED_CLAIM_REPLACEMENT, answer
from calobot.llm.content import TextContent
from calobot.persistence.models import FoodEntry, Provenance
from calobot.persistence.seed import seed_all
from calobot.safety.medical import REFUSAL_TEXT
from calobot.telemetry.bus import event_bus
from calobot.telemetry.context import bind_telemetry_context


def _make_entry(user_id: int, description: str, grams: float, kcal_per_100g: float, when: dt.datetime):
    return FoodEntry(
        user_id=user_id,
        description=description,
        grams=grams,
        kcal_per_100g=kcal_per_100g,
        kcal=kcal_per_100g * grams / 100.0,
        provenance=Provenance.tabella,
        consumed_at=when,
    )


async def test_medical_question_is_refused_before_any_model_call(db_session, settings, llm):
    await seed_all(db_session)
    user = await create_onboarded_user(db_session, 42)

    reply = await answer(
        db_session,
        llm.gateway,
        user,
        settings.timezone,
        "ho l'anoressia, mi aiuti?",
        TextContent(text="ho l'anoressia, mi aiuti?"),
        "Grillo Parlante",
        max_rounds=4,
    )

    assert reply == REFUSAL_TEXT
    assert llm.calls == []


async def test_answer_uses_retrieved_totals(db_session, settings, llm):
    await seed_all(db_session)
    user = await create_onboarded_user(db_session, 42)
    db_session.add(
        _make_entry(user.id, "mela", 150, 52, dt.datetime(2026, 8, 17, 12, 0, tzinfo=dt.UTC))
    )
    await db_session.flush()

    llm.push_agent_turn(
        [[ToolCall(name="get_calorie_summary", arguments={"period": "day"})]],
        final={
            "answer_text": "Oggi hai mangiato circa 78 kcal.",
            "used_data": True,
            "declined_reason": None,
        },
    )

    reply = await answer(
        db_session,
        llm.gateway,
        user,
        settings.timezone,
        "quante calorie ho mangiato oggi?",
        TextContent(text="quante calorie ho mangiato oggi?"),
        "Grillo Parlante",
        max_rounds=4,
    )

    assert "78" in reply
    # gather round + no-more-tools signal + narration call
    assert len(llm.calls) == 3
    assert llm.calls[0]["tools"][0]["function"]["name"] == "get_calorie_summary"


async def test_greeting_needs_no_tool_call(db_session, settings, llm):
    await seed_all(db_session)
    user = await create_onboarded_user(db_session, 42)

    llm.push_agent_turn(
        [],
        final={"answer_text": "Ciao! Come posso aiutarti?", "used_data": False, "declined_reason": None},
    )

    reply = await answer(
        db_session, llm.gateway, user, settings.timezone, "ciao", TextContent(text="ciao"), "Grillo", max_rounds=4
    )

    assert "Ciao" in reply
    assert len(llm.calls) == 2  # one no-more-tools gather round, then narration


async def test_exhausted_round_bound_gives_up_gracefully(db_session, settings, llm):
    await seed_all(db_session)
    user = await create_onboarded_user(db_session, 42)

    for _ in range(4):
        llm.push(ToolCallsResponse(calls=[ToolCall(name="get_calorie_summary", arguments={"period": "day"})]))

    reply = await answer(
        db_session, llm.gateway, user, settings.timezone, "boh", TextContent(text="boh"), "Grillo", max_rounds=4
    )

    assert reply == COULD_NOT_ANSWER_TEXT


async def test_gather_and_narration_share_one_agent_turn_id(db_session, settings, llm):
    """design.md - Group an agent turn in telemetry with a correlation id: every
    llm_transaction from one advice interaction must carry the same agent_turn_id, so
    a monitor can tell which calls belong to the same user question."""
    await seed_all(db_session)
    user = await create_onboarded_user(db_session, 42)

    llm.push_agent_turn(
        [[ToolCall(name="get_calorie_summary", arguments={"period": "day"})]],
        final={"answer_text": "78 kcal", "used_data": True, "declined_reason": None},
    )

    queue = event_bus.subscribe()
    try:
        with bind_telemetry_context(chat_id=42):
            await answer(
                db_session,
                llm.gateway,
                user,
                settings.timezone,
                "quante calorie ho mangiato oggi?",
                TextContent(text="quante calorie ho mangiato oggi?"),
                "Grillo",
                max_rounds=4,
            )
    finally:
        event_bus.unsubscribe(queue)

    events = []
    while not queue.empty():
        events.append(queue.get_nowait())

    turn_ids = {e["agent_turn_id"] for e in events}
    assert len(turn_ids) == 1
    assert None not in turn_ids
    assert len(events) == 3  # gather round + no-more-tools round + narration


async def test_narration_claiming_a_record_is_replaced(db_session, settings, llm):
    await seed_all(db_session)
    user = await create_onboarded_user(db_session, 42)

    llm.push_agent_turn(
        [],
        final={
            "answer_text": "Ho registrato la tua colazione.",
            "used_data": False,
            "declined_reason": None,
        },
    )

    reply = await answer(
        db_session, llm.gateway, user, settings.timezone, "ciao", TextContent(text="ciao"), "Grillo", max_rounds=4
    )

    assert reply == UNFOUNDED_CLAIM_REPLACEMENT
