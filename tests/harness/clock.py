"""A clock a scenario drives (specs/conversation-simulation - Simulated time).

Installed into the single seam in `calobot.persistence.timeutil`, so it reaches
every read of "now" at once - including the SQLAlchemy column defaults that stamp
`created_at` on every stored row, which is what makes day-attribution assertions
mean anything.
"""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

from calobot.persistence import timeutil


class SimulatedClock:
    def __init__(self, start: dt.datetime) -> None:
        if start.tzinfo is None:
            raise ValueError("the simulated clock needs an aware instant")
        self._now = start.astimezone(dt.UTC)

    def now(self) -> dt.datetime:
        return self._now

    def install(self) -> SimulatedClock:
        timeutil.set_clock(self.now)
        return self

    @staticmethod
    def uninstall() -> None:
        timeutil.reset_clock()

    # -- driving ----------------------------------------------------------

    def set(self, moment: dt.datetime) -> None:
        if moment.tzinfo is None:
            raise ValueError("the simulated clock needs an aware instant")
        self._now = moment.astimezone(dt.UTC)

    def set_local(self, moment: dt.datetime, tz: ZoneInfo) -> None:
        """Set the instant from a wall-clock reading in `tz`, which is how a scenario
        expresses "day 3 at 13:20" without doing the offset arithmetic itself."""
        self.set(moment.replace(tzinfo=tz))

    def advance(
        self, *, days: int = 0, hours: int = 0, minutes: int = 0, seconds: int = 0
    ) -> None:
        self._now += dt.timedelta(days=days, hours=hours, minutes=minutes, seconds=seconds)

    def advance_to_next_local_day(self, tz: ZoneInfo, *, at_hour: int = 9) -> None:
        """Move to a given hour of the following local calendar day in `tz`. Crossing
        a day boundary this way stays correct across DST, because the target is a
        wall-clock reading rather than a fixed number of hours."""
        local_tomorrow = self._now.astimezone(tz).date() + dt.timedelta(days=1)
        self.set_local(dt.datetime.combine(local_tomorrow, dt.time(hour=at_hour)), tz)
