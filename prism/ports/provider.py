from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any

from prism.domain.models import ProviderResponse


class ProviderAdapter(ABC):
    """Contract for an LLM provider adapter."""

    @abstractmethod
    async def complete(self, request: dict[str, Any]) -> ProviderResponse:
        """Return a complete, normalized provider response."""
        ...

    @abstractmethod
    def stream(self, request: dict[str, Any]) -> AsyncIterator[dict[str, Any]]:
        """Yield provider response chunks asynchronously."""
        ...
