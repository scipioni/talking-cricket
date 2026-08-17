from __future__ import annotations

import pytest

from calobot.photo.label import LabelReading, LabelUnreadable, interpret_label


def test_energy_per_100g_in_kcal_is_used_directly():
    result = interpret_label(LabelReading(energy_value=542, energy_unit="kcal"))
    assert result.kcal_per_100g == 542


def test_kilojoules_are_converted_to_kilocalories():
    result = interpret_label(LabelReading(energy_value=2268, energy_unit="kj"))
    assert result.kcal_per_100g == pytest.approx(542, abs=1)


def test_per_portion_energy_is_derived_to_per_100g():
    result = interpret_label(
        LabelReading(energy_value=271, energy_unit="kcal", per_portion=True, portion_grams=50)
    )
    assert result.kcal_per_100g == pytest.approx(542, abs=1)


def test_per_portion_without_a_stated_portion_weight_is_unreadable():
    with pytest.raises(LabelUnreadable):
        interpret_label(LabelReading(energy_value=271, energy_unit="kcal", per_portion=True))


def test_no_energy_value_read_is_unreadable():
    with pytest.raises(LabelUnreadable):
        interpret_label(LabelReading(energy_value=None))


def test_implausible_energy_density_is_rejected():
    """Catches the dangerous OCR failure mode: a magnitude error (542 misread as
    5420) rather than a small digit slip."""
    with pytest.raises(LabelUnreadable):
        interpret_label(LabelReading(energy_value=5420, energy_unit="kcal"))


def test_product_name_defaults_when_illegible():
    result = interpret_label(LabelReading(energy_value=100, product_name_it=None))
    assert result.display_name_it
