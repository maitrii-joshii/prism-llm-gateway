# Prism LLM Gateway

> **A production-grade LLM gateway** that sits between your teams and AI providers — handling authentication, smart routing, semantic caching, rate limiting, budget enforcement, resilient failover, and full observability through a single OpenAI-compatible API.

```
Team A ──┐
Team B ──┼──► POST /v1/chat/completions ──► PRISM ──► OpenAI / Groq
Team C ──┘       x-api-key: prism-sk-...           ◄── streamed response
```

---

## Features

- **OpenAI-compatible API** — drop-in replacement; no client changes needed
- **Virtual key authentication** — per-team keys with SHA-256 hashing, never stored raw
- **Rate limiting** — per-key token-bucket limiter (configurable RPM), race-condition safe
- **Budget enforcement** — monthly spend caps per key with atomic SQL accounting
- **Model allowlists** — restrict each key to a subset of models/aliases
- **Semantic caching** — bag-of-words cosine similarity; paraphrased questions hit the cache; tenant-isolated by construction
- **Smart routing (`auto`)** — heuristic difficulty classifier routes to `fast` or `smart` tier automatically
- **Model aliases** — `fast`, `smart`, `quality` decouple callers from real model names
- **Streaming (SSE)** — token-by-token pass-through with correct `[DONE]` termination
- **Resilient execution** — configurable retries with exponential backoff + jitter, automatic provider failover
- **Structured JSON logging** — every request logged to stdout; decision trace on each line
- **Admin API** — usage by key, recent request logs, cache statistics
- **Ops console** — single-page HTML dashboard at `/console`; no build step
- **Docker Compose** — one command to start the full stack

---

## Quick Start (Docker Compose)

```bash
# 1. Clone and configure
cp .env.example .env
# Edit .env — add OPENAI_API_KEY and GROQ_API_KEY

# 2. Start the full stack
docker-compose up --build -d

# 3. Verify
curl http://localhost:3000/health
# {"status":"ok"}
```

That's it. Send your first request:

```bash
curl http://localhost:3000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "x-api-key: prism-sk-search-1a2b3c" \
  -d '{"model": "fast", "messages": [{"role": "user", "content": "Hello!"}]}'
```

---

## Manual Setup (without Docker)

### Prerequisites

- Python 3.12+
- An [OpenAI API key](https://platform.openai.com/api-keys) and/or a [Groq API key](https://console.groq.com/keys)

### Steps

```bash
# 1. Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate        # Linux / macOS
.venv\Scripts\activate           # Windows

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env
# Edit .env — set at minimum:
#   OPENAI_API_KEY=sk-...
#   GROQ_API_KEY=gsk_...
#   PRISM_ADMIN_TOKEN=your-secret-admin-token

# 4. Start the gateway
python -m prism.main
# Listening on http://0.0.0.0:3000
```

### Run with mock providers (no real API keys needed)

```bash
# Terminal 1 — alpha mock on port 9001
python scripts/mock_provider.py --port 9001 --name alpha

# Terminal 2 — beta mock on port 9002
python scripts/mock_provider.py --port 9002 --name beta

# Terminal 3 — gateway pointing at mocks
# In .env set:
#   OPENAI_BASE_URL=http://localhost:9001
#   OPENAI_API_KEY=mock-key
#   GROQ_BASE_URL=http://localhost:9002
#   GROQ_API_KEY=mock-key
python -m prism.main
```

---

## API Documentation

### Authentication

All gateway requests require a virtual key in the `x-api-key` header.

```
x-api-key: prism-sk-search-1a2b3c
```

### Model Aliases

| Alias | Primary Model | Fallback | Use When |
|---|---|---|---|
| `fast` | `gpt-4o-mini` | `llama-3.3-70b-versatile` | Simple lookups, extraction, listing |
| `smart` | `llama-3.3-70b-versatile` | `gpt-4o-mini` | Reasoning, proofs, code generation |
| `quality` | `llama-3.3-70b-versatile` | `gpt-4o-mini` | High-quality generation |
| `auto` | Classifier decides | — | Let Prism pick the right tier |

You may also use real model names directly (if they are in your key's allowlist):
- `gpt-4o-mini`
- `llama-3.3-70b-versatile`

---

### OpenAPI Specification & Interactive Docs

- **Swagger UI:** Accessible interactively at `http://localhost:3000/docs`
- **ReDoc:** Accessible at `http://localhost:3000/redoc`
- **Static Contract:** Version-controlled OpenAPI 3.1 definitions available at [`docs/openapi.json`](docs/openapi.json) and [`docs/openapi.yaml`](docs/openapi.yaml).

---

### `POST /v1/chat/completions`

Standard OpenAI-compatible chat completions endpoint.

**Non-streaming request:**

```bash
curl http://localhost:3000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "x-api-key: prism-sk-search-1a2b3c" \
  -d '{
    "model": "fast",
    "messages": [
      {"role": "system", "content": "You are a helpful assistant."},
      {"role": "user", "content": "What is the capital of France?"}
    ]
  }'
```

**Response:**

```json
{
  "id": "chatcmpl-...",
  "object": "chat.completion",
  "choices": [{
    "message": {"role": "assistant", "content": "The capital of France is Paris."},
    "finish_reason": "stop",
    "index": 0
  }],
  "usage": {"prompt_tokens": 20, "completion_tokens": 9, "total_tokens": 29}
}
```

**Custom response headers:**

| Header | Example | Description |
|---|---|---|
| `x-prism-request-id` | `req_a1b2c3d4` | Unique trace ID for this request |
| `x-prism-provider` | `openai/gpt-4o-mini` | Which provider and model answered |
| `x-prism-cache` | `miss` / `hit` / `skip` | Semantic cache result |
| `x-prism-fallback` | `true` | Present when a fallback provider was used |
| `x-prism-cost-usd` | `0.000012` | Estimated cost in USD (0 for cache hits) |

---

**Streaming request:**

```bash
curl -N http://localhost:3000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "x-api-key: prism-sk-search-1a2b3c" \
  -d '{
    "model": "fast",
    "messages": [{"role": "user", "content": "Count to five slowly."}],
    "stream": true
  }'
```

**Smart routing via `auto`:**

```bash
curl http://localhost:3000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "x-api-key: prism-sk-search-1a2b3c" \
  -d '{
    "model": "auto",
    "messages": [{"role": "user", "content": "Prove that the square root of 2 is irrational."}]
  }'
# → routes to "smart" tier (proof request detected by classifier)
```

---

**Error responses** follow the OpenAI format:

```json
{
  "error": {
    "message": "Invalid API key.",
    "type": "authentication_error",
    "code": 401
  }
}
```

| HTTP Status | Error Type | Cause |
|---|---|---|
| 400 | `invalid_request` | Missing `model` or `messages`, invalid `max_tokens` |
| 401 | `authentication_error` | Missing or invalid `x-api-key` |
| 403 | `model_not_allowed` | Model not in key's allowlist |
| 404 | `not_found_error` | Unknown model alias |
| 429 | `rate_limit_exceeded` | Per-minute request limit reached |
| 429 | `budget_exceeded` | Monthly spend cap reached |
| 502 | `upstream_error` | Provider unreachable or returned an error |

---

### `GET /health`

```bash
curl http://localhost:3000/health
# {"status": "ok"}
```

---

### `GET /metrics`

Export Prometheus-compatible metrics for monitoring and alerting:

```bash
curl http://localhost:3000/metrics
```

**Sample Output:**
```promql
# HELP prism_requests_total Total number of chat completion requests handled by Prism.
# TYPE prism_requests_total counter
prism_requests_total{cache="miss",fallback="false",model="openai/gpt-4o-mini",provider="openai",status_code="200"} 42
prism_requests_total{cache="hit",fallback="false",model="openai/gpt-4o-mini",provider="openai",status_code="200"} 18

# HELP prism_request_duration_seconds Request duration in seconds.
# TYPE prism_request_duration_seconds summary
prism_request_duration_seconds_count 60
prism_request_duration_seconds_sum 14.825120
prism_request_duration_seconds{quantile="0.5"} 0.210450
prism_request_duration_seconds{quantile="0.95"} 0.589120
prism_request_duration_seconds{quantile="0.99"} 1.120300

# HELP prism_tokens_total Prism gateway metric prism_tokens_total.
# TYPE prism_tokens_total counter
prism_tokens_total{type="prompt"} 1240
prism_tokens_total{type="completion"} 890
```

---

### Admin Endpoints

All admin endpoints require the `PRISM_ADMIN_TOKEN` as a Bearer token.

**Usage by key:**

```bash
curl http://localhost:3000/admin/usage \
  -H "Authorization: Bearer admin-secret-change-me"

# Optional month filter:
curl "http://localhost:3000/admin/usage?month=2026-11" \
  -H "Authorization: Bearer admin-secret-change-me"
```

```json
{
  "month": "2026-11",
  "total_keys": 2,
  "usage": [
    {
      "key_hash": "a3f9...",
      "month": "2026-11",
      "total_spend_usd": 0.000423,
      "total_tokens": 1850,
      "total_requests": 12,
      "cache_hits": 4
    }
  ]
}
```

**Recent request logs:**

```bash
curl "http://localhost:3000/admin/logs?limit=20&offset=0" \
  -H "Authorization: Bearer admin-secret-change-me"

# Filter by key hash:
curl "http://localhost:3000/admin/logs?key_hash=a3f9..." \
  -H "Authorization: Bearer admin-secret-change-me"
```

**Cache statistics:**

```bash
curl http://localhost:3000/admin/cache/stats \
  -H "Authorization: Bearer admin-secret-change-me"
```

```json
{
  "total_entries": 42,
  "total_hits": 18,
  "cache_hit_rate": 0.3
}
```

---

### Ops Console

Open in your browser — no installation required:

```
http://localhost:3000/console
```

Enter your `PRISM_ADMIN_TOKEN` in the token field and click **Connect**. The console shows:
- Cache hit rate, total entries, active keys, total spend (stat cards)
- Usage table by key (spend, tokens, requests, cache hits)
- Recent request log (status, model, provider, cost, latency, cache result)
- Auto-refresh every 10 seconds (toggle with the **Auto** button)

---

## Configuration

All configuration is via environment variables. Copy `.env.example` to `.env` and edit.

| Variable | Default | Description |
|---|---|---|
| `PORT` | `3000` | HTTP server port |
| `PRISM_LOG_LEVEL` | `INFO` | Log verbosity: `DEBUG` \| `INFO` \| `WARNING` \| `ERROR` |
| `PRISM_DB_PATH` | `data/prism.db` | SQLite database file path |
| `PRISM_CONFIG_DIR` | `config/` | Directory containing JSON config files |
| `OPENAI_API_KEY` | — | **Required.** OpenAI API key |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | OpenAI-compatible base URL |
| `GROQ_API_KEY` | — | **Required.** Groq API key |
| `GROQ_BASE_URL` | `https://api.groq.com/openai/v1` | Groq base URL |
| `PRISM_ADMIN_TOKEN` | — | Secret token for admin API endpoints |
| `PRISM_PROVIDER_TIMEOUT_SECONDS` | `30.0` | Total provider request timeout |
| `PRISM_CONNECT_TIMEOUT_SECONDS` | `5.0` | TCP connection timeout |
| `PRISM_MAX_RETRIES` | `2` | Retry attempts before failover |
| `PRISM_RETRY_BASE_DELAY_SECONDS` | `1.0` | Base delay for exponential backoff |
| `PRISM_MAX_TOKENS_CAP` | `4096` | Hard cap on `max_tokens` per request |

### Configuration files (`config/`)

| File | Purpose |
|---|---|
| `seed_keys.json` | Virtual key definitions (tenant ID, budget, RPM, allowlist) |
| `model_pricing.json` | Input/output cost per million tokens per model |
| `gateway_config.sample.json` | Alias-to-model mappings and provider fallback chains |

**Seed key format:**

```json
[
  {
    "key": "prism-sk-search-1a2b3c",
    "tenant_id": "tenant-search",
    "budget_usd": 100.0,
    "rate_limit_rpm": 60,
    "model_allowlist": ["fast", "smart", "auto"],
    "cache_enabled": true,
    "cache_threshold": 0.85,
    "status": "active"
  }
]
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                       PRISM                              │
│                                                         │
│   HTTP Layer  →  Request Pipeline  →  Provider Layer    │
│                                                         │
│   Pipeline stages (in order):                           │
│   auth → validate → rate_limit → resolve → allowlist    │
│        → budget → cache → provider_call → meter → log   │
└─────────────────────────────────────────────────────────┘
```

Prism follows **Hexagonal Architecture** (Ports & Adapters):

- **Domain layer** (`prism/domain/`) — pure business rules, no I/O, no frameworks. `CostCalculator`, `TokenBucketRateLimiter`, error types, data models.
- **Services layer** (`prism/services/`) — pipeline orchestration, stage sequencing, `CacheService`, `ResilientExecutor`.
- **Adapters layer** (`prism/adapters/`) — `OpenAICompatibleProvider`, `SQLiteKeyRepository`, `BowEmbedder`, `SystemClock`.
- **API layer** (`prism/api/`) — FastAPI routes, middleware, error handler, admin router.

See [`docs/architecture.md`](docs/architecture.md) for the full architecture document.

---

## Design Decisions

Eight Architecture Decision Records (ADRs) document the key choices:

| ADR | Decision |
|---|---|
| [ADR-001](docs/adr/ADR-001-cache-hits-and-limits.md) | Cache hits count toward rate limit but are free on budget |
| [ADR-002](docs/adr/ADR-002-mid-stream-failure.md) | Mid-stream provider failure → SSE error event; no provider switching |
| [ADR-003](docs/adr/ADR-003-budget-overshoot.md) | Streaming budget is admit-then-record; bounded overshoot accepted |
| [ADR-004](docs/adr/ADR-004-cache-scope-and-keying.md) | Cache scoped by `key_hash + alias`; key = system prompt + last user message |
| [ADR-005](docs/adr/ADR-005-time-sensitive-content.md) | Keyword blocklist skips cache for time-sensitive prompts |
| [ADR-006](docs/adr/ADR-006-prompt-storage-in-logs.md) | Prompt text not stored in logs by default |
| [ADR-007](docs/adr/ADR-007-auto-and-allowlist.md) | `auto` requires explicit allowlist entry; resolved tier also checked |
| [ADR-008](docs/adr/ADR-008-router-training-data.md) | Hand-authored training data only; eval file never peeked during development |

---

## Routing Logic (`auto`)

When a request uses `model: "auto"`, the **difficulty classifier** decides whether to route to `fast` (simpler, cheaper) or `smart` (more capable):

```
"What is the capital of France?"        → fast  (simple lookup)
"Prove that √2 is irrational."          → smart (mathematical proof)
"List the planets in the solar system." → fast  (enumeration)
"Debug this async Python race condition." → smart (code + reasoning)
```

**Classifier signals used:**

| Signal | Tier |
|---|---|
| `prove`, `derive`, `explain why`, `analyze`, `compare`, `contrast` | `smart` |
| Triple backticks (code blocks), mathematical notation | `smart` |
| Multi-part structure (`first... then... finally`) | `smart` |
| `list`, `name`, `find`, `what is`, `who is`, `when did` | `fast` |
| Short, single-concept questions | `fast` |

The classifier must beat a length-only baseline (>200 chars → smart, else → fast) on the routing eval set. Results are in [`docs/routing_eval_results.md`](docs/routing_eval_results.md).

> **Note:** The `auto` alias must be explicitly included in a key's `model_allowlist` to be used. See [ADR-007](docs/adr/ADR-007-auto-and-allowlist.md).

---

## Cache Scoping (Tenant Isolation)

The semantic cache is **structurally isolated per tenant** — not filtered after the fact. Every cache lookup query includes `WHERE key_hash = ? AND alias = ?`:

```sql
SELECT * FROM cache_entries
WHERE key_hash = :key_hash    -- tenant isolation
  AND alias    = :alias        -- model tier isolation
```

It is impossible by construction for Team A's cached answer to be served to Team B, even if their prompts are identical.

**Cache key composition:** `system_prompt + last_user_message` (embedded with bag-of-words cosine similarity).

**Cache threshold:** 0.85 by default (configurable per key). Paraphrases match; near-misses do not.

**Time-sensitive prompts** (containing: `now`, `today`, `latest`, `current`, `right now`, `live`, `breaking`) skip the cache and always hit the provider.

---

## Failover Behavior

Each alias defines a **fallback chain**. If the primary provider fails, Prism automatically tries the next in the chain:

```json
"fast": {
  "primary_model": "gpt-4o-mini",
  "fallback_chain": ["llama-3.3-70b-versatile"]
}
```

**Retry strategy:** Exponential backoff with jitter on the same provider for transient errors (5xx, timeout). Provider-level 429s and connection failures trigger immediate failover to the next provider.

**Failover indicator:** Successful fallback responses include the `x-prism-fallback: true` header.

**Mid-stream rule:** Failover only applies *before* the first byte is sent. If a provider dies mid-stream, Prism sends an SSE error event and closes the stream cleanly — it does not switch providers mid-response (see [ADR-002](docs/adr/ADR-002-mid-stream-failure.md)).

---

## Testing

```bash
# All tests
pytest tests/ -v

# Unit tests only (fast, no network)
pytest tests/unit/ -v

# Integration tests
pytest tests/integration/ -v

# Concurrency tests (rate limiter race condition)
pytest tests/concurrency/ -v

# With coverage
pytest tests/ --cov=prism --cov-report=term-missing
```

**Test suite structure:**

| Directory | What It Tests |
|---|---|
| `tests/unit/` | Domain logic: cost, rate limiter, cache, classifier, auth, errors |
| `tests/integration/` | Full HTTP pipeline with `FakeAdapter` (no real providers) |
| `tests/concurrency/` | Rate limiter under concurrent load — zero over-admission |
| `tests/helpers/` | `FakeAdapter`, `FakeClock` — test doubles used by all test types |

---

## Docker

### Build and start

```bash
docker-compose up --build -d
docker-compose ps            # check all services are healthy
```

### View logs

```bash
docker-compose logs -f prism-gateway
```

### Stop and clean up

```bash
docker-compose down          # stop (data persists in named volume)
docker-compose down -v       # stop and delete all data
```

### Simulate provider failover

```bash
# Stop the primary provider
docker-compose stop alpha-mock

# Requests still succeed — Prism fails over to beta
curl http://localhost:3000/v1/chat/completions \
  -H "x-api-key: prism-sk-search-1a2b3c" \
  -H "Content-Type: application/json" \
  -d '{"model": "fast", "messages": [{"role": "user", "content": "Hi"}]}'
# Response includes: x-prism-fallback: true

# Restore primary
docker-compose start alpha-mock
```

### Rebuild only the gateway

```bash
docker-compose up --build -d prism-gateway
```

---

## Verification

All verification uses the **official, unmodified Airtribe starter files**:
`data/seed_keys.json`, `data/model_pricing.json`, `data/gateway_config.sample.json`,
`data/routing_eval.jsonl`, and `scripts/{smoke_test,load_test,mock_provider}.py`.
The gateway loads the starter formats directly (see `prism/config/loader.py`);
the default config directory is `data/` (mock providers `alpha`/`beta`).
Set `PRISM_CONFIG_DIR=config` to use the real OpenAI/Groq profile instead.

Start the stack (compose publishes the gateway on port 3000):

```bash
docker compose up --build -d
```

### Smoke test (official)

```bash
python scripts/smoke_test.py --url http://localhost:3000 --key prism-sk-search-1a2b3c --model fast
```

### Load test (official)

```bash
python scripts/load_test.py --url http://localhost:3000 --key prism-sk-free-7g8h9i \
    --model fast --requests 30 --concurrency 10 --rpm-limit 10
```

Compare its client-side totals with `GET /admin/usage` for the same key.

### Routing eval (official labeled set)

```bash
python scripts/routing_eval.py
```

Writes `docs/routing_eval_results.md` and `docs/routing_eval_results.json`.

### Failure drill (official mock providers)

```bash
curl -X POST http://localhost:9001/admin/config -d '{"mode": "down"}'   # alpha down -> beta serves, x-prism-fallback: true
curl -X POST http://localhost:9001/admin/config -d '{"mode": "ok", "fail_rate": 0}'
```

### Earlier in-process checks (own tests, not the official ones)

`scripts/smoke_test_inprocess.py` and `scripts/load_test_inprocess.py` run the
app in-process with fake adapters; `data/own_routing_eval.jsonl` is a
self-written set. They are supplementary and are **not** the graded scripts.

### Manual walkthrough

```bash
# Health
curl http://localhost:3000/health

# Non-streaming
curl http://localhost:3000/v1/chat/completions \
  -H "x-api-key: prism-sk-search-1a2b3c" \
  -H "Content-Type: application/json" \
  -d '{"model": "fast", "messages": [{"role": "user", "content": "Hello"}]}'

# Streaming
curl -N http://localhost:3000/v1/chat/completions \
  -H "x-api-key: prism-sk-search-1a2b3c" \
  -H "Content-Type: application/json" \
  -d '{"model": "fast", "messages": [{"role": "user", "content": "Count to 5"}], "stream": true}'

# Cache hit (send same request twice — second returns x-prism-cache: hit)
curl http://localhost:3000/v1/chat/completions \
  -H "x-api-key: prism-sk-search-1a2b3c" \
  -H "Content-Type: application/json" \
  -d '{"model": "fast", "messages": [{"role": "user", "content": "Hello"}]}'

# Auth failure → 401
curl http://localhost:3000/v1/chat/completions \
  -H "x-api-key: invalid-key" \
  -H "Content-Type: application/json" \
  -d '{"model": "fast", "messages": [{"role": "user", "content": "Hi"}]}'

# Admin usage
curl http://localhost:3000/admin/usage \
  -H "Authorization: Bearer admin-secret-change-me"
```

---

## Known Limitations

| Limitation | Why It's Acceptable | Future Fix |
|---|---|---|
| Rate limiter is **in-memory** | Single-instance deployment only | Redis-backed distributed limiter |
| **SQLite single-writer** | One gateway instance | PostgreSQL for multi-instance |
| **Bag-of-words embedder** | Simple, offline, explainable; no API key needed | Swap in a real embedding model via the `Embedder` interface |
| **Budget can slightly overshoot during concurrent streams** | Admitted if budget remains at start; true cost recorded at end. Overshoot bound: O(concurrent\_streams × average\_request\_cost). See ADR-003. | Pre-reserve estimated cost before streaming begins |
| **Mid-stream provider failure does not failover** | Once the first byte has been sent to the client the HTTP headers are committed and stream topology is fixed. Switching providers mid-stream would produce incoherent "franken-answers". Instead, Prism sends an SSE error event and closes the stream. See ADR-002. | Pre-flight provider check before first byte (future) |
| **No HTTPS** | Development / demo only | Reverse proxy (nginx) or TLS termination |
| **No prompt storage in logs** | Privacy-safe by default | Enable with `PRISM_LOG_PROMPTS=true` (future) |
| `auto` requires explicit allowlist entry | Prevents allowlist bypass; well-documented (ADR-007) | — |

---

## Project Structure

```
prism-llm-gateway/
│
├── prism/                        # Application package
│   ├── main.py                   # Composition root — wires all objects
│   ├── domain/                   # Pure business rules (no I/O)
│   │   ├── models.py             # Core data models (Pydantic)
│   │   ├── errors.py             # Typed error hierarchy
│   │   ├── limiter.py            # Token-bucket rate limiter
│   │   └── security.py           # Key hashing helpers
│   ├── services/                 # Orchestration layer
│   │   ├── pipeline.py           # Stage sequencer
│   │   ├── cache.py              # Semantic cache service
│   │   ├── executor.py           # Resilient executor (retry/failover)
│   │   ├── router.py             # Difficulty classifier
│   │   ├── streaming.py          # SSE streaming proxy
│   │   └── stages/               # Individual pipeline stages
│   │       ├── auth.py           # Virtual key authentication
│   │       ├── validate.py       # Request body validation
│   │       ├── rate_limiter.py   # Rate limit enforcement
│   │       ├── resolve.py        # Alias → model resolution + auto routing
│   │       ├── allowlist.py      # Model allowlist check
│   │       ├── budget.py         # Budget enforcement + cost metering
│   │       └── cache.py          # Cache lookup / store stage
│   ├── adapters/                 # Infrastructure implementations
│   │   ├── openai_compatible.py  # OpenAI-compatible HTTP provider
│   │   ├── sqlite_repos.py       # SQLite key/usage/log/cache repos
│   │   ├── bow_embedder.py       # Bag-of-words cosine embedder
│   │   └── system_clock.py       # Real clock (injectable)
│   ├── api/                      # HTTP layer
│   │   ├── routes.py             # POST /v1/chat/completions
│   │   ├── admin.py              # GET /admin/* endpoints
│   │   ├── middleware.py         # Request ID injection
│   │   └── error_handler.py      # PrismError → JSON response
│   ├── config/
│   │   ├── settings.py           # Typed env-var settings
│   │   ├── loader.py             # JSON config file loader
│   │   └── logging.py            # Structured JSON log config
│   └── ports/                    # Interfaces (abstract base classes)
│       ├── provider.py           # ProviderAdapter ABC
│       ├── repositories.py       # Repository ABCs
│       ├── embedder.py           # Embedder ABC
│       └── clock.py              # Clock ABC
│
├── config/                       # Configuration files
│   ├── seed_keys.json            # Virtual key definitions
│   ├── model_pricing.json        # Token pricing per model
│   └── gateway_config.sample.json # Alias and provider config
│
├── console/
│   └── index.html                # Ops console (single HTML file)
│
├── data/                         # Runtime data (gitignored)
│   └── prism.db                  # SQLite database
│
├── docs/
│   ├── architecture.md           # Full architecture document
│   ├── implementation-plan.md    # 15-day task-by-task plan
│   ├── adr/                      # Architecture Decision Records
│   │   ├── ADR-001-cache-hits-and-limits.md
│   │   ├── ADR-002-mid-stream-failure.md
│   │   ├── ADR-003-budget-overshoot.md
│   │   ├── ADR-004-cache-scope-and-keying.md
│   │   ├── ADR-005-time-sensitive-content.md
│   │   ├── ADR-006-prompt-storage-in-logs.md
│   │   ├── ADR-007-auto-and-allowlist.md
│   │   └── ADR-008-router-training-data.md
│   └── verification/             # Verification outputs
│
├── scripts/
│   ├── smoke_test.py             # End-to-end feature verification
│   ├── routing_eval.py           # Classifier accuracy measurement
│   └── mock_provider.py          # Lightweight mock LLM provider
│
├── tests/
│   ├── unit/                     # Fast, isolated domain tests
│   ├── integration/              # Full HTTP pipeline tests
│   ├── concurrency/              # Race condition / over-admission tests
│   └── helpers/                  # FakeAdapter, FakeClock
│
├── Dockerfile                    # Multi-stage production image
├── docker-compose.yml            # Gateway + mock providers
├── .env.example                  # Environment variable template
├── requirements.txt              # Python dependencies
└── README.md                     # This file
```

---

## License

MIT — see [LICENSE](LICENSE).

