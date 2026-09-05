from __future__ import annotations


async def test_help_lists_all_commands(client):
    sent = await client.help()

    assert len(sent) == 1
    text = sent[0].text
    for command in ("/start", "/profilo", "/annulla", "/cancellami", "/help"):
        assert command in text


async def test_help_mentions_photo_capabilities(client):
    sent = await client.help()
    assert len(sent) == 1
    text = sent[0].text
    assert "FOTO" in text
    assert "piatto o alimento" in text
    assert "tabella nutrizionale" in text
    assert "codice a barre" in text


async def test_help_mentions_activity_examples(client):
    sent = await client.help()
    assert len(sent) == 1
    text = sent[0].text
    assert "Attività" in text
    assert "camminata" in text
    assert "corsa" in text


async def test_help_describes_stored_entry_corrections(client):
    sent = await client.help()
    text = sent[0].text
    assert "200g" in text
    assert "/annulla" in text


async def test_help_describes_the_nudge_capability(client):
    sent = await client.help()
    text = sent[0].text
    assert "/notifiche_on" in text and "/notifiche_off" in text
    assert "obiettivo di peso" in text  # one of the kinds it may originate
    assert "disattivate di default" in text  # off unless the user opts in
    # the conversational way is described, not only the commands
    assert "scrivimelo" in text
    assert "basta notifiche" in text


async def test_welcome_mentions_counts_and_opt_in_messages(client, db_session):
    sent = await client.start()

    text = "".join(message.text for message in sent)
    assert "macronutrienti" in text
    assert "sodio" in text and "zuccheri" in text
    assert "scriverti" in text  # the bot can write first, opt-in
    assert "sperimentale" in text  # the disclaimer is untouched
