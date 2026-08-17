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

FIELD_TEXT_ATTR: dict[str, str] = {
    "sesso": "sesso_text",
    "data_nascita": "data_nascita_text",
    "altezza_cm": "altezza_text",
    "peso_attuale_kg": "peso_attuale_text",
    "peso_obiettivo_kg": "peso_obiettivo_text",
    "livello_attivita": "livello_attivita_text",
    "ritmo": "ritmo_text",
}

FIELD_PARSERS: dict[str, Any] = {
    "sesso": parsing.parse_sesso,
    "data_nascita": parsing.parse_data_nascita,
    "altezza_cm": parsing.parse_height_cm,
    "peso_attuale_kg": parsing.parse_weight_kg,
    "peso_obiettivo_kg": parsing.parse_weight_kg,
    "livello_attivita": parsing.parse_livello_attivita,
    "ritmo": parsing.parse_ritmo,
}

FIELD_RANGES: dict[str, tuple[float, float]] = {
    "altezza_cm": (100, 250),
    "peso_attuale_kg": (30, 400),
    "peso_obiettivo_kg": (30, 400),
}


def _prompt_for(expected_field: str | None) -> str:
    if expected_field is None:
        return ONBOARDING_PROMPT
    return (
        ONBOARDING_PROMPT
        + f'\nIn particolare, è appena stata posta questa domanda: '
        f'"{QUESTIONS[expected_field]}". Se il messaggio è una risposta diretta a '
        f"questa domanda ma non menziona esplicitamente un'unità o un campo (es. un "
        f"numero nudo), attribuiscilo comunque al campo atteso ({expected_field})."
    )


async def extract_onboarding_fields(
    gateway: LLMGateway, content: MessageContent, expected_field: str | None = None
) -> OnboardingExtraction:
    return await gateway.call_structured(
        step="extract",
        system_prompt=_prompt_for(expected_field),
        content=content,
        schema=OnboardingExtraction,
    )


def parse_field_raw(field: str, text: str) -> tuple[Any | None, str | None]:
    """Deterministically parses raw text for a single onboarding field. Returns
    (value, error_message); value is None if unparseable or out of range."""
    value = FIELD_PARSERS[field](text)
    if value is None:
        return None, None
    range_ = FIELD_RANGES.get(field)
    if range_ is not None and not (range_[0] <= value <= range_[1]):
        return None, RANGE_ERRORS[field]
    return value, None


def parse_and_validate(extraction: OnboardingExtraction) -> tuple[dict[str, Any], list[str]]:
    """Returns (parsed_values, error_messages). Parsed values use the field keys in
    ONBOARDING_FIELDS; only successfully parsed and in-range values are included."""
    parsed: dict[str, Any] = {}
    errors: list[str] = []

    for field in ONBOARDING_FIELDS:
        text = getattr(extraction, FIELD_TEXT_ATTR[field])
        if not text:
            continue
        value, error = parse_field_raw(field, text)
        if error:
            errors.append(error)
        elif value is not None:
            parsed[field] = value

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
