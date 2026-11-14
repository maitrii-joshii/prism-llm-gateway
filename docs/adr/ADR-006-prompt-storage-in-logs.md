# ADR-006: Prompt Storage in Request Logs

**Status:** Accepted  
**Date:** 2026-11-10

---

## Context

The `request_logs` table records metadata about every request that passes through Prism. This data is used for the ops console, debugging, cost auditing, and routing analysis.

A natural question arises: **Should the full prompt text be stored in the request log?**

Arguments for storing the full prompt:
- Makes debugging much easier — when investigating a wrong or unexpected answer, the operator can see exactly what was sent.
- Useful for classifier improvement — logged prompts are real-world training data for the routing classifier.
- Consistent with how most LLM API providers log requests (with opt-out).

Arguments against storing the full prompt:
- **Privacy risk** — prompts may contain PII (names, emails, internal business information, medical data).
- **Storage cost** — prompts can be large (thousands of tokens). Storing every prompt multiplies database size significantly.
- **Compliance risk** — depending on the industry and jurisdiction, storing user-generated text requires explicit consent and data retention policies.
- **Secret leakage** — users sometimes accidentally include API keys, passwords, or other secrets in prompts.

---

## Decision

**Do not store prompt text in request logs by default.**

The `request_logs` schema stores only metadata:

| Column | Stored |
|--------|--------|
| `request_id` | ✅ |
| `key_hash` | ✅ (hash only, not the raw key) |
| `model_requested` | ✅ |
| `model_resolved` | ✅ |
| `provider` | ✅ |
| `status_code` | ✅ |
| `prompt_tokens` | ✅ |
| `completion_tokens` | ✅ |
| `cost_usd` | ✅ |
| `cache_result` | ✅ |
| `fallback_used` | ✅ |
| `retries` | ✅ |
| `latency_ms` | ✅ |
| `decision_trace` | ✅ |
| `prompt_text` | ❌ Not stored by default |
| `response_text` | ❌ Not stored by default |

If needed for debugging, prompt logging can be enabled via the `PRISM_LOG_PROMPTS=true` environment variable (not implemented in the current scope — documented as future work).

---

## Consequences

**Positive:**
- **Privacy-safe by default** — operators do not need to configure anything to avoid logging PII.
- Smaller database — metadata rows are small and predictable in size.
- No secrets can appear in the database from prompt text.
- Compliance posture is simpler — the system can truthfully state "we do not store prompt content."

**Negative / Trade-offs:**
- Debugging is harder without prompt text. Operators must reproduce issues by re-sending the same request.
- The routing classifier cannot be improved from production logs without enabling prompt logging.
- The decision trace (which is stored) partially compensates — it records *why* each pipeline decision was made, even without the prompt text.

**Security note:** The `key_hash` stored in logs is the SHA-256 hash of the virtual key. The raw key is never stored anywhere in the database. Even full access to `prism.db` does not reveal any tenant's key.

