# ADR-004: Cache Scope and Multi-Turn Keying

**Status:** Accepted  
**Date:** 2026-11-10

---

## Context

The semantic cache must answer two questions:

1. **Scope:** Which requests can a cache entry be matched against? Should Team A's cached answers be visible to Team B?
2. **Cache key composition:** For multi-turn conversations with multiple messages, what text do we embed and compare to find a match?

**On scope:** The fundamental requirement is that tenants must be fully isolated. A cache hit for Team A must never serve Team B's request, even if the prompts are identical. This is both a correctness requirement (different teams may have different system prompts, contexts, or model aliases) and a security requirement (confidential answers must not leak).

**On cache key composition:** A conversation can contain many messages — a system prompt, several user/assistant exchanges, and a final user message. Options include:
- Embed the entire conversation history
- Embed only the last user message
- Embed the system prompt + last user message

---

## Decision

**Scope:** Cache entries are scoped by `key_hash + alias`. The SQL query that searches for matches always includes `WHERE key_hash = ? AND alias = ?`. Cross-tenant leakage is **impossible by construction** — the scope is part of the query predicate, not a post-filter.

```sql
SELECT * FROM cache_entries
WHERE key_hash = :key_hash
  AND alias    = :alias
ORDER BY hit_count DESC
```

**Cache key composition:** Embed the concatenation of `system_prompt + last_user_message`.

```python
def build_cache_text(messages: list[dict]) -> str:
    system = next(
        (m["content"] for m in messages if m["role"] == "system"), ""
    )
    last_user = next(
        (m["content"] for m in reversed(messages) if m["role"] == "user"), ""
    )
    return f"{system} {last_user}".strip()
```

Embedding the full history was rejected because: (a) very long histories produce noisy embeddings that hurt similarity accuracy; (b) the final user message is what changes between turns and what determines the response — history context is captured by the system prompt.

Embedding only the last user message was rejected because: two tenants with the same final question but different system prompts (e.g., different persona instructions) would incorrectly match each other's cache entries.

---

## Consequences

**Positive:**
- **Zero cross-tenant leakage** — structurally guaranteed at the query level, not by application logic.
- The `alias` dimension adds another layer of isolation: even within the same tenant, `fast` and `smart` responses are stored and matched separately.
- Paraphrased final questions match correctly even across different conversation lengths.

**Negative / Trade-offs:**
- Two conversations with different early turns but the same system prompt and final question will match — the cache does not distinguish mid-conversation context. This is an acceptable approximation for a semantic cache.
- Changing the system prompt invalidates all existing cache entries for that tenant (new embedding, new entry). This is correct behavior but may surprise operators who rotate system prompts.

**Future consideration:** If mid-conversation context becomes important, the cache key could include a hash of the last N message pairs. Not implemented in the current scope.

