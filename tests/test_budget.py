from __future__ import annotations

import datetime as dt

import pytest

from calobot.persistence.models import LivelloAttivita, Ritmo, Sesso
from calobot.profile.budget import compute_budget, is_goal_weight_unsafe


def _dob(age: int, on_date: dt.date) -> dt.date:
    return dt.date(on_date.year - age, on_date.month, on_date.day)


def test_deficit_for_weight_loss_goal():
    today = dt.date(2026, 1, 1)
    result = compute_budget(
        sesso=Sesso.maschio,
        data_nascita=_dob(30, today),
        height_cm=178,
        current_weight_kg=90,
        goal_weight_kg=80,
        activity_level=LivelloAttivita.moderato,
        ritmo=Ritmo.moderato,
        on_date=today,
    )
    assert result.direction == "deficit"
    assert result.target_kcal < result.tdee
    assert not result.floor_applied


def test_surplus_for_weight_gain_goal():
    today = dt.date(2026, 1, 1)
    result = compute_budget(
        sesso=Sesso.femmina,
        data_nascita=_dob(25, today),
        height_cm=165,
        current_weight_kg=50,
        goal_weight_kg=58,
        activity_level=LivelloAttivita.leggero,
        ritmo=Ritmo.lento,
        on_date=today,
    )
    assert result.direction == "surplus"
    assert result.target_kcal > result.tdee


def test_maintenance_when_goal_reached():
    today = dt.date(2026, 1, 1)
    result = compute_budget(
        sesso=Sesso.femmina,
        data_nascita=_dob(40, today),
        height_cm=160,
        current_weight_kg=60,
        goal_weight_kg=60,
        activity_level=LivelloAttivita.sedentario,
        ritmo=Ritmo.moderato,
        on_date=today,
    )
    assert result.direction == "maintenance"
    assert result.target_kcal == pytest.approx(result.tdee)


def test_floor_clamps_aggressive_deficit_for_small_woman():
    today = dt.date(2026, 1, 1)
    result = compute_budget(
        sesso=Sesso.femmina,
        data_nascita=_dob(22, today),
        height_cm=155,
        current_weight_kg=52,
        goal_weight_kg=40,
        activity_level=LivelloAttivita.sedentario,
        ritmo=Ritmo.sostenuto,
        on_date=today,
    )
    assert result.direction == "deficit"
    assert result.floor_applied
    assert result.target_kcal == 1200
    assert result.effective_kg_per_week < 0.75


def test_goal_weight_unsafe_bmi():
    assert is_goal_weight_unsafe(45, 175) is True
    assert is_goal_weight_unsafe(70, 175) is False


def test_age_computed_from_date_not_stored():
    from calobot.profile.budget import age_years

    dob = dt.date(1990, 6, 15)
    assert age_years(dob, dt.date(2026, 6, 14)) == 35
    assert age_years(dob, dt.date(2026, 6, 15)) == 36
