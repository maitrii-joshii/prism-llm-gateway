from datetime import datetime, timezone

from prism.ports.clock import Clock


class SystemClock(Clock):
    """Clock implementation that returns the current UTC time."""

    def now(self) -> datetime:
        return datetime.now(timezone.utc)
