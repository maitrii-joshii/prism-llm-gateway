from abc import ABC, abstractmethod
from datetime import datetime


class Clock(ABC):
    """Contract for providing the current time."""

    @abstractmethod
    def now(self) -> datetime:
        """Return the current time as a datetime."""
        ...
