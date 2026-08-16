"""The simulated user (group 7).

The observation boundary is the test that matters. If the agent could see the
database, it could word its next message so as to route around a bug a real user
would have walked straight into - and the run would pass for the wrong reason.
"""

from __future__ import annotations

from harness.scenario import ALL_BEHAVIOURS, COOPERATIVE, HOSTILE
from harness.transport import SentMessage
from harness.user_agent import BEHAVIOUR_INSTRUCTIONS, SimulatedUser, observable_transcript


def _reply(text: str, options: dict[str, str] | None = None) -> SentMessage:
    return SentMessage(message_id=1, chat_id=42, text=text, options=options or {})


# -- observation boundary -------------------------------------------------


def test_the_agent_sees_only_replies_and_offered_labels():
    transcript = observable_transcript(
        [
            _reply("Quanto era la porzione?", {"piccolo (~80g)": "ans:piccolo (~80g)"}),
            _reply("Registrato: riso 150g - 195 kcal"),
        ]
    )

    assert "Quanto era la porzione?" in transcript
    assert "piccolo (~80g)" in transcript
    # The action data behind a label is not something a user can see.
    assert "ans:" not in transcript


def test_the_transcript_carries_no_identifiers():
    transcript = observable_transcript([_reply("Registrato: riso 150g")])

    assert "message_id" not in transcript
    assert "entry" not in transcript.lower()


def test_an_empty_conversation_is_described_not_faked():
    assert "non è ancora iniziata" in observable_transcript([])


def test_only_the_recent_conversation_is_shown():
    replies = [_reply(f"messaggio {n}") for n in range(20)]

    transcript = observable_transcript(replies, limit=3)

    assert "messaggio 19" in transcript
    assert "messaggio 5" not in transcript


async def test_the_agent_is_never_handed_a_session(agent_llm):
    """Structural: the utterance call takes the persona, the intent and the visible
    conversation. There is no parameter through which state could arrive."""
    import inspect

    parameters = set(inspect.signature(SimulatedUser.utterance).parameters)

    assert parameters == {"self", "intent", "behaviour", "replies"}


# -- repertoire -----------------------------------------------------------


def test_every_declared_behaviour_has_an_instruction():
    assert set(BEHAVIOUR_INSTRUCTIONS) == set(ALL_BEHAVIOURS)


def test_hostility_is_a_dial_not_a_mode():
    cooperative = SimulatedUser(gateway=None, persona=COOPERATIVE)  # type: ignore[arg-type]
    hostile = SimulatedUser(gateway=None, persona=HOSTILE)  # type: ignore[arg-type]

    assert not COOPERATIVE.is_hostile
    assert HOSTILE.is_hostile
    # The cooperative persona is the same machinery with an empty repertoire.
    assert cooperative.supports("straight")
    assert not cooperative.supports("non-answer")
    assert hostile.supports("non-answer")


# -- rendering ------------------------------------------------------------


async def test_the_intent_and_the_behaviour_both_reach_the_model(agent_llm):
    agent = SimulatedUser(agent_llm.gateway, HOSTILE)
    agent_llm.push({"message": "boh"})

    said = await agent.utterance(
        intent="non rispondere alla domanda sulla porzione",
        behaviour="non-answer",
        replies=[_reply("Quanto era la porzione?", {"medio": "ans:medio"})],
    )

    assert said == "boh"
    sent = agent_llm.calls[0]["messages"]
    system, user = sent[0]["content"], sent[1]["content"][0]["text"]
    assert HOSTILE.description in system
    assert BEHAVIOUR_INSTRUCTIONS["non-answer"] in system
    assert "non rispondere alla domanda sulla porzione" in user
    assert "Quanto era la porzione?" in user


async def test_the_agent_reacts_to_an_unanticipated_question(agent_llm):
    """A question the scenario did not foresee must not fail the scenario: the agent
    answers it in character."""
    agent = SimulatedUser(agent_llm.gateway, HOSTILE)
    agent_llm.push({"message": "e che ne so"})

    said = await agent.utterance(
        intent="dire che hai mangiato del riso",
        behaviour="non-answer",
        replies=[_reply("Con che condimento?")],
    )

    assert said
    assert "Con che condimento?" in agent_llm.calls[0]["messages"][1]["content"][0]["text"]


async def test_surrounding_whitespace_is_stripped(agent_llm):
    agent = SimulatedUser(agent_llm.gateway, COOPERATIVE)
    agent_llm.push({"message": "  ho mangiato una mela  "})

    assert await agent.utterance(intent="log an apple", behaviour="straight", replies=[]) == (
        "ho mangiato una mela"
    )
