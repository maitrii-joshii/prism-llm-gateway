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

    Designed to resist two classic routing traps:
    1. Long-but-trivial prompts (log excerpts with key=value pairs,
       on-call schedules, polite email rewrites, boilerplate summaries).
    2. Short-but-hard prompts (mathematical proofs, Fermi estimation,
       algorithmic complexity bounds, distributed consensus anomalies,
       and production root-cause debugging).
    """

    HARD_SIGNALS = [
        "prove",
        "disprove",
        "derive",
        "why",
        "explain the logic",
        "explain how",
        "show your reasoning",
        "reason through",
        "step by step",
        "step-by-step",
        "debug",
        "deadlock",
        "race condition",
        "split-brain",
        "most likely causes",
        "how you would confirm",
        "root cause",
        "plausible mechanisms",
        "analyze",
        "compare",
        "contrast",
        "compare and contrast",
        "design",
        "implement",
        "optimize",
        "evaluate",
        "justify",
        "with justification",
        "trade-offs",
        "tradeoffs",
        "calculate",
        "solve",
        "trace",
        "architecture",
        "consistency guarantees",
        "network partition",
        "quorum",
        "zero-downtime",
        "migration plan",
        "roll back",
        "rollback",
        "estimate how many",
        "time complexity",
        "space complexity",
        "recurrence relation",
        "master theorem",
        "dynamic programming",
    ]

    EASY_SIGNALS = [
        "list",
        "extract",
        "what is the name",
        "what is the capital",
        "what is the default",
        "what is the timestamp",
        "what does",
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
        "rewrite",
        "rephrase",
        "one-line",
        "fixing a typo",
    ]

    CODE_BLOCK_PATTERN = re.compile(
        r"```[\s\S]*?```|~~~[\s\S]*?~~~"
    )

    INLINE_CODE_PATTERN = re.compile(r"`[^`]+`")

    # Matches LaTeX commands, Big-O complexity, exponents (x^2), math symbols,
    # spaces around comparison/equality operators (x + 1 = 0), or single-letter
    # variable assignments (N=3, R=2), while ignoring multi-letter log/URL
    # key=value attributes (status=200, path=/health).
    MATH_PATTERN = re.compile(
        r"(\\frac|\\sqrt|\\sum|\\int|\\lim|"
        r"\\begin\{|\\end\{|"
        r"\\alpha|\\beta|"
        r"\\theta|\\pi|"
        r"\\[a-zA-Z]+|"
        r"\bO\([n1log\^2\s\*+]+\)|"
        r"[a-zA-Z0-9]\s*\^\s*[a-zA-Z0-9]|"
        r"[≤≥±∑∫√]|"
        r"\s[=<>]\s|"
        r"(?<![a-zA-Z_])[a-zA-Z]\s*=\s*\d+)"
    )

    MULTI_PART_PATTERN = re.compile(
        r"\bfirst\b[\s\S]*?\bthen\b[\s\S]*?\bfinally\b",
        re.IGNORECASE,
    )

    # Trivial phrase overrides where a polysemous word ("design of the flag")
    # appears in a simple factual lookup.
    TRIVIAL_DESIGN_PATTERN = re.compile(
        r"\bdesign\s+of\s+the\b",
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
            and not (
                signal == "design"
                and self.TRIVIAL_DESIGN_PATTERN.search(normalized_prompt)
            )
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
