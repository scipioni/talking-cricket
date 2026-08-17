"""Nutrition label reading (tasks.md 3.1-3.6). The label path bypasses the food
composition table and the LLM estimator entirely (design.md - Label reading writes
straight into the resolution cache): it reads energy per 100 g directly off the
package and writes it into the resolution cache with `etichetta` provenance,
which is why it needs its own plausibility bounds rather than reusing the food
resolver's estimate path."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from calobot.food.resolver import (
    MAX_PLAUSIBLE_KCAL_PER_100G,
    MIN_PLAUSIBLE_KCAL_PER_100G,
    normalize_description,
    write_resolution,
)
from calobot.llm.content import ImageContent
from calobot.llm.gateway import LLMGateway
from calobot.persistence.models import Provenance

SYSTEM_PROMPT = """\
Leggi la tabella nutrizionale nella foto di un'etichetta alimentare.
product_name_it: il nome del prodotto se leggibile, altrimenti null.
energy_value: il valore numerico dell'energia così come scritto (per 100g/100ml se
presente, altrimenti per porzione), altrimenti null se non leggibile con sicurezza.
energy_unit: "kcal" o "kj", l'unità in cui è scritto il valore energetico.
per_portion: true se il valore letto è per porzione e non per 100g/100ml.
portion_grams: il peso della porzione in grammi, SOLO se energy_value è per
porzione e il peso della porzione è scritto sull'etichetta, altrimenti null.
"""


class LabelReading(BaseModel):
    product_name_it: str | None = None
    energy_value: float | None = Field(default=None, ge=0)
    energy_unit: Literal["kcal", "kj"] = "kcal"
    per_portion: bool = False
    portion_grams: float | None = Field(default=None, gt=0)


class LabelUnreadable(Exception):
    """The energy value could not be read with confidence, or a per-portion label
    didn't state the portion weight (specs/photo-input - Label illegible)."""


class LabelResult(BaseModel):
    kcal_per_100g: float
    display_name_it: str


KJ_PER_KCAL = 4.184


async def read_label(gateway: LLMGateway, image: ImageContent) -> LabelReading:
    # Prefer the higher-resolution rendering when available (tasks.md 1.2).
    content = image
    if image.label_base64_data is not None and image.label_base64_data != image.base64_data:
        content = ImageContent(
            base64_data=image.label_base64_data, mime_type=image.mime_type, caption=image.caption
        )
    return await gateway.call_structured(
        step="extract", system_prompt=SYSTEM_PROMPT, content=content, schema=LabelReading
    )


def interpret_label(reading: LabelReading) -> LabelResult:
    """Pure conversion/validation, kept separate from the LLM call so it's testable
    without a gateway (tasks.md 3.2-3.4)."""
    if reading.energy_value is None:
        raise LabelUnreadable("energy value not read")

    value = reading.energy_value
    if reading.energy_unit == "kj":
        value = value / KJ_PER_KCAL

    if reading.per_portion:
        if reading.portion_grams is None:
            raise LabelUnreadable("per-portion label without a stated portion weight")
        value = value * 100.0 / reading.portion_grams

    if not (MIN_PLAUSIBLE_KCAL_PER_100G <= value <= MAX_PLAUSIBLE_KCAL_PER_100G):
        raise LabelUnreadable(f"implausible energy density: {value} kcal/100g")

    return LabelResult(
        kcal_per_100g=value,
        display_name_it=reading.product_name_it or "prodotto confezionato",
    )


async def resolve_from_label(
    session: AsyncSession, gateway: LLMGateway, image: ImageContent
) -> LabelResult:
    """Reads the label, validates it, and writes it into the resolution cache with
    `etichetta` provenance (tasks.md 3.5), respecting the cross-provenance trust
    ordering (design.md - Provenance gains two values...). Raises LabelUnreadable
    on anything that should be reported back to the user rather than stored."""
    reading = await read_label(gateway, image)
    result = interpret_label(reading)

    key = normalize_description(result.display_name_it)
    await write_resolution(
        session,
        key=key,
        kcal_per_100g=result.kcal_per_100g,
        provenance=Provenance.etichetta,
        display_name_it=result.display_name_it,
    )
    return result
