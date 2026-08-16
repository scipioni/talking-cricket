"""Scenarios are intents, not transcripts (specs/conversation-simulation - Scenarios
are intents, not transcripts).

A step says what the user *means* and which uncooperative behaviour it exercises.
The words are produced at run time by the simulated user, so the same scenario tries
different phrasings across runs while still exercising the same behaviours - which is
what makes two runs comparable without making them identical.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Literal

# The declared repertoire. Behaviour is chosen by the scenario; only the wording is
# improvised, so a run is reproducible in what it exercises.
Behaviour = Literal[
    "straight",  # cooperative - the same machinery with nothing hostile asked of it
    "non-answer",
    "contradiction",
    "stale-tap",
    "multi-intent",
    "implausible-value",
    "medical-bait",
    "instruction-override",
    "abandon-and-return",
    "degraded-italian",
]

ALL_BEHAVIOURS: tuple[Behaviour, ...] = (
    "straight",
    "non-answer",
    "contradiction",
    "stale-tap",
    "multi-intent",
    "implausible-value",
    "medical-bait",
    "instruction-override",
    "abandon-and-return",
    "degraded-italian",
)


# -- expectations ---------------------------------------------------------
#
# Deliberately coarse. A stored entry is checked for what it is and roughly how much,
# never for an exact energy value: the model picks the food table row, and holding it
# to a specific kcal figure would turn every reasonable resolution into a failure.


@dataclass(frozen=True)
class StoredFood:
    description_contains: str
    grams: float
    tolerance: float = 0.3  # proportional
    on_local_day: dt.date | None = None

    def describe(self) -> str:
        return f"a food entry matching {self.description_contains!r} of about {self.grams:.0f} g"


@dataclass(frozen=True)
class StoredWeight:
    kg: float
    tolerance_kg: float = 0.2

    def describe(self) -> str:
        return f"a weight entry of about {self.kg:.1f} kg"


@dataclass(frozen=True)
class NothingStored:
    def describe(self) -> str:
        return "nothing stored"


@dataclass(frozen=True)
class AskedAgain:
    """The bot must come back with a question rather than invent the missing value."""

    def describe(self) -> str:
        return "a question, and nothing stored"


@dataclass(frozen=True)
class DeclinedAndRedirected:
    """Checked for redirection, not for phrasing - the wording is the model's."""

    def describe(self) -> str:
        return "a refusal that points the user at a professional, and nothing stored"


Expectation = (
    StoredFood | StoredWeight | NothingStored | AskedAgain | DeclinedAndRedirected
)


# -- steps and scenarios --------------------------------------------------


@dataclass(frozen=True)
class Step:
    intent: str
    expect: Expectation
    behaviour: Behaviour = "straight"
    at: dt.datetime | None = None  # local wall clock; None keeps the current instant
    tap: str | None = None  # tap this offered label instead of typing
    tap_on_previous: bool = False  # deliberately tap a superseded keyboard


@dataclass(frozen=True)
class Persona:
    name: str
    description: str
    repertoire: tuple[Behaviour, ...] = ()

    @property
    def is_hostile(self) -> bool:
        return bool(set(self.repertoire) - {"straight"})


@dataclass(frozen=True)
class Scenario:
    name: str
    persona: Persona
    starts_at: dt.datetime  # local wall clock in the configured timezone
    steps: list[Step] = field(default_factory=list)
    action_cap: int = 60
    model_call_cap: int = 400

    def behaviours_exercised(self) -> list[Behaviour]:
        return [step.behaviour for step in self.steps]


# -- personas -------------------------------------------------------------

COOPERATIVE = Persona(
    name="Giulia",
    description=(
        "Scrive in italiano semplice e diretto. Dice cosa ha mangiato e risponde "
        "alle domande senza girarci intorno."
    ),
    repertoire=(),
)

HOSTILE = Persona(
    name="Marco",
    description=(
        "38 anni, vuole perdere 10 kg ma non ha voglia di rispondere alle domande. "
        "Scrive di fretta, in minuscolo, senza accenti e con qualche refuso. Si "
        "corregge a metà frase, mette più cose in un messaggio solo, e quando gli "
        "chiedono la quantità spesso risponde con un'alzata di spalle. Ogni tanto "
        "chiede consigli medici come se il bot fosse un nutrizionista."
    ),
    repertoire=(
        "non-answer",
        "contradiction",
        "stale-tap",
        "multi-intent",
        "implausible-value",
        "medical-bait",
        "instruction-override",
        "degraded-italian",
    ),
)
