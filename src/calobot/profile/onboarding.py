"""Onboarding: conversational field collection over the same draft machinery used
for logging (design.md - onboarding is 'just another pending-draft flow'). One LLM
call per message extracts whichever profile fields are present in free text; a
deterministic parser (parsing.py) then turns each into a typed, validated value -
same LLM-understands / code-validates split as the rest of the system.

See specs/user-profile - Onboarding conversation, Profile fields."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from calobot.llm.content import MessageContent
from calobot.llm.gateway import LLMGateway
from calobot.profile import parsing

ONBOARDING_FIELDS = [
    "sesso",
    "data_nascita",
    "altezza_cm",
    "peso_attuale_kg",
    "peso_obiettivo_kg",
    "livello_attivita",
    "ritmo",
]

QUESTIONS: dict[str, str] = {
    "sesso": "Per calcolare il tuo fabbisogno calorico, sei uomo o donna?",
    "data_nascita": "Quando sei nato/a? (es. 15/06/1990, oppure semplicemente la tua età)",
    "altezza_cm": "Quanto sei alto/a, in cm?",
    "peso_attuale_kg": "Quanto pesi attualmente, in kg?",
    "peso_obiettivo_kg": "Qual è il tuo peso obiettivo, in kg?",
    "livello_attivita": "Come definiresti il tuo livello di attività abituale?",
    "ritmo": "Con che ritmo vorresti raggiungere il tuo obiettivo?",
}

OPTIONS: dict[str, list[str]] = {
    "sesso": ["maschio", "femmina"],
    "livello_attivita": ["sedentario", "leggero", "moderato", "attivo", "molto_attivo"],
    "ritmo": ["lento", "moderato", "sostenuto"],
}

RANGE_ERRORS = {
    "altezza_cm": "L'altezza deve essere tra 100 e 250 cm.",
    "peso_attuale_kg": "Il peso deve essere tra 30 e 400 kg.",
    "peso_obiettivo_kg": "Il peso obiettivo deve essere tra 30 e 400 kg.",
}


class OnboardingExtraction(BaseModel):
    sesso_text: str | None = None
    data_nascita_text: str | None = None
    altezza_text: str | None = None
    peso_attuale_text: str | None = None
    peso_obiettivo_text: str | None = None
    livello_attivita_text: str | None = None
    ritmo_text: str | None = None


ONBOARDING_PROMPT = """\
L'utente sta completando la registrazione a un bot di tracciamento nutrizionale.
Estrai dal messaggio, se presenti, i valori verbatim (senza interpretarli) per:
sesso, data di nascita o età, altezza, peso attuale, peso obiettivo, livello di
attività abituale, ritmo desiderato per raggiungere l'obiettivo. Lascia null i
campi non menzionati nel messaggio.
"""


async def extract_onboarding_fields(
    gateway: LLMGateway, content: MessageContent
) -> OnboardingExtraction:
    return await gateway.call_structured(
        step="extract",
        system_prompt=ONBOARDING_PROMPT,
        content=content,
        schema=OnboardingExtraction,
    )


def parse_and_validate(extraction: OnboardingExtraction) -> tuple[dict[str, Any], list[str]]:
    """Returns (parsed_values, error_messages). Parsed values use the field keys in
    ONBOARDING_FIELDS; only successfully parsed and in-range values are included."""
    parsed: dict[str, Any] = {}
    errors: list[str] = []

    if extraction.sesso_text:
        sesso = parsing.parse_sesso(extraction.sesso_text)
        if sesso:
            parsed["sesso"] = sesso

    if extraction.data_nascita_text:
        data_nascita = parsing.parse_data_nascita(extraction.data_nascita_text)
        if data_nascita:
            parsed["data_nascita"] = data_nascita

    if extraction.altezza_text:
        altezza = parsing.parse_height_cm(extraction.altezza_text)
        if altezza is not None:
            if 100 <= altezza <= 250:
                parsed["altezza_cm"] = altezza
            else:
                errors.append(RANGE_ERRORS["altezza_cm"])

    if extraction.peso_attuale_text:
        peso_attuale = parsing.parse_weight_kg(extraction.peso_attuale_text)
        if peso_attuale is not None:
            if 30 <= peso_attuale <= 400:
                parsed["peso_attuale_kg"] = peso_attuale
            else:
                errors.append(RANGE_ERRORS["peso_attuale_kg"])

    if extraction.peso_obiettivo_text:
        peso_obiettivo = parsing.parse_weight_kg(extraction.peso_obiettivo_text)
        if peso_obiettivo is not None:
            if 30 <= peso_obiettivo <= 400:
                parsed["peso_obiettivo_kg"] = peso_obiettivo
            else:
                errors.append(RANGE_ERRORS["peso_obiettivo_kg"])

    if extraction.livello_attivita_text:
        livello = parsing.parse_livello_attivita(extraction.livello_attivita_text)
        if livello:
            parsed["livello_attivita"] = livello

    if extraction.ritmo_text:
        ritmo = parsing.parse_ritmo(extraction.ritmo_text)
        if ritmo:
            parsed["ritmo"] = ritmo

    return parsed, errors


def first_missing_field(known: dict[str, Any], has_weight_entry: bool) -> str | None:
    for field in ONBOARDING_FIELDS:
        if field == "peso_attuale_kg":
            if not has_weight_entry and "peso_attuale_kg" not in known:
                return field
            continue
        if field not in known:
            return field
    return None
