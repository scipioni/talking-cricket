"""Engine setup. WAL mode + busy timeout so reporting reads don't block ingestion writes
(design.md - Persistence). Single-writer discipline is enforced at the deployment layer
(Dockerfile/stack file), not here - this module only configures the connection."""

from __future__ import annotations

from typing import Any

import logging
from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

logger = logging.getLogger(__name__)

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


class NonRetentiveAsyncSession(AsyncSession):
    async def commit(self) -> None:
        """Bypass transaction commit if the active_no_retention context is True."""
        from calobot.telemetry.context import active_no_retention

        if active_no_retention.get(False):
            logger.info("Database commit bypassed because no-retention mode is active.")
            await self.flush()
            return
        await super().commit()


def _set_sqlite_pragmas(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def create_engine(database_url: str, *, in_memory: bool = False) -> AsyncEngine:
    kwargs: dict[str, Any] = {}
    if in_memory:
        # tests use a single shared in-memory connection, not WAL (irrelevant without a file)
        kwargs["poolclass"] = StaticPool
        kwargs["connect_args"] = {"check_same_thread": False}
    engine = create_async_engine(database_url, **kwargs)
    if not in_memory:
        event.listen(engine.sync_engine, "connect", _set_sqlite_pragmas)
    return engine


def init_engine(database_url: str, *, in_memory: bool = False) -> None:
    global _engine, _session_factory
    _engine = create_engine(database_url, in_memory=in_memory)
    _session_factory = async_sessionmaker(
        _engine, class_=NonRetentiveAsyncSession, expire_on_commit=False
    )


def get_engine() -> AsyncEngine:
    if _engine is None:
        raise RuntimeError("Engine not initialized: call init_engine() first")
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    if _session_factory is None:
        raise RuntimeError("Engine not initialized: call init_engine() first")
    return _session_factory
