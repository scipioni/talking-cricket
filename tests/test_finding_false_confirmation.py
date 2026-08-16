"""The finding the simulation harness found first, and the two defences against it
(specs/message-ingestion - A message carrying a loggable intent is not conversation,
Only the storing path may confirm a record).

The failure, from run 1 of `marco-three-days`: a message stating a meal, a weight and
a run came back classified as conversation, and the conversational reply announced

    "Ho registrato: cena (150g pasta con sugo + 200g pollo), peso (89.3 kg)
     e attivita (4 km corsa)."

while storing none of it - in the same turn as a notice saying part of the message had
*not* been registered. Nothing downstream can detect this. The user believes their day
is logged and it is not.

The recorded exchanges are embedded verbatim as constants rather than read from
`simulation-runs/`, which holds only the most recent run and has already been
overwritten twice. A finding is durable once it is in a test.
"""

from __future__ import annotations

from harness.invariants import claims_something_was_recorded
from harness.llm import ScriptedLLM
from harness.state import create_onboarded_user
from sqlalchemy import select

from calobot.persistence.models import FoodEntry
from calobot.persistence.seed import seed_all

MULTI_INTENT_MESSAGE = (
    "cena: 150g di pasta con sugo + 200g di pollo, peso oggi 89.3 kg, "
    "ho corso 4 km stamattina"
)

# Verbatim from the run-1 recording: the classifier called the whole message
# conversation while reporting the parts it had set aside. That contradiction is the
# routing signal this change acts on.
RECORDED_CLASSIFICATION = {
    "intent": "other",
    "ignored_text": "peso oggi 89.3 kg, ho corso 4 km stamattina",
}
RECORDED_REPLY = {
    "reply_text": (
        "Ciao! Ho registrato: cena (150g pasta con sugo + 200g pollo), peso (89.3 kg) "
        "e attività (4 km corsa). Se vuoi, posso aiutarti a calcolare le calorie o "
        "tenere traccia del tuo progresso. Dimmi come preferisci procedere!"
    )
}


def _install(run, monkeypatch) -> ScriptedLLM:
    return ScriptedLLM(run.client.settings).install(monkeypatch)


def test_the_recorded_reply_does_claim_a_record_was_made():
    """Pins the detector against the real text, so the tests below fail for the right
    reason rather than because the wording stopped matching."""
    assert claims_something_was_recorded(RECORDED_REPLY["reply_text"])


# -- the routing fix ------------------------------------------------------


async def test_the_contradiction_routes_the_message_to_the_log(db_session, run, monkeypatch):
    """The dominant content is the remainder, not the ignored text. Re-classifying the
    ignored text would have logged the weight and lost the meal."""
    await seed_all(db_session)
    await create_onboarded_user(db_session, 42)

    llm = _install(run, monkeypatch)
    llm.push(
        RECORDED_CLASSIFICATION,
        # the remainder, re-classified
        {"intent": "food", "ignored_text": None},
        {
            "items": [
                {
                    "description": "pasta con sugo",
                    "quantity_grams": 150,
                    "quantity_count": None,
                    "count_unit_hint": None,
                    "household_measure": None,
                    "preparation": None,
                    "preparation_material_but_unstated": False,
                }
            ],
            "when_text": None,
        },
        {"selected_candidate_id": None},
        {"kcal_per_100g": 150, "display_name_it": "pasta con sugo"},
    )

    sent = await run.say(MULTI_INTENT_MESSAGE)

    db_session.expire_all()
    entry = (await db_session.execute(select(FoodEntry))).scalars().one()
    assert entry.grams == 150
    # The ignored-text notice still tells the user what was left out.
    assert "non l'ho registrato" in sent[0].text
    run.assert_clean()


async def test_an_ordinary_greeting_costs_one_classification_and_one_reply(
    db_session, run, monkeypatch
):
    """The common path is untouched: no ignored text, so no contradiction, so no extra
    model call. If this ever needs a third response staged, the reroute has started
    firing on messages it should not."""
    await seed_all(db_session)
    await create_onboarded_user(db_session, 42)

    llm = _install(run, monkeypatch)
    llm.push(
        {"intent": "other", "ignored_text": None},
        {"reply_text": "Ciao! Dimmi pure cosa hai mangiato."},
    )

    await run.say("ciao come stai")

    assert len(llm.calls) == 2
    run.assert_clean()


async def test_a_contradiction_the_classifier_stands_by_falls_back_to_conversation(
    db_session, run, monkeypatch
):
    """Task 2.3: when the remainder is still not loggable, nothing is stored and the
    message is answered as conversation."""
    await seed_all(db_session)
    await create_onboarded_user(db_session, 42)

    llm = _install(run, monkeypatch)
    llm.push(
        {"intent": "other", "ignored_text": "una cosa a caso"},
        {"intent": "other", "ignored_text": None},  # remainder: still conversation
        {"reply_text": "Non ho capito bene, puoi ripetere?"},
    )

    await run.say("buonasera, una cosa a caso")

    db_session.expire_all()
    assert list((await db_session.execute(select(FoodEntry))).scalars()) == []
    run.assert_clean()


# -- the backstop ---------------------------------------------------------


async def test_a_conversational_reply_never_claims_a_record(db_session, run, monkeypatch):
    """The guard, isolated from routing: the classifier reports no ignored text, so
    nothing reroutes, and the reply still claims three records were made. Nothing was
    stored, so the claim must not reach the user."""
    await seed_all(db_session)
    await create_onboarded_user(db_session, 42)

    llm = _install(run, monkeypatch)
    llm.push({"intent": "other", "ignored_text": None}, RECORDED_REPLY)

    sent = await run.say(MULTI_INTENT_MESSAGE)

    assert not claims_something_was_recorded(sent[-1].text), (
        f"the claim reached the user: {sent[-1].text!r}"
    )
    run.assert_clean()


async def test_a_conversational_reply_making_no_claim_is_sent_unchanged(
    db_session, run, monkeypatch
):
    await seed_all(db_session)
    await create_onboarded_user(db_session, 42)

    llm = _install(run, monkeypatch)
    reply = "Ciao! Scrivimi cosa hai mangiato e lo aggiungo al diario."
    llm.push({"intent": "other", "ignored_text": None}, {"reply_text": reply})

    sent = await run.say("ciao")

    assert sent[-1].text == reply
    run.assert_clean()
