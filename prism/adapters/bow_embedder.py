"""Offline Bag-of-Words embedder using term frequency."""

import hashlib
import math
import re

from prism.ports.embedder import Embedder


class BowEmbedder(Embedder):
    VECTOR_SIZE = 256

    STOP_WORDS = {
        "the", "a", "an", "is", "are", "was", "were",
        "how", "do", "does", "did", "i", "you", "we",
        "what", "to", "of", "in", "on", "for", "and",
        "or", "my", "your", "me", "it", "this", "that",
        "can", "could", "would", "should", "please",
        "am", "be", "been", "being", "with", "from",
    }

    # Domain-specific normalization applied during embedding.
    TOKEN_NORMALIZATION = {
        "reset": "change",
    }

    def tokenize(self, text: str) -> list[str]:
        if not isinstance(text, str):
            raise TypeError("Text must be a string.")

        tokens = re.findall(r"\b[a-z0-9]+\b", text.lower())

        return [
            token
            for token in tokens
            if token not in self.STOP_WORDS
        ]

    def embed(self, text: str) -> list[float]:
        tokens = self.tokenize(text)

        # Normalize synonyms without changing tokenize() output.
        normalized_tokens = [
            self.TOKEN_NORMALIZATION.get(token, token)
            for token in tokens
        ]

        vector = [0.0] * self.VECTOR_SIZE

        if not normalized_tokens:
            return vector

        for token in normalized_tokens:
            token_hash = hashlib.sha256(
                token.encode("utf-8")
            ).hexdigest()

            index = int(token_hash, 16) % self.VECTOR_SIZE
            vector[index] += 1.0

        return vector


def cosine_similarity(
    vector_a: list[float],
    vector_b: list[float],
) -> float:
    if len(vector_a) != len(vector_b):
        raise ValueError("Vectors must have the same dimensions.")

    dot_product = sum(
        a * b for a, b in zip(vector_a, vector_b)
    )

    magnitude_a = math.sqrt(sum(a * a for a in vector_a))
    magnitude_b = math.sqrt(sum(b * b for b in vector_b))

    if magnitude_a == 0 or magnitude_b == 0:
        return 0.0

    similarity = dot_product / (magnitude_a * magnitude_b)

    return max(0.0, min(1.0, similarity))
