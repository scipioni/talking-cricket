"""Turns an ActivityExtraction into a draft item, decides what's missing (duration,
and intensity when it materially changes MET), and finalizes into a stored entry.
See specs/activity-logging - Duration missing, Intensity clarification, Energy
expenditure computation, Activity does not alter the calorie budget."""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from calobot.activity.resolver import resolve_met
from calobot.ingestion.quantities import is_real_quantity
from calobot.ingestion.schemas import ActivityExtraction
from calobot.llm.gateway import LLMGateway
from calobot.persistence.candidates import retrieve_met_candidates
from calobot.persistence.models import ActivityEntry, Provenance
from calobot.persistence.timeutil import resolve_when_text, utcnow

# Unlike a food portion, a duration is genuinely the user's to choose and varies far
# less with the activity, so these stay fixed - but the old 60 min ceiling was wrong
# for the long, low-intensity activities people actually log (a hike, a bike ride),
# and pushed them onto the free-text path where "2 ore" used to parse as 2 minutes.
DURATION_OPTIONS_MIN = {"15 min": 15, "30 min": 30, "45 min": 45, "60 min": 60, "90 min": 90}

# MET values within this ratio of each other are treated as "not materially different",
# so an unmatched intensity doesn't trigger a clarification when it wouldn't move the number.
MATERIAL_MET_RATIO = 1.3


@dataclass(frozen=True)
class ClarificationNeeded:
    field: str
    question_text: str
    options: list[str]


@dataclass(frozen=True)
class FinalizedActivity:
    entry: ActivityEntry
    is_estimate: bool


def build_items(extraction: ActivityExtraction) -> list[dict[str, Any]]:
    item = extraction.model_dump()
    item["resolved"] = {}
    return [item]


async def check_item(
    session: AsyncSession, item: dict[str, Any]
) -> ClarificationNeeded | None:
    resolved = item.get("resolved", {})

    # Same rule as food grams: a duration is an amount, not merely a value that is
    # present, so a dictated zero goes back through the clarification loop rather
    # than becoming a stored entry of no duration.
    if not is_real_quantity(item.get("duration_minutes")) and "duration_minutes" not in resolved:
        return ClarificationNeeded(
            field="duration_minutes",
            question_text=f"Quanto è durata l'attività ({item['activity_description']})?",
            options=list(DURATION_OPTIONS_MIN.keys()),
        )

    if not item.get("intensity_text") and "intensity" not in resolved:
        candidates = await retrieve_met_candidates(session, item["activity_description"])
        same_name = [c for c in candidates if c.name_it == item["activity_description"]]
        intensities = {c.intensity for c in same_name if c.intensity}
        if len(intensities) > 1:
            mets = [c.met for c in same_name if c.intensity]
            if max(mets) / min(mets) >= MATERIAL_MET_RATIO:
                return ClarificationNeeded(
                    field="intensity",
                    question_text=f"A che intensità hai fatto {item['activity_description']}?",
                    options=sorted(intensities),
                )

    return None


def apply_answer(item: dict[str, Any], field: str, raw_answer: str) -> dict[str, Any]:
    resolved = dict(item.get("resolved", {}))
    if field == "duration_minutes":
        minutes = DURATION_OPTIONS_MIN.get(raw_answer) or _parse_minutes_free_text(raw_answer)
        if is_real_quantity(minutes):
            resolved["duration_minutes"] = minutes
    elif field == "intensity" and raw_answer.strip():
        resolved["intensity"] = raw_answer.strip()
    return {**item, "resolved": resolved}


def _parse_minutes_free_text(text: str) -> float | None:
    """A bare number means minutes, but an explicit hour unit has to be honoured:
    "2 ore" used to parse as 2.0, and 2 is a perfectly real quantity, so a two-hour
    hike was silently stored as two minutes instead of being re-asked."""
    lowered = re.sub(r"[’`]", "'", text.strip().lower())

    hours_match = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:ore\b|ora\b|h\b)", lowered)
    if hours_match:
        hours: float | None = float(hours_match.group(1).replace(",", "."))
    elif re.search(r"\bun'?\s*ora\b", lowered):
        hours = 1.0
    else:
        hours = None

    if hours is not None:
        minutes = hours * 60.0
        # "un'ora e mezza", "1 ora e 20"
        trailing = re.search(r"\be\s+(?:(mezz\w*)|(\d+))", lowered)
        if trailing:
            minutes += 30.0 if trailing.group(1) else float(trailing.group(2))
        return minutes

    if re.search(r"\bmezz'?\s*ora\b", lowered):
        return 30.0

    match = re.search(r"(\d+(?:[.,]\d+)?)", lowered)
    if not match:
        return None
    return float(match.group(1).replace(",", "."))


def resolve_when(when_text: str | None, tz, now: dt.datetime | None = None) -> dt.datetime:
    """'ieri' shifts the calendar day (in `tz`); an explicit clock time in when_text
    (e.g. 'alle 15') overrides the time-of-day."""
    now = now or utcnow()
    return resolve_when_text(when_text, tz, now)


async def finalize_item(
    session: AsyncSession,
    gateway: LLMGateway,
    user_id: int,
    item: dict[str, Any],
    current_weight_kg: float,
    tz,
) -> FinalizedActivity:
    resolved = item["resolved"]
    duration_minutes = item.get("duration_minutes") or resolved["duration_minutes"]
    intensity_text = item.get("intensity_text") or resolved.get("intensity")

    met_result = await resolve_met(session, gateway, item["activity_description"], intensity_text)
    kcal = met_result.met * current_weight_kg * (duration_minutes / 60.0)

    entry = ActivityEntry(
        user_id=user_id,
        activity=item["activity_description"],
        duration_minutes=duration_minutes,
        met=met_result.met,
        kcal=kcal,
        provenance=met_result.provenance,
        performed_at=resolve_when(item.get("when_text"), tz),
    )
    session.add(entry)
    await session.flush()

    return FinalizedActivity(entry=entry, is_estimate=met_result.provenance == Provenance.llm)
