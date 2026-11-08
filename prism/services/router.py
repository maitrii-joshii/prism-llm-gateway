"""Difficulty classifiers for Prism model routing."""

import re
from abc import ABC, abstractmethod
from typing import TypedDict


class ClassificationResult(TypedDict):
    """Structured result returned by a difficulty classifier."""

    tier: str
    score: float
    reason: str


class DifficultyClassifier(ABC):
    """Strategy interface for classifying prompt difficulty."""

    @abstractmethod
    def classify(self, prompt: str) -> ClassificationResult:
        """Classify a prompt and return its routing decision."""
        raise NotImplementedError


class LengthOnlyClassifier(DifficultyClassifier):
    """Baseline classifier that uses only prompt length."""

    SMART_THRESHOLD = 200

    def classify(self, prompt: str) -> ClassificationResult:
        """Classify a prompt using its character count only."""

        if not isinstance(prompt, str):
            raise TypeError("Prompt must be a string.")

        prompt_length = len(prompt)

        if prompt_length > self.SMART_THRESHOLD:
            return {
                "tier": "smart",
                "score": 1.0,
                "reason": (
                    f"prompt length {prompt_length} exceeds "
                    f"{self.SMART_THRESHOLD} characters"
                ),
            }

        return {
            "tier": "fast",
            "score": 0.0,
            "reason": (
                f"prompt length {prompt_length} is within "
                f"{self.SMART_THRESHOLD} characters"
            ),
        }


class HeuristicClassifier(DifficultyClassifier):
    """
    Classify prompts using linguistic, code, math, and
    multi-part instruction signals.
    """

    HARD_SIGNALS = [
        "prove",
        "derive",
        "why",
        "explain the logic",
        "debug",
        "deadlock",
        "step by step",
        "step-by-step",
        "reason through",
        "analyze",
        "compare",
        "contrast",
        "compare and contrast",
        "design",
        "implement",
        "optimize",
        "evaluate",
        "justify",
        "calculate",
        "solve",
        "trace",
        "architecture",
    ]

    EASY_SIGNALS = [
        "list",
        "extract",
        "what is the name",
        "look up",
        "translate",
        "summarize",
        "define",
        "who is",
        "when is",
        "where is",
        "give the date",
        "convert",
        "format",
        "spell",
        "identify",
    ]

    CODE_BLOCK_PATTERN = re.compile(
        r"```[\s\S]*?```|~~~[\s\S]*?~~~"
    )

    INLINE_CODE_PATTERN = re.compile(r"`[^`]+`")

    MATH_PATTERN = re.compile(
        r"(\\frac|\\sqrt|\\sum|\\int|\\lim|"
        r"\\begin\{|\\end\{|"
        r"\\alpha|\\beta|"
        r"\\theta|\\pi|"
        r"\\[a-zA-Z]+|"
        r"[=<>≤≥±∑∫√]|"
        r"\d+\s*[\^*/]\s*\d+)"
    )

    MULTI_PART_PATTERN = re.compile(
        r"\bfirst\b[\s\S]*?\bthen\b[\s\S]*?\bfinally\b",
        re.IGNORECASE,
    )

    def classify(self, prompt: str) -> ClassificationResult:
        """Analyze prompt signals and choose fast or smart routing."""

        if not isinstance(prompt, str):
            raise TypeError("Prompt must be a string.")

        normalized_prompt = prompt.lower()

        hard_matches = [
            signal
            for signal in self.HARD_SIGNALS
            if self._contains_phrase(normalized_prompt, signal)
        ]

        easy_matches = [
            signal
            for signal in self.EASY_SIGNALS
            if self._contains_phrase(normalized_prompt, signal)
        ]

        reasons = list(hard_matches)

        # Code blocks and inline code indicate technical complexity.
        if self.CODE_BLOCK_PATTERN.search(prompt):
            hard_matches.append("code block")
            reasons.append("code block")

        elif self.INLINE_CODE_PATTERN.search(prompt):
            hard_matches.append("inline code")
            reasons.append("inline code")

        # Mathematical notation indicates possible complexity.
        if self.MATH_PATTERN.search(prompt):
            hard_matches.append("math notation")
            reasons.append("math notation")

        # Detect multi-part instructions as a combined signal.
        if self.MULTI_PART_PATTERN.search(prompt):
            hard_matches.append("multi-part instructions")
            reasons.append("multi-part instructions")

        hard_count = len(hard_matches)
        easy_count = len(easy_matches)
        total_signals = hard_count + easy_count

        if total_signals == 0:
            score = 0.0
        else:
            score = hard_count / total_signals

        score = round(score, 2)

        tier = (
            "smart"
            if score >= 0.5 and hard_count > 0
            else "fast"
        )

        if tier == "smart":
            reason = f"{'; '.join(reasons)}; judged complex"
        elif easy_matches:
            reason = f"{'; '.join(easy_matches)}; judged simple"
        else:
            reason = "no strong difficulty signals; defaulted to fast"

        return {
            "tier": tier,
            "score": score,
            "reason": reason,
        }

    @staticmethod
    def _contains_phrase(text: str, phrase: str) -> bool:
        """Match a phrase without matching it inside another word."""

        pattern = (
            r"(?<!\w)"
            + re.escape(phrase)
            + r"(?!\w)"
        )

        return re.search(pattern, text) is not None


__all__ = [
    "ClassificationResult",
    "DifficultyClassifier",
    "LengthOnlyClassifier",
    "HeuristicClassifier",
]
