from __future__ import annotations

from calobot.profile.service import register_or_get_user
from calobot.telegram.handlers import _welcome_message


def test_welcome_message_covers_required_content():
    lowered = _welcome_message("Grillo Parlante").lower()
    # purpose/capabilities
    assert "peso" in lowered
    assert "attività" in lowered
    # data sources
    assert "usda" in lowered
    assert "modello linguistico" in lowered or "llm" in lowered
    # disclaimer: experimental, not medical, no liability
    assert "non è un ausilio medico" in lowered
    assert "sperimentale" in lowered
    assert "responsabilità" in lowered


async def test_is_new_true_only_on_first_contact(db_session):
    first = await register_or_get_user(db_session, telegram_user_id=999)
    await db_session.commit()
    assert first.is_new is True

    second = await register_or_get_user(db_session, telegram_user_id=999)
    assert second.is_new is False
