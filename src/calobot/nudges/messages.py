"""Fixed Italian templates, one per nudge kind. See design.md - Decisions: content
is never LLM-generated here, precisely so the content constraints in
specs/proactive-nudges (no body commentary, no failure-framing, no push toward
eating less) are guaranteed by construction rather than by a prompt.
"""

from __future__ import annotations

from calobot.nudges.signals import NudgeCandidate

STOP_INSTRUCTION = "\n\nPuoi disattivare questi messaggi in ogni momento con /notifiche_off."

_TEMPLATES: dict[str, str] = {
    "goal_reached": (
        "Hai raggiunto il tuo obiettivo di peso che ti eri dato! 🎉 Se vuoi, puoi "
        "impostarne uno nuovo o continuare così."
    ),
    "broken_streak": (
        "Non registri nulla da qualche giorno. Nessun problema: quando vuoi puoi "
        "riprendere da dove avevi lasciato, senza fretta."
    ),
    "unresolved_suggestion": (
        "Qualche giorno fa ti avevo dato un consiglio: \"{tip}\". Com'è andata? Se "
        "ti va, fammi sapere o continua a registrare per capire se sta funzionando."
    ),
}


def compose(candidate: NudgeCandidate) -> str:
    template = _TEMPLATES[candidate.kind]
    if candidate.kind == "unresolved_suggestion" and candidate.advice_record is not None:
        text = template.format(tip=candidate.advice_record.content)
    else:
        text = template
    return text + STOP_INSTRUCTION
