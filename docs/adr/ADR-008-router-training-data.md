# ADR-008: Router Training Data & Multi-Set Trap Evaluation

**Status:** Accepted  
**Date:** 2026-11-12

---

## Context

The difficulty classifier (used by the `auto` alias) must be developed and evaluated rigorously without train/test leakage. Three datasets are maintained in `data/`:

1. **Training examples (`data/training_examples.jsonl` — 60 prompts):** Hand-authored labeled prompts (`30 fast`, `30 smart`) used to design and tune the classifier's linguistic and structural rules.
2. **Official evaluation set (`data/routing_eval.jsonl` — 20 prompts):** The unmodified held-out evaluation dataset from the Airtribe starter pack (`10 fast`, `10 smart`), including short-but-hard and long-but-trivial traps.
3. **Extended adversarial trap benchmark (`data/routing_eval_extended.jsonl` — 40 prompts):** An expanded test suite (`20 fast`, `20 smart`) containing log excerpts with `key=value` pairs, schedules, environment variable dumps, polysemous keywords (`"design of the national flag"`), Fermi estimates, distributed consensus scenarios, and adversarial semantic puzzles phrased without standard keywords.

Failure modes to avoid:

1. **Train/eval overlap** — reusing evaluation prompts in the training set inflates accuracy and invalidates generalization claims.
2. **Naive regex false positives on logs/configs** — treating every `=` character as mathematical notation misclassifies long server log excerpts (`status=200 path=/health`) as `smart`.
3. **Length bias** — routing based on character count fails on concise mathematical proofs (`< 80` chars) and verbose lookup tables (`> 250` chars).

---

## Decision

1. **Strict Dataset Isolation (`0` overlap):**
   - `data/training_examples.jsonl` (60 cases), `data/routing_eval.jsonl` (20 official cases), and `data/routing_eval_extended.jsonl` (40 extended trap cases) are strictly disjoint.
   - Disjointness is enforced automatically in `scripts/routing_eval.py` (`verify_dataset_isolation`) and in unit tests (`tests/unit/test_router.py`).

2. **Length-Only Baseline (`> 200` chars → `smart`, else `fast`):**
   - Used as the control benchmark. Because trap datasets contain short proofs and long lookups, the length-only baseline scores **35.00%** on both the official 20-case set and the extended 40-case trap benchmark.

3. **Refined Signal & Structural Classification (`HeuristicClassifier`):**
   - **Hard signals:** Proofs/derivations (`prove`, `disprove`, `derive`), causal & diagnostic analysis (`why`, `explain how`, `most likely causes`, `how you would confirm`, `plausible mechanisms`, `show your reasoning`, `estimate how many`), system architecture & trade-offs (`design` [excluding trivial `"design of the"`], `trade-offs`, `with justification`, `consistency guarantees`, `network partition`, `quorum`, `zero-downtime`, `migration plan`, `roll back`), and algorithmic complexity (`time complexity`, `recurrence relation`, `dynamic programming`).
   - **Structural patterns:** Fenced/inline code blocks, multi-part instructions (`first... then... finally`), and context-aware mathematical notation (LaTeX, Big-O complexity `O(n^2)`, exponents `x^2`, math operators with spaces `x + 1 = 0`, and single-letter variable equations `N=3`, while ignoring multi-letter log/config `key=value` pairs like `status=200`).
   - **Easy signals:** Factual lookups (`what is the capital`, `what is the default`, `what is the timestamp`, `what does`, `who is`, `when is`, `where is`), transformations (`convert`, `translate`, `format`, `rewrite`, `rephrase`, `summarize`), and simple extractions (`list`, `extract`, `define`, `identify`, `one-line`, `fixing a typo`).

---

## Consequences

**Positive:**
- **Verifiable train/test separation:** Automated tests guarantee zero prompt overlap across all 120 labeled prompts (60 train + 20 official eval + 40 extended eval).
- **Strong trap resistance:** Achieves **100.00% (20/20)** on the official starter eval set and **92.50% (37/40)** on the extended adversarial trap benchmark (**95.00% combined across all 60 eval cases**, beating the length-only baseline by **+60.00 percentage points**).
- **Honest failure mode documentation:** The 3 adversarial misses on the extended set (quoted book titles containing `'Why'` and narrative puzzles without technical keywords) are explicitly documented in `docs/routing_eval_results.md`.
