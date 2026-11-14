"""Unit tests for Prism's heuristic difficulty classifier and eval datasets."""

import json
from pathlib import Path

import pytest

from prism.services.router import (
    DifficultyClassifier,
    HeuristicClassifier,
    LengthOnlyClassifier,
)

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


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


def test_log_key_value_pairs_do_not_trigger_false_math_notation(classifier):
    prompt = (
        "Log excerpt: 2026-07-01T09:12:03Z status=200 path=/health "
        "duration_ms=12; 2026-07-01T09:14:10Z ERROR upstream=payments. "
        "What is the timestamp of the ERROR line?"
    )
    result = classifier.classify(prompt)

    assert result["tier"] == "fast"
    assert "math notation" not in result["reason"]


def test_trivial_design_of_phrase_is_classified_as_fast(classifier):
    result = classifier.classify("What is the design of the Indian flag?")

    assert result["tier"] == "fast"


def test_diagnostic_list_causes_trap_is_classified_as_smart(classifier):
    prompt = (
        "Our API p95 latency doubled after a deploy. "
        "List the most likely causes and how you would confirm each."
    )
    result = classifier.classify(prompt)

    assert result["tier"] == "smart"


def _load_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def test_training_and_eval_datasets_are_strictly_disjoint():
    train = _load_jsonl(DATA_DIR / "training_examples.jsonl")
    official_eval = _load_jsonl(DATA_DIR / "routing_eval.jsonl")
    extended_eval = _load_jsonl(DATA_DIR / "routing_eval_extended.jsonl")

    assert len(train) >= 50
    assert len(official_eval) == 20
    assert len(extended_eval) >= 40

    def norm(text: str) -> str:
        return " ".join(text.strip().lower().split())

    train_prompts = {norm(item["prompt"]) for item in train}
    official_prompts = {norm(item["prompt"]) for item in official_eval}
    extended_prompts = {norm(item["prompt"]) for item in extended_eval}

    assert not (train_prompts & official_prompts)
    assert not (train_prompts & extended_prompts)
    assert not (official_prompts & extended_prompts)


def test_heuristic_beats_length_baseline_on_both_eval_sets(classifier):
    baseline = LengthOnlyClassifier()
    official_eval = _load_jsonl(DATA_DIR / "routing_eval.jsonl")
    extended_eval = _load_jsonl(DATA_DIR / "routing_eval_extended.jsonl")

    for dataset in (official_eval, extended_eval):
        base_correct = sum(
            baseline.classify(item["prompt"])["tier"] == item["expected_tier"]
            for item in dataset
        )
        heur_correct = sum(
            classifier.classify(item["prompt"])["tier"] == item["expected_tier"]
            for item in dataset
        )
        base_acc = base_correct / len(dataset)
        heur_acc = heur_correct / len(dataset)

        assert heur_acc >= 0.85
        assert heur_acc - base_acc >= 0.40
