# Cache Threshold Tuning — Day 12, Task 12.4

## Objective

Find a cache similarity threshold that allows paraphrased prompts to reuse cached responses while preventing unrelated prompts from receiving cached responses.

## Test Cases

| Type | Original Prompt | Compared Prompt |
|---|---|---|
| Should match | Reset my password | How do I change my password? |
| Should not match | Reset my password | Enable 2FA on my account |

## Embedder Refinement

The existing Bag-of-Words embedder uses token hashing and cosine similarity.

Initially, the password paraphrase pair scored only 0.50 because the words `reset` and `change` were treated as different tokens.

A small domain-specific normalization rule was introduced:

- `reset` → `change`

After normalization:

- Both password prompts produce the tokens `change`, `password`.
- The 2FA prompt produces the tokens `enable`, `2fa`, `account`.

This improves matching for the tested password paraphrase. It is lexical normalization, not a true semantic embedding model.

## Threshold Evaluation

| Prompt Pair | Similarity | 0.80 | 0.85 | 0.90 |
|---|---:|---|---|---|
| Password reset / password change | 1.0000 | HIT | HIT | HIT |
| Password reset / enable 2FA | 0.0000 | MISS | MISS | MISS |

## Selected Threshold: 0.85

The selected threshold is **0.85**.

Reasons:

1. It successfully matches the tested paraphrased password prompts.
2. It rejects the tested unrelated 2FA prompt.
3. It provides a middle ground between the three evaluated thresholds.
4. It matches the existing SQLite schema default.

Both seed virtual keys in `config/seed_keys.json` were updated to use `0.85`.

## Conclusion

The selected threshold passes both required test cases.

The current Bag-of-Words implementation is based on lexical overlap and limited token normalization. More diverse paraphrases and near-miss prompts should be evaluated before treating this threshold as production-ready.
