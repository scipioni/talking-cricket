"""Deterministic, regex-based parsing for onboarding free-text answers. Kept out of
the LLM path deliberately: these are short numeric/date answers where a fixed parser
is both cheaper and more predictable than a model call, and it keeps onboarding
testable without a live endpoint."""

from __future__ import annotations

import datetime as dt
import re

from calobot.persistence.timeutil import today_local


def parse_sesso(text: str) -> str | None:
    text = text.strip().lower()
    if text in {"maschio", "uomo", "m", "male"}:
        return "maschio"
    if text in {"femmina", "donna", "f", "female"}:
        return "femmina"
    return None


def parse_height_cm(text: str) -> float | None:
    match = re.search(r"(\d+(?:[.,]\d+)?)", text)
    if not match:
        return None
    value = float(match.group(1).replace(",", "."))
    if value < 3:  # e.g. "1.78" meters
        value *= 100
    return value


def parse_weight_kg(text: str) -> float | None:
    match = re.search(r"(\d+(?:[.,]\d+)?)", text)
    if not match:
        return None
    return float(match.group(1).replace(",", "."))


def parse_data_nascita(text: str, today: dt.date | None = None) -> dt.date | None:
    today = today or today_local()
    text = text.strip().lower()

    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%y"):
        try:
            return dt.datetime.strptime(text, fmt).date()
        except ValueError:
            continue

    age_match = re.search(r"(\d{1,3})\s*ann", text) or re.fullmatch(r"(\d{1,3})", text)
    if age_match:
        age = int(age_match.group(1))
        if 0 < age < 130:
            # Approximate: exact day/month is unrecoverable from "N anni" alone, but
            # age_years() will recompute the right age from this date on most days
            # of the year, and onboarding never claims day-level precision here.
            return today.replace(year=today.year - age)

    return None


def parse_livello_attivita(text: str) -> str | None:
    text = text.strip().lower()
    mapping = {
        "sedentario": "sedentario",
        "leggero": "leggero",
        "moderato": "moderato",
        "attivo": "attivo",
        "molto attivo": "molto_attivo",
        "molto_attivo": "molto_attivo",
    }
    return mapping.get(text)


def parse_ritmo(text: str) -> str | None:
    text = text.strip().lower()
    mapping = {
        "lento": "lento",
        "moderato": "moderato",
        "sostenuto": "sostenuto",
    }
    return mapping.get(text)
