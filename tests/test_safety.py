from __future__ import annotations

from unittest.mock import AsyncMock

from calobot.llm.content import TextContent
from calobot.llm.gateway import LLMGateway
from calobot.safety.conversation import handle_other
from calobot.safety.medical import REFUSAL_TEXT, is_medical_topic
from calobot.settings import Settings


def test_medical_keywords_detected():
    assert is_medical_topic("ho il diabete, cosa posso mangiare?")
    assert is_medical_topic("che farmaco devo prendere?")
    assert not is_medical_topic("ciao come stai")


async def test_medical_topic_refused_without_calling_llm():
    settings = Settings(telegram_bot_token="x")  # type: ignore[call-arg]
    gateway = LLMGateway(settings)
    gateway._client.chat.completions.create = AsyncMock()

    reply = await handle_other(gateway, "ho l'anoressia, mi aiuti?", TextContent(text="x"))

    assert reply == REFUSAL_TEXT
    gateway._client.chat.completions.create.assert_not_awaited()
