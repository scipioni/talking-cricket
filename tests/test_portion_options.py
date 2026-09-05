"""The tiered vague-portion scale (specs/food-logging - Quantity resolution, as
modified by food-table-reference-portions): unit multiples for countable foods, the
bundled table's reference portions, the extraction's estimates, the generic scale
last."""

from __future__ import annotations

from calobot.food.quantities import PORTION_OPTIONS_G, portion_options_for
from calobot.ingestion.schemas import FoodItemExtraction


def _item(**overrides) -> FoodItemExtraction:
    return FoodItemExtraction(description=overrides.pop("description", "maionese"), **overrides)


def test_countable_unit_multiples_come_first():
    options = portion_options_for(_item(description="uovo"), table_portions=(40, 55, 90))
    assert list(options) == ["1 uovo (~55g)", "2 uova (~110g)", "3 uova (~165g)"]


def test_table_portions_beat_extraction_estimates():
    options = portion_options_for(
        _item(
            household_measure="un cucchiaio",
            portion_small_g=10,
            portion_medium_g=20,
            portion_generous_g=40,
        ),
        table_portions=(10, 15, 30),
    )
    assert list(options.values()) == [10, 15, 30]  # the table's scale, not the model's


def test_extraction_estimates_when_the_table_does_not_know_the_food():
    options = portion_options_for(
        _item(
            description="sushi",
            household_measure="un piatto",
            portion_small_g=100,
            portion_medium_g=180,
            portion_generous_g=300,
        )
    )
    assert list(options.values()) == [100, 180, 300]


def test_generic_scale_is_the_last_resort():
    options = portion_options_for(_item(description="qualcosa di sconosciuto"))
    assert options == PORTION_OPTIONS_G


def test_a_partial_table_triple_is_ignored():
    # A row missing even one portion value is not a scale; fall through to extraction.
    options = portion_options_for(
        _item(household_measure="un piatto", portion_small_g=100),
        table_portions=None,
    )
    assert options == PORTION_OPTIONS_G
