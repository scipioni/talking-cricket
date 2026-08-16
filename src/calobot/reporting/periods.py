"""Period resolution. See specs/reporting - Report periods. Deterministic keyword
matching rather than an LLM call: the vocabulary is small and bounded, and a report
request shouldn't pay model latency for something this narrow."""

from __future__ import annotations

from typing import Literal

Period = Literal["day", "week", "month", "year"]


def parse_period(text: str | None) -> Period:
    if not text:
        return "day"
    t = text.lower()
    if "ann" in t:  # anno, annuale, annuo
        return "year"
    if "mes" in t:  # mese, mensile
        return "month"
    if "settiman" in t:  # settimana, settimanale
        return "week"
    return "day"
