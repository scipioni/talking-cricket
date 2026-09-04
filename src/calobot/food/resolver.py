"""Hybrid kcal resolution: cache -> bundled table (LLM picks the row) -> LLM estimate.
See specs/food-logging - Hybrid energy resolution, Resolution cache and consistency,
Food descriptions presented in Italian. design.md - Calorie resolution: the model is
a matcher over retrieved candidates, never a search engine, and every resolution is
cached so the same food always costs the same for that user."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from calobot.llm.content import MessageContent, TextContent
from calobot.llm.gateway import LLMGateway
from calobot.persistence.candidates import retrieve_food_candidates
from calobot.persistence.models import Provenance, ResolutionCache
from calobot.persistence.timeutil import utcnow

MAX_PLAUSIBLE_KCAL_PER_100G = 950  # pure fat (~900) plus headroom; catches OCR/LLM magnitude errors
MIN_PLAUSIBLE_KCAL_PER_100G = 0

# Trust ordering across provenance values (design.md - Label reading writes straight
# into the resolution cache): a photographed label is ground truth for the item the
# user is actually holding; a lookup service record may describe a different pack;
# the bundled table is a matched row, not the exact product; a model estimate is the
# last resort. A higher-trust value overwrites a lower-trust one for the same
# normalized key - never the reverse.
PROVENANCE_TRUST: dict[Provenance, int] = {
    Provenance.etichetta: 3,
    Provenance.off: 2,
    Provenance.tabella: 1,
    Provenance.llm: 0,
}


def normalize_description(description: str) -> str:
    text = description.strip().lower()
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"\s+", " ", text)
    return text


@dataclass(frozen=True)
class ResolvedFood:
    kcal_per_100g: float
    provenance: Provenance
    display_name_it: str
    protein_per_100g: float | None = None
    fat_per_100g: float | None = None
    carbs_per_100g: float | None = None
    fiber_per_100g: float | None = None


class RowSelection(BaseModel):
    selected_candidate_id: int | None = Field(
        default=None, description="id of the best matching candidate, or null if none fit"
    )


class EstimateResult(BaseModel):
    kcal_per_100g: float = Field(ge=0, le=MAX_PLAUSIBLE_KCAL_PER_100G)
    display_name_it: str
    protein_per_100g: float | None = Field(default=None, ge=0, le=100)
    fat_per_100g: float | None = Field(default=None, ge=0, le=100)
    carbs_per_100g: float | None = Field(default=None, ge=0, le=100)
    fiber_per_100g: float | None = Field(default=None, ge=0, le=100)


async def _select_from_table(
    gateway: LLMGateway, description: str, content: MessageContent
) -> RowSelection:
    return await gateway.call_structured(
        step="extract",
        system_prompt=(
            "Ti vengono forniti un alimento descritto da un utente italiano e una "
            "lista di righe candidate di una tabella nutrizionale (in inglese, con "
            "un id). Scegli l'id della riga che corrisponde meglio all'alimento "
            "descritto, oppure null se nessuna corrisponde davvero."
        ),
        content=content,
        schema=RowSelection,
    )


async def _estimate(gateway: LLMGateway, content: MessageContent) -> EstimateResult:
    return await gateway.call_structured(
        step="extract",
        system_prompt=(
            "Stima le kilocalorie per 100 grammi dell'alimento descritto "
            "dall'utente (italiano), insieme a proteine, grassi, carboidrati e fibre "
            "per 100 grammi. display_name_it deve essere il nome "
            "dell'alimento in italiano, come lo scriverebbe un utente."
        ),
        content=content,
        schema=EstimateResult,
    )


async def write_resolution(
    session: AsyncSession,
    *,
    key: str,
    kcal_per_100g: float,
    provenance: Provenance,
    display_name_it: str,
    protein_per_100g: float | None = None,
    fat_per_100g: float | None = None,
    carbs_per_100g: float | None = None,
    fiber_per_100g: float | None = None,
) -> None:
    """Writes a resolution into the cache, respecting the trust ordering: a
    higher-trust value overwrites a lower-trust one for the same key, but never the
    reverse (tasks.md 6.2). Macro fields follow the same all-or-nothing overwrite as
    kcal_per_100g - see design.md, add-macro-nutrient-tracking."""
    existing = await session.get(ResolutionCache, key)
    if existing is not None:
        if PROVENANCE_TRUST[provenance] < PROVENANCE_TRUST[existing.provenance]:
            return
        existing.kcal_per_100g = kcal_per_100g
        existing.protein_per_100g = protein_per_100g
        existing.fat_per_100g = fat_per_100g
        existing.carbs_per_100g = carbs_per_100g
        existing.fiber_per_100g = fiber_per_100g
        existing.provenance = provenance
        existing.display_name_it = display_name_it
        existing.created_at = utcnow()
        await session.flush()
        return

    session.add(
        ResolutionCache(
            normalized_key=key,
            kcal_per_100g=kcal_per_100g,
            protein_per_100g=protein_per_100g,
            fat_per_100g=fat_per_100g,
            carbs_per_100g=carbs_per_100g,
            fiber_per_100g=fiber_per_100g,
            provenance=provenance,
            display_name_it=display_name_it,
            created_at=utcnow(),
        )
    )
    await session.flush()


async def refresh_cached_macros(
    session: AsyncSession, gateway: LLMGateway, description: str
) -> ResolvedFood | None:
    """For a food whose energy is already cached - so `resolve_food_energy` would
    return it unchanged via the cache-hit path below, never re-resolving - but whose
    macro columns are still null (a resolution cached before add-macro-nutrient-
    tracking added them), resolves just the macro values and patches them onto the
    existing cache row. kcal_per_100g, provenance and display_name_it are left
    untouched, since only the macro columns were ever missing. Used by
    scripts/backfill_macros.py, where the normal resolve_food_energy cache hit would
    otherwise mean every already-logged food stays macro-null forever.

    Returns None when there is no cache entry to refresh, or its macros are already
    resolved (nothing to do)."""
    key = normalize_description(description)
    cached = await session.get(ResolutionCache, key)
    if cached is None:
        return None
    if any(
        v is not None
        for v in (
            cached.protein_per_100g,
            cached.fat_per_100g,
            cached.carbs_per_100g,
            cached.fiber_per_100g,
        )
    ):
        return None

    candidates = await retrieve_food_candidates(session, description)
    macros: tuple[float | None, float | None, float | None, float | None] | None = None

    if candidates:
        candidate_text = "\n".join(
            f"id={c.id}: {c.source_name_en} (alias italiano: {c.matched_alias})"
            for c in candidates
        )
        prompt_content = TextContent(
            text=f'Alimento descritto dall\'utente: "{description}"\n\nCandidati:\n{candidate_text}'
        )
        selection = await _select_from_table(gateway, description, prompt_content)
        if selection.selected_candidate_id is not None:
            chosen = next(
                (c for c in candidates if c.id == selection.selected_candidate_id), None
            )
            if chosen is not None:
                macros = (
                    chosen.protein_per_100g,
                    chosen.fat_per_100g,
                    chosen.carbs_per_100g,
                    chosen.fiber_per_100g,
                )

    if macros is None:
        estimate = await _estimate(gateway, TextContent(text=description))
        macros = (
            estimate.protein_per_100g,
            estimate.fat_per_100g,
            estimate.carbs_per_100g,
            estimate.fiber_per_100g,
        )

    cached.protein_per_100g, cached.fat_per_100g, cached.carbs_per_100g, cached.fiber_per_100g = macros
    await session.flush()

    return ResolvedFood(
        kcal_per_100g=cached.kcal_per_100g,
        provenance=cached.provenance,
        display_name_it=cached.display_name_it,
        protein_per_100g=macros[0],
        fat_per_100g=macros[1],
        carbs_per_100g=macros[2],
        fiber_per_100g=macros[3],
    )


async def resolve_food_energy(
    session: AsyncSession, gateway: LLMGateway, description: str
) -> ResolvedFood:
    key = normalize_description(description)

    cached = await session.get(ResolutionCache, key)
    if cached is not None:
        return ResolvedFood(
            kcal_per_100g=cached.kcal_per_100g,
            provenance=cached.provenance,
            display_name_it=cached.display_name_it,
            protein_per_100g=cached.protein_per_100g,
            fat_per_100g=cached.fat_per_100g,
            carbs_per_100g=cached.carbs_per_100g,
            fiber_per_100g=cached.fiber_per_100g,
        )

    candidates = await retrieve_food_candidates(session, description)

    resolved: ResolvedFood | None = None

    if candidates:
        candidate_text = "\n".join(
            f"id={c.id}: {c.source_name_en} (alias italiano: {c.matched_alias})"
            for c in candidates
        )
        prompt_content = TextContent(
            text=f'Alimento descritto dall\'utente: "{description}"\n\nCandidati:\n{candidate_text}'
        )
        selection = await _select_from_table(gateway, description, prompt_content)
        if selection.selected_candidate_id is not None:
            chosen = next(
                (c for c in candidates if c.id == selection.selected_candidate_id), None
            )
            if chosen is not None:
                resolved = ResolvedFood(
                    kcal_per_100g=chosen.kcal_per_100g,
                    provenance=Provenance.tabella,
                    display_name_it=description,  # specs/food-logging: always show it in Italian
                    protein_per_100g=chosen.protein_per_100g,
                    fat_per_100g=chosen.fat_per_100g,
                    carbs_per_100g=chosen.carbs_per_100g,
                    fiber_per_100g=chosen.fiber_per_100g,
                )

    if resolved is None:
        estimate = await _estimate(gateway, TextContent(text=description))
        resolved = ResolvedFood(
            kcal_per_100g=estimate.kcal_per_100g,
            provenance=Provenance.llm,
            display_name_it=estimate.display_name_it or description,
            protein_per_100g=estimate.protein_per_100g,
            fat_per_100g=estimate.fat_per_100g,
            carbs_per_100g=estimate.carbs_per_100g,
            fiber_per_100g=estimate.fiber_per_100g,
        )

    await write_resolution(
        session,
        key=key,
        kcal_per_100g=resolved.kcal_per_100g,
        provenance=resolved.provenance,
        display_name_it=resolved.display_name_it,
        protein_per_100g=resolved.protein_per_100g,
        fat_per_100g=resolved.fat_per_100g,
        carbs_per_100g=resolved.carbs_per_100g,
        fiber_per_100g=resolved.fiber_per_100g,
    )

    return resolved
