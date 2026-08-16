"""Turns a FoodExtraction into per-item drafts, decides what's still missing, and
finalizes items into stored entries. See specs/food-logging and specs/message-ingestion
- Draft completeness and the clarification loop."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from calobot.food.quantities import PORTION_OPTIONS_G, resolve_quantity
from calobot.food.resolver import resolve_food_energy
from calobot.ingestion.quantities import is_real_quantity
from calobot.ingestion.schemas import FoodExtraction, FoodItemExtraction
from calobot.llm.gateway import LLMGateway
from calobot.persistence.models import FoodEntry, Provenance
from calobot.persistence.timeutil import utcnow

PREPARATION_OPTIONS = ["fritto", "bollito", "al forno", "alla griglia"]


@dataclass(frozen=True)
class ClarificationNeeded:
    field: str
    question_text: str
    options: list[str]


@dataclass(frozen=True)
class FinalizedFood:
    entry: FoodEntry
    is_estimate: bool
    quantity_is_estimated_from_count: bool


def build_items(extraction: FoodExtraction) -> list[dict[str, Any]]:
    items = []
    for food_item in extraction.items:
        item = food_item.model_dump()
        item["when_text"] = extraction.when_text
        item["resolved"] = {}
        items.append(item)
    return items


def _as_extraction_fields(item: dict[str, Any]) -> FoodItemExtraction:
    return FoodItemExtraction(
        description=item["description"],
        quantity_grams=item.get("quantity_grams"),
        quantity_count=item.get("quantity_count"),
        count_unit_hint=item.get("count_unit_hint"),
        household_measure=item.get("household_measure"),
        preparation=item.get("resolved", {}).get("preparation") or item.get("preparation"),
        preparation_material_but_unstated=item.get("preparation_material_but_unstated", False),
    )


async def check_item(
    session: AsyncSession, item: dict[str, Any]
) -> ClarificationNeeded | None:
    resolved = item.get("resolved", {})

    if "portion_grams" not in resolved:
        fields = _as_extraction_fields(item)
        quantity = resolve_quantity(fields)
        if quantity is None:
            return ClarificationNeeded(
                field="portion_grams",
                question_text=f"Quanto pesava la porzione di {item['description']}?",
                options=list(PORTION_OPTIONS_G.keys()),
            )
        resolved["portion_grams"] = quantity.grams
        resolved["quantity_is_estimated_from_count"] = quantity.is_estimated_from_count
        item["resolved"] = resolved

    if item.get("preparation_material_but_unstated") and "preparation" not in resolved:
        return ClarificationNeeded(
            field="preparation",
            question_text=f"Come era preparato/a {item['description']}?",
            options=PREPARATION_OPTIONS,
        )

    return None


def apply_answer(item: dict[str, Any], field: str, raw_answer: str) -> dict[str, Any]:
    """Applies a clarification answer, whether it came from a button label or free
    text. Leaves the field unresolved (rather than storing None) when the answer
    can't be parsed, so check_item re-asks instead of crashing at finalize time."""
    resolved = dict(item.get("resolved", {}))
    if field == "portion_grams":
        grams = PORTION_OPTIONS_G.get(raw_answer)
        if grams is None:
            grams = _parse_grams_free_text(raw_answer)
        # A user can type "0 grammi" as easily as the model can extract it, so the
        # answer path applies the same rule: an unreal amount leaves the field
        # unresolved and check_item asks again.
        if is_real_quantity(grams):
            resolved["portion_grams"] = grams
            resolved["quantity_is_estimated_from_count"] = False
    elif field == "preparation" and raw_answer.strip():
        resolved["preparation"] = raw_answer.strip()
    item = {**item, "resolved": resolved}
    return item


def _parse_grams_free_text(text: str) -> float | None:
    import re

    match = re.search(r"(\d+(?:[.,]\d+)?)", text)
    if not match:
        return None
    return float(match.group(1).replace(",", "."))


def resolve_when(when_text: str | None, tz, now: dt.datetime | None = None) -> dt.datetime:
    """Minimal deterministic resolution: 'ieri' -> yesterday, otherwise now. Anything
    more nuanced ('ieri a cena') is expected to have been folded into when_text
    by extraction; full natural-language date parsing is a fair place to extend this."""
    now = now or utcnow()
    if when_text and "ieri" in when_text.lower():
        return now - dt.timedelta(days=1)
    return now


async def finalize_item(
    session: AsyncSession,
    gateway: LLMGateway,
    user_id: int,
    item: dict[str, Any],
    tz,
) -> FinalizedFood:
    resolved = item["resolved"]
    grams = resolved["portion_grams"]
    description = item["description"]
    if resolved.get("preparation"):
        description = f"{description} {resolved['preparation']}"

    energy = await resolve_food_energy(session, gateway, description)
    kcal = energy.kcal_per_100g * grams / 100.0

    entry = FoodEntry(
        user_id=user_id,
        description=item["description"],
        grams=grams,
        kcal_per_100g=energy.kcal_per_100g,
        kcal=kcal,
        provenance=energy.provenance,
        consumed_at=resolve_when(item.get("when_text"), tz),
    )
    session.add(entry)
    await session.flush()

    return FinalizedFood(
        entry=entry,
        is_estimate=energy.provenance == Provenance.llm,
        quantity_is_estimated_from_count=resolved.get("quantity_is_estimated_from_count", False),
    )
