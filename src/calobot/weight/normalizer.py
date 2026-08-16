"""Normalizes conversational weight statements into a precise kg value via the LLM.
See specs/weight-logging - Conversational value normalization: fractional word forms,
unitless values, and values relative to the last recorded weight."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from calobot.llm.content import TextContent
from calobot.llm.gateway import LLMGateway

SYSTEM_PROMPT = """\
Interpreta il testo che descrive il peso corporeo di un utente italiano.
Se il testo indica un valore assoluto (es. "78 e mezzo", "77,4", "peso 78kg"),
restituisci kg_absolute con il valore in kg e lascia null delta_kg/direction.
Se il testo indica una VARIAZIONE relativa al peso precedente (es. "ho perso
mezzo chilo", "sono ingrassato di un chilo"), restituisci delta_kg (sempre
positivo, l'entità del cambiamento) e direction ("loss" o "gain"), lasciando
null kg_absolute.
"""


class WeightNormalization(BaseModel):
    kg_absolute: float | None = Field(default=None, ge=0, le=500)
    delta_kg: float | None = Field(default=None, ge=0, le=100)
    direction: Literal["gain", "loss"] | None = None


async def normalize_weight_text(gateway: LLMGateway, value_text: str) -> WeightNormalization:
    return await gateway.call_structured(
        step="extract",
        system_prompt=SYSTEM_PROMPT,
        content=TextContent(text=value_text),
        schema=WeightNormalization,
    )
