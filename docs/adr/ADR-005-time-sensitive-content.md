# ADR-005: Time-Sensitive Content (Never Cached)

**Status:** Accepted  
**Date:** 2026-11-10

---

## Context

The semantic cache serves cached responses to semantically similar prompts. This is correct for stable-answer questions like *"What is the capital of France?"* — the answer is the same today as it was last week.

However, some prompts ask about the **current state of the world**:

- *"What's the weather right now?"*
- *"What's the latest news today?"*
- *"What is the current price of Bitcoin?"*
- *"What time is it now?"*

Serving a cached answer to these questions would be actively harmful — a user asking for the current weather in November should not receive an answer cached from July.

The challenge is detecting these time-sensitive prompts reliably without an expensive model call.

Options considered:

1. **Keyword blocklist** — if the prompt contains certain words/phrases, skip the cache.
2. **Model-based classification** — use an LLM to determine if the question is time-sensitive.
3. **Opt-in caching** — do not cache by default; require explicit opt-in.
4. **Short TTL** — cache all responses but expire them after a short duration (e.g., 5 minutes).

---

## Decision

**Use a keyword blocklist (option 1).** If the prompt text contains any of the following tokens, skip the cache lookup and storage entirely:

```python
TIME_SENSITIVE_KEYWORDS = {
    "now", "today", "latest", "current", "right now",
    "this moment", "currently", "at this time", "as of today",
    "real-time", "live", "breaking",
}
```

The check is case-insensitive and applied to the full prompt text before the cache lookup stage. If matched, `cache_status` is set to `"skip"` and the `x-prism-cache: skip` header is returned.

Option 2 (model-based) is rejected because it would require a provider call before the cache lookup — defeating the purpose and adding latency to every request.

Option 3 (opt-in) is rejected because it would make the cache useless by default.

Option 4 (TTL) is rejected because the bag-of-words embedder used in the current implementation does not support TTL-based eviction without additional schema changes, and even a 5-minute-old weather answer is wrong.

---

## Consequences

**Positive:**
- Simple to implement, understand, and audit — the blocklist is a plain Python set.
- Zero false negatives for the common time-sensitive patterns.
- The keyword list is extensible — add entries without changing architecture.

**Negative / Trade-offs:**
- **False positives are possible.** A prompt like *"What is the current best practice for password hashing?"* contains "current" but its answer is stable. This request will unnecessarily skip the cache.
- The keyword list is English-only. Multilingual prompts may not be detected.
- The list requires manual maintenance as language patterns evolve.

**Configuration:** The keyword set should be configurable via a config file or environment variable in a future iteration, allowing operators to tune for their tenant population's language patterns.

**Implementation note:** The check is applied in `prism/services/cache.py` in the `is_cacheable()` method, which also checks `cache_enabled` on the key config. Both must be true for a cache lookup to proceed.

