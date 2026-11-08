"""Evaluate Prism routing classifiers against a held-out dataset."""

import json
import sys
from pathlib import Path

# Resolve project root regardless of the current working directory.
PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from prism.services.router import (
    HeuristicClassifier,
    LengthOnlyClassifier,
)


DATASET_PATH = PROJECT_ROOT / "data" / "routing_eval.jsonl"
REPORT_PATH = PROJECT_ROOT / "docs" / "routing_eval_results.md"


def load_examples():
    """Load and validate evaluation examples."""

    if not DATASET_PATH.exists():
        raise FileNotFoundError(
            f"Evaluation dataset not found: {DATASET_PATH}"
        )

    examples = []

    with DATASET_PATH.open(encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            if not line.strip():
                continue

            try:
                example = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Invalid JSON on line {line_number}: {exc}"
                ) from exc

            if "prompt" not in example or "expected_tier" not in example:
                raise ValueError(
                    f"Missing prompt or expected_tier on line {line_number}"
                )

            if example["expected_tier"] not in {"fast", "smart"}:
                raise ValueError(
                    f"Invalid expected_tier on line {line_number}"
                )

            examples.append(example)

    if not examples:
        raise ValueError("Evaluation dataset is empty.")

    return examples


def evaluate_classifier(classifier, examples):
    """Run a classifier and collect per-example predictions."""

    results = []

    for index, example in enumerate(examples, start=1):
        prediction = classifier.classify(example["prompt"])

        expected = example["expected_tier"]
        predicted = prediction["tier"]

        results.append({
            "index": index,
            "prompt": example["prompt"],
            "expected": expected,
            "predicted": predicted,
            "correct": expected == predicted,
            "score": prediction["score"],
            "reason": prediction["reason"],
        })

    correct_count = sum(
        result["correct"] for result in results
    )

    total_count = len(results)
    accuracy = correct_count / total_count * 100

    return {
        "results": results,
        "correct": correct_count,
        "incorrect": total_count - correct_count,
        "total": total_count,
        "accuracy": accuracy,
    }


def generate_report(
    baseline_results,
    heuristic_results,
    examples,
):
    """Generate a Markdown report with accuracy and case-level results."""

    lines = [
        "# Prism Routing Evaluation Results",
        "",
        "## Evaluation Summary",
        "",
        f"- Total evaluation examples: **{len(examples)}**",
        f"- Fast examples: **{sum(e['expected_tier'] == 'fast' for e in examples)}**",
        f"- Smart examples: **{sum(e['expected_tier'] == 'smart' for e in examples)}**",
        "",
        "## Classifier Accuracy",
        "",
        "| Metric | Length-Only Baseline | Heuristic Classifier |",
        "|---|---:|---:|",
        f"| Correct predictions | {baseline_results['correct']} | {heuristic_results['correct']} |",
        f"| Incorrect predictions | {baseline_results['incorrect']} | {heuristic_results['incorrect']} |",
        f"| Total examples | {baseline_results['total']} | {heuristic_results['total']} |",
        f"| Accuracy | **{baseline_results['accuracy']:.2f}%** | **{heuristic_results['accuracy']:.2f}%** |",
        "",
        "## Evaluation Per Case",
        "",
        "| # | Expected | Baseline | Baseline result | Heuristic | Heuristic result |",
        "|---:|---|---|---|---|---|",
    ]

    for baseline, heuristic in zip(
        baseline_results["results"],
        heuristic_results["results"],
    ):
        baseline_status = "PASS" if baseline["correct"] else "FAIL"
        heuristic_status = "PASS" if heuristic["correct"] else "FAIL"

        lines.append(
            f"| {baseline['index']} "
            f"| {baseline['expected']} "
            f"| {baseline['predicted']} "
            f"| {baseline_status} "
            f"| {heuristic['predicted']} "
            f"| {heuristic_status} |"
        )

    lines.extend([
        "",
        "## Heuristic Prediction Details",
        "",
    ])

    for result in heuristic_results["results"]:
        status = "PASS" if result["correct"] else "FAIL"

        prompt = result["prompt"].replace("|", "\\|").replace("\n", " ")

        lines.extend([
            f"### Case {result['index']} — {status}",
            "",
            f"- **Prompt:** {prompt}",
            f"- **Expected:** {result['expected']}",
            f"- **Predicted:** {result['predicted']}",
            f"- **Score:** {result['score']}",
            f"- **Reason:** {result['reason']}",
            "",
        ])

    difference = (
        heuristic_results["accuracy"]
        - baseline_results["accuracy"]
    )

    lines.extend([
        "## Conclusion",
        "",
        f"- Length-only baseline accuracy: **{baseline_results['accuracy']:.2f}%**",
        f"- Heuristic classifier accuracy: **{heuristic_results['accuracy']:.2f}%**",
        f"- Accuracy improvement: **{difference:+.2f} percentage points**",
        "",
    ])

    if heuristic_results["accuracy"] > baseline_results["accuracy"]:
        lines.append(
            "**Result: PASS — Heuristic classifier beats the length-only baseline.**"
        )
    elif heuristic_results["accuracy"] == baseline_results["accuracy"]:
        lines.append(
            "**Result: FAIL — Heuristic classifier matches the baseline but does not beat it.**"
        )
    else:
        lines.append(
            "**Result: FAIL — Heuristic classifier performs below the baseline.**"
        )

    lines.append("")

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def main():
    """Run the routing evaluation and save the report."""

    examples = load_examples()

    baseline = LengthOnlyClassifier()
    heuristic = HeuristicClassifier()

    baseline_results = evaluate_classifier(baseline, examples)
    heuristic_results = evaluate_classifier(heuristic, examples)

    print("\n========== PRISM ROUTING EVALUATION ==========\n")

    print(f"Total examples: {len(examples)}")

    for name, result in [
        ("Length-only baseline", baseline_results),
        ("Heuristic classifier", heuristic_results),
    ]:
        print(f"\n{name}:")
        print(f"  Correct: {result['correct']}")
        print(f"  Incorrect: {result['incorrect']}")
        print(f"  Accuracy: {result['accuracy']:.2f}%")

    print("\n========== PER-CASE RESULTS ==========\n")

    for baseline_result, heuristic_result in zip(
        baseline_results["results"],
        heuristic_results["results"],
    ):
        status = "PASS" if heuristic_result["correct"] else "FAIL"

        print(
            f"Case {heuristic_result['index']}: "
            f"Expected={heuristic_result['expected']}, "
            f"Baseline={baseline_result['predicted']}, "
            f"Heuristic={heuristic_result['predicted']} "
            f"[{status}]"
        )

    improvement = (
        heuristic_results["accuracy"]
        - baseline_results["accuracy"]
    )

    print(f"\nAccuracy improvement: {improvement:+.2f} percentage points")

    generate_report(
        baseline_results,
        heuristic_results,
        examples,
    )

    print(f"\nReport saved to: {REPORT_PATH}")

    if heuristic_results["accuracy"] <= baseline_results["accuracy"]:
        print("\nEvaluation failed: heuristic must beat the baseline.")
        sys.exit(1)

    print("\nEvaluation passed: heuristic beats the baseline.")


if __name__ == "__main__":
    main()
