"""Conversational replies for the 'other' intent. See specs/message-ingestion -
Conversational message: answered within the safety limits of user-profile, without
creating any entry. The medical guard in medical.py runs first and never reaches
the model (design.md - Safety)."""

from __future__ import annotations

import logging

from pydantic import BaseModel

from calobot.llm.content import MessageContent
from calobot.llm.gateway import LLMGateway
from calobot.safety.claims import asserts_a_record
from calobot.safety.medical import REFUSAL_TEXT, is_medical_topic

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
Sei Calobot, un bot italiano di tracciamento nutrizionale (non un consulente
medico). Rispondi in modo breve e cordiale in italiano. NON dare consigli
medici, clinici, su farmaci, diagnosi o disturbi alimentari: se l'utente
chiede questo, rispondi che non sei uno strumento medico e suggerisci di
rivolgersi a un professionista, senza aggiungere altro. Non inventare mai
un'affermazione clinica. Il tuo scopo è aiutare l'utente a registrare cibo,
peso e attività fisica, e spiegare come farlo se richiesto.
"""


class ConversationalReply(BaseModel):
    reply_text: str


UNFOUNDED_CLAIM_REPLACEMENT = (
    "Non ho registrato niente: non sono riuscito a capire cosa volevi tracciare. "
    'Puoi riscrivermelo? Per esempio: "ho mangiato 150g di pasta".'
)


async def handle_other(gateway: LLMGateway, text: str, content: MessageContent) -> str:
    if is_medical_topic(text):
        return REFUSAL_TEXT

    result = await gateway.call_structured(
        step="extract",
        system_prompt=SYSTEM_PROMPT,
        content=content,
        schema=ConversationalReply,
    )
    reply = result.reply_text

    # This branch stores nothing by construction - it is the one intent that creates
    # no entry - so any claim it makes that something was recorded is false. The
    # prompt above already forbids inventing claims and the model did it anyway
    # (specs/message-ingestion - Only the storing path may confirm a record), so the
    # check is deterministic and runs after generation.
    #
    # Replaced wholesale rather than edited: the reply was generated on a false
    # premise, and trimming the offending sentence leaves text that is still wrong
    # about what just happened.
    if asserts_a_record(reply):
        logger.warning(
            "suppressed a conversational reply claiming a record was made: %r", reply
        )
        return UNFOUNDED_CLAIM_REPLACEMENT

    return reply
