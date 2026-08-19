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

    if is_real_quantity(item.quantity_count):
        # The prompt asks for the counted noun in count_unit_hint, but for the most
        # ordinary phrasing of all - "mangio una pesca" - the model puts it in
        # description and leaves the hint null, having already said it once. Requiring
        # the hint sent that straight to the vague-portion question, with "pesca": 150
        # sitting in the table right here.
        hint = (item.count_unit_hint or item.description).strip().lower()
        unit_weight = TYPICAL_UNIT_WEIGHTS_G.get(hint)
        # The table stays authoritative - it is deterministic, free, and keeps "due
        # mele" weighing the same for every user on every day. The model's estimate is
        # consulted only where the table has nothing to say, which is the entire class
        # of bug the table kept reopening one noun at a time (see above): a stated,
        # precise count no longer degrades into a vague-portion question just because
        # a word is missing. The result is still flagged as estimated-from-count and
        # the assumed weight is stated back to the user either way.
        if unit_weight is None and is_real_quantity(item.typical_unit_weight_g):
            unit_weight = item.typical_unit_weight_g
        if unit_weight is not None:
            return ResolvedQuantity(
                grams=item.quantity_count * unit_weight, is_estimated_from_count=True
            )

    return None


# Generic fallback offered as tappable options when a portion can't be resolved
# automatically and the extraction didn't supply food-specific estimates (e.g. an
# older draft, or a photo-derived item built without going through extraction).
PORTION_OPTIONS_G: dict[str, float] = {
    "piccolo (~80g)": 80,
    "medio (~120g)": 120,
    "abbondante (~180g)": 180,
}


def portion_options_for(item: FoodItemExtraction) -> dict[str, float]:
    """A flat 80/120/180g scale fits a slice of bread as poorly as it fits a plate
    of pasta. When extraction supplied food-specific estimates alongside a household
    measure, use those instead of the generic fallback."""
    if (
        is_real_quantity(item.portion_small_g)
        and is_real_quantity(item.portion_medium_g)
        and is_real_quantity(item.portion_generous_g)
    ):
        return {
            f"piccolo (~{item.portion_small_g:.0f}g)": item.portion_small_g,
            f"medio (~{item.portion_medium_g:.0f}g)": item.portion_medium_g,
            f"abbondante (~{item.portion_generous_g:.0f}g)": item.portion_generous_g,
        }

    # If the food is a known countable item (e.g. uovo, mela, banana) in TYPICAL_UNIT_WEIGHTS_G,
    # offer multiples of its typical unit weight as intuitive portion options.
    desc = (item.count_unit_hint or item.description or "").strip().lower()
    unit_weight = TYPICAL_UNIT_WEIGHTS_G.get(desc)
    if unit_weight is not None:
        singular = desc
        plural = desc
        keys_with_same_weight = [k for k, w in TYPICAL_UNIT_WEIGHTS_G.items() if w == unit_weight]
        if desc == "uovo" or desc == "uova":
            singular = "uovo"
            plural = "uova"
        else:
            sorted_keys = sorted(keys_with_same_weight, key=len)
            if sorted_keys:
                singular = sorted_keys[0]
                plural = sorted_keys[-1] if len(sorted_keys) > 1 else sorted_keys[0]

        return {
            f"1 {singular} (~{unit_weight:.0f}g)": unit_weight,
            f"2 {plural} (~{unit_weight * 2:.0f}g)": unit_weight * 2,
            f"3 {plural} (~{unit_weight * 3:.0f}g)": unit_weight * 3,
        }

    return PORTION_OPTIONS_G
