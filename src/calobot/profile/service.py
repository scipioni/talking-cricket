"""Profile service: registration, onboarding progress (persisted directly on the User
row and via WeightEntry/ActivityLevelHistory, so resumability is automatic - see
onboarding.py module docstring), budget reporting, editing and deletion.

See specs/user-profile in full.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from calobot.persistence.models import (
    ActivityLevelHistory,
    LivelloAttivita,
    Ritmo,
    Sesso,
    User,
    WeightEntry,
)
from calobot.persistence.repository import (
    create_user,
    get_current_activity_level,
    get_latest_weight,
    get_user_by_telegram_id,
    get_weight_on_day,
    hard_delete_user,
)
from calobot.persistence.timeutil import today_in_timezone, utcnow
from calobot.profile.budget import BudgetResult, compute_budget, is_goal_weight_unsafe
from calobot.profile.onboarding import first_missing_field
from calobot.settings import get_settings


@dataclass(frozen=True)
class RegistrationResult:
    user: User
    is_new: bool
    onboarding_complete: bool


async def register_or_get_user(session: AsyncSession, telegram_user_id: int) -> RegistrationResult:
    user = await get_user_by_telegram_id(session, telegram_user_id)
    if user is not None:
        return RegistrationResult(
            user=user, is_new=False, onboarding_complete=user.onboarding_complete
        )
    user = await create_user(session, telegram_user_id)
    return RegistrationResult(user=user, is_new=True, onboarding_complete=False)


async def known_onboarding_fields(session: AsyncSession, user: User) -> dict[str, Any]:
    known: dict[str, Any] = {}
    if user.sesso is not None:
        known["sesso"] = user.sesso.value
    if user.data_nascita is not None:
        known["data_nascita"] = user.data_nascita
    if user.altezza_cm is not None:
        known["altezza_cm"] = user.altezza_cm
    weight = await get_latest_weight(session, user.id)
    if weight is not None:
        known["peso_attuale_kg"] = weight.kg
    if user.peso_obiettivo_kg is not None:
        known["peso_obiettivo_kg"] = user.peso_obiettivo_kg
    activity = await get_current_activity_level(session, user.id)
    if activity is not None:
        known["livello_attivita"] = activity.livello.value
    if user.ritmo is not None:
        known["ritmo"] = user.ritmo.value
    return known


async def next_onboarding_question(session: AsyncSession, user: User) -> str | None:
    known = await known_onboarding_fields(session, user)
    has_weight = "peso_attuale_kg" in known
    return first_missing_field(known, has_weight)


async def apply_onboarding_field(
    session: AsyncSession, user: User, field: str, value
) -> str | None:
    """Applies one validated onboarding field. Returns an error message if the value
    is rejected (e.g. unsafe goal weight), else None."""
    if field == "sesso":
        user.sesso = Sesso(value)
    elif field == "data_nascita":
        user.data_nascita = value
    elif field == "altezza_cm":
        user.altezza_cm = value
    elif field == "peso_attuale_kg":
        # One weight per day (specs/weight-logging - One weight per day): if the
        # onboarding flow ends up applying this field twice for the same day (e.g.
        # the user re-answers, or a message is reprocessed), replace the existing
        # entry instead of a second insert violating the unique (user_id, day)
        # constraint.
        day = today_in_timezone(get_settings().timezone)
        existing = await get_weight_on_day(session, user.id, day)
        if existing is not None:
            existing.kg = value
            existing.recorded_at = utcnow()
        else:
            session.add(WeightEntry(user_id=user.id, kg=value, day=day))
    elif field == "peso_obiettivo_kg":
        if user.altezza_cm is not None and is_goal_weight_unsafe(value, user.altezza_cm):
            return (
                "Questo obiettivo di peso risulterebbe in un indice di massa corporea "
                "sotto i livelli di sicurezza (18.5). Puoi indicarmi un peso obiettivo diverso?"
            )
        user.peso_obiettivo_kg = value
    elif field == "livello_attivita":
        session.add(
            ActivityLevelHistory(
                user_id=user.id, livello=LivelloAttivita(value), effective_from=utcnow()
            )
        )
    elif field == "ritmo":
        user.ritmo = Ritmo(value)
    else:
        raise ValueError(f"unknown onboarding field: {field}")

    await session.flush()
    return None


async def maybe_complete_onboarding(session: AsyncSession, user: User) -> bool:
    """Marks onboarding complete once every field is known. Returns True if this call
    is what completed it (so the caller can show the disclaimer exactly once)."""
    if user.onboarding_complete:
        return False
    if await next_onboarding_question(session, user) is not None:
        return False
    user.onboarding_complete = True
    await session.flush()
    return True


async def current_budget(session: AsyncSession, user: User) -> BudgetResult | None:
    weight = await get_latest_weight(session, user.id)
    activity = await get_current_activity_level(session, user.id)
    if not (
        user.sesso
        and user.data_nascita
        and user.altezza_cm
        and weight
        and user.peso_obiettivo_kg
        and activity
        and user.ritmo
    ):
        return None
    return compute_budget(
        sesso=user.sesso,
        data_nascita=user.data_nascita,
        height_cm=user.altezza_cm,
        current_weight_kg=weight.kg,
        goal_weight_kg=user.peso_obiettivo_kg,
        activity_level=activity.livello,
        ritmo=user.ritmo,
    )


async def format_profile_summary(session: AsyncSession, user: User) -> str:
    weight = await get_latest_weight(session, user.id)
    activity = await get_current_activity_level(session, user.id)
    lines = [
        f"Sesso: {user.sesso.value if user.sesso else '-'}",
        f"Data di nascita: {user.data_nascita.isoformat() if user.data_nascita else '-'}",
        f"Altezza: {user.altezza_cm} cm" if user.altezza_cm else "Altezza: -",
        f"Peso attuale: {weight.kg} kg" if weight else "Peso attuale: -",
        f"Peso obiettivo: {user.peso_obiettivo_kg} kg" if user.peso_obiettivo_kg else "Peso obiettivo: -",
        f"Livello di attività: {activity.livello.value}" if activity else "Livello di attività: -",
        f"Ritmo: {user.ritmo.value}" if user.ritmo else "Ritmo: -",
    ]
    budget = await current_budget(session, user)
    if budget is not None:
        lines.append(f"Budget calorico giornaliero: {budget.target_kcal:.0f} kcal")
    return "\n".join(lines)


async def delete_all_user_data(session: AsyncSession, user: User) -> None:
    await hard_delete_user(session, user.id)
    await session.commit()
