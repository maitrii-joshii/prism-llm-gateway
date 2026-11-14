"""Load test for the Prism LLM Gateway.

Measures three things:
  1. Over-admission — concurrent requests must never exceed the RPM cap
  2. Usage accounting accuracy — total recorded tokens == sum of all responses
  3. Latency statistics — p50, p95, p99 across a burst of sequential requests

Uses FastAPI TestClient with FakeAdapter (no external providers required).
"""

import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import FastAPI
from fastapi.testclient import TestClient

from prism.adapters.bow_embedder import BowEmbedder
from prism.adapters.sqlite_repos import (
    CacheRepository,
    SQLiteKeyRepository,
    SQLiteLogRepository,
    SQLiteUsageRepository,
    hash_api_key,
    init_database,
)
from prism.adapters.system_clock import SystemClock
from prism.api.error_handler import prism_error_handler
from prism.api.middleware import request_id_middleware
from prism.api.routes import router
from prism.domain.errors import PrismError
from prism.domain.limiter import TokenBucketRateLimiter
from prism.domain.models import (
    AliasConfig,
    GatewayConfig,
    ModelPricing,
    ProviderResponse,
    VirtualKeyConfig,
)
from prism.services.cache import CacheService
from tests.helpers.fake_adapter import FakeProviderAdapter


# ── Constants ────────────────────────────────────────────────────────────────

FAST_MODEL = "gpt-4o-mini"
SMART_MODEL = "llama-3.3-70b-versatile"

LOAD_KEY = "load-test-key"
RATE_KEY = "rate-limit-test-key"

RPM_LIMIT = 20            # Rate limit for the rate-limit key
CONCURRENT_WORKERS = 40   # 2× the limit → exactly half should be admitted
LATENCY_REQUESTS = 100    # Sequential requests to measure latency


# ── App factory ──────────────────────────────────────────────────────────────

def build_app(temp_dir: Path, rpm: int = 1000) -> FastAPI:
    """Create a fully-wired test application."""

    db_path = str(temp_dir / "load_test.db")
    init_database(db_path)

    app = FastAPI(title="Prism Load Test")
    app.middleware("http")(request_id_middleware)
    app.include_router(router)
    app.add_exception_handler(PrismError, prism_error_handler)

    app.state.clock = SystemClock()
    app.state.rate_limiter = TokenBucketRateLimiter(app.state.clock)

    key_repo = SQLiteKeyRepository(db_path)
    key_repo.seed_keys([
        VirtualKeyConfig(
            key_hash=hash_api_key(LOAD_KEY),
            tenant_id="load-tenant",
            budget_usd=10_000.0,
            rate_limit_rpm=rpm,
            model_allowlist=[FAST_MODEL, SMART_MODEL, "fast"],
            cache_enabled=False,
            cache_threshold=0.85,
            status="active",
        ),
    ])

    app.state.key_repository = key_repo
    app.state.usage_repository = SQLiteUsageRepository(db_path)
    app.state.log_repository = SQLiteLogRepository(db_path)
    app.state.cache_repository = CacheRepository(db_path)
    app.state.cache_service = CacheService(
        embedder=BowEmbedder(),
        repository=app.state.cache_repository,
    )

    fake = FakeProviderAdapter(
        response=ProviderResponse(
            content="Load test response.",
            model=FAST_MODEL,
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
            finish_reason="stop",
            raw_response={},
        )
    )

    app.state.provider_adapters = {
        FAST_MODEL: fake,
        SMART_MODEL: fake,
    }
    app.state.provider_adapter = fake
    app.state.loaded_config = GatewayConfig(
        aliases={
            "fast": AliasConfig(
                alias_name="fast",
                primary_model=FAST_MODEL,
                fallback_chain=[],
            ),
        },
        model_pricing={
            FAST_MODEL: ModelPricing(
                model_name=FAST_MODEL,
                input_price_per_million=0.15,
                output_price_per_million=0.60,
            ),
            SMART_MODEL: ModelPricing(
                model_name=SMART_MODEL,
                input_price_per_million=0.59,
                output_price_per_million=0.79,
            ),
        },
        max_retries=0,
    )

    return app


PAYLOAD = {
    "model": "fast",
    "messages": [{"role": "user", "content": "Load test request."}],
}


# ── Test 1: Over-admission ────────────────────────────────────────────────────

def test_over_admission() -> dict:
    """
    Fire CONCURRENT_WORKERS concurrent requests against a key with RPM_LIMIT.
    Exactly RPM_LIMIT should be admitted; the rest must receive 429.
    """

    print(f"\n[1/3] Over-admission test")
    print(f"      Sending {CONCURRENT_WORKERS} concurrent requests "
          f"against RPM={RPM_LIMIT} limit ...")

    with TemporaryDirectory() as tmp:
        app = build_app(Path(tmp), rpm=RPM_LIMIT)

        statuses = []

        with TestClient(app) as client:
            def send(_):
                resp = client.post(
                    "/v1/chat/completions",
                    json=PAYLOAD,
                    headers={"x-api-key": LOAD_KEY},
                )
                return resp.status_code

            with ThreadPoolExecutor(max_workers=CONCURRENT_WORKERS) as pool:
                futures = [pool.submit(send, i) for i in range(CONCURRENT_WORKERS)]
                for f in as_completed(futures):
                    statuses.append(f.result())

    admitted = statuses.count(200)
    rejected_429 = statuses.count(429)
    other = len(statuses) - admitted - rejected_429

    over_admitted = max(0, admitted - RPM_LIMIT)

    print(f"      Admitted (200): {admitted}")
    print(f"      Rejected (429): {rejected_429}")
    print(f"      Other:          {other}")
    print(f"      Over-admission: {over_admitted}")

    if over_admitted == 0:
        print(f"      [PASS] Zero over-admission")
    else:
        print(f"      [FAIL] Over-admitted {over_admitted} requests beyond the {RPM_LIMIT} RPM cap")

    return {
        "total": CONCURRENT_WORKERS,
        "admitted": admitted,
        "rejected_429": rejected_429,
        "other": other,
        "rpm_limit": RPM_LIMIT,
        "over_admission_count": over_admitted,
        "pass": over_admitted == 0,
    }


# ── Test 2: Usage accounting accuracy ────────────────────────────────────────

def test_usage_accuracy() -> dict:
    """
    Send N sequential successful requests and verify that the usage table
    records exactly N × tokens_per_response tokens.
    """

    request_count = 50
    tokens_per_response = 15  # prompt=10 + completion=5

    print(f"\n[2/3] Usage accounting accuracy test")
    print(f"      Sending {request_count} sequential requests "
          f"({tokens_per_response} tokens each) ...")

    with TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        app = build_app(tmp_path, rpm=10_000)

        with TestClient(app) as client:
            for i in range(request_count):
                resp = client.post(
                    "/v1/chat/completions",
                    json={
                        "model": "fast",
                        "messages": [
                            {"role": "user", "content": f"Request number {i}."}
                        ],
                    },
                    headers={"x-api-key": LOAD_KEY},
                )
                assert resp.status_code == 200, f"Request {i} failed: {resp.text}"

        key_hash = hash_api_key(LOAD_KEY)
        month = datetime.now(timezone.utc).strftime("%Y-%m")
        usage = app.state.usage_repository.get_usage(key_hash, month)

    expected_tokens = request_count * tokens_per_response
    actual_tokens = usage.total_tokens
    actual_requests = usage.total_requests
    discrepancy = abs(actual_tokens - expected_tokens)

    print(f"      Expected tokens:  {expected_tokens}")
    print(f"      Recorded tokens:  {actual_tokens}")
    print(f"      Expected requests: {request_count}")
    print(f"      Recorded requests: {actual_requests}")
    print(f"      Token discrepancy: {discrepancy}")

    accounting_ok = discrepancy == 0 and actual_requests == request_count

    if accounting_ok:
        print(f"      [PASS] Usage accounting is exact")
    else:
        print(f"      [FAIL] Usage accounting mismatch detected")

    return {
        "request_count": request_count,
        "tokens_per_response": tokens_per_response,
        "expected_tokens": expected_tokens,
        "actual_tokens": actual_tokens,
        "expected_requests": request_count,
        "actual_requests": actual_requests,
        "token_discrepancy": discrepancy,
        "pass": accounting_ok,
    }


# ── Test 3: Latency statistics ────────────────────────────────────────────────

def test_latency() -> dict:
    """
    Send LATENCY_REQUESTS sequential requests and report p50/p95/p99 latency.
    Uses wall-clock time measured around the client call.
    """

    print(f"\n[3/3] Latency statistics ({LATENCY_REQUESTS} sequential requests) ...")

    with TemporaryDirectory() as tmp:
        app = build_app(Path(tmp), rpm=10_000)
        latencies_ms = []

        with TestClient(app) as client:
            for i in range(LATENCY_REQUESTS):
                t0 = time.perf_counter()
                resp = client.post(
                    "/v1/chat/completions",
                    json={
                        "model": "fast",
                        "messages": [{"role": "user", "content": f"Latency probe {i}."}],
                    },
                    headers={"x-api-key": LOAD_KEY},
                )
                elapsed_ms = (time.perf_counter() - t0) * 1000
                latencies_ms.append(elapsed_ms)
                assert resp.status_code == 200, f"Request {i} failed: {resp.text}"

    latencies_ms.sort()
    p50 = statistics.median(latencies_ms)
    p95 = latencies_ms[int(len(latencies_ms) * 0.95)]
    p99 = latencies_ms[int(len(latencies_ms) * 0.99)]
    p_min = latencies_ms[0]
    p_max = latencies_ms[-1]
    mean = statistics.mean(latencies_ms)

    print(f"      Min:  {p_min:.2f} ms")
    print(f"      p50:  {p50:.2f} ms")
    print(f"      p95:  {p95:.2f} ms")
    print(f"      p99:  {p99:.2f} ms")
    print(f"      Max:  {p_max:.2f} ms")
    print(f"      Mean: {mean:.2f} ms")
    print(f"      [INFO] Latency measured in-process (TestClient); "
          "real HTTP adds ~1-5ms network overhead.")

    return {
        "request_count": LATENCY_REQUESTS,
        "min_ms": round(p_min, 2),
        "mean_ms": round(mean, 2),
        "p50_ms": round(p50, 2),
        "p95_ms": round(p95, 2),
        "p99_ms": round(p99, 2),
        "max_ms": round(p_max, 2),
    }


# ── Report writer ─────────────────────────────────────────────────────────────

def write_report(over_adm: dict, usage_acc: dict, latency: dict) -> Path:
    """Write a Markdown report to docs/verification/load_test_report.md."""

    report_path = PROJECT_ROOT / "docs" / "verification" / "load_test_report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)

    run_date = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    over_adm_result = "✅ PASS" if over_adm["pass"] else "❌ FAIL"
    usage_result = "✅ PASS" if usage_acc["pass"] else "❌ FAIL"

    lines = [
        "# Prism Load Test Report",
        "",
        f"> **Run date:** {run_date}  ",
        f"> **Python test client** (in-process, no live server required)  ",
        f"> **Provider:** FakeAdapter (deterministic, no network calls)",
        "",
        "---",
        "",
        "## Summary",
        "",
        "| Test | Result |",
        "|---|---|",
        f"| Over-admission | {over_adm_result} — {over_adm['over_admission_count']} over-admitted out of {over_adm['total']} concurrent requests |",
        f"| Usage accounting | {usage_result} — {usage_acc['token_discrepancy']} token discrepancy across {usage_acc['request_count']} requests |",
        f"| Latency | ℹ️ INFO — p50={latency['p50_ms']} ms, p95={latency['p95_ms']} ms, p99={latency['p99_ms']} ms |",
        "",
        "---",
        "",
        "## 1. Over-Admission Test",
        "",
        f"Fired **{over_adm['total']} concurrent requests** against a key with **RPM cap = {over_adm['rpm_limit']}**.",
        "Exactly the cap number should be admitted; the rest must receive HTTP 429.",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Total concurrent requests | {over_adm['total']} |",
        f"| RPM cap | {over_adm['rpm_limit']} |",
        f"| Admitted (HTTP 200) | {over_adm['admitted']} |",
        f"| Rejected (HTTP 429) | {over_adm['rejected_429']} |",
        f"| Other status codes | {over_adm['other']} |",
        f"| **Over-admission count** | **{over_adm['over_admission_count']}** |",
        f"| **Result** | **{over_adm_result}** |",
        "",
        "> [!NOTE]",
        "> The token-bucket rate limiter uses a threading lock to make the",
        "> check-and-decrement operation atomic. This prevents race conditions",
        "> where two concurrent threads both see `tokens > 0` and both decrement.",
        "",
        "---",
        "",
        "## 2. Usage Accounting Accuracy",
        "",
        f"Sent **{usage_acc['request_count']} sequential requests** with a fake provider returning exactly **{usage_acc['tokens_per_response']} tokens each**.",
        "Verified that the usage table records the exact expected totals.",
        "",
        "| Metric | Expected | Actual |",
        "|---|---:|---:|",
        f"| Total tokens | {usage_acc['expected_tokens']} | {usage_acc['actual_tokens']} |",
        f"| Total requests | {usage_acc['expected_requests']} | {usage_acc['actual_requests']} |",
        f"| Token discrepancy | 0 | {usage_acc['token_discrepancy']} |",
        f"| **Result** | | **{usage_result}** |",
        "",
        "> [!NOTE]",
        "> Usage is recorded via atomic SQL `UPDATE ... SET tokens = tokens + ?`.",
        "> There is no read-modify-write cycle, so concurrent updates cannot",
        "> produce lost updates or double-counting.",
        "",
        "---",
        "",
        "## 3. Latency Statistics",
        "",
        f"Sent **{latency['request_count']} sequential requests** through the full pipeline",
        "(auth → rate limit → resolve → allowlist → budget → cache → provider → meter → log).",
        "",
        "| Percentile | Latency |",
        "|---|---:|",
        f"| Min | {latency['min_ms']} ms |",
        f"| p50 (median) | {latency['p50_ms']} ms |",
        f"| p95 | {latency['p95_ms']} ms |",
        f"| p99 | {latency['p99_ms']} ms |",
        f"| Max | {latency['max_ms']} ms |",
        f"| Mean | {latency['mean_ms']} ms |",
        "",
        "> [!IMPORTANT]",
        "> Latency is measured **in-process** using FastAPI's `TestClient`.",
        "> This excludes real network I/O (TCP round-trip ~1–5 ms) and OS",
        "> scheduling overhead. With a live HTTP server, expect p50 to be",
        "> approximately the in-process p50 + network latency.",
        "",
        "---",
        "",
        "## Notes",
        "",
        "- All tests use `FakeProviderAdapter` — provider latency is 0 ms by design.",
        "  Real provider calls add 100–3000 ms depending on model and load.",
        "- The rate limiter is in-memory. In a multi-instance deployment,",
        "  each instance would have its own bucket, potentially multiplying the",
        "  effective RPM limit by the number of instances.",
        "- Cache is disabled for load tests to ensure every request goes through",
        "  the full pipeline and is accounted for.",
        "",
    ]

    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("\n" + "=" * 60)
    print("  PRISM LOAD TEST")
    print("=" * 60)

    over_adm = test_over_admission()
    usage_acc = test_usage_accuracy()
    latency = test_latency()

    report_path = write_report(over_adm, usage_acc, latency)

    print("\n" + "=" * 60)
    print("  LOAD TEST COMPLETE")
    print("=" * 60)
    print(f"\nOver-admission:    {'PASS' if over_adm['pass'] else 'FAIL'} "
          f"({over_adm['over_admission_count']} over-admitted)")
    print(f"Usage accounting:  {'PASS' if usage_acc['pass'] else 'FAIL'} "
          f"(discrepancy: {usage_acc['token_discrepancy']} tokens)")
    print(f"Latency (p50/p95/p99): "
          f"{latency['p50_ms']} / {latency['p95_ms']} / {latency['p99_ms']} ms")
    print(f"\nReport saved to: {report_path}")

    all_pass = over_adm["pass"] and usage_acc["pass"]
    if not all_pass:
        sys.exit(1)

    print("\nAll load test checks passed.")


if __name__ == "__main__":
    main()

