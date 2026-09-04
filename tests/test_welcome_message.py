from __future__ import annotations

from calobot.profile.service import register_or_get_user
from calobot.telegram.handlers import HELP_TEXT, _welcome_message


def test_welcome_message_covers_required_content():
    """specs/help-and-welcome - The welcome message orients a first-time user,
    scenario 'A new user makes first contact'."""
    lowered = _welcome_message("Grillo Parlante").lower()
    # purpose/capabilities
    assert "peso" in lowered
    assert "attività" in lowered
    # disclaimer: experimental, not medical
    assert "parere medico" in lowered or "ausilio medico" in lowered
    assert "sperimentale" in lowered
    # names the bot, and leads into profile setup
    assert "grillo parlante" in lowered
    assert "profilo" in lowered


def test_welcome_message_shows_an_advice_example():
    """specs/help-and-welcome - The welcome message orients a first-time user: the
    examples must cover asking about own data and asking for a meal suggestion, both
    reachable by writing to the bot since 2026-08-17 and 2026-08-23 respectively."""
    lowered = _welcome_message("Grillo Parlante").lower()

    assert "come sono andato" in lowered
    assert "cosa posso mangiare" in lowered


def test_welcome_message_disclaimer_is_present():
    """specs/help-and-welcome - scenario 'The disclaimer is present'."""
    lowered = _welcome_message("Grillo Parlante").lower()

    assert "sperimentale" in lowered
    assert "non sostituisce un parere medico" in lowered


# -- help text: every conversational capability is discoverable --------------------

_HELP_CAPABILITY_MARKERS = {
    "log food": "ho mangiato una mela",
    "log activity": "un'ora di camminata",
    "log weight": "oggi peso 78kg",
    "request a report": "report settimanale",
    "ask about own data": "come sono andato questa settimana?",
    "ask for a meal suggestion": "cosa posso mangiare stasera?",
    "send a photo": "foto",
    "correct the profile": "peso obiettivo",
}


def test_help_text_shows_an_example_for_every_conversational_capability():
    """specs/help-and-welcome - Every conversational capability is discoverable from
    the help text, scenario 'A user asks what the bot can do'."""
    lowered = HELP_TEXT.lower()

    missing = [name for name, marker in _HELP_CAPABILITY_MARKERS.items() if marker not in lowered]
    assert not missing, f"help text does not describe: {missing}"


def test_help_text_lists_the_commands():
    """specs/help-and-welcome - Every conversational capability is discoverable from
    the help text: the commands the bot responds to are listed."""
    for command in ("/start", "/profilo", "/annulla", "/cancellami", "/help"):
        assert command in HELP_TEXT


def test_help_text_states_that_macronutrients_are_tracked_but_sodium_and_sugar_are_not():
    """specs/help-and-welcome - The help text states what the bot does not track,
    scenario 'A user wonders whether macronutrients are tracked'."""
    lowered = HELP_TEXT.lower()

    assert "calorie" in lowered
    assert "macronutrienti" in lowered
    assert "proteine" in lowered
    assert "non traccio" in lowered
    assert "sodio" in lowered


def test_self_description_promises_nothing_clinical():
    """specs/help-and-welcome - Self-description makes no claim the bot cannot honour,
    scenario 'No clinical promise is made'."""
    for text in (HELP_TEXT, _welcome_message("Grillo Parlante")):
        lowered = text.lower()
        for promise in ("diagnos", "cura ", "terapia", "prescriz"):
            assert promise not in lowered


def test_help_text_describes_no_unimplemented_capability():
    """specs/help-and-welcome - scenario 'An example is shown for an unimplemented
    capability': guards against advertising unshipped work. proactive-nudges has
    since shipped (default-off, opt-in via /notifiche_on), so mentioning it here is
    no longer premature - only "promemoria" and the two open-ended reminder phrasings
    remain unshipped."""
    lowered = HELP_TEXT.lower()

    for unshipped in ("promemoria", "ti ricorderò", "ti scriverò io"):
        assert unshipped not in lowered


async def test_is_new_true_only_on_first_contact(db_session):
    first = await register_or_get_user(db_session, telegram_user_id=999)
    await db_session.commit()
    assert first.is_new is True

    second = await register_or_get_user(db_session, telegram_user_id=999)
    assert second.is_new is False
