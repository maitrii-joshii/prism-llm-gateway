# Prism Routing Evaluation Results

## Evaluation Summary

- Total evaluation examples: **20**
- Fast examples: **9**
- Smart examples: **11**

## Classifier Accuracy

| Metric | Length-Only Baseline | Heuristic Classifier |
|---|---:|---:|
| Correct predictions | 8 | 20 |
| Incorrect predictions | 12 | 0 |
| Total examples | 20 | 20 |
| Accuracy | **40.00%** | **100.00%** |

## Evaluation Per Case

| # | Expected | Baseline | Baseline result | Heuristic | Heuristic result |
|---:|---|---|---|---|---|
| 1 | fast | fast | PASS | fast | PASS |
| 2 | fast | fast | PASS | fast | PASS |
| 3 | fast | fast | PASS | fast | PASS |
| 4 | fast | fast | PASS | fast | PASS |
| 5 | fast | fast | PASS | fast | PASS |
| 6 | smart | fast | FAIL | smart | PASS |
| 7 | smart | fast | FAIL | smart | PASS |
| 8 | smart | fast | FAIL | smart | PASS |
| 9 | smart | fast | FAIL | smart | PASS |
| 10 | smart | fast | FAIL | smart | PASS |
| 11 | smart | fast | FAIL | smart | PASS |
| 12 | smart | fast | FAIL | smart | PASS |
| 13 | fast | fast | PASS | fast | PASS |
| 14 | fast | smart | FAIL | fast | PASS |
| 15 | smart | fast | FAIL | smart | PASS |
| 16 | smart | fast | FAIL | smart | PASS |
| 17 | fast | fast | PASS | fast | PASS |
| 18 | fast | fast | PASS | fast | PASS |
| 19 | smart | fast | FAIL | smart | PASS |
| 20 | smart | fast | FAIL | smart | PASS |

## Heuristic Prediction Details

### Case 1 — PASS

- **Prompt:** What does HTTP stand for?
- **Expected:** fast
- **Predicted:** fast
- **Score:** 0.0
- **Reason:** no strong difficulty signals; defaulted to fast

### Case 2 — PASS

- **Prompt:** List three advantages of PostgreSQL.
- **Expected:** fast
- **Predicted:** fast
- **Score:** 0.0
- **Reason:** list; judged simple

### Case 3 — PASS

- **Prompt:** Translate good morning into German.
- **Expected:** fast
- **Predicted:** fast
- **Score:** 0.0
- **Reason:** translate; judged simple

### Case 4 — PASS

- **Prompt:** Define the term load balancing.
- **Expected:** fast
- **Predicted:** fast
- **Score:** 0.0
- **Reason:** define; judged simple

### Case 5 — PASS

- **Prompt:** What is the default port for PostgreSQL?
- **Expected:** fast
- **Predicted:** fast
- **Score:** 0.0
- **Reason:** no strong difficulty signals; defaulted to fast

### Case 6 — PASS

- **Prompt:** Prove that there are infinitely many prime numbers.
- **Expected:** smart
- **Predicted:** smart
- **Score:** 1.0
- **Reason:** prove; judged complex

### Case 7 — PASS

- **Prompt:** Why can a distributed transaction fail?
- **Expected:** smart
- **Predicted:** smart
- **Score:** 1.0
- **Reason:** why; judged complex

### Case 8 — PASS

- **Prompt:** Compare optimistic and pessimistic concurrency control.
- **Expected:** smart
- **Predicted:** smart
- **Score:** 1.0
- **Reason:** compare; judged complex

### Case 9 — PASS

- **Prompt:** Analyze the race condition in this code.
- **Expected:** smart
- **Predicted:** smart
- **Score:** 1.0
- **Reason:** analyze; judged complex

### Case 10 — PASS

- **Prompt:** Design a fault-tolerant payment processing system.
- **Expected:** smart
- **Predicted:** smart
- **Score:** 1.0
- **Reason:** design; judged complex

### Case 11 — PASS

- **Prompt:** Calculate the time complexity of merge sort.
- **Expected:** smart
- **Predicted:** smart
- **Score:** 1.0
- **Reason:** calculate; judged complex

### Case 12 — PASS

- **Prompt:** Explain step by step how a database deadlock can occur.
- **Expected:** smart
- **Predicted:** smart
- **Score:** 1.0
- **Reason:** deadlock; step by step; judged complex

### Case 13 — PASS

- **Prompt:** What is the capital of Japan? Please provide a short factual answer. I only need the city name and nothing else.
- **Expected:** fast
- **Predicted:** fast
- **Score:** 0.0
- **Reason:** no strong difficulty signals; defaulted to fast

### Case 14 — PASS

- **Prompt:** Summarize the following information about web development: HTML structures pages, CSS controls presentation, JavaScript adds interactivity, and browsers execute these technologies to display websites. Keep the summary concise and do not provide technical analysis or additional examples.
- **Expected:** fast
- **Predicted:** fast
- **Score:** 0.0
- **Reason:** summarize; judged simple

### Case 15 — PASS

- **Prompt:** Explain why a distributed system can experience a split-brain condition and analyze how quorum-based consensus helps prevent inconsistent writes.
- **Expected:** smart
- **Predicted:** smart
- **Score:** 1.0
- **Reason:** why; analyze; judged complex

### Case 16 — PASS

- **Prompt:** Debug this code and explain why it produces an incorrect result: ```python def average(values):     return sum(values) / len(values) ```
- **Expected:** smart
- **Predicted:** smart
- **Score:** 1.0
- **Reason:** why; debug; code block; judged complex

### Case 17 — PASS

- **Prompt:** Identify the programming language used in this statement: print('Hello World')
- **Expected:** fast
- **Predicted:** fast
- **Score:** 0.0
- **Reason:** identify; judged simple

### Case 18 — PASS

- **Prompt:** Convert 25 Celsius into Fahrenheit.
- **Expected:** fast
- **Predicted:** fast
- **Score:** 0.0
- **Reason:** convert; judged simple

### Case 19 — PASS

- **Prompt:** Derive the recurrence relation for merge sort and solve it using the Master Theorem.
- **Expected:** smart
- **Predicted:** smart
- **Score:** 1.0
- **Reason:** derive; solve; judged complex

### Case 20 — PASS

- **Prompt:** First explain database indexing, then compare B-tree and hash indexes, and finally analyze their performance trade-offs.
- **Expected:** smart
- **Predicted:** smart
- **Score:** 1.0
- **Reason:** analyze; compare; multi-part instructions; judged complex

## Conclusion

- Length-only baseline accuracy: **40.00%**
- Heuristic classifier accuracy: **100.00%**
- Accuracy improvement: **+60.00 percentage points**

**Result: PASS — Heuristic classifier beats the length-only baseline.**
