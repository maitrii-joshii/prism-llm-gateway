"""Unit tests for Prism's heuristic difficulty classifier."""

import pytest

from prism.services.router import (
    DifficultyClassifier,
    HeuristicClassifier,
)


@pytest.fixture
def classifier():
    return HeuristicClassifier()


def test_heuristic_classifier_implements_strategy_interface(classifier):
    assert isinstance(classifier, DifficultyClassifier)


def test_short_hard_prompt_is_classified_as_smart(classifier):
    result = classifier.classify("Prove that 2 is irrational.")

    assert result["tier"] == "smart"
    assert 0.0 <= result["score"] <= 1.0
    assert "prove" in result["reason"]


def test_easy_prompt_is_classified_as_fast(classifier):
    result = classifier.classify("List five Python frameworks.")

    assert result["tier"] == "fast"
    assert result["score"] == 0.0


def test_long_easy_prompt_is_classified_as_fast(classifier):
    prompt = (
        "Summarize the following information in a short paragraph. "
        "The document describes the history of Python, its creator, "
        "release date, popularity, community, and common applications. "
        "Keep the summary simple and easy to understand."
    )

    result = classifier.classify(prompt)

    assert result["tier"] == "fast"


def test_code_block_is_classified_as_smart(classifier):
    prompt = """
    Debug this code:

    ```python
    def divide(a, b):
        return a / b
    ```
    """

    result = classifier.classify(prompt)

    assert result["tier"] == "smart"
    assert "code block" in result["reason"]


def test_math_notation_is_classified_as_smart(classifier):
    result = classifier.classify("Solve x^2 + 2x + 1 = 0.")

    assert result["tier"] == "smart"
    assert "math notation" in result["reason"]


def test_easy_and_hard_signals_are_scored(classifier):
    result = classifier.classify(
        "Explain the logic and summarize the result."
    )

    assert result["tier"] == "smart"
    assert result["score"] == pytest.approx(0.5)


def test_prompt_without_signals_defaults_to_fast(classifier):
    result = classifier.classify(
        "Hello, I hope you are having a good day."
    )

    assert result["tier"] == "fast"
    assert result["score"] == 0.0


def test_invalid_prompt_type_raises_type_error(classifier):
    with pytest.raises(TypeError):
        classifier.classify(None)


def test_result_contains_required_fields(classifier):
    result = classifier.classify("Translate hello into French.")

    assert set(result.keys()) == {
        "tier",
        "score",
        "reason",
    }

    assert result["tier"] in {"fast", "smart"}
    assert isinstance(result["score"], float)
    assert isinstance(result["reason"], str)
