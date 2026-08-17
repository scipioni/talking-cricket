"""The claim guard (specs/message-ingestion - Only the storing path may confirm a
record).

Two implementations of "does this text claim a record" exist on purpose: the
production guard in `calobot/safety/claims.py` and the harness invariant in
`tests/harness/invariants.py`. They are deliberately not shared - if one has a
blind spot, the other still sees. The last test here checks they agree on the cases
that matter, which is how a divergence surfaces as a failure rather than as silence.
"""

from __future__ import annotations

import pytest
from harness.invariants import claims_something_was_recorded as harness_detector
from harness.state import create_onboarded_user, food_extraction
from sqlalchemy import select

from calobot.advice.agent import UNFOUNDED_CLAIM_REPLACEMENT as ADVICE_UNFOUNDED_CLAIM_REPLACEMENT
from calobot.persistence.models import FoodEntry
from calobot.persistence.seed import seed_all
from calobot.safety.claims import asserts_a_record
from calobot.safety.conversation import UNFOUNDED_CLAIM_REPLACEMENT

CLAIMS = [
    "Ho registrato: cena (150g pasta con sugo + 200g pollo), peso (89.3 kg) e attività (4 km corsa).",
    "Registrato: pasta al pesto 120g - 364 kcal",
    "Peso registrato: 89.5 kg",
    "Ok, ho salvato tutto.",
    "L'ho aggiunta al diario di oggi.",
    # Added for the advice agent (specs/advice-agent - "Answer claims a record was
    # made" covers recorded, changed or removed alike): a false claim of deletion or
    # modification is the same failure as a false claim of creation.
    "Ho eliminato la cena di oggi.",
    "Ho cancellato la voce del pranzo.",
    "Ho modificato il tuo obiettivo di peso a 60 kg.",
]

NOT_CLAIMS = [
    "Ho notato anche: \"x\" - non l'ho registrato, scrivimelo di nuovo separatamente.",
    # Flagged as a claim by a live run, wrongly: it is the correction path's question,
    # where the participle describes an existing entry rather than asserting a new one.
    # Both detectors missed it, and only the guard's placement kept it out of
    # production - so it is pinned here for both.
    "Intendi correggere l'ultima voce registrata o è una voce nuova?",
    "Vuoi vedere la voce registrata? Dimmi pure.",
    "Non ho registrato niente: non sono riuscito a capire cosa volevi tracciare.",
    "Quanto pesava la porzione di riso?",
    "Il peso indicato non è in un intervallo plausibile.",
    "Ciao! Scrivimi cosa hai mangiato e lo aggiungo al diario.",
    "Non ho capito. Quanto pesava la porzione?",
    "Non posso eliminare o modificare nulla: posso solo leggere i tuoi dati.",
    "Vuoi che ti spieghi come eliminare una voce dal diario?",
]


@pytest.mark.parametrize("text", CLAIMS)
def test_an_assertion_of_a_record_is_detected(text):
    assert asserts_a_record(text)


@pytest.mark.parametrize("text", NOT_CLAIMS)
def test_a_negated_or_unrelated_reply_is_not_a_claim(text):
    assert not asserts_a_record(text)


def test_a_claim_followed_by_a_question_is_still_a_claim():
    """The question rule scopes to its own sentence. Skipping the whole reply because
    it ends in a question mark would be the opposite failure."""
    assert asserts_a_record("Ho registrato la cena. Vuoi correggerla?")
    assert harness_detector("Ho registrato la cena. Vuoi correggerla?")


def test_negation_is_scoped_to_its_own_clause():
    """The ignored-text notice and a real confirmation can appear in one turn. Scoping
    negation to the clause is what keeps the first from masking the second."""
    assert asserts_a_record("non l'ho registrato, ma ho salvato la cena")


def test_the_replacement_message_does_not_itself_claim_a_record():
    """It would be an unfortunate loop."""
    assert not asserts_a_record(UNFOUNDED_CLAIM_REPLACEMENT)


def test_the_advice_agents_replacement_message_does_not_itself_claim_a_record():
    """Same loop, guarded the same way, for the advice agent's own replacement text."""
    assert not asserts_a_record(ADVICE_UNFOUNDED_CLAIM_REPLACEMENT)
    assert not harness_detector(ADVICE_UNFOUNDED_CLAIM_REPLACEMENT)


# -- scoping --------------------------------------------------------------


async def test_a_genuine_confirmation_is_never_examined_or_altered(db_session, run, llm):
    """Task 3.8: the guard lives in the conversational branch, which stores nothing by
    construction. A reply from the storing path is not a candidate, so a real
    confirmation cannot be suppressed - even though its text would match."""
    await seed_all(db_session)
    await create_onboarded_user(db_session, 42)

    llm.push(
        {"intent": "food", "ignored_text": None},
        food_extraction(description="noci", quantity_grams=10),
        {"selected_candidate_id": 1},
    )

    sent = await run.say("ho mangiato 10g di noci")

    assert "Registrato" in sent[-1].text
    assert asserts_a_record(sent[-1].text)  # it does claim - correctly
    db_session.expire_all()
    assert len(list((await db_session.execute(select(FoodEntry))).scalars())) == 1
    run.assert_clean()


# -- the two implementations ----------------------------------------------


@pytest.mark.parametrize("text", CLAIMS + NOT_CLAIMS)
def test_the_guard_and_the_harness_invariant_agree(text):
    """Not a licence to merge them. They are written differently on purpose - this
    asserts that the difference has not yet produced a disagreement on a case anyone
    has thought of, which is exactly as far as the guarantee goes."""
    assert asserts_a_record(text) == harness_detector(text)
