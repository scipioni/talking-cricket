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

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from calobot.llm.gateway import LLMGateway, ToolDefinition
from calobot.persistence.models import User
from calobot.persistence.repository import get_entries_in_range
from calobot.persistence.timeutil import day_bounds_utc, period_bounds_utc, today_in_timezone
from calobot.profile.budget import BudgetResult
from calobot.profile.service import current_budget
from calobot.reporting.aggregation import build_food_report, build_weight_report
from calobot.reporting.dietician import build_dietitian_review
from calobot.reporting.periods import Period

# Caps the rows a single question can pull back, so a wide date range cannot crowd
# the narration call's context with raw entries (design.md - Risks: Tool output
# crowding the context).
MAX_LISTED_ENTRIES = 50


class PeriodQuery(BaseModel):
    period: Literal["day", "week", "month", "year"]
    reference_day: dt.date | None = None


class DateRangeQuery(BaseModel):
    start_day: dt.date
    end_day: dt.date


class NoArgs(BaseModel):
    pass


def _resolve_reference_day(args: PeriodQuery, tz: ZoneInfo) -> dt.date:
    return args.reference_day or today_in_timezone(tz)


def _calorie_summary_handler(session: AsyncSession, user: User, tz: ZoneInfo, budget: BudgetResult | None):
    async def handler(args: PeriodQuery) -> dict[str, Any]:
        reference_day = _resolve_reference_day(args, tz)
        budget_kcal = budget.target_kcal if budget else None
        report = await build_food_report(session, user.id, args.period, reference_day, tz, budget_kcal)
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
        review = await build_dietitian_review(gateway, entries, tz)
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


def _profile_and_budget_handler(
    session: AsyncSession, user: User, tz: ZoneInfo, budget: BudgetResult | None
):
    async def handler(_args: NoArgs) -> dict[str, Any]:
        if budget is None:
            return {"no_data": True, "reason": "profilo non ancora completo: budget non calcolabile"}
        today = today_in_timezone(tz)
        food_today = await build_food_report(session, user.id, "day", today, tz, budget.target_kcal)
        eaten_today = food_today.total_kcal if food_today.has_data else 0.0
        return {
            "no_data": False,
            "daily_budget_kcal": round(budget.target_kcal),
            "goal_kg": user.peso_obiettivo_kg,
            "eaten_today_kcal": round(eaten_today),
            "remaining_today_kcal": round(budget.target_kcal - eaten_today),
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
                "Elenco dei singoli pasti registrati tra due date, con descrizione, "
                "grammi, calorie e ora del pasto."
            ),
            args_schema=DateRangeQuery,
            handler=_list_entries_handler(session, user, tz),
        ),
        ToolDefinition(
            name="get_profile_and_budget",
            description=(
                "Budget calorico giornaliero dell'utente, obiettivo di peso e quante "
                "calorie restano oggi."
            ),
            args_schema=NoArgs,
            handler=_profile_and_budget_handler(session, user, tz, budget),
        ),
    ]
