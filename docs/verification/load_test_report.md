# Prism Load Test Report

> **Run date:** 2026-11-10 17:15 UTC  
> **Python test client** (in-process, no live server required)  
> **Provider:** FakeAdapter (deterministic, no network calls)

---

## Summary

| Test | Result |
|---|---|
| Over-admission | ✅ PASS — 0 over-admitted out of 40 concurrent requests |
| Usage accounting | ✅ PASS — 0 token discrepancy across 50 requests |
| Latency | ℹ️ INFO — p50=50.45 ms, p95=56.95 ms, p99=62.43 ms |

---

## 1. Over-Admission Test

Fired **40 concurrent requests** against a key with **RPM cap = 20**.
Exactly the cap number should be admitted; the rest must receive HTTP 429.

| Metric | Value |
|---|---|
| Total concurrent requests | 40 |
| RPM cap | 20 |
| Admitted (HTTP 200) | 20 |
| Rejected (HTTP 429) | 20 |
| Other status codes | 0 |
| **Over-admission count** | **0** |
| **Result** | **✅ PASS** |

> [!NOTE]
> The token-bucket rate limiter uses a threading lock to make the
> check-and-decrement operation atomic. This prevents race conditions
> where two concurrent threads both see `tokens > 0` and both decrement.

---

## 2. Usage Accounting Accuracy

Sent **50 sequential requests** with a fake provider returning exactly **15 tokens each**.
Verified that the usage table records the exact expected totals.

| Metric | Expected | Actual |
|---|---:|---:|
| Total tokens | 750 | 750 |
| Total requests | 50 | 50 |
| Token discrepancy | 0 | 0 |
| **Result** | | **✅ PASS** |

> [!NOTE]
> Usage is recorded via atomic SQL `UPDATE ... SET tokens = tokens + ?`.
> There is no read-modify-write cycle, so concurrent updates cannot
> produce lost updates or double-counting.

---

## 3. Latency Statistics

Sent **100 sequential requests** through the full pipeline
(auth → rate limit → resolve → allowlist → budget → cache → provider → meter → log).

| Percentile | Latency |
|---|---:|
| Min | 39.87 ms |
| p50 (median) | 50.45 ms |
| p95 | 56.95 ms |
| p99 | 62.43 ms |
| Max | 62.43 ms |
| Mean | 50.19 ms |

> [!IMPORTANT]
> Latency is measured **in-process** using FastAPI's `TestClient`.
> This excludes real network I/O (TCP round-trip ~1–5 ms) and OS
> scheduling overhead. With a live HTTP server, expect p50 to be
> approximately the in-process p50 + network latency.

---

## Notes

- All tests use `FakeProviderAdapter` — provider latency is 0 ms by design.
  Real provider calls add 100–3000 ms depending on model and load.
- The rate limiter is in-memory. In a multi-instance deployment,
  each instance would have its own bucket, potentially multiplying the
  effective RPM limit by the number of instances.
- Cache is disabled for load tests to ensure every request goes through
  the full pipeline and is accounted for.
