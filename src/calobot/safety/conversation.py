"""Conversational replies for the 'other' intent. See specs/message-ingestion -
Conversational message: answered within the safety limits of user-profile, without
creating any entry. The medical guard in medical.py runs first and never reaches
the model (design.md - Safety)."""

from __future__ import annotations

from pydantic import BaseModel

from calobot.llm.content import MessageContent
from calobot.llm.gateway import LLMGateway
from calobot.safety.medical import REFUSAL_TEXT, is_medical_topic

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


async def handle_other(gateway: LLMGateway, text: str, content: MessageContent) -> str:
    if is_medical_topic(text):
        return REFUSAL_TEXT

    result = await gateway.call_structured(
        step="extract",
        system_prompt=SYSTEM_PROMPT,
        content=content,
        schema=ConversationalReply,
    )
    return result.reply_text
