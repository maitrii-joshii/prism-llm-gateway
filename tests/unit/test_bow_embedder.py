"""Unit tests for the Bag-of-Words embedder."""

import pytest

from prism.adapters.bow_embedder import BowEmbedder, cosine_similarity


@pytest.fixture
def embedder():
    return BowEmbedder()


def test_embed_returns_fixed_size_vector(embedder):
    vector = embedder.embed("Reset my password")

    assert len(vector) == BowEmbedder.VECTOR_SIZE
    assert all(isinstance(value, float) for value in vector)


def test_stop_words_are_removed(embedder):
    tokens = embedder.tokenize("How do I reset my password?")

    assert tokens == ["reset", "password"]


def test_tokens_are_lowercase(embedder):
    tokens = embedder.tokenize("RESET Password")

    assert tokens == ["reset", "password"]


def test_empty_text_returns_zero_vector(embedder):
    vector = embedder.embed("")

    assert len(vector) == BowEmbedder.VECTOR_SIZE
    assert all(value == 0.0 for value in vector)


def test_related_prompts_have_higher_similarity(embedder):
    first = embedder.embed("Reset my password")
    second = embedder.embed("How do I change my password?")

    similarity = cosine_similarity(first, second)

    assert similarity > 0.3


def test_unrelated_prompts_have_low_similarity(embedder):
    first = embedder.embed("Reset my password")
    second = embedder.embed("What is quantum computing?")

    similarity = cosine_similarity(first, second)

    assert similarity < 0.2


def test_identical_prompts_have_similarity_one(embedder):
    first = embedder.embed("Reset my password")
    second = embedder.embed("Reset my password")

    assert cosine_similarity(first, second) == pytest.approx(1.0)


def test_zero_vectors_have_zero_similarity():
    zero_vector = [0.0, 0.0, 0.0]

    assert cosine_similarity(zero_vector, zero_vector) == 0.0


def test_different_vector_dimensions_raise_error():
    with pytest.raises(ValueError):
        cosine_similarity([1.0, 2.0], [1.0, 2.0, 3.0])


def test_cosine_similarity_is_within_valid_range(embedder):
    first = embedder.embed("Reset my password")
    second = embedder.embed("How do I change my password?")

    similarity = cosine_similarity(first, second)

    assert 0.0 <= similarity <= 1.0
