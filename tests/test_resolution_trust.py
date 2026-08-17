"""Provenance trust ordering for the resolution cache (tasks.md 6.2): a
higher-trust value overwrites a lower-trust one for the same key, never the
reverse - etichetta > off > tabella > llm (design.md - Label reading writes
straight into the resolution cache)."""

from __future__ import annotations

from calobot.food.resolver import normalize_description, write_resolution
from calobot.persistence.models import Provenance, ResolutionCache


async def _cached(session, key):
    return await session.get(ResolutionCache, key)


async def test_higher_trust_overwrites_lower_trust(db_session):
    key = normalize_description("barretta ai cereali")
    await write_resolution(
        db_session, key=key, kcal_per_100g=100, provenance=Provenance.llm, display_name_it="x"
    )

    await write_resolution(
        db_session,
        key=key,
        kcal_per_100g=430,
        provenance=Provenance.etichetta,
        display_name_it="Barretta ai cereali",
    )

    cached = await _cached(db_session, key)
    assert cached.kcal_per_100g == 430
    assert cached.provenance == Provenance.etichetta


async def test_lower_trust_does_not_overwrite_higher_trust(db_session):
    key = normalize_description("barretta ai cereali")
    await write_resolution(
        db_session,
        key=key,
        kcal_per_100g=430,
        provenance=Provenance.etichetta,
        display_name_it="Barretta ai cereali",
    )

    await write_resolution(
        db_session, key=key, kcal_per_100g=999, provenance=Provenance.llm, display_name_it="x"
    )

    cached = await _cached(db_session, key)
    assert cached.kcal_per_100g == 430
    assert cached.provenance == Provenance.etichetta


async def test_off_does_not_overwrite_etichetta_but_does_overwrite_tabella(db_session):
    key = normalize_description("yogurt bianco")
    await write_resolution(
        db_session, key=key, kcal_per_100g=60, provenance=Provenance.tabella, display_name_it="x"
    )
    await write_resolution(
        db_session, key=key, kcal_per_100g=65, provenance=Provenance.off, display_name_it="Yogurt bianco"
    )
    assert (await _cached(db_session, key)).provenance == Provenance.off

    await write_resolution(
        db_session,
        key=key,
        kcal_per_100g=70,
        provenance=Provenance.etichetta,
        display_name_it="Yogurt bianco",
    )
    assert (await _cached(db_session, key)).provenance == Provenance.etichetta

    await write_resolution(
        db_session, key=key, kcal_per_100g=999, provenance=Provenance.off, display_name_it="x"
    )
    cached = await _cached(db_session, key)
    assert cached.provenance == Provenance.etichetta
    assert cached.kcal_per_100g == 70
