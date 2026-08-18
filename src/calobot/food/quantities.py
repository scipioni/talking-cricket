"""Quantity resolution to grams. See specs/food-logging - Quantity resolution:
explicit grams and countable-item counts resolve automatically; vague household
measures ("un piatto", "una porzione") deliberately do not, and go through
clarification instead (design.md - 'ask rather than assume')."""

from __future__ import annotations

from dataclasses import dataclass

from calobot.ingestion.quantities import is_real_quantity
from calobot.ingestion.schemas import FoodItemExtraction

# Typical single-unit weight in grams for common countable foods. Deliberately
# narrow: anything not listed here is treated as unresolvable, matching the spec's
# distinction between countable items and vague household measures.
#
# Both singular and plural Italian forms are listed for every entry. The extraction
# prompt asks the model for the singular ("due mele" -> count_unit_hint="mela"), but
# it does not reliably follow that - a plural hint straight from the user's own words
# ("2 noci") reaches here just as often, and a dict miss used to fall through to the
# generic 80/120/180g portion clarification regardless of how small and precise the
# stated count was (the exact failure "noce" alone was added to fix once already;
# its plural "noci" reopened the same gap).
TYPICAL_UNIT_WEIGHTS_G: dict[str, float] = {
    "mela": 180,
    "mele": 180,
    "banana": 120,
    "banane": 120,
    "pera": 170,
    "pere": 170,
    "arancia": 200,
    "arance": 200,
    "kiwi": 75,  # invariant plural
    "pesca": 150,
    "pesche": 150,
    "albicocca": 40,
    "albicocche": 40,
    "prugna": 60,
    "prugne": 60,
    "uovo": 55,
    "uova": 55,  # irregular plural
    "fetta di pane": 30,
    "fette di pane": 30,
    "fetta": 30,
    "fette": 30,
    "cucchiaio": 15,
    "cucchiai": 15,
    "cucchiaino": 5,
    "cucchiaini": 5,
    "bicchiere": 200,
    "bicchieri": 200,
    "noce": 5,
    "noci": 5,
    "mandorla": 1.2,
    "mandorle": 1.2,
    "nocciola": 1.3,
    "nocciole": 1.3,
    "pistacchio": 0.7,
    "pistacchi": 0.7,
    "anacardo": 1.5,
    "anacardi": 1.5,
    "arachide": 0.8,
    "arachidi": 0.8,
}


@dataclass(frozen=True)
class ResolvedQuantity:
    grams: float
    is_estimated_from_count: bool


def resolve_quantity(item: FoodItemExtraction) -> ResolvedQuantity | None:
    if is_real_quantity(item.quantity_grams):
        return ResolvedQuantity(grams=item.quantity_grams, is_estimated_from_count=False)

    if is_real_quantity(item.quantity_count) and item.count_unit_hint:
        unit_weight = TYPICAL_UNIT_WEIGHTS_G.get(item.count_unit_hint.strip().lower())
        if unit_weight is not None:
            return ResolvedQuantity(
                grams=item.quantity_count * unit_weight, is_estimated_from_count=True
            )

    return None


# Offered as tappable options when a portion can't be resolved automatically
# (specs/message-ingestion - clarification loop offers common answers as buttons).
PORTION_OPTIONS_G: dict[str, float] = {
    "piccolo (~80g)": 80,
    "medio (~120g)": 120,
    "abbondante (~180g)": 180,
}
