"""Read-only tools for the advice agent. See specs/advice-agent - The agent's data
access is read-only, User identity is bound outside the conversation, Absent data is
reported as absent, not estimated.

Every tool wraps a deterministic aggregator that already backs a report or chart, so
an advice answer for a period cannot disagree with a report for the same period
(design.md - Decision 4). `user_id` and `tz` are closed over by `build_tool_registry`
at construction time and never appear in a tool's args schema, so the model cannot
see, name or change whose data is read (design.md - Decision 5).
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from calobot.advice.memory import advice_history
from calobot.llm.gateway import LLMGateway, ToolDefinition
from calobot.persistence.models import User
from calobot.persistence.repository import get_entries_in_range
from calobot.persistence.timeutil import day_bounds_utc, period_bounds_utc, today_in_timezone
from calobot.profile.budget import BudgetResult
from calobot.profile.service import current_budget
from calobot.reporting.aggregation import (
    build_activity_report,
    build_food_report,
    build_period_comparison,
    build_weight_report,
)
from calobot.reporting.dietician import build_dietitian_review
from calobot.reporting.periods import Period

# Caps the rows a single question can pull back, so a wide date range cannot crowd
# the narration call's context with raw entries (design.md - Risks: Tool output
# crowding the context).
MAX_LISTED_ENTRIES = 50

# The situations a meal suggestion can be made in. Derived from the day's figures by
# `_meal_suggestion_context_handler`, never by the model comparing numbers itself
# (specs/advice-agent - The suggestion situation is determined outside the language
# model).
SuggestionMode = Literal["within_budget", "over_budget", "no_budget"]

# What a suggestion must stay under once the day's balance is spent. A constant rather
# than a line of prompt prose, so the narration guard can enforce it (design.md -
# Decision 4) and the nutrition judgement it encodes is reviewable in one place.
OVER_BUDGET_CEILING_KCAL = 100

# The window `get_meal_suggestion_context` reads for the qualitative variety signal,
# matching `RecentDaysQuery`'s default so both tools describe the same recent past.
SUGGESTION_RECENT_DAYS = 2


class PeriodQuery(BaseModel):
    period: Literal["day", "week", "month", "year"]
    reference_day: dt.date | None = None


class DateRangeQuery(BaseModel):
    start_day: dt.date
    end_day: dt.date


class RecentDaysQuery(BaseModel):
    days: int = Field(default=2, ge=1, le=5)


class NoArgs(BaseModel):
    pass


def _resolve_reference_day(args: PeriodQuery, tz: ZoneInfo) -> dt.date:
    return args.reference_day or today_in_timezone(tz)


def _calorie_summary_handler(session: AsyncSession, user: User, tz: ZoneInfo, budget: BudgetResult | None):
    async def handler(args: PeriodQuery) -> dict[str, Any]:
        reference_day = _resolve_reference_day(args, tz)
        budget_kcal = budget.target_kcal if budget else None
        activity_kcal_today = 0.0
        if args.period == "day":
            activity_today = await build_activity_report(session, user.id, "day", reference_day, tz)
            activity_kcal_today = activity_today.total_kcal if activity_today.has_data else 0.0
        report = await build_food_report(
            session, user.id, args.period, reference_day, tz, budget_kcal, activity_kcal_today=activity_kcal_today
        )
        if not report.has_data:
            return {
                "no_data": True,
                "period": args.period,
                "reference_day": reference_day.isoformat(),
            }
        return {
            "no_data": False,
            "period": args.period,
            "reference_day": reference_day.isoformat(),
            "total_kcal": round(report.total_kcal),
            "daily_average_kcal": round(report.daily_average_kcal),
            "budget_kcal": round(report.budget_kcal) if report.budget_kcal is not None else None,
            "difference_kcal": (
                round(report.difference_kcal) if report.difference_kcal is not None else None
            ),
            "days_with_no_data": [d.isoformat() for d in report.days_with_no_data],
        }

    return handler


def _weight_summary_handler(session: AsyncSession, user: User, tz: ZoneInfo):
    async def handler(args: PeriodQuery) -> dict[str, Any]:
        reference_day = _resolve_reference_day(args, tz)
        report = await build_weight_report(
            session, user.id, args.period, reference_day, tz, user.peso_obiettivo_kg
        )
        if not report.has_data:
            return {
                "no_data": True,
                "period": args.period,
                "reference_day": reference_day.isoformat(),
            }
        return {
            "no_data": False,
            "period": args.period,
            "reference_day": reference_day.isoformat(),
            "start_kg": report.start_kg,
            "end_kg": report.end_kg,
            "change_kg": report.change_kg,
            "remaining_to_goal_kg": report.remaining_to_goal_kg,
            "projected_date": report.projected_date.isoformat() if report.projected_date else None,
            "projection_unavailable_reason": report.projection_unavailable_reason,
        }

    return handler


def _period_comparison_handler(session: AsyncSession, user: User, tz: ZoneInfo):
    """Backs `get_period_comparison` (specs/advice-agent - Reported figures come from
    deterministic computation, comparison scenario). Every figure and signal comes
    from `build_period_comparison`; the handler only shapes the payload, matching the
    `no_data`-style explicitness the other tools already use."""

    async def handler(args: PeriodQuery) -> dict[str, Any]:
        reference_day = _resolve_reference_day(args, tz)
        result = await build_period_comparison(
            session, user.id, args.period, reference_day, tz, user.peso_obiettivo_kg
        )
        comparison = result.comparison
        if not comparison.has_current_data:
            return {
                "no_data": True,
                "period": args.period,
                "reference_day": reference_day.isoformat(),
            }

        consistency = result.logging_consistency
        timing = result.meal_timing
        density = result.calorie_density

        return {
            "no_data": False,
            "period": args.period,
            "reference_day": reference_day.isoformat(),
            "has_previous_period_data": comparison.has_previous_data,
            "calories_avg_current_kcal": (
                round(comparison.calories_avg_current) if comparison.calories_avg_current is not None else None
            ),
            "calories_avg_previous_kcal": (
                round(comparison.calories_avg_previous) if comparison.calories_avg_previous is not None else None
            ),
            "calories_avg_delta_kcal": (
                round(comparison.calories_avg_delta) if comparison.calories_avg_delta is not None else None
            ),
            "weight_change_current_kg": comparison.weight_change_current_kg,
            "weight_change_previous_kg": comparison.weight_change_previous_kg,
            "weight_change_delta_kg": comparison.weight_change_delta_kg,
            "activity_minutes_current": round(comparison.activity_minutes_current),
            "activity_minutes_previous": round(comparison.activity_minutes_previous),
            "activity_minutes_delta": round(comparison.activity_minutes_delta),
            "logging_consistency": {
                "enough_data": consistency.enough_data,
                "ratio_current": consistency.ratio_current,
                "ratio_previous": consistency.ratio_previous,
            },
            "meal_timing_drift": {
                "enough_data": timing.enough_data,
                "typical_last_meal_hour_current": timing.typical_last_meal_hour_current,
                "typical_last_meal_hour_previous": timing.typical_last_meal_hour_previous,
                "drift_hours": timing.drift_hours,
            },
            "calorie_density_trend": {
                "enough_data": density.enough_data,
                "kcal_per_100g_current": (
                    round(density.kcal_per_100g_current) if density.kcal_per_100g_current is not None else None
                ),
                "kcal_per_100g_previous": (
                    round(density.kcal_per_100g_previous) if density.kcal_per_100g_previous is not None else None
                ),
                "trend": density.trend,
            },
        }

    return handler


def _advice_history_handler(session: AsyncSession, user: User, tz: ZoneInfo):
    """Backs `get_advice_history` (specs/advice-memory - The advice agent may read
    prior advice)."""

    async def handler(_args: NoArgs) -> dict[str, Any]:
        records = await advice_history(session, user, tz)
        if not records:
            return {"no_data": True}
        return {
            "no_data": False,
            "records": [
                {
                    "surface": r.surface.value,
                    "category": r.category,
                    "content": r.content,
                    "situation": r.situation,
                    "outcome": r.outcome.value,
                    "created_at": r.created_at.astimezone(tz).isoformat(),
                }
                for r in records
            ],
        }

    return handler


_REVIEW_MIN_PERIODS: tuple[Period, ...] = ("week", "month", "year")


def _dietician_review_handler(
    session: AsyncSession, user: User, tz: ZoneInfo, gateway: LLMGateway
):
    async def handler(args: PeriodQuery) -> dict[str, Any]:
        if args.period not in _REVIEW_MIN_PERIODS:
            return {
                "no_data": True,
                "reason": "una revisione del nutrizionista richiede almeno una settimana di dati",
            }
        reference_day = _resolve_reference_day(args, tz)
        start, end = period_bounds_utc(args.period, reference_day, tz)
        entries = await get_entries_in_range(session, "food", user.id, start, end)
        review = await build_dietitian_review(gateway, entries, tz, args.period)
        if review is None:
            return {"no_data": True, "period": args.period, "reference_day": reference_day.isoformat()}
        if isinstance(review, str):
            return {"no_data": True, "message": review}
        return {"no_data": False, "period": args.period, **review.model_dump()}

    return handler


def _list_entries_handler(session: AsyncSession, user: User, tz: ZoneInfo):
    async def handler(args: DateRangeQuery) -> dict[str, Any]:
        start, _ = day_bounds_utc(args.start_day, tz)
        _, end = day_bounds_utc(args.end_day, tz)
        entries = await get_entries_in_range(session, "food", user.id, start, end)
        if not entries:
            return {
                "no_data": True,
                "start_day": args.start_day.isoformat(),
                "end_day": args.end_day.isoformat(),
            }
        capped = entries[:MAX_LISTED_ENTRIES]
        return {
            "no_data": False,
            "truncated": len(entries) > MAX_LISTED_ENTRIES,
            "entries": [
                {
                    "description": e.description,
                    "grams": e.grams,
                    "kcal": round(e.kcal),
                    "consumed_at": e.consumed_at.astimezone(tz).isoformat(),
                    "provenance": e.provenance.value,
                }
                for e in capped
            ],
        }

    return handler


async def _recent_food_payload(
    session: AsyncSession, user: User, tz: ZoneInfo, days: int
) -> dict[str, Any]:
    """The recent-meals view shared by `get_recent_food_descriptions` and
    `get_meal_suggestion_context`, so a suggestion reasons over exactly the entries a
    direct lookup would return."""
    today = today_in_timezone(tz)
    start, _ = day_bounds_utc(today - dt.timedelta(days=days), tz)
    _, end = day_bounds_utc(today, tz)
    entries = await get_entries_in_range(session, "food", user.id, start, end)
    if not entries:
        return {"no_data": True, "days": days}
    capped = entries[:MAX_LISTED_ENTRIES]
    return {
        "no_data": False,
        "truncated": len(entries) > MAX_LISTED_ENTRIES,
        "days": days,
        "entries": [
            {
                "description": e.description,
                "kcal": round(e.kcal),
                "day": e.consumed_at.astimezone(tz).date().isoformat(),
            }
            for e in capped
        ],
    }


def _recent_food_descriptions_handler(session: AsyncSession, user: User, tz: ZoneInfo):
    """Backs `get_recent_food_descriptions`: a relative-days window resolved
    server-side (like the period tools' `reference_day`), so the model never has to
    produce an absolute date the way `list_food_entries` requires (design.md -
    Decisions)."""

    async def handler(args: RecentDaysQuery) -> dict[str, Any]:
        return await _recent_food_payload(session, user, tz, args.days)

    return handler


async def _today_balance(
    session: AsyncSession, user: User, tz: ZoneInfo, budget: BudgetResult
) -> tuple[float, int]:
    """Today's eaten total and remaining balance, off the same reporting path a day
    report uses. Shared by `get_profile_and_budget` and `get_meal_suggestion_context`
    so the figure a suggestion is derived from cannot drift from the figure a direct
    budget question reports."""
    today = today_in_timezone(tz)
    activity_today = await build_activity_report(session, user.id, "day", today, tz)
    activity_kcal_today = activity_today.total_kcal if activity_today.has_data else 0.0
    food_today = await build_food_report(
        session, user.id, "day", today, tz, budget.target_kcal, activity_kcal_today=activity_kcal_today
    )
    eaten_today = food_today.total_kcal if food_today.has_data else 0.0
    remaining = round(budget.target_kcal + food_today.activity_credit_kcal - eaten_today)
    return eaten_today, remaining


def _profile_and_budget_handler(
    session: AsyncSession, user: User, tz: ZoneInfo, budget: BudgetResult | None
):
    async def handler(_args: NoArgs) -> dict[str, Any]:
        if budget is None:
            return {"no_data": True, "reason": "profilo non ancora completo: budget non calcolabile"}
        eaten_today, remaining = await _today_balance(session, user, tz, budget)
        return {
            "no_data": False,
            "daily_budget_kcal": round(budget.target_kcal),
            "goal_kg": user.peso_obiettivo_kg,
            "eaten_today_kcal": round(eaten_today),
            "remaining_today_kcal": remaining,
        }

    return handler


def _meal_suggestion_context_handler(
    session: AsyncSession, user: User, tz: ZoneInfo, budget: BudgetResult | None
):
    """Backs `get_meal_suggestion_context`. The model's only judgement is that the
    user is asking what to eat - expressed by calling this tool at all. Everything
    that follows from the day's figures, including which situation applies and what
    ceiling it imposes, is derived here (specs/advice-agent - The suggestion situation
    is determined outside the language model)."""

    async def handler(_args: NoArgs) -> dict[str, Any]:
        recent_food = await _recent_food_payload(session, user, tz, SUGGESTION_RECENT_DAYS)
        if budget is None:
            return {
                "mode": "no_budget",
                "ceiling_kcal": None,
                "remaining_today_kcal": None,
                "reason": "profilo non ancora completo: budget non calcolabile",
                "recent_food": recent_food,
            }
        _, remaining = await _today_balance(session, user, tz, budget)
        mode: SuggestionMode
        ceiling: int
        if remaining > 0:
            mode, ceiling = "within_budget", remaining
        else:
            # Zero counts as spent: there is no balance left to suggest a meal within.
            mode, ceiling = "over_budget", OVER_BUDGET_CEILING_KCAL
        return {
            "mode": mode,
            "ceiling_kcal": ceiling,
            "remaining_today_kcal": remaining,
            "recent_food": recent_food,
        }

    return handler


async def build_tool_registry(
    session: AsyncSession, gateway: LLMGateway, user: User, tz: ZoneInfo
) -> list[ToolDefinition]:
    """Builds the read-only tool set for one advice interaction, with `user.id` and
    `tz` closed over so no tool schema can express or accept them."""
    budget = await current_budget(session, user)

    return [
        ToolDefinition(
            name="get_calorie_summary",
            description=(
                "Totale, media giornaliera, budget e differenza delle calorie mangiate "
                "in un periodo (giorno, settimana, mese, anno)."
            ),
            args_schema=PeriodQuery,
            handler=_calorie_summary_handler(session, user, tz, budget),
        ),
        ToolDefinition(
            name="get_weight_summary",
            description=(
                "Andamento del peso in un periodo: peso iniziale, finale, variazione, "
                "quanto manca all'obiettivo e la data prevista al ritmo attuale."
            ),
            args_schema=PeriodQuery,
            handler=_weight_summary_handler(session, user, tz),
        ),
        ToolDefinition(
            name="get_dietician_review",
            description=(
                "Revisione comportamentale del nutrizionista su densita' calorica, orari "
                "dei pasti, varieta' e qualita' delle fonti. Richiede almeno una settimana."
            ),
            args_schema=PeriodQuery,
            handler=_dietician_review_handler(session, user, tz, gateway),
        ),
        ToolDefinition(
            name="list_food_entries",
            description=(
                "Elenco dei singoli pasti registrati in un intervallo di date preciso "
                "(richiede due date esatte), con descrizione, grammi, calorie e ora del pasto."
            ),
            args_schema=DateRangeQuery,
            handler=_list_entries_handler(session, user, tz),
        ),
        ToolDefinition(
            name="get_recent_food_descriptions",
            description=(
                "Descrizioni e calorie dei pasti registrati negli ultimi N giorni da oggi "
                "(nessuna data da calcolare): utile per valutare varieta' e bilanciamento "
                "recente prima di suggerire cosa mangiare."
            ),
            args_schema=RecentDaysQuery,
            handler=_recent_food_descriptions_handler(session, user, tz),
        ),
        ToolDefinition(
            name="get_profile_and_budget",
            description=(
                "Budget calorico giornaliero dell'utente, obiettivo di peso e quante "
                "calorie restano oggi. Usalo quando l'utente CHIEDE questi numeri (es. "
                "\"quante calorie mi restano?\"), non quando chiede cosa mangiare."
            ),
            args_schema=NoArgs,
            handler=_profile_and_budget_handler(session, user, tz, budget),
        ),
        ToolDefinition(
            name="get_period_comparison",
            description=(
                "Confronta un periodo (giorno, settimana, mese, anno) con il periodo "
                "immediatamente precedente: differenza di calorie medie, variazione di "
                "peso e minuti di attivita', piu' tre segnali comportamentali gia' "
                "calcolati (costanza nel registrare, deriva dell'orario dell'ultimo "
                "pasto, tendenza della densita' calorica). Usalo per domande come "
                "\"sto migliorando?\" o \"come mi sto comportando ultimamente?\": ogni "
                "segnale indica gia' se i dati sono sufficienti, non serve dedurlo o "
                "calcolarlo tu."
            ),
            args_schema=PeriodQuery,
            handler=_period_comparison_handler(session, user, tz),
        ),
        ToolDefinition(
            name="get_advice_history",
            description=(
                "Consigli gia' dati all'utente in passato (dal parere del "
                "nutrizionista, dal consiglio giornaliero o da un tuo suggerimento "
                "precedente), con l'esito se determinabile (seguito, non seguito, "
                "non ancora determinabile). Usalo per domande come \"il consiglio di "
                "ieri ha funzionato?\" o \"cosa mi avevi consigliato?\"."
            ),
            args_schema=NoArgs,
            handler=_advice_history_handler(session, user, tz),
        ),
        ToolDefinition(
            name="get_meal_suggestion_context",
            description=(
                "Usalo quando l'utente chiede cosa mangiare o una ricetta (es. \"cosa "
                "posso mangiare stasera?\", \"cosa mi consigli per cena?\"). Restituisce "
                "gia' pronti la situazione del suo budget di oggi, il limite di calorie "
                "entro cui restare e i pasti recenti: non devi calcolare o confrontare "
                "nulla tu."
            ),
            args_schema=NoArgs,
            handler=_meal_suggestion_context_handler(session, user, tz, budget),
        ),
    ]
