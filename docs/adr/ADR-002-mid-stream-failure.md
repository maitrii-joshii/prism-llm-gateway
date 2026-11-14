# ADR-002: Mid-Stream Provider Failure

**Status:** Accepted  
**Date:** 2026-11-10

---

## Context

Prism supports streaming responses via Server-Sent Events (SSE). The gateway uses a "tee" pattern: it reads chunks from the upstream provider and immediately forwards each chunk to the client.

A question arises: **what happens if the upstream provider dies or disconnects mid-stream — after the first chunk has already been sent to the client?**

Options considered:

1. **Switch providers mid-stream** — detect the failure, connect to the fallback provider, and continue streaming from wherever the first provider left off.
2. **Send an SSE error event and close the stream** — notify the client that the stream ended abnormally, then terminate the connection.
3. **Buffer the entire response** — only forward to the client once the full response is received, so failover is transparent.

---

## Decision

**Send an SSE error event and close the stream. No mid-stream provider switching.**

```
# When the provider dies mid-stream:
data: {"error": {"message": "Stream interrupted by upstream provider", "type": "upstream_error"}}

data: [DONE]
```

Option 1 (mid-stream switch) is rejected because:
- Tokens produced by two different models cannot be coherently spliced. The second model has no context of what the first already produced, so the continuation would be semantically incoherent ("franken-answers").
- The client's context window would contain partial output from one model and partial from another, making debugging and reproducibility impossible.

Option 3 (full buffering) is rejected because:
- It eliminates the latency benefit of streaming. Users wait for the entire response before seeing anything.
- It increases memory pressure on the gateway (must hold the full response in memory).

**Failover is still applied — but only before the first byte is sent.** If a provider fails at the connection stage or during header negotiation, Prism can transparently retry or failover to the next provider in the chain.

---

## Consequences

**Positive:**
- Response coherence is guaranteed — clients never receive a semantically broken spliced answer.
- The implementation is simpler: the streaming path has a single try/finally block; no mid-stream retry state machine is needed.
- The behavior is clearly documented and clients can implement their own retry logic (re-send the full request).

**Negative / Trade-offs:**
- Some streams will end with an error event rather than a complete answer. The client must handle this.
- The user experience may be jarring — they see partial text, then an error.
- The gateway cannot hide the provider failure from the end user in the streaming case (unlike non-streaming, where failover is completely transparent).

**Implementation note:** The stream handler wraps provider iteration in `try/except`. On any `UpstreamError` or connection exception during streaming, it yields one final SSE error chunk and then returns. The `finally` block always records whatever tokens were consumed before the failure.

**Documentation requirement:** The API contract must clearly state that streaming responses can terminate with an error event, and clients should handle `data: {"error": ...}` chunks.

