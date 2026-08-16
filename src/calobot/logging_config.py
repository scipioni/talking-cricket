import logging
import sys


def configure_logging(level: str) -> None:
    # force=True: without it, basicConfig() is a no-op once the root logger has
    # any handler - which it will, the second time this is called after Alembic's
    # migration step runs logging.config.fileConfig(alembic.ini) and installs its
    # own root handler. Without force=True that second call would silently do
    # nothing, leaving the app's own logging level/format clobbered by alembic's.
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stdout,
        force=True,
    )
    # aiogram is chatty at INFO with full update payloads; keep it at WARNING unless debugging.
    logging.getLogger("aiogram.event").setLevel(logging.WARNING)
