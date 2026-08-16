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

    engine_module._session_factory = async_sessionmaker(engine, expire_on_commit=False)

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
