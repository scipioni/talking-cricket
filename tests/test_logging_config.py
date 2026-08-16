"""Regression test for a real bug found while running the app for real (not just
under pytest): Alembic's migration step calls logging.config.fileConfig(alembic.ini),
which (a) disables every pre-existing logger not listed in alembic.ini and (b) resets
the root logger's level/handlers per alembic.ini's own [logger_root] section (WARNING).
Both silently swallow the app's own INFO logs for the rest of the process, with no
error - it looks exactly like a hang, since the bot keeps working, just silently."""

from __future__ import annotations

import io
import logging
from contextlib import redirect_stdout
from logging.config import fileConfig

from calobot.logging_config import configure_logging


def test_configure_logging_survives_alembic_fileconfig(tmp_path):
    ini_path = tmp_path / "alembic.ini"
    ini_path.write_text(
        "[loggers]\nkeys = root\n\n"
        "[handlers]\nkeys = console\n\n"
        "[formatters]\nkeys = generic\n\n"
        "[logger_root]\nlevel = WARNING\nhandlers = console\nqualname =\n\n"
        "[handler_console]\nclass = StreamHandler\nargs = (sys.stderr,)\nlevel = NOTSET\n"
        "formatter = generic\n\n"
        "[formatter_generic]\nformat = %(levelname)s %(message)s\n"
    )

    configure_logging("INFO")
    logger = logging.getLogger("calobot.some.module")

    # Simulates run_migrations(): alembic's own fileConfig call, exactly as
    # migrations/env.py invokes it (with the fix applied there too).
    fileConfig(str(ini_path), disable_existing_loggers=False)

    assert logger.disabled is False
    assert logging.getLogger().level == logging.WARNING  # alembic did reset this

    # The second configure_logging() call, as main.py does after migrations,
    # must actually restore INFO-level logging - not silently no-op - and
    # configure_logging() binds to whatever sys.stdout is at call time.
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        configure_logging("INFO")
        logger.info("this must be visible")

    assert "this must be visible" in buffer.getvalue()
