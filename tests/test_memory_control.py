from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def clean_no_retention():
    from calobot.ingestion.drafts import no_retention_drafts
    from calobot.telemetry.context import _get_persistence_path, no_retention_chats

    no_retention_chats.clear()
    no_retention_drafts.clear()
    path = _get_persistence_path()
    if path.exists():
        path.unlink()
    yield
    no_retention_chats.clear()
    no_retention_drafts.clear()
    if path.exists():
        path.unlink()


async def test_help_lists_memory_commands(client):
    sent = await client.help()
    assert len(sent) == 1
    text = sent[0].text
    assert "/memory_off" in text
    assert "/memory_on" in text


async def test_no_retention_mode_does_not_persist(client, db_session):
    from calobot.persistence.repository import get_user_by_telegram_id

    # 1. Verify user does not exist yet
    user_before = await get_user_by_telegram_id(db_session, client.telegram_user_id)
    assert user_before is None

    # 2. Activate no retention mode
    replies = await client.say("/memory_off")
    assert len(replies) == 1
    assert "nessuna ritenzione" in replies[0].text

    # 3. Try to register with /start
    await client.say("/start")

    # 4. Verify user was NOT saved to the database
    user_after = await get_user_by_telegram_id(db_session, client.telegram_user_id)
    assert user_after is None


async def test_memory_on_restores_retention(client, db_session):
    from calobot.persistence.repository import get_user_by_telegram_id

    # 1. Activate no retention mode
    await client.say("/memory_off")

    # 2. Deactivate no retention mode (turn memory back on)
    replies = await client.say("/memory_on")
    assert len(replies) == 1
    assert "normale riattivata" in replies[0].text

    # 3. Register with /start
    await client.say("/start")

    # 4. Verify user WAS successfully saved to the database
    user = await get_user_by_telegram_id(db_session, client.telegram_user_id)
    assert user is not None


async def test_profile_command_shows_memory_status(client):
    # Register first (to ensure user exists for profile)
    await client.say("/start")

    # 1. Check with memory ON (default)
    replies_on = await client.say("/profilo")
    assert "Stato memoria: ON" in replies_on[0].text

    # 2. Check with memory OFF
    await client.say("/memory_off")
    replies_off = await client.say("/profilo")
    assert "Stato memoria: OFF" in replies_off[0].text


async def test_no_retention_persistence_survives_reloads(client):
    from calobot.telemetry.context import (
        _get_persistence_path,
        load_no_retention_chats,
        no_retention_chats,
    )

    path = _get_persistence_path()
    assert not path.exists()

    # 1. Activate no retention mode
    await client.say("/memory_off")
    assert client.chat_id in no_retention_chats
    assert path.exists()

    # 2. Simulate process restart by clearing the in-memory set and reloading from file
    no_retention_chats.clear()
    assert client.chat_id not in no_retention_chats

    load_no_retention_chats()
    assert client.chat_id in no_retention_chats

    # 3. Deactivate no retention mode (turn memory back on)
    await client.say("/memory_on")
    assert client.chat_id not in no_retention_chats

    # 4. Simulate process restart again (should load empty list/no-retention off)
    no_retention_chats.add(client.chat_id)  # Add dummy
    load_no_retention_chats()
    assert client.chat_id not in no_retention_chats


async def test_no_retention_mode_preserves_drafts_across_turns(client, db_session, llm):
    from harness.state import create_onboarded_user

    from calobot.persistence.seed import seed_all

    # 1. Seed and onboard user directly
    await seed_all(db_session)
    await create_onboarded_user(db_session, client.telegram_user_id)

    # 2. Enable no-retention mode
    await client.say("/memory_off")

    # 3. Log a physical activity without specifying intensity, which requires clarification
    # Push 1: classify -> activity
    # Push 2: extract -> camminata, 30 min
    # Push 3: resolve_met selection -> None
    # Push 4: resolve_met estimate -> 5.5 MET
    llm.push(
        {"intent": "activity", "ignored_text": None},
        {"activity_description": "camminata", "duration_minutes": 30},
        {"selected_candidate_id": None},
        {"met": 5.5},
    )

    replies = await client.say("ho camminato mezz'ora")

    # It should ask for intensity
    assert "intensità" in replies[0].text

    # 4. Answer the clarification (e.g. svelta)
    final_replies = await client.say("svelta")

    # It should successfully log and finalize the activity!
    assert "Registrato: camminata" in final_replies[0].text

