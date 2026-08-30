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


# -- prompt composition: one fragment per derived situation (design.md - Decision 2) --


def test_narrate_prompt_appends_nothing_when_no_suggestion_was_asked_for():
    from calobot.advice.agent import _SUGGESTION_FRAGMENTS, _narrate_system_prompt

    prompt = _narrate_system_prompt("Grillo Parlante", None)

    for fragment in _SUGGESTION_FRAGMENTS.values():
        assert fragment not in prompt


def test_narrate_prompt_appends_exactly_one_fragment_per_mode():
    from calobot.advice.agent import _SUGGESTION_FRAGMENTS, _narrate_system_prompt

    for mode, expected in _SUGGESTION_FRAGMENTS.items():
        prompt = _narrate_system_prompt("Grillo Parlante", mode)
        assert expected in prompt
        others = [f for m, f in _SUGGESTION_FRAGMENTS.items() if m != mode]
        for other in others:
            assert other not in prompt


def test_base_prompt_carries_no_branch_logic():
    """tasks.md 4.2: the numbered if/else prose is gone from the shared prompt - the
    branch is decided in tools.py and expressed by which fragment is appended."""
    from calobot.advice.agent import _narrate_base_prompt

    base = _narrate_base_prompt("Grillo Parlante")

    assert "remaining_today_kcal" not in base
    assert "RICETTE" not in base
    assert "NEGATIVE" not in base


def test_gather_prompt_no_longer_demands_two_separate_retrievals():
    """tasks.md 4.1: one tool replaces the 'usa SEMPRE both tools' instruction."""
    from calobot.advice.agent import GATHER_SYSTEM_PROMPT

    assert "usa SEMPRE" not in GATHER_SYSTEM_PROMPT
    assert "get_meal_suggestion_context" in GATHER_SYSTEM_PROMPT


def test_over_budget_fragment_states_the_ceiling_and_forbids_fasting():
    """specs/advice-agent - Empathetic counseling for budget deficits."""
    from calobot.advice.agent import SUGGESTION_FRAGMENT_OVER_BUDGET

    lowered = SUGGESTION_FRAGMENT_OVER_BUDGET.lower()
    assert "ceiling_kcal" in lowered
    assert "digiun" in lowered
    assert "100 kcal" in lowered


def test_no_budget_fragment_states_no_remaining_balance():
    """specs/advice-agent - Budget-appropriate meal and recipe suggestions, scenario
    'Profile incomplete so no budget exists'."""
    from calobot.advice.agent import SUGGESTION_FRAGMENT_NO_BUDGET

    assert "remaining_today_kcal" not in SUGGESTION_FRAGMENT_NO_BUDGET
    assert "non e' calcolabile" in SUGGESTION_FRAGMENT_NO_BUDGET


# -- the guard on a composed suggestion (specs/advice-agent - An answer inconsistent
# -- with the determined situation is not delivered) ---------------------------------


def _derived(mode, ceiling=None, remaining=None):
    from calobot.advice.agent import _DerivedSuggestion

    return _DerivedSuggestion(mode=mode, ceiling_kcal=ceiling, remaining_kcal=remaining)


def _answer_declaring(mode, kcal=None):
    from calobot.advice.agent import AdviceAnswer

    return AdviceAnswer(
        answer_text="qualcosa", used_data=True, suggestion_mode=mode, suggested_kcal_total=kcal
    )


def test_guard_passes_an_answer_matching_the_derived_situation():
    from calobot.advice.agent import _suggestion_is_inconsistent

    derived = _derived("over_budget", ceiling=100, remaining=-150)
    assert _suggestion_is_inconsistent(_answer_declaring("over_budget", 60), derived) is False


def test_guard_catches_an_answer_narrating_the_wrong_situation():
    from calobot.advice.agent import _suggestion_is_inconsistent

    derived = _derived("over_budget", ceiling=100, remaining=-150)
    assert _suggestion_is_inconsistent(_answer_declaring("within_budget", 400), derived) is True


def test_guard_catches_a_suggestion_above_the_ceiling():
    from calobot.advice.agent import _suggestion_is_inconsistent

    derived = _derived("over_budget", ceiling=100, remaining=0)
    assert _suggestion_is_inconsistent(_answer_declaring("over_budget", 400), derived) is True


def test_guard_ignores_the_ceiling_when_the_balance_is_positive():
    """A within-budget ceiling is the remaining balance itself, and the figure the
    model declares for a proposed dish is an estimate (design.md - Decision 5), so it
    is not grounds for suppression."""
    from calobot.advice.agent import _suggestion_is_inconsistent

    derived = _derived("within_budget", ceiling=400, remaining=400)
    assert _suggestion_is_inconsistent(_answer_declaring("within_budget", 420), derived) is False


def test_fallback_texts_read_as_answers_not_diagnostics():
    """specs/advice-agent - scenario 'Substituted reply reads as an answer'."""
    from calobot.advice.agent import SUGGESTION_FALLBACK_TEXT, _suggestion_fallback

    for mode in SUGGESTION_FALLBACK_TEXT:
        text = _suggestion_fallback(mode, 400)
        lowered = text.lower()
        for word in ("errore", "non sono riuscito", "riformulare", "non ho capito"):
            assert word not in lowered
        assert len(text) > 40

    assert "400" in _suggestion_fallback("within_budget", 400)


def test_fallback_for_an_exceeded_budget_does_not_tell_the_user_to_skip_a_meal():
    from calobot.advice.agent import _suggestion_fallback

    text = _suggestion_fallback("over_budget", -150).lower()

    # Skipping is mentioned only to advise against it, so assert the negation rather
    # than banning the word.
    assert "non e' il caso di saltare il pasto" in text
    assert "digiun" not in text
    assert "brodo" in text


async def test_incomplete_profile_selects_the_no_budget_fragment(db_session, settings, llm):
    """specs/advice-agent - Budget-appropriate meal and recipe suggestions, scenario
    'Profile incomplete so no budget exists'.

    Tested at this layer rather than through the transport: a user whose profile is
    incomplete is routed to onboarding before a message can reach the advice agent, so
    `no_budget` is only reachable by calling the agent directly. The branch is kept
    because it is the same defensive shape `get_profile_and_budget` already has for a
    missing budget.
    """
    from calobot.advice.agent import SUGGESTION_FRAGMENT_NO_BUDGET
    from calobot.persistence.repository import create_user

    await seed_all(db_session)
    user = await create_user(db_session, telegram_user_id=77)
    await db_session.flush()

    llm.push_agent_turn(
        [[ToolCall(name="get_meal_suggestion_context", arguments={})]],
        final={
            "answer_text": "Ti propongo del pollo alla piastra con verdure.",
            "used_data": True,
            "declined_reason": None,
            "suggestion_mode": "no_budget",
            "suggested_kcal_total": 300,
        },
    )

    reply = await answer(
        db_session,
        llm.gateway,
        user,
        settings.timezone,
        "cosa posso mangiare stasera?",
        TextContent(text="cosa posso mangiare stasera?"),
        "Grillo Parlante",
        max_rounds=4,
    )

    narration_prompt = llm.calls[-1]["messages"][0]["content"]
    assert SUGGESTION_FRAGMENT_NO_BUDGET in narration_prompt
    assert "pollo" in reply
