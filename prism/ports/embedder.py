from abc import ABC, abstractmethod


class Embedder(ABC):
    """Contract for converting text into a numerical vector."""

    @abstractmethod
    def embed(self, text: str) -> list[float]:
        """Convert text into an embedding vector."""
        ...
