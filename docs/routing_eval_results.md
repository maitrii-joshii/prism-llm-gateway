# Prism Routing Evaluation Results

## Dataset Isolation & Train/Test Boundary

- **Training Set (`data/training_examples.jsonl`):** 60 hand-authored labeled prompts (30 `fast`, 30 `smart`)
- **Official Eval Set (`data/routing_eval.jsonl`):** 20 held-out prompts from the Airtribe starter pack (10 `fast`, 10 `smart`)
- **Extended Adversarial Trap Set (`data/routing_eval_extended.jsonl`):** 40 additional trap prompts (20 `fast`, 20 `smart`)
- **Train/Eval Overlap Check:** `0` overlapping prompts across all three datasets (enforced via automated check)

---

## 1. Official Airtribe Eval Set (`data/routing_eval.jsonl` — 20 Cases)

| Metric | Length-Only Baseline (>200 chars) | Heuristic Classifier |
|---|---:|---:|
| Correct predictions | 7 / 20 | 20 / 20 |
| Incorrect predictions | 13 | 0 |
| Accuracy | **35.00%** | **100.00%** |
| Improvement over baseline | — | **+65.00 percentage points** |

### Official Per-Case Results

| ID | Note | Expected | Baseline | Baseline result | Heuristic | Heuristic result | Reason |
|---|---|---|---|---|---|---|---|
| `route_001` | short, easy fact | fast | fast | PASS | fast | PASS | what is the capital; judged simple |
| `route_002` | short, easy conversion | fast | fast | PASS | fast | PASS | convert; judged simple |
| `route_003` | short, easy writing | fast | fast | PASS | fast | PASS | one-line; fixing a typo; judged simple |
| `route_004` | short, easy definition | fast | fast | PASS | fast | PASS | what does; judged simple |
| `route_005` | short, easy translation | fast | fast | PASS | fast | PASS | translate; judged simple |
| `route_006` | trap: long input, trivial lookup task | fast | smart | FAIL | fast | PASS | who is; judged simple |
| `route_007` | trap: long input, trivial extraction task | fast | smart | FAIL | fast | PASS | what is the timestamp; judged simple |
| `route_008` | short, easy extraction | fast | fast | PASS | fast | PASS | extract; judged simple |
| `route_009` | short, easy arithmetic | fast | fast | PASS | fast | PASS | no strong difficulty signals; defaulted to fast |
| `route_010` | trap: longer input, trivial rewrite task | fast | smart | FAIL | fast | PASS | rewrite; judged simple |
| `route_011` | trap: short but hard proof | smart | fast | FAIL | smart | PASS | prove; judged complex |
| `route_012` | trap: short but multi-step estimation | smart | fast | FAIL | smart | PASS | show your reasoning; estimate how many; judged complex |
| `route_013` | trap: short but deep systems reasoning | smart | fast | FAIL | smart | PASS | why; plausible mechanisms; judged complex |
| `route_014` | complex design task | smart | fast | FAIL | smart | PASS | design; trade-offs; judged complex |
| `route_015` | complex comparison and recommendation | smart | fast | FAIL | smart | PASS | compare; with justification; judged complex |
| `route_016` | hard algorithm with explanation | smart | fast | FAIL | smart | PASS | explain how; math notation; judged complex |
| `route_017` | deep distributed-systems question | smart | fast | FAIL | smart | PASS | consistency guarantees; network partition; quorum; math notation; judged complex |
| `route_018` | complex planning task | smart | fast | FAIL | smart | PASS | zero-downtime; migration plan; roll back; judged complex |
| `route_019` | trap: shortish but expert debugging | smart | fast | FAIL | smart | PASS | most likely causes; how you would confirm; judged complex |
| `route_020` | trap: short but requires a proof | smart | fast | FAIL | smart | PASS | prove; disprove; judged complex |

---

## 2. Extended Adversarial Trap Benchmark (`data/routing_eval_extended.jsonl` — 40 Cases)

This larger benchmark tests 40 additional prompts including long-but-trivial log/schedule/env-var traps, polysemous keyword traps (`"design of the national flag"`), short-but-hard Fermi/proof/quorum traps, and adversarial semantic puzzles phrased without standard keywords.

| Metric | Length-Only Baseline (>200 chars) | Heuristic Classifier | Combined (60 Eval Cases) |
|---|---:|---:|---:|
| Correct predictions | 14 / 40 | 37 / 40 | 57 / 60 (vs 21 / 60 baseline) |
| Incorrect predictions | 26 | 3 | 3 |
| Accuracy | **35.00%** | **92.50%** | **95.00%** (vs **35.00%** baseline) |
| Improvement over baseline | — | **+57.50 pp** | **+60.00 pp** |

### Analysis of Classifier Misses on Adversarial Traps

- **`ext_020`** (*adversarial trap: quoted book title contains 'Why'*): Expected `fast`, predicted `smart` (`why; judged complex`).
  - *Prompt:* "Who is the author of the book 'Why Nations Fail' and in what year was it published?"
- **`ext_039`** (*adversarial trap: Two Generals impossibility theorem without keywords*): Expected `smart`, predicted `fast` (`no strong difficulty signals; defaulted to fast`).
  - *Prompt:* "Two generals must attack at dawn over an unreliable messenger channel. Can they ever reach certainty?"
- **`ext_040`** (*adversarial trap: non-atomic thread interleaving puzzle without keywords*): Expected `smart`, predicted `fast` (`no strong difficulty signals; defaulted to fast`).
  - *Prompt:* "Two threads increment a shared counter 1000 times each without locks. What is the minimum possible final value?"

**Why these misses occur:** Rule-based and structural heuristics excel when prompts contain explicit task verbs (`prove`, `derive`, `analyze`, `extract`, `rewrite`), structural markers (code blocks, Big-O notation, single-letter variable equations), or diagnostic phrases (`most likely causes`). They fail in two specific regimes:
1. **Quoted entity false positives (`ext_020`):** A factual lookup about a work whose title contains a reasoning keyword (`'Why Nations Fail'`) triggers the `why` signal despite being a simple bibliographic question (`1 hard / 2 total = 0.50 >= 0.5`).
2. **Implicit semantic puzzles (`ext_039`, `ext_040`):** When a deep distributed-consensus theorem (Two Generals' Problem) or thread-interleaving race condition is stated purely as a narrative story without technical keywords, the zero-signal default routes it to `fast`.

### Extended Per-Case Results

| ID | Note | Expected | Baseline | Baseline result | Heuristic | Heuristic result | Reason |
|---|---|---|---|---|---|---|---|
| `ext_001` | short, easy fact | fast | fast | PASS | fast | PASS | what is the capital; judged simple |
| `ext_002` | short, easy unit conversion | fast | fast | PASS | fast | PASS | convert; judged simple |
| `ext_003` | short, one-line commit message | fast | fast | PASS | fast | PASS | one-line; fixing a typo; judged simple |
| `ext_004` | short, status code lookup | fast | fast | PASS | fast | PASS | what does; judged simple |
| `ext_005` | short, phrase translation | fast | fast | PASS | fast | PASS | translate; judged simple |
| `ext_006` | trap: long schedule input, trivial owner lookup | fast | smart | FAIL | fast | PASS | who is; judged simple |
| `ext_007` | trap: long log with key=value pairs, trivial timestamp extraction | fast | smart | FAIL | fast | PASS | what is the timestamp; judged simple |
| `ext_008` | short, regex-like extraction | fast | fast | PASS | fast | PASS | extract; judged simple |
| `ext_009` | short, simple arithmetic | fast | fast | PASS | fast | PASS | no strong difficulty signals; defaulted to fast |
| `ext_010` | trap: long incident text, simple tone rewrite | fast | smart | FAIL | fast | PASS | rewrite; judged simple |
| `ext_011` | trap: long release note, one-sentence summary | fast | smart | FAIL | fast | PASS | summarize; judged simple |
| `ext_012` | trap: polysemous keyword 'design' in factual question | fast | fast | PASS | fast | PASS | no strong difficulty signals; defaulted to fast |
| `ext_013` | trap: long env var list with '=' signs, trivial lookup | fast | smart | FAIL | fast | PASS | what is the name; judged simple |
| `ext_014` | short, single-sentence definition | fast | fast | PASS | fast | PASS | define; judged simple |
| `ext_015` | short, acronym enumeration | fast | fast | PASS | fast | PASS | list; judged simple |
| `ext_016` | short, default port lookup | fast | fast | PASS | fast | PASS | what is the default; judged simple |
| `ext_017` | short, alphabetical formatting | fast | fast | PASS | fast | PASS | format; judged simple |
| `ext_018` | trap: long timeline, simple date lookup | fast | smart | FAIL | fast | PASS | when is; judged simple |
| `ext_019` | short, HTTP method identification | fast | fast | PASS | fast | PASS | identify; judged simple |
| `ext_020` | adversarial trap: quoted book title contains 'Why' | fast | fast | PASS | smart | FAIL | why; judged complex |
| `ext_021` | trap: short mathematical proof | smart | fast | FAIL | smart | PASS | prove; judged complex |
| `ext_022` | trap: short Fermi estimation | smart | fast | FAIL | smart | PASS | show your reasoning; estimate how many; judged complex |
| `ext_023` | trap: short systems causal reasoning | smart | fast | FAIL | smart | PASS | why; plausible mechanisms; judged complex |
| `ext_024` | distributed system design with trade-offs | smart | fast | FAIL | smart | PASS | design; trade-offs; judged complex |
| `ext_025` | consensus comparison and justification | smart | fast | FAIL | smart | PASS | compare; with justification; judged complex |
| `ext_026` | graph algorithm with complexity bound | smart | fast | FAIL | smart | PASS | explain how; math notation; judged complex |
| `ext_027` | quorum consistency during partition | smart | fast | FAIL | smart | PASS | consistency guarantees; network partition; math notation; judged complex |
| `ext_028` | zero-downtime schema migration and rollback | smart | fast | FAIL | smart | PASS | zero-downtime; migration plan; roll back; judged complex |
| `ext_029` | trap: starts with 'List' but requires production root-cause debugging | smart | fast | FAIL | smart | PASS | most likely causes; how you would confirm; judged complex |
| `ext_030` | trap: short number-theory proof | smart | fast | FAIL | smart | PASS | prove; disprove; math notation; judged complex |
| `ext_031` | trap: short SQL code block bug | smart | fast | FAIL | smart | PASS | debug; code block; judged complex |
| `ext_032` | trap: short recurrence derivation | smart | fast | FAIL | smart | PASS | derive; solve; time complexity; recurrence relation; judged complex |
| `ext_033` | multi-part database internals comparison | smart | fast | FAIL | smart | PASS | analyze; compare; multi-part instructions; judged complex |
| `ext_034` | trap: short distributed quorum failure | smart | fast | FAIL | smart | PASS | step by step; split-brain; quorum; judged complex |
| `ext_035` | trap: short memory model concurrency analysis | smart | fast | FAIL | smart | PASS | race condition; analyze; judged complex |
| `ext_036` | trap: short DP space optimization | smart | fast | FAIL | smart | PASS | optimize; dynamic programming; math notation; judged complex |
| `ext_037` | trap: short security trade-off evaluation | smart | fast | FAIL | smart | PASS | evaluate; trade-offs; judged complex |
| `ext_038` | trap: short lock-free data structure implementation | smart | fast | FAIL | smart | PASS | implement; trace; judged complex |
| `ext_039` | adversarial trap: Two Generals impossibility theorem without keywords | smart | fast | FAIL | fast | FAIL | no strong difficulty signals; defaulted to fast |
| `ext_040` | adversarial trap: non-atomic thread interleaving puzzle without keywords | smart | fast | FAIL | fast | FAIL | no strong difficulty signals; defaulted to fast |

---

## Conclusion

- Official 20-case eval accuracy: **100.00%** vs **35.00%** length-only baseline (**+65.00 pp**)
- Extended 40-case trap accuracy: **92.50%** vs **35.00%** length-only baseline (**+57.50 pp**)

**Result: PASS — Heuristic classifier significantly beats the length-only baseline across both official and extended trap evaluations.**
