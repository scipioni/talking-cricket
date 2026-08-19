"""What the clarification loop offers, and what it accepts back.

The shared defect behind these: the question was always the same question. One
80/120/180g portion scale was offered for a spoon of mayonnaise and for a plate of
pasta alike, and one fry/boil/bake/grill list for an egg as for a chicken breast -
so the buttons were frequently all wrong, and the user fell through to free text,
where a stated unit was then thrown away ("2 ore" -> 2 minutes, "1 kg" -> 1 gram).
"""

from __future__ import annotations

import pytest

from calobot.activity.planner import _parse_minutes_free_text
from calobot.food.planner import (
    PREPARATION_OPTIONS,
    _parse_grams_free_text,
    preparation_options_for,
)
from calobot.food.quantities import PORTION_OPTIONS_G, portion_options_for
from calobot.ingestion.schemas import FoodItemExtraction


def _item(**overrides) -> FoodItemExtraction:
    return FoodItemExtraction(**{"description": "cena", **overrides})


# -- portion size scaled to the food --------------------------------------


def test_portion_options_use_the_food_specific_estimates_when_given():
    options = portion_options_for(
        _item(
            household_measure="un cucchiaio",
            portion_small_g=10,
            portion_medium_g=20,
            portion_generous_g=40,
        )
    )
    assert options == {"piccolo (~10g)": 10, "medio (~20g)": 20, "abbondante (~40g)": 40}


def test_portion_options_fall_back_to_the_generic_scale_when_extraction_gave_none():
    """Photo-derived items are built without going through food extraction, so the
    generic scale has to remain a working fallback rather than an error case."""
    assert portion_options_for(_item(household_measure="un piatto")) == PORTION_OPTIONS_G


def test_portion_options_fall_back_when_the_estimates_are_incomplete():
    options = portion_options_for(
        _item(household_measure="un piatto", portion_small_g=10, portion_medium_g=20)
    )
    assert options == PORTION_OPTIONS_G


def test_portion_options_for_known_countable_items():
    # Test for "uovo"
    options_egg = portion_options_for(_item(description="uovo"))
    assert options_egg == {
        "1 uovo (~55g)": 55,
        "2 uova (~110g)": 110,
        "3 uova (~165g)": 165,
    }

    # Test for "mela"
    options_apple = portion_options_for(_item(description="mela"))
    assert options_apple == {
        "1 mela (~180g)": 180,
        "2 mele (~360g)": 360,
        "3 mele (~540g)": 540,
    }


# -- preparation scaled to the food ---------------------------------------


def test_preparation_options_use_the_food_specific_list_when_given():
    """None of fry/boil/bake/grill describes an egg the way a user would."""
    options = preparation_options_for(
        _item(
            description="uovo",
            preparation_material_but_unstated=True,
            preparation_options=["sodo", "strapazzato", "in camicia", "fritto"],
        )
    )
    assert options == ["sodo", "strapazzato", "in camicia", "fritto"]


def test_preparation_options_fall_back_when_extraction_gave_none():
    assert (
        preparation_options_for(_item(preparation_material_but_unstated=True))
        == PREPARATION_OPTIONS
    )


def test_a_single_preparation_option_is_not_a_question():
    """One button is an assumption with a tap attached, not a choice - fall back to
    the generic list rather than lead the user to the only answer offered."""
    assert (
        preparation_options_for(
            _item(preparation_material_but_unstated=True, preparation_options=["fritto"])
        )
        == PREPARATION_OPTIONS
    )


def test_blank_preparation_options_are_discarded():
    assert (
        preparation_options_for(
            _item(preparation_material_but_unstated=True, preparation_options=["", "  "])
        )
        == PREPARATION_OPTIONS
    )


# -- a stated unit in a free-text answer is honoured ----------------------


@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        ("2 ore", 120),
        ("1 ora", 60),
        ("1,5 ore", 90),
        ("2 h", 120),
        ("un'ora e mezza", 90),
        ("1 ora e 20", 80),
        ("mezz'ora", 30),
        # A bare number still means minutes, which is what the buttons offer.
        ("90 minuti", 90),
        ("45", 45),
    ],
)
def test_duration_answers_honour_a_stated_hour_unit(answer, expected):
    """"2 ore" used to parse as 2.0 - real enough to pass the quantity floor, so a
    two-hour hike was stored as two minutes with no question asked."""
    assert _parse_minutes_free_text(answer) == expected


@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        ("1 kg", 1000),
        ("0,5 kg", 500),
        ("3 chili", 3000),
        ("2 etti", 200),
        ("1 hg", 100),
        # A bare number still means grams, which is what the buttons offer.
        ("250 grammi", 250),
        ("150 g", 150),
        ("80", 80),
    ],
)
def test_portion_answers_honour_a_stated_weight_unit(answer, expected):
    """"1 kg" used to parse as 1.0 and be stored as a one-gram portion."""
    assert _parse_grams_free_text(answer) == expected


def test_an_answer_with_no_number_stays_unparsed():
    """Unparsed means re-asked, which is the safe outcome - unlike a wrong unit,
    which passes the quantity floor and is stored silently."""
    assert _parse_grams_free_text("mezzo chilo") is None
    assert _parse_minutes_free_text("boh") is None
