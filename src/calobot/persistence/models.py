"""SQLAlchemy models. See specs/user-profile, food-logging, activity-logging, weight-logging,
entry-correction, message-ingestion for the behaviour these back."""

from __future__ import annotations

import datetime as dt
import enum

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# The column defaults below stamp every stored row, so they must read the same clock
# as the rest of the system. This module used to define its own copy of utcnow(),
# which meant a simulated clock moved day-boundary logic without moving the
# timestamps those boundaries are applied to.
from calobot.persistence.timeutil import utcnow


class Base(DeclarativeBase):
    pass


class Sesso(enum.StrEnum):
    maschio = "maschio"
    femmina = "femmina"


class LivelloAttivita(enum.StrEnum):
    sedentario = "sedentario"
    leggero = "leggero"
    moderato = "moderato"
    attivo = "attivo"
    molto_attivo = "molto_attivo"


class Ritmo(enum.StrEnum):
    lento = "lento"  # 0.25 kg/settimana
    moderato = "moderato"  # 0.5 kg/settimana
    sostenuto = "sostenuto"  # 0.75 kg/settimana


class Provenance(enum.StrEnum):
    tabella = "tabella"
    llm = "llm"
    etichetta = "etichetta"  # reserved for calobot-photo-input
    off = "off"  # reserved for calobot-photo-input


class DraftIntent(enum.StrEnum):
    onboarding = "onboarding"
    food = "food"
    weight = "weight"
    activity = "activity"
    correction = "correction"
    profile = "profile"


class AdviceSurface(enum.StrEnum):
    """Which part of the bot produced a recorded piece of advice. See
    specs/advice-memory - Advice is recorded by the code that emits it."""

    dietician_review = "dietician_review"
    daily_advice = "daily_advice"
    advice_agent = "advice_agent"


class AdviceTopic(enum.StrEnum):
    """Assigned once, deterministically, at write time by
    `calobot.advice.memory.classify_topic` (design.md - Decisions). A record whose
    text matches neither pattern has no topic and never enters outcome resolution."""

    meal_timing = "meal_timing"
    logging_consistency = "logging_consistency"


class AdviceOutcome(enum.StrEnum):
    """See specs/advice-memory - Outcome is determined deterministically where
    possible. Starts and, for a topic-less record, stays `undetermined` forever."""

    undetermined = "undetermined"
    followed = "followed"
    not_followed = "not_followed"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    sesso: Mapped[Sesso | None] = mapped_column(Enum(Sesso), nullable=True)
    data_nascita: Mapped[dt.date | None] = mapped_column(nullable=True)
    altezza_cm: Mapped[float | None] = mapped_column(Float, nullable=True)
    peso_obiettivo_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    ritmo: Mapped[Ritmo | None] = mapped_column(Enum(Ritmo), nullable=True)
    onboarding_complete: Mapped[bool] = mapped_column(Boolean, default=False)
    disclaimer_shown: Mapped[bool] = mapped_column(Boolean, default=False)
    photo_notice_shown: Mapped[bool] = mapped_column(Boolean, default=False)
    # specs/proactive-nudges - Nudges are off until a user opts in.
    nudges_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    last_nudge_sent_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    activity_levels: Mapped[list[ActivityLevelHistory]] = relationship(
        back_populates="user", order_by="ActivityLevelHistory.effective_from"
    )
    food_entries: Mapped[list[FoodEntry]] = relationship(back_populates="user")
    activity_entries: Mapped[list[ActivityEntry]] = relationship(back_populates="user")
    weight_entries: Mapped[list[WeightEntry]] = relationship(back_populates="user")
    pending_drafts: Mapped[list[PendingDraft]] = relationship(back_populates="user")
    advice_records: Mapped[list[AdviceRecord]] = relationship(back_populates="user")


class ActivityLevelHistory(Base):
    """Profilo attività: stored with an effective date so the budget is auditable
    and a stale factor can be recalibrated later (design.md - Energy model)."""

    __tablename__ = "activity_level_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    livello: Mapped[LivelloAttivita] = mapped_column(Enum(LivelloAttivita))
    effective_from: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped[User] = relationship(back_populates="activity_levels")


class WeightEntry(Base):
    __tablename__ = "weight_entries"
    __table_args__ = (UniqueConstraint("user_id", "day", name="uq_weight_user_day"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    kg: Mapped[float] = mapped_column(Float)
    day: Mapped[dt.date] = mapped_column(index=True)
    recorded_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    deleted_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confirmation_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    user: Mapped[User] = relationship(back_populates="weight_entries")


class FoodEntry(Base):
    __tablename__ = "food_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    description: Mapped[str] = mapped_column(String)
    # Null when kcal was stated directly and the energy density needed to back-derive
    # a gram amount could not be resolved - see specs/food-logging, "Calorie value
    # stated directly".
    grams: Mapped[float | None] = mapped_column(Float, nullable=True)
    kcal_per_100g: Mapped[float] = mapped_column(Float)
    kcal: Mapped[float] = mapped_column(Float)
    # Null when the macro could not be resolved for this food (see
    # specs/food-logging - Food entry macro-nutrient contents), or when grams itself
    # is unresolved and there is nothing to scale a per-100g value by.
    protein_g: Mapped[float | None] = mapped_column(Float, nullable=True)
    fat_g: Mapped[float | None] = mapped_column(Float, nullable=True)
    carbs_g: Mapped[float | None] = mapped_column(Float, nullable=True)
    fiber_g: Mapped[float | None] = mapped_column(Float, nullable=True)
    provenance: Mapped[Provenance] = mapped_column(Enum(Provenance))
    consumed_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    deleted_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confirmation_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    user: Mapped[User] = relationship(back_populates="food_entries")


class ActivityEntry(Base):
    __tablename__ = "activity_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    activity: Mapped[str] = mapped_column(String)
    duration_minutes: Mapped[float] = mapped_column(Float)
    met: Mapped[float] = mapped_column(Float)
    kcal: Mapped[float] = mapped_column(Float)
    provenance: Mapped[Provenance] = mapped_column(Enum(Provenance))
    performed_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    deleted_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confirmation_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    user: Mapped[User] = relationship(back_populates="activity_entries")


class ResolutionCache(Base):
    """Keyed on a normalized food description. See specs/food-logging -
    Resolution cache and consistency: the same food must always cost the same."""

    __tablename__ = "resolution_cache"

    normalized_key: Mapped[str] = mapped_column(String, primary_key=True)
    kcal_per_100g: Mapped[float] = mapped_column(Float)
    protein_per_100g: Mapped[float | None] = mapped_column(Float, nullable=True)
    fat_per_100g: Mapped[float | None] = mapped_column(Float, nullable=True)
    carbs_per_100g: Mapped[float | None] = mapped_column(Float, nullable=True)
    fiber_per_100g: Mapped[float | None] = mapped_column(Float, nullable=True)
    provenance: Mapped[Provenance] = mapped_column(Enum(Provenance))
    display_name_it: Mapped[str] = mapped_column(String)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class METCache(Base):
    """Same role as ResolutionCache but for activities: normalized activity name -> MET."""

    __tablename__ = "met_cache"

    normalized_key: Mapped[str] = mapped_column(String, primary_key=True)
    met: Mapped[float] = mapped_column(Float)
    provenance: Mapped[Provenance] = mapped_column(Enum(Provenance))
    display_name_it: Mapped[str] = mapped_column(String)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PendingDraft(Base):
    """Persisted so a clarification survives a restart (design.md - Drafts and the
    clarification loop). Exactly one open draft per user at a time."""

    __tablename__ = "pending_drafts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, index=True)
    intent: Mapped[DraftIntent] = mapped_column(Enum(DraftIntent))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    awaiting_field: Mapped[str | None] = mapped_column(String, nullable=True)
    target_entry_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    target_entry_type: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    user: Mapped[User] = relationship(back_populates="pending_drafts")


class AdviceRecord(Base):
    """Durable record of advice given to a user. See specs/advice-memory. Soft-deleted
    like a logged entry (`deleted_at`), though nothing sets it yet - the proposal
    calls for the convention regardless (design.md - Decisions); /cancellami still
    hard-deletes it via `hard_delete_user`."""

    __tablename__ = "advice_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    surface: Mapped[AdviceSurface] = mapped_column(Enum(AdviceSurface))
    # A short code-chosen label such as "dietician_tip_week" or "meal_suggestion",
    # used to find "the previous tip of the same kind" for suppression.
    category: Mapped[str] = mapped_column(String)
    content: Mapped[str] = mapped_column(String)
    # Short code-authored description of what prompted the advice (report period,
    # suggestion mode), never raw user message text.
    situation: Mapped[str] = mapped_column(String)
    topic: Mapped[AdviceTopic | None] = mapped_column(Enum(AdviceTopic), nullable=True)
    outcome: Mapped[AdviceOutcome] = mapped_column(Enum(AdviceOutcome), default=AdviceOutcome.undetermined)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    deleted_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship(back_populates="advice_records")


class FoodDataRow(Base):
    """Seeded from the bundled USDA FDC subset. See openspec/changes/calobot-v1/tasks.md 3.1-3.2."""

    __tablename__ = "food_data_rows"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_name_en: Mapped[str] = mapped_column(String)
    kcal_per_100g: Mapped[float] = mapped_column(Float)
    protein_per_100g: Mapped[float | None] = mapped_column(Float, nullable=True)
    fat_per_100g: Mapped[float | None] = mapped_column(Float, nullable=True)
    carbs_per_100g: Mapped[float | None] = mapped_column(Float, nullable=True)
    fiber_per_100g: Mapped[float | None] = mapped_column(Float, nullable=True)
    aliases_it: Mapped[str] = mapped_column(String)  # semicolon-separated
    # Self-authored typical Italian household portions (specs/food-logging - Quantity
    # resolution): the reference scale offered as vague-portion options. Null where a
    # portion question makes no sense; see docs/DATA_SOURCES.md.
    portion_small_g: Mapped[float | None] = mapped_column(Float, nullable=True)
    portion_medium_g: Mapped[float | None] = mapped_column(Float, nullable=True)
    portion_generous_g: Mapped[float | None] = mapped_column(Float, nullable=True)


class METDataRow(Base):
    """Own-compiled Italian activity table. See openspec/changes/calobot-v1/tasks.md 3.3."""

    __tablename__ = "met_data_rows"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name_it: Mapped[str] = mapped_column(String)
    intensity: Mapped[str | None] = mapped_column(String, nullable=True)
    met: Mapped[float] = mapped_column(Float)
    source_note: Mapped[str] = mapped_column(String)
