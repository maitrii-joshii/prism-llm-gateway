from datetime import datetime, timedelta, timezone

from prism.ports.clock import Clock


class FakeClock(Clock):
    """A controllable clock for deterministic tests."""

    def __init__(self, current_time: datetime) -> None:
        if current_time.tzinfo is None or current_time.utcoffset() is None:
            raise ValueError("current_time must be timezone-aware")

        self._current_time = current_time

    def now(self) -> datetime:
        return self._current_time

    def advance(self, seconds: float) -> None:
        if seconds < 0:
            raise ValueError("seconds cannot be negative")

        self._current_time += timedelta(seconds=seconds)
