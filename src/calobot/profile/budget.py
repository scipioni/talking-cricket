"""Daily calorie budget: BMR (Mifflin-St Jeor) x activity factor - deficit(ritmo), with
safety floors. Pure functions, computed on demand rather than stored, so 'recomputed
whenever any input changes' (specs/user-profile) is automatic rather than something to
remember to trigger. See design.md - Safety: code enforces the numeric guardrails,
the LLM/system prompt only handles the conversation."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Literal

from calobot.persistence.models import LivelloAttivita, Ritmo, Sesso

ACTIVITY_FACTORS: dict[LivelloAttivita, float] = {
    LivelloAttivita.sedentario: 1.2,
    LivelloAttivita.leggero: 1.375,
    LivelloAttivita.moderato: 1.55,
    LivelloAttivita.attivo: 1.725,
    LivelloAttivita.molto_attivo: 1.9,
}

# kg/week implied by each ritmo option, and the daily kcal deficit that produces it
# (1 kg of fat ~= 7700 kcal).
RITMO_KG_PER_WEEK: dict[Ritmo, float] = {
    Ritmo.lento: 0.25,
    Ritmo.moderato: 0.5,
    Ritmo.sostenuto: 0.75,
}
KCAL_PER_KG_FAT = 7700

FLOOR_KCAL: dict[Sesso, float] = {
    Sesso.maschio: 1500,
    Sesso.femmina: 1200,
}

MIN_HEALTHY_BMI = 18.5

Direction = Literal["deficit", "surplus", "maintenance"]


@dataclass(frozen=True)
class BudgetResult:
    bmr: float
    tdee: float
    target_kcal: float
    direction: Direction
    floor_applied: bool
    effective_kg_per_week: float


def age_years(data_nascita: dt.date, on_date: dt.date) -> int:
    years = on_date.year - data_nascita.year
    if (on_date.month, on_date.day) < (data_nascita.month, data_nascita.day):
        years -= 1
    return years


def compute_bmr(sesso: Sesso, weight_kg: float, height_cm: float, age: int) -> float:
    base = 10 * weight_kg + 6.25 * height_cm - 5 * age
    return base + 5 if sesso == Sesso.maschio else base - 161


def bmi(weight_kg: float, height_cm: float) -> float:
    height_m = height_cm / 100
    return weight_kg / (height_m * height_m)


def is_goal_weight_unsafe(goal_weight_kg: float, height_cm: float) -> bool:
    return bmi(goal_weight_kg, height_cm) < MIN_HEALTHY_BMI


def compute_budget(
    *,
    sesso: Sesso,
    data_nascita: dt.date,
    height_cm: float,
    current_weight_kg: float,
    goal_weight_kg: float,
    activity_level: LivelloAttivita,
    ritmo: Ritmo,
    on_date: dt.date | None = None,
) -> BudgetResult:
    on_date = on_date or dt.date.today()
    age = age_years(data_nascita, on_date)
    bmr = compute_bmr(sesso, current_weight_kg, height_cm, age)
    tdee = bmr * ACTIVITY_FACTORS[activity_level]

    goal_delta = goal_weight_kg - current_weight_kg
    # "goal reached" - specs/user-profile - Goal already reached: within half the
    # smallest ritmo step, treat as at-goal rather than requiring an exact match.
    if abs(goal_delta) < 0.1:
        return BudgetResult(
            bmr=bmr,
            tdee=tdee,
            target_kcal=tdee,
            direction="maintenance",
            floor_applied=False,
            effective_kg_per_week=0.0,
        )

    kg_per_week = RITMO_KG_PER_WEEK[ritmo]
    daily_kcal_delta = kg_per_week * KCAL_PER_KG_FAT / 7

    if goal_delta > 0:
        target = tdee + daily_kcal_delta
        return BudgetResult(
            bmr=bmr,
            tdee=tdee,
            target_kcal=target,
            direction="surplus",
            floor_applied=False,
            effective_kg_per_week=kg_per_week,
        )

    target = tdee - daily_kcal_delta
    floor = FLOOR_KCAL[sesso]
    if target < floor:
        # Deficit clamped to the floor: report the realistic pace this implies,
        # per specs/user-profile - Deficit would breach the floor.
        actual_daily_deficit = tdee - floor
        effective_kg_per_week = max(actual_daily_deficit, 0) * 7 / KCAL_PER_KG_FAT
        return BudgetResult(
            bmr=bmr,
            tdee=tdee,
            target_kcal=floor,
            direction="deficit",
            floor_applied=True,
            effective_kg_per_week=effective_kg_per_week,
        )

    return BudgetResult(
        bmr=bmr,
        tdee=tdee,
        target_kcal=target,
        direction="deficit",
        floor_applied=False,
        effective_kg_per_week=kg_per_week,
    )
