"""Turns a FoodExtraction into per-item drafts, decides what's still missing, and
finalizes items into stored entries. See specs/food-logging and specs/message-ingestion
- Draft completeness and the clarification loop."""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from calobot.food.quantities import portion_options_for, resolve_quantity
from calobot.food.resolver import resolve_food_energy
from calobot.ingestion.quantities import is_real_quantity
from calobot.ingestion.schemas import FoodExtraction, FoodItemExtraction
from calobot.llm.gateway import LLMGateway
from calobot.persistence.candidates import table_portions_for
from calobot.persistence.models import FoodEntry, Provenance
from calobot.persistence.timeutil import resolve_when_text, utcnow

# Generic fallback, used when extraction supplied no food-specific list. None of the
# four fits an egg or a plate of pasta, which is why the extraction is asked for the
# preparations that actually apply to the food in hand.
PREPARATION_OPTIONS = ["fritto", "bollito", "al forno", "alla griglia"]


def preparation_options_for(item: FoodItemExtraction) -> list[str]:
    """Deciding `preparation_material_but_unstated` already means weighing which
    preparations of this food differ in energy, so the extraction is asked to name
    them rather than have that reasoning thrown away and a fixed list offered."""
    options = [option.strip() for option in item.preparation_options if option.strip()]
    # One option is not a question - it is an assumption with a button on it.
    return options if len(options) >= 2 else PREPARATION_OPTIONS


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
    kcal_is_stated: bool


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
        stated_kcal=item.get("stated_kcal"),
        quantity_grams=item.get("quantity_grams"),
        quantity_count=item.get("quantity_count"),
        count_unit_hint=item.get("count_unit_hint"),
        typical_unit_weight_g=item.get("typical_unit_weight_g"),
        household_measure=item.get("household_measure"),
        portion_small_g=item.get("portion_small_g"),
        portion_medium_g=item.get("portion_medium_g"),
        portion_generous_g=item.get("portion_generous_g"),
        preparation=item.get("resolved", {}).get("preparation") or item.get("preparation"),
        preparation_material_but_unstated=item.get("preparation_material_but_unstated", False),
        preparation_options=item.get("preparation_options") or [],
    )


async def check_item(
    session: AsyncSession, item: dict[str, Any]
) -> ClarificationNeeded | None:
    resolved = item.get("resolved", {})

    # A stated calorie value is enough to store the entry on its own - see
    # specs/food-logging, "Calorie value stated directly" - so the portion-size
    # clarification is skipped even when grams/count are also unresolved.
    if "portion_grams" not in resolved and not is_real_quantity(item.get("stated_kcal")):
        fields = _as_extraction_fields(item)
        quantity = resolve_quantity(fields)
        if quantity is None:
            # The table's reference portions for this food, so the buttons are the
            # food's own scale rather than the generic plate-size fallback. The map
            # displayed is stored on the item: apply_answer maps the tapped label
            # against it, and cannot re-run this lookup (it has no session - and
            # re-running it could return different candidates).
            options = portion_options_for(
                fields, await table_portions_for(session, item["description"])
            )
            item["portion_options"] = options
            return ClarificationNeeded(
                field="portion_grams",
                question_text=f"Quanto pesava la porzione di {item['description']}?",
                options=list(options.keys()),
            )
        resolved["portion_grams"] = quantity.grams
        resolved["quantity_is_estimated_from_count"] = quantity.is_estimated_from_count
        item["resolved"] = resolved

    if item.get("preparation_material_but_unstated") and "preparation" not in resolved:
        return ClarificationNeeded(
            field="preparation",
            question_text=f"Come era preparato/a {item['description']}?",
            options=preparation_options_for(_as_extraction_fields(item)),
        )

    return None


def apply_answer(item: dict[str, Any], field: str, raw_answer: str) -> dict[str, Any]:
    """Applies a clarification answer, whether it came from a button label or free
    text. Leaves the field unresolved (rather than storing None) when the answer
    can't be parsed, so check_item re-asks instead of crashing at finalize time."""
    resolved = dict(item.get("resolved", {}))
    if field == "portion_grams":
        # The map displayed with the question, stored on the item when it was asked:
        # the label must resolve to the grams it showed, whatever a fresh lookup
        # would say now.
        shown_options = item.get("portion_options")
        if shown_options is not None:
            grams = shown_options.get(raw_answer)
        else:
            grams = portion_options_for(_as_extraction_fields(item)).get(raw_answer)
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
    """A bare number means grams, but a stated unit has to be honoured: "1 kg" used
    to parse as 1.0, and 1 is a real quantity, so it was stored as a one-gram portion
    rather than re-asked."""
    match = re.search(r"(\d+(?:[.,]\d+)?)\s*(kg|kilogramm\w*|chil\w*|hg|ett\w*)?", text.lower())
    if not match:
        return None
    value = float(match.group(1).replace(",", "."))
    unit = match.group(2)
    if unit is None:
        return value
    if unit.startswith(("kg", "kilo", "chil")):
        return value * 1000.0
    return value * 100.0  # hg / etto


def resolve_when(when_text: str | None, tz, now: dt.datetime | None = None) -> dt.datetime:
    """'ieri' shifts the calendar day (in `tz`, so day boundaries land on local
    midnight); an explicit clock time in when_text (e.g. 'alle 15') overrides the
    time-of-day. Anything more nuanced ('ieri a cena') is expected to have been
    folded into when_text by extraction; full natural-language date parsing is a
    fair place to extend this."""
    now = now or utcnow()
    return resolve_when_text(when_text, tz, now)


async def finalize_item(
    session: AsyncSession,
    gateway: LLMGateway,
    user_id: int,
    item: dict[str, Any],
    tz,
) -> FinalizedFood:
    resolved = item["resolved"]
    description = item["description"]
    preparation = resolved.get("preparation") or item.get("preparation")
    if preparation:
        description = f"{description} {preparation}"

    energy = await resolve_food_energy(session, gateway, description)

    kcal_is_stated = is_real_quantity(item.get("stated_kcal"))
    if kcal_is_stated:
        kcal = float(item["stated_kcal"])
        grams = kcal / energy.kcal_per_100g * 100.0 if energy.kcal_per_100g > 0 else None
    else:
        grams = resolved["portion_grams"]
        kcal = energy.kcal_per_100g * grams / 100.0

    def scale_macro(per_100g: float | None) -> float | None:
        # specs/food-logging - Food entry macro-nutrient contents: a macro that can't
        # be resolved, or grams itself being unresolved, is stored as absent, never 0.
        if per_100g is None or grams is None:
            return None
        return per_100g * grams / 100.0

    entry = FoodEntry(
        user_id=user_id,
        description=description,
        grams=grams,
        kcal_per_100g=energy.kcal_per_100g,
        kcal=kcal,
        protein_g=scale_macro(energy.protein_per_100g),
        fat_g=scale_macro(energy.fat_per_100g),
        carbs_g=scale_macro(energy.carbs_per_100g),
        fiber_g=scale_macro(energy.fiber_per_100g),
        provenance=energy.provenance,
        consumed_at=resolve_when(item.get("when_text"), tz),
    )
    session.add(entry)
    await session.flush()

    return FinalizedFood(
        entry=entry,
        is_estimate=energy.provenance == Provenance.llm,
        quantity_is_estimated_from_count=resolved.get("quantity_is_estimated_from_count", False),
        kcal_is_stated=kcal_is_stated,
    )
