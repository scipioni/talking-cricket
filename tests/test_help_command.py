from __future__ import annotations


async def test_help_lists_all_commands(client):
    sent = await client.help()

    assert len(sent) == 1
    text = sent[0].text
    for command in ("/start", "/profilo", "/annulla", "/cancellami", "/help"):
        assert command in text
