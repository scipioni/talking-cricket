"""Entry point. Runs migrations, seeds the bundled datasets, then starts the bot
with long polling (design.md - Migration Plan: 'run Alembic migrations on startup
before the bot begins polling')."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

from calobot.logging_config import configure_logging
from calobot.persistence.engine import get_session_factory, init_engine
from calobot.persistence.migrate import run_migrations
from calobot.persistence.seed import seed_all
from calobot.persistence.startup_checks import ensure_database_not_on_network_fs
from calobot.settings import Settings, get_settings
from calobot.telegram.handlers import router
from calobot.telegram.logging_middleware import (
    IncomingLoggingMiddleware,
    OutgoingLoggingMiddleware,
)

logger = logging.getLogger(__name__)


async def _async_main(settings: Settings) -> None:
    init_engine(settings.database_url)

    logger.info("loading persistent no-retention chats")
    from calobot.telemetry.context import load_no_retention_chats

    load_no_retention_chats()

    logger.info("seeding bundled datasets")
    session_factory = get_session_factory()
    async with session_factory() as session:
        await seed_all(session)

    bot = Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    bot.session.middleware(OutgoingLoggingMiddleware())
    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Avvia la registrazione o mostra il profilo"),
            BotCommand(command="profilo", description="Mostra i tuoi dati e il budget calorico"),
            BotCommand(command="annulla", description="Elimina l'ultima voce registrata"),
            BotCommand(command="cancellami", description="Elimina definitivamente tutti i dati"),
            BotCommand(command="memory_off", description="Attiva modalità nessuna ritenzione (test)"),
            BotCommand(command="memory_on", description="Riattiva la modalità normale"),
            BotCommand(command="help", description="Mostra i comandi disponibili"),
        ]
    )

    dispatcher = Dispatcher()
    dispatcher.update.outer_middleware(IncomingLoggingMiddleware())
    dispatcher.include_router(router)

    # Start the background in-memory telemetry history collector
    from calobot.telemetry.history import telemetry_history

    telemetry_history.start_listening()

    # Create and configure uvicorn server for the telemetry APIs and Dashboard
    import uvicorn

    from calobot.telemetry.server import app as telemetry_app

    config = uvicorn.Config(
        telemetry_app,
        host="0.0.0.0",
        port=settings.web_port,
        log_level="warning",
    )
    server = uvicorn.Server(config)

    logger.info("web interface listening on http://localhost:%d", settings.web_port)
    logger.info(
        "starting concurrent bot long polling and telemetry fastapi web server on port %d",
        settings.web_port,
    )

    try:
        await asyncio.gather(
            dispatcher.start_polling(bot, settings=settings),
            server.serve(),
        )
    finally:
        telemetry_history.stop_listening()


def run() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)

    ensure_database_not_on_network_fs(settings.database_path)

    # A no-op when the parent already exists (e.g. the /data volume mount in
    # Docker); lets a relative local-dev path work without a manual mkdir.
    Path(settings.database_path).resolve().parent.mkdir(parents=True, exist_ok=True)

    # Alembic's async path runs its own asyncio.run() internally, so this must
    # happen before the bot's own event loop starts (asyncio.run below), or it
    # would try to nest one event loop inside another.
    logger.info("running migrations")
    run_migrations(settings.database_url)

    # Alembic's env.py calls logging.config.fileConfig(alembic.ini), which resets
    # the root logger's level (alembic.ini sets it to WARNING) for the rest of the
    # process - silently swallowing every INFO log from here on, including the
    # ones below, with no error. Restore our own configuration before continuing.
    configure_logging(settings.log_level)

    asyncio.run(_async_main(settings))


if __name__ == "__main__":
    run()
