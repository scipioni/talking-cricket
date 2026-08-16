"""Classification and extraction schemas. Kept small and flat per design.md - The
interpretation pipeline: nesting and unions are where a small model's schema
adherence falls off, so each intent gets its own tiny schema rather than one big union."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Intent = Literal["food", "weight", "activity", "correction", "report", "other"]


class Classification(BaseModel):
    intent: Intent
    # See specs/message-ingestion - "Message mixing two intents": the classifier names
    # the dominant intent and flags what else was present so nothing is silently dropped.
    ignored_text: str | None = Field(
        default=None,
        description="Verbatim part of the message belonging to a second intent, if any.",
    )


class FoodItemExtraction(BaseModel):
    description: str
    quantity_grams: float | None = Field(default=None, ge=0, le=5000)
    quantity_count: float | None = Field(default=None, ge=0, le=50)
    count_unit_hint: str | None = None  # e.g. "mela", "uovo", "fetta"
    household_measure: str | None = None  # e.g. "un piatto", "una porzione" - not auto-resolved
    preparation: str | None = None  # e.g. "fritto", "bollito", "al forno"
    preparation_material_but_unstated: bool = Field(
        default=False,
        description=(
            "True only if this food's plausible preparations differ materially in "
            "energy (e.g. pollo fritto vs bollito) and none was stated."
        ),
    )


class FoodExtraction(BaseModel):
    items: list[FoodItemExtraction]
    when_text: str | None = None  # e.g. "ieri sera", "stamattina"


class WeightExtraction(BaseModel):
    value_text: str  # verbatim as stated, e.g. "78 e mezzo", "ho perso mezzo chilo"
    when_text: str | None = None


class ActivityExtraction(BaseModel):
    activity_description: str
    duration_minutes: float | None = Field(default=None, ge=0, le=1440)
    intensity_text: str | None = None
    when_text: str | None = None


class CorrectionExtraction(BaseModel):
    correction_text: str  # verbatim, e.g. "no erano 20g"


class ReportExtraction(BaseModel):
    period_text: str | None = None  # e.g. "questo mese", "l'ultima settimana"
    topic: Literal["food", "weight", "activity", "all"] = "all"


class ClarificationReplyExtraction(BaseModel):
    """Used to interpret a free-text answer to a clarification question against the
    single field currently being asked about."""

    resolved_value: str | None = Field(
        default=None, description="The value for the field being asked about, or null if unclear."
    )
