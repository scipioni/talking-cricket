from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def clean_no_retention():
    from calobot.telemetry.context import no_retention_chats
    no_retention_chats.clear()
    yield
    no_retention_chats.clear()


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
