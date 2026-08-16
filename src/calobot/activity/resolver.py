"""MET resolution: cache -> bundled table (LLM picks the row, considering intensity)
-> LLM estimate. Mirrors calobot.food.resolver; see specs/activity-logging - Energy
expenditure computation, Intensity clarification."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from calobot.food.resolver import normalize_description
from calobot.llm.content import TextContent
from calobot.llm.gateway import LLMGateway
from calobot.persistence.candidates import retrieve_met_candidates
from calobot.persistence.models import METCache, Provenance
from calobot.persistence.timeutil import utcnow

MAX_PLAUSIBLE_MET = 20.0
MIN_PLAUSIBLE_MET = 0.5


@dataclass(frozen=True)
class ResolvedMET:
    met: float
    provenance: Provenance


class METRowSelection(BaseModel):
    selected_candidate_id: int | None = None


class METEstimate(BaseModel):
    met: float = Field(ge=MIN_PLAUSIBLE_MET, le=MAX_PLAUSIBLE_MET)


async def resolve_met(
    session: AsyncSession, gateway: LLMGateway, activity_description: str, intensity_text: str | None
) -> ResolvedMET:
    key = normalize_description(f"{activity_description} {intensity_text or ''}")

    cached = await session.get(METCache, key)
    if cached is not None:
        return ResolvedMET(met=cached.met, provenance=cached.provenance)

    candidates = await retrieve_met_candidates(session, activity_description)

    resolved: ResolvedMET | None = None
    if candidates:
        candidate_text = "\n".join(
            f"id={c.id}: {c.name_it}"
            + (f" ({c.intensity})" if c.intensity else "")
            + f" MET={c.met}"
            for c in candidates
        )
        selection = await gateway.call_structured(
            step="extract",
            system_prompt=(
                "Ti vengono forniti un'attività fisica descritta da un utente "
                "italiano (con eventuale intensità) e una lista di righe candidate "
                "di una tabella MET. Scegli l'id della riga che corrisponde meglio, "
                "considerando l'intensità se indicata, oppure null se nessuna corrisponde."
            ),
            content=TextContent(
                text=(
                    f'Attività: "{activity_description}", intensità: "{intensity_text or "non indicata"}"\n\n'
                    f"Candidati:\n{candidate_text}"
                )
            ),
            schema=METRowSelection,
        )
        if selection.selected_candidate_id is not None:
            chosen = next(
                (c for c in candidates if c.id == selection.selected_candidate_id), None
            )
            if chosen is not None:
                resolved = ResolvedMET(met=chosen.met, provenance=Provenance.tabella)

    if resolved is None:
        estimate = await gateway.call_structured(
            step="extract",
            system_prompt=(
                "Stima il valore MET (metabolic equivalent) dell'attività fisica "
                "descritta dall'utente, considerando l'intensità se indicata."
            ),
            content=TextContent(
                text=f'Attività: "{activity_description}", intensità: "{intensity_text or "non indicata"}"'
            ),
            schema=METEstimate,
        )
        resolved = ResolvedMET(met=estimate.met, provenance=Provenance.llm)

    session.add(
        METCache(
            normalized_key=key,
            met=resolved.met,
            provenance=resolved.provenance,
            display_name_it=activity_description,
            created_at=utcnow(),
        )
    )
    await session.flush()

    return resolved
