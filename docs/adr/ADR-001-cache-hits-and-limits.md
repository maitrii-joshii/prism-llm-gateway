# ADR-001: Cache Hits and Rate Limits / Budgets

**Status:** Accepted  
**Date:** 2026-11-10

---

## Context

When a request is served from the semantic cache, it costs $0 and requires no provider call. Two questions arise:

1. **Rate limiting:** Should a cache hit count against the tenant's rate-limit quota (requests per minute)?
2. **Budget enforcement:** Should a cache hit be blocked if the tenant has exhausted their monthly budget?

These are distinct concerns. Getting the answer wrong in either direction causes real problems:
- If cache hits are free from rate limiting, a tenant could flood the gateway with requests that happen to hit the cache, still causing load on the gateway's cache-lookup and pipeline machinery.
- If cache hits are blocked by an empty budget, tenants lose the benefit of caching entirely — the cache stops working exactly when it's most valuable (when a team is trying to squeeze the last value out of a depleted budget).

---

## Decision

**Rate limiting:** Cache hits **do** consume rate-limit quota.  
**Budget enforcement:** Cache hits are **allowed even if the budget is exhausted**, because their cost is $0.

Concretely, in the pipeline order:

```
auth → validate → rate_limit → resolve → allowlist → budget → CACHE → provider_call → meter → log
```

- The rate limiter runs **before** the cache lookup — a cache hit still consumes a token from the bucket.
- The budget check runs **before** the cache lookup — but a cache hit records $0, so no budget is deducted. The check only blocks requests that would actually spend money.

---

## Consequences

**Positive:**
- Teams with an exhausted budget can still benefit from their cached answers — their users experience continuity rather than a hard wall.
- The rate limiter still protects the gateway from cache-flooding abuse.
- The pipeline order is consistent and easy to reason about: cheap/fast checks first, expensive checks before the expensive operation.

**Negative / Trade-offs:**
- A tenant with a $0 budget and 100 RPM limit could make 100 cache lookups per minute at zero cost indefinitely. This is intentional and acceptable — cache hits are cheap infrastructure-wise.
- If the cache lookup itself ever becomes a significant resource (e.g., with a large vector index), revisit whether cache hits should be rate-limited at a lower quota.

**Implementation note:** The budget stage checks `current_spend >= budget_usd`. Since `cost_usd` for a cache hit is `0.0`, the usage record update after a cache hit adds nothing to the spend total.

