"""Classification and extraction schemas. Kept small and flat per design.md - The
interpretation pipeline: nesting and unions are where a small model's schema
adherence falls off, so each intent gets its own tiny schema rather than one big union."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Intent = Literal["food", "weight", "activity", "profile", "correction", "report", "other"]

# Every onboarding field except peso_attuale_kg, which is not a profile field on this
# path - it writes a WeightEntry and stays with the weight intent (design.md - Current
# weight is not settable on this path).
ProfileField = Literal[
    "sesso", "data_nascita", "altezza_cm", "peso_obiettivo_kg", "livello_attivita", "ritmo"
]


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
    # Set only when the user states a calorie amount directly (e.g. "100kcal di
    # melanzane") rather than a quantity - see specs/food-logging, "Calorie value
    # stated directly". Kept separate from quantity_grams so the model has an
    # explicit slot for "this number is calories, not grams".
    stated_kcal: float | None = Field(default=None, ge=0, le=5000)
    quantity_grams: float | None = Field(default=None, ge=0, le=5000)
    quantity_count: float | None = Field(default=None, ge=0, le=50)
    count_unit_hint: str | None = None  # e.g. "mela", "uovo", "fetta"
    # Fallback for count_unit_hint values missing from TYPICAL_UNIT_WEIGHTS_G, whose
    # every miss used to send a precise count to the vague-portion clarification -
    # see quantities.py.
    typical_unit_weight_g: float | None = Field(default=None, ge=0, le=5000)
    household_measure: str | None = None  # e.g. "un piatto", "una porzione" - not auto-resolved
    # Only meaningful alongside household_measure: plausible gram estimates for THIS
    # food specifically (a sauce and a pasta dish don't share a portion scale), offered
    # as clarification buttons rather than assumed outright - see quantities.py.
    portion_small_g: float | None = Field(default=None, ge=0, le=5000)
    portion_medium_g: float | None = Field(default=None, ge=0, le=5000)
    portion_generous_g: float | None = Field(default=None, ge=0, le=5000)
    preparation: str | None = None  # e.g. "fritto", "bollito", "al forno"
    preparation_material_but_unstated: bool = Field(
        default=False,
        description=(
            "True only if this food's plausible preparations differ materially in "
            "energy (e.g. pollo fritto vs bollito) and none was stated."
        ),
    )
    # The preparations worth asking about for THIS food ("sodo"/"strapazzato" for an
    # egg, not the generic fry/boil/bake/grill list). Deciding the flag above already
    # requires weighing exactly these, so they cost nothing extra to return.
    preparation_options: list[str] = Field(default_factory=list)


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


class ProfileEditExtraction(BaseModel):
    """Names the field being set and quotes the value verbatim; interpreting the
    value stays with the deterministic per-field parser onboarding already uses
    (design.md - Extraction names the field and quotes the value)."""

    field: ProfileField | None = Field(
        default=None,
        description="The profile field being set, or null if none is clearly named.",
    )
    value_text: str = ""  # verbatim as stated, e.g. "16/5/72", "74kg", "sedentario"


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
