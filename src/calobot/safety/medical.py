"""Hard, code-enforced backstop for medical/eating-disorder topics. See
specs/user-profile - Safety limits on goals and budgets: 'SHALL NOT give medical,
clinical or eating-disorder advice'. This is a keyword guard that short-circuits
before any LLM call, so the refusal does not depend on the model choosing to comply
(design.md - Safety: 'the model cannot be trusted to enforce them alone')."""

from __future__ import annotations

MEDICAL_KEYWORDS = [
    "malattia",
    "farmaco",
    "farmaci",
    "diagnosi",
    "disturbo alimentare",
    "anoressia",
    "bulimia",
    "medicina",
    "medico",
    "dottore",
    "patologia",
    "terapia",
    "sintomi",
    "cura per",
    "insulina",
    "diabete",
    "gravidanza",
    "incinta",
    "colesterolo",
    "pressione",
    "ipertensione",
    "ipercolesterolemia",
]

REFUSAL_TEXT = (
    "Non sono uno strumento medico e non posso dare consigli su condizioni "
    "cliniche, farmaci o disturbi alimentari. Per questo genere di domande ti "
    "consiglio di parlarne con un medico o uno specialista."
)


def is_medical_topic(text: str) -> bool:
    lowered = text.lower()
    return any(keyword in lowered for keyword in MEDICAL_KEYWORDS)
