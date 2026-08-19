from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio

os.environ.setdefault("CALOBOT_TELEGRAM_BOT_TOKEN", "test-token")

from calobot.persistence.engine import create_engine, get_session_factory, init_engine
from calobot.persistence.models import Base


@pytest_asyncio.fixture
async def db_session() -> AsyncIterator:
    init_engine("sqlite+aiosqlite://", in_memory=True)
    from calobot.persistence import engine as engine_module

    engine = create_engine("sqlite+aiosqlite://", in_memory=True)
    engine_module._engine = engine
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from calobot.persistence.engine import NonRetentiveAsyncSession

    engine_module._session_factory = async_sessionmaker(
        engine, class_=NonRetentiveAsyncSession, expire_on_commit=False
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = get_session_factory()
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.fixture
def settings():
    from calobot.settings import get_settings

    get_settings.cache_clear()
    return get_settings()


@pytest.fixture(autouse=True)
def offline(request, monkeypatch):
    """No test contacts the language model endpoint unless it is marked `live`.

    Enforced at the HTTP client rather than trusted: a scenario that silently reached
    a real endpoint would make the suite slow, costly and non-deterministic without
    anything failing to say so.
    """
    if request.node.get_closest_marker("live"):
        return

    async def blocked(*args, **kwargs):
        raise AssertionError(
            "this test tried to contact the language model endpoint; use the `llm` "
            "fixture, a cassette, or mark the test with @pytest.mark.live"
        )

    monkeypatch.setattr("openai.AsyncOpenAI.post", blocked, raising=False)
    monkeypatch.setattr("openai.AsyncOpenAI.request", blocked, raising=False)


@pytest.fixture
def fake_bot():
    from harness.transport import FakeBot

    return FakeBot()


@pytest.fixture
def client(fake_bot, settings, db_session):
    """A user in a private chat, driving the real handlers through the transport
    double. Depends on db_session so the engine the handlers reach for is the
    in-memory one."""
    from harness.client import Client

    return Client(fake_bot, settings, telegram_user_id=42)


@pytest.fixture
def llm(settings, monkeypatch):
    from harness.llm import ScriptedLLM

    return ScriptedLLM(settings).install(monkeypatch)


@pytest.fixture
def run(client, db_session, settings):
    """The same conversation as `client`, with the hard invariants evaluated after
    every action."""
    from harness.run import CheckedRun

    return CheckedRun(client=client, session=db_session, tz=settings.timezone)


@pytest.fixture
def agent_llm(settings):
    """A scripted model for the simulated user. Deliberately a separate gateway from
    the bot's: the two are different actors, and interleaving their scripted replies
    in one queue makes a test unreadable."""
    from harness.llm import ScriptedLLM

    return ScriptedLLM(settings)


@pytest.fixture
def clock():
    """A clock the test drives, installed into the single seam every read of "now"
    goes through. Always uninstalled, so one test cannot leave the process in
    simulated time."""
    import datetime as dt

    from harness.clock import SimulatedClock

    simulated = SimulatedClock(dt.datetime(2026, 3, 2, 9, 0, tzinfo=dt.UTC)).install()
    try:
        yield simulated
    finally:
        simulated.uninstall()
