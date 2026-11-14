# ADR-003: Budget Overshoot During Streaming

**Status:** Accepted  
**Date:** 2026-11-10

---

## Context

Prism enforces per-tenant monthly spending budgets. For non-streaming requests, the cost is known precisely before the response is returned — the usage object in the provider's response contains exact token counts, and cost is calculated and recorded atomically.

For **streaming requests**, the final cost is unknown when the request starts. The provider sends token counts only in the final SSE chunk (the usage chunk), which arrives after all content chunks. This creates a timing problem:

**How do we enforce a budget when we don't know the cost until after we've already started serving the response?**

Options considered:

1. **Pre-flight cost estimation** — estimate the cost based on input tokens before streaming, reserve that amount, and then reconcile at the end.
2. **Admit-then-record** — allow the request if the budget has not yet been exhausted at the start. Record the true cost at the end. Accept that concurrent in-flight requests may cause a small overshoot.
3. **Buffer the full response** — wait for the usage chunk, calculate cost, then stream only if within budget (effectively converting streaming to non-streaming for budget purposes).

---

## Decision

**Use admit-then-record (option 2). Accept a bounded, documented budget overshoot.**

The budget check at the pipeline stage asks: "Is the current spend below the budget limit?" If yes, the request proceeds. The true cost is recorded after the stream completes (in the `finally` block of the streaming handler). No pre-reservation or estimation is performed.

**The overshoot bound:** With `MAX_RETRIES` retries and a maximum request size of `PRISM_MAX_TOKENS_CAP` tokens, the worst-case overshoot is bounded by:

```
max_overshoot ≈ concurrent_requests × max_tokens_cap × max_output_price_per_token
```

For typical configurations (e.g., 4096 token cap, $15/million output tokens), the overshoot per concurrent request is at most ~$0.06. With reasonable concurrency, this is an acceptable margin for a development/demo system.

Option 1 is rejected because input token estimation is unreliable (tokenization varies by model) and would require model-specific tokenizer libraries.

Option 3 is rejected because it eliminates the entire benefit of streaming for the client.

---

## Consequences

**Positive:**
- Streaming works as intended — clients receive tokens incrementally without buffering.
- The implementation is straightforward: the budget check is a simple read-and-compare; the cost record is a simple atomic SQL update after streaming.
- No external tokenizer dependency required.

**Negative / Trade-offs:**
- Tenants can slightly exceed their budget during concurrent streaming requests. The overshoot is bounded but non-zero.
- The overshoot cannot be avoided without fundamentally changing the streaming model.

**Mitigation strategies (not implemented, documented as future work):**
- Pre-reserve an estimated cost based on `max_tokens` parameter if provided.
- Track in-flight estimated cost in a shared counter and include it in the budget check.

**Documentation requirement:** The README and API contract must state: *"Budget enforcement for streaming requests is best-effort. Concurrent in-flight requests may cause spend to slightly exceed the configured limit. The overshoot is bounded by the product of concurrent requests and maximum response cost."*

