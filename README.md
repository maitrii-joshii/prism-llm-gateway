# Prism LLM Gateway

> A production-style **LLM gateway** that sits between your teams and AI providers. It handles authentication, smart routing, semantic caching, rate limiting, budget enforcement, resilient failover and observability behind a single **OpenAI-compatible API**.

```
Team A ──┐
Team B ──┼──► POST /v1/chat/completions ──► PRISM ──► Provider alpha / beta (or OpenAI / Groq)
Team C ──┘       x-api-key: prism-sk-...           ◄── JSON or streamed (SSE) response
```

---

## Table of Contents

1. [Features](#features)
2. [Run with Docker (recommended)](#run-with-docker-recommended)
3. [Run without Docker](#run-without-docker)
4. [Ops Console (Admin + Playground)](#ops-console)
5. [API Reference](#api-reference)
6. [Configuration](#configuration)
7. [Architecture](#architecture)
8. [Behavior Guides: routing, cache, failover](#routing-logic-auto)
9. [Testing & Verification](#testing--verification)
10. [Documentation Index](#documentation-index)
11. [Project structure](#project-structure)

---

## Features

- **OpenAI-compatible API**: drop-in `POST /v1/chat/completions` and `GET /v1/models`.
- **Virtual key authentication**: per-team keys, SHA-256 hashed, never stored raw.
- **Rate limiting**: per-key token-bucket limiter (RPM), race-condition safe.
- **Budget enforcement**: monthly spend caps per key with atomic SQL accounting.
- **Model allowlists**: restrict each key to a subset of aliases/models.
- **Semantic cache**: bag-of-words cosine similarity, tenant-isolated by construction.
- **Smart routing (`auto`)**: difficulty classifier routes to the `fast` or `smart` tier.
- **Model aliases**: `fast`, `smart`, `auto` (plus any alias in your config) decouple callers from real model names.
- **Streaming (SSE)**: token-by-token pass-through with correct `[DONE]` termination.
- **Resilient execution**: retries with exponential backoff + jitter and provider failover.
- **Observability**: structured JSON logs, request IDs, Prometheus `/metrics`.
- **Admin API**: usage by key, request logs, cache statistics.
- **Ops Console**: single HTML page at `/console` with two tabs: **Admin** and **Playground & Response**. No build step.
- **Docker Compose**: one command starts the gateway plus two mock providers.

---

## Run with Docker (recommended)

The Docker setup needs **no API keys**. By default the gateway loads the official starter data in [`data/`](data/) and talks to two mock LLM providers (`alpha`, `beta`) that run as containers.

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (or Docker Engine) with Compose v2
- Ports `3000`, `9001`, `9002` free

### Step 1: Clone the repository

```bash
git clone https://github.com/maitrii-joshii/prism-llm-gateway.git
cd prism-llm-gateway
```

### Step 2 (optional): set an admin token

Compose falls back to `admin-secret-change-me` if `PRISM_ADMIN_TOKEN` is not set. To choose your own:

```bash
cp .env.example .env          # Windows PowerShell: Copy-Item .env.example .env
# edit .env and set PRISM_ADMIN_TOKEN=your-secret
```

### Step 3: Build and start the stack

```bash
docker compose up --build -d
docker compose ps             # wait until all three services show "healthy"
```

| Service | Container | URL | Purpose |
|---|---|---|---|
| `prism-gateway` | `prism-gateway` | http://localhost:3000 | The gateway (API, console, admin, metrics) |
| `alpha-mock` | `prism-alpha-mock` | http://localhost:9001 | Mock provider alpha (primary) |
| `beta-mock` | `prism-beta-mock` | http://localhost:9002 | Mock provider beta (fallback) |

SQLite data lives in the named volume `prism-db`, mounted at `/app/dbdata`, so it survives restarts.

### Step 4: Verify

```bash
curl http://localhost:3000/health
# {"status":"ok"}
```

### Step 5: Send a request

Starter keys (from [`data/seed_keys.json`](data/seed_keys.json)):

| Team | Key | Allowed models | RPM | Budget / month |
|---|---|---|---|---|
| search | `prism-sk-search-1a2b3c` | `fast` | 60 | \$50 |
| research | `prism-sk-research-4d5e6f` | `fast`, `smart`, `auto` | 300 | \$500 |
| free-tier | `prism-sk-free-7g8h9i` | `fast` | 10 | \$5 |
| budget-demo | `prism-sk-budget-demo-0j1k2l` | `fast` | 60 | \$0.00001 (for `budget_exceeded` demos) |

```bash
curl http://localhost:3000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "x-api-key: prism-sk-search-1a2b3c" \
  -d '{"model":"fast","messages":[{"role":"user","content":"Hello!"}]}'
```

Open the console at **http://localhost:3000/console** (see [Ops Console](#ops-console)).

### Step 6: Useful Docker commands

```bash
docker compose logs -f prism-gateway          # follow structured JSON logs
docker compose up --build -d prism-gateway    # rebuild only the gateway after code changes
docker compose down                           # stop (data persists in the prism-db volume)
docker compose down -v                        # stop and delete all data
```

### Simulate provider failover

```bash
docker compose stop alpha-mock                # primary provider goes down
curl -i http://localhost:3000/v1/chat/completions \
  -H "x-api-key: prism-sk-search-1a2b3c" -H "Content-Type: application/json" \
  -d '{"model":"fast","messages":[{"role":"user","content":"Hi"}]}'
# 200 OK with header: x-prism-fallback: true
docker compose start alpha-mock               # restore
```

The mock providers also accept runtime control (official starter behavior):

```bash
curl -X POST http://localhost:9001/admin/config -d '{"mode":"down"}'
curl -X POST http://localhost:9001/admin/config -d '{"mode":"ok","fail_rate":0}'
```

### What the Docker image does

[`Dockerfile`](Dockerfile) is a **multi-stage** build on `python:3.12-slim`:

1. **builder**: installs `requirements.txt` into an isolated prefix and copies the code.
2. **production**: copies the dependencies and code, runs as a **non-root** `prism` user, exposes `3000`, includes a `/health` **HEALTHCHECK**, and starts `uvicorn prism.main:app`.

Image defaults: `PORT=3000`, `PRISM_CONFIG_DIR=/app/data`, `PRISM_DB_PATH=/app/dbdata/prism.db`. `docker-compose.yml` overrides the provider URLs so they resolve inside the compose network (`PRISM_PROVIDER_ALPHA_BASE_URL=http://alpha-mock:9001/v1`, and the same for beta). [`.dockerignore`](.dockerignore) keeps `.env`, databases, tests and docs out of the image.

### Using real providers in Docker

1. Put your keys in `.env` (for example via `PRISM_PROVIDER_<NAME>_API_KEY`, see [Configuration](#configuration)).
2. Point the gateway at the real-provider profile in [`config/`](config/): set `PRISM_CONFIG_DIR=/app/config` for the `prism-gateway` service in `docker-compose.yml`, then run `docker compose up --build -d`.

---

## Run without Docker

### Prerequisites

- Python 3.12+

### Steps

```bash
# 1. Virtual environment
python -m venv .venv
source .venv/bin/activate            # Linux / macOS
.venv\Scripts\activate               # Windows

# 2. Dependencies
pip install -r requirements.txt

# 3. Environment
cp .env.example .env                 # then set PRISM_ADMIN_TOKEN (and PORT if needed)

# 4. Start two mock providers (separate terminals)
python scripts/mock_provider.py --port 9001 --name alpha
python scripts/mock_provider.py --port 9002 --name beta

# 5. Start the gateway (uses data/ starter config by default)
python -m prism.main
```

The gateway listens on `PORT` / `PRISM_PORT` (default `8000` when run directly; `3000` in Docker). Console: `http://localhost:<port>/console`.

> To use the real OpenAI-compatible profile instead of mocks, set `PRISM_CONFIG_DIR=config` and provide each provider's key (see [Configuration](#configuration)).

---

## Ops Console

Served by the gateway at **`/`** and **`/console`** from [`console/index.html`](console/index.html). It is a single page with two tabs:

### 🛡️ Admin tab

- Enter your `PRISM_ADMIN_TOKEN` and click **Connect**.
- Stat cards: cache hit rate, cache entries, active keys, total spend.
- **Usage by Key** and **Recent Requests** tables.
- Header controls **Refresh** and **Auto** (auto-refresh every 10 s) work from either tab.

### ⚡ Playground & Response tab

- Pick a **Virtual API Key**, a **Model / Routing Target** (`auto`, `fast`, `smart`) and a prompt, or use the quick presets (simple, complex, cache-hit paraphrase).
- Click **Ask Gateway** to see the **Live Decision Inspector**: model selected, provider, cache hit/miss, fallback, cost, latency and the model's response.
- If an admin token has been entered, the Admin tab data refreshes after each request.

> The playground's key dropdown lists the keys of the real-provider profile in [`config/seed_keys.json`](config/seed_keys.json). With the default Docker/starter profile, use the starter keys above (for example `prism-sk-search-1a2b3c` with `fast`), or switch to `PRISM_CONFIG_DIR=config`.

---

## API Reference

### Authentication

| Surface | Header |
|---|---|
| Gateway (`/v1/*`) | `x-api-key: <virtual key>` (or `Authorization: Bearer <virtual key>`) |
| Admin (`/admin/*`) | `Authorization: Bearer <PRISM_ADMIN_TOKEN>` |

### Interactive docs

- **Swagger UI:** `http://localhost:3000/docs`
- **ReDoc:** `http://localhost:3000/redoc`
- **Static contract:** [`docs/openapi.json`](docs/openapi.json), [`docs/openapi.yaml`](docs/openapi.yaml) (regenerate with `python scripts/generate_openapi.py`)

### Endpoints

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/v1/chat/completions` | virtual key | Chat completion, JSON or `stream: true` (SSE) |
| GET | `/v1/models` | none | Available models and aliases |
| GET | `/health` | none | Liveness |
| GET | `/metrics` | none | Prometheus metrics |
| GET | `/admin/usage?month=YYYY-MM` | admin | Usage grouped by key (defaults to current month) |
| GET | `/admin/logs?limit=&offset=&key_hash=` | admin | Recent request logs (`limit` 1-500) |
| GET | `/admin/cache/stats` | admin | Cache entries, hits, hit rate |
| GET | `/`, `/console` | none | Ops console |

### `POST /v1/chat/completions`

```bash
curl http://localhost:3000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "x-api-key: prism-sk-research-4d5e6f" \
  -d '{
    "model": "auto",
    "messages": [{"role": "user", "content": "Prove that the square root of 2 is irrational."}]
  }'
# auto routes this to the "smart" tier
```

Streaming: add `"stream": true` and use `curl -N`.

**Response headers**

| Header | Example | Meaning |
|---|---|---|
| `x-prism-request-id` | `req_a1b2c3d4` | Trace ID |
| `x-prism-provider` | `alpha/alpha-small` | Provider/model that answered |
| `x-prism-cache` | `hit` / `miss` / `skip` | Semantic cache result |
| `x-prism-fallback` | `true` | A fallback provider served the request |
| `x-prism-cost-usd` | `0.000012` | Estimated cost (0 for cache hits) |

**Errors** use the OpenAI shape: `{"error": {"message": "...", "type": "...", "code": 401}}`

| Status | Type | Cause |
|---|---|---|
| 400 | `invalid_request` | Missing/invalid `model`, `messages`, `max_tokens` |
| 401 | `authentication_error` | Missing or invalid key |
| 403 | `model_not_allowed` | Model not in the key's allowlist |
| 404 | `not_found_error` | Unknown alias |
| 429 | `rate_limit_exceeded` | Per-minute limit reached |
| 429 | `budget_exceeded` | Monthly cap reached |
| 502 | `upstream_error` | All providers failed |

### Admin examples

```bash
TOKEN=admin-secret-change-me     # or your PRISM_ADMIN_TOKEN
curl http://localhost:3000/admin/usage       -H "Authorization: Bearer $TOKEN"
curl "http://localhost:3000/admin/logs?limit=20" -H "Authorization: Bearer $TOKEN"
curl http://localhost:3000/admin/cache/stats -H "Authorization: Bearer $TOKEN"
```

### Metrics

`GET /metrics` exports Prometheus text: `prism_requests_total{cache,fallback,model,provider,status_code}`, `prism_request_duration_seconds` (summary with quantiles) and `prism_tokens_total{type}`.

---

## Configuration

Settings come from environment variables (a `.env` file is loaded automatically; copy [`.env.example`](.env.example)).

| Variable | Default | Description |
|---|---|---|
| `PORT` / `PRISM_PORT` | `8000` locally, `3000` in Docker | HTTP port |
| `PRISM_LOG_LEVEL` | `INFO` | `DEBUG` \| `INFO` \| `WARNING` \| `ERROR` |
| `PRISM_DB_PATH` | `data/prism.db` (`/app/dbdata/prism.db` in Docker) | SQLite file |
| `PRISM_CONFIG_DIR` | `data/` (`/app/data` in Docker) | Folder holding the JSON config files |
| `PRISM_ADMIN_TOKEN` | none (compose default `admin-secret-change-me`) | Admin bearer token. If unset, admin endpoints reject all requests |
| `PRISM_PROVIDER_<NAME>_BASE_URL` | from JSON | Override a provider's base URL (e.g. `PRISM_PROVIDER_ALPHA_BASE_URL`) |
| `PRISM_PROVIDER_<NAME>_API_KEY` | from JSON | Override a provider's API key |
| `PRISM_PROVIDER_TIMEOUT_SECONDS` | `30.0` | Total provider timeout |
| `PRISM_CONNECT_TIMEOUT_SECONDS` | `5.0` | Connect timeout |
| `PRISM_MAX_RETRIES` | `2` | Retries before failover |
| `PRISM_RETRY_BASE_DELAY_SECONDS` | `1.0` | Backoff base delay |
| `PRISM_MAX_TOKENS_CAP` | `4096` | Hard cap on `max_tokens` |
| `OPENAI_API_KEY`, `GROQ_API_KEY` (+ `*_BASE_URL`) | none | Used only in the legacy fallback when no `providers` are defined in the gateway config |

### Config profiles

| Profile | Folder | Providers | When to use |
|---|---|---|---|
| **Starter / mock** (default) | [`data/`](data/) | `alpha`, `beta` mocks | Docker, demos, verification |
| **Real providers** | [`config/`](config/) | `openai` (OpenRouter URL), `qwen` (Groq URL) | Live LLM calls. Set `PRISM_CONFIG_DIR=config` and the provider keys |

Each folder contains `seed_keys.json` (tenants, budgets, rate limits, allowlists, cache settings), `model_pricing.json` (cost per 1M tokens) and `gateway_config*.json` (providers, aliases, fallbacks, retry). The loader supports the official starter schema as well as the `config/` schema. If `gateway_config.json` exists it is used, otherwise `gateway_config.sample.json`.

---

## Architecture

Prism follows **Hexagonal Architecture (Ports & Adapters)**. A request flows through an ordered pipeline:

```
auth → validate → rate_limit → resolve (alias / auto) → allowlist
     → budget → cache lookup → provider call (retry + failover) → meter → log
```

| Layer | Path | Responsibility |
|---|---|---|
| Domain | `prism/domain/` | Pure rules: cost calculation, token-bucket limiter, cache decision, errors, models, key hashing |
| Ports | `prism/ports/` | Interfaces: provider, repositories, embedder, clock |
| Services | `prism/services/` | Pipeline and stages, `CacheService`, router/classifier, resilient executor, streaming, metrics, admin, observability |
| Adapters | `prism/adapters/` | OpenAI-compatible HTTP provider, SQLite repositories, bag-of-words embedder, system clock |
| API | `prism/api/` | FastAPI routes, admin router, request-ID middleware, error handler |
| Config | `prism/config/` | Typed settings, JSON config loader, logging |

`prism/main.py` is the composition root: it loads config, initializes SQLite, seeds keys, builds provider adapters and attaches everything to `app.state`.

Rationale for each key decision is recorded in the ADRs below. The original design documents (architecture, implementation plan, PDF) are no longer in the repository; this section and the ADRs are the source of truth.

### Design decisions (ADRs)

| ADR | Decision |
|---|---|
| [ADR-001](docs/adr/ADR-001-cache-hits-and-limits.md) | Cache hits count toward the rate limit but are free on budget |
| [ADR-002](docs/adr/ADR-002-mid-stream-failure.md) | Mid-stream provider failure sends an SSE error event, with no provider switching |
| [ADR-003](docs/adr/ADR-003-budget-overshoot.md) | Streaming budget is admit-then-record; bounded overshoot accepted |
| [ADR-004](docs/adr/ADR-004-cache-scope-and-keying.md) | Cache scoped by `key_hash + alias`; key is system prompt + last user message |
| [ADR-005](docs/adr/ADR-005-time-sensitive-content.md) | Keyword blocklist skips cache for time-sensitive prompts |
| [ADR-006](docs/adr/ADR-006-prompt-storage-in-logs.md) | Prompt text is not stored in logs by default |
| [ADR-007](docs/adr/ADR-007-auto-and-allowlist.md) | `auto` requires an explicit allowlist entry; the resolved tier is also checked |
| [ADR-008](docs/adr/ADR-008-router-training-data.md) | Hand-authored router training data; eval file not used during development |

---

## Routing Logic (`auto`)

With `model: "auto"` the heuristic classifier ([`prism/services/router.py`](prism/services/router.py)) picks `fast` (cheap) or `smart` (capable):

```
"What is the capital of France?"          → fast
"Prove that √2 is irrational."            → smart
"List the planets in the solar system."   → fast
"Debug this async Python race condition." → smart
```

Signals include reasoning verbs (`prove`, `derive`, `analyze`, `compare`), code blocks and math, and multi-step structure (→ `smart`), versus lookups and short single-concept questions (→ `fast`). It must beat a length-only baseline on the labeled set; results are in [`docs/routing_eval_results.md`](docs/routing_eval_results.md). Reproduce with `python scripts/routing_eval.py`.

> The key must list `auto` in its `model_allowlist` to use it ([ADR-007](docs/adr/ADR-007-auto-and-allowlist.md)).

## Cache Scoping (Tenant Isolation)

Every lookup is constrained by `WHERE key_hash = ? AND alias = ?`, so one tenant's cached answer can never be served to another. The cache key is `system_prompt + last_user_message`, matched by bag-of-words cosine similarity against a per-key threshold (for example `0.92` for search and `0.85` for free-tier). Time-sensitive prompts (`now`, `today`, `latest`, `current`, ...) skip the cache. Threshold analysis: [`docs/cache_threshold_tuning.md`](docs/cache_threshold_tuning.md).

## Failover Behavior

Each alias has a primary and fallbacks (for example `fast`: `alpha-small` then `beta-small`). Transient errors (5xx, timeouts) are retried with exponential backoff and jitter; provider 429s and connection failures fail over immediately. A fallback response carries `x-prism-fallback: true`. Failover only happens **before the first byte**; after that a failure ends the stream with an SSE error event ([ADR-002](docs/adr/ADR-002-mid-stream-failure.md)).

---

## Testing & Verification

### Automated tests

```bash
pip install -r requirements.txt
pytest tests/ -v                         # everything
pytest tests/unit -v                     # fast domain/unit tests
pytest tests/integration -v              # full HTTP pipeline with FakeAdapter
pytest tests/concurrency -v              # rate limiter race conditions
pytest tests/ --cov=prism --cov-report=term-missing
```

| Directory | Covers |
|---|---|
| `tests/unit/` | Cost, limiter, cache, router, auth, config, repositories, admin, streaming, logging |
| `tests/integration/` | Pipeline, semantic cache, streaming, failover, error paths, passthrough |
| `tests/concurrency/` | Limiter under concurrent load (no over-admission) |
| `tests/helpers/` | `FakeAdapter`, `FakeClock` |

CI ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)) runs the tests, builds the Docker image and validates `docker compose config` on every push and pull request.

### End-to-end checks against the running Docker stack

```bash
python scripts/smoke_test.py --url http://localhost:3000 --key prism-sk-search-1a2b3c --model fast
python scripts/load_test.py  --url http://localhost:3000 --key prism-sk-free-7g8h9i \
       --model fast --requests 30 --concurrency 10 --rpm-limit 10
python scripts/routing_eval.py
```

Compare the load test totals with `GET /admin/usage` for the same key. Recorded outputs are in [`docs/verification/`](docs/verification/).

### Manual walkthrough

```bash
curl http://localhost:3000/health
# non-streaming
curl http://localhost:3000/v1/chat/completions -H "x-api-key: prism-sk-search-1a2b3c" \
  -H "Content-Type: application/json" -d '{"model":"fast","messages":[{"role":"user","content":"Hello"}]}'
# streaming
curl -N http://localhost:3000/v1/chat/completions -H "x-api-key: prism-sk-search-1a2b3c" \
  -H "Content-Type: application/json" -d '{"model":"fast","messages":[{"role":"user","content":"Count to 5"}],"stream":true}'
# send the same prompt twice: second response has x-prism-cache: hit
# invalid key → 401
curl -i http://localhost:3000/v1/chat/completions -H "x-api-key: bad" \
  -H "Content-Type: application/json" -d '{"model":"fast","messages":[{"role":"user","content":"Hi"}]}'
```

Supplementary in-process scripts (`scripts/smoke_test_inprocess.py`, `scripts/load_test_inprocess.py`, `data/own_routing_eval.jsonl`) are our own checks, separate from the official starter scripts.

---

## Documentation Index

| Document | Content |
|---|---|
| [`docs/starter/PRISM_PROBLEM_STATEMENT.md`](docs/starter/PRISM_PROBLEM_STATEMENT.md) | Project requirements and deliverables |
| [`docs/starter/API_CONTRACT.md`](docs/starter/API_CONTRACT.md), [`DATA_MODEL.md`](docs/starter/DATA_MODEL.md) | API and data model contracts |
| [`docs/starter/IMPLEMENTATION_GUIDE.md`](docs/starter/IMPLEMENTATION_GUIDE.md), [`EVALUATION_GUIDE.md`](docs/starter/EVALUATION_GUIDE.md) | Implementation and evaluation guidance |
| [`docs/adr/`](docs/adr/) | Eight Architecture Decision Records |
| [`docs/openapi.json`](docs/openapi.json) / [`.yaml`](docs/openapi.yaml) | Generated OpenAPI 3.1 contract |
| [`docs/routing_eval_results.md`](docs/routing_eval_results.md) | Router accuracy vs. baseline |
| [`docs/cache_threshold_tuning.md`](docs/cache_threshold_tuning.md) | Cache similarity threshold analysis |
| [`docs/verification/`](docs/verification/) | Load test report, smoke test output, walkthrough |

---

## Project Structure

```
prism-llm-gateway/
├── prism/
│   ├── main.py                    # Composition root (FastAPI app, lifespan wiring)
│   ├── domain/                    # cost, limiter, cache_decision, errors, models, security
│   ├── ports/                     # clock, embedder, provider, repositories
│   ├── services/
│   │   ├── pipeline.py, chat_completion.py, chat_streaming.py
│   │   ├── cache.py, router.py, executor.py, streaming*.py, metrics.py, admin.py
│   │   ├── stages/                # auth, validate, rate_limiter, resolve, allowlist, budget, cache
│   │   ├── providers/             # execution, streaming_execution
│   │   ├── observability/         # request_logging, usage_recording
│   │   └── models/                # model listing
│   ├── adapters/                  # openai_compatible, sqlite_repos, bow_embedder, system_clock
│   ├── api/                       # routes, admin, middleware, responses, error_handler
│   └── config/                    # settings, loader, logging
├── config/                        # Real-provider profile (openai/qwen)
├── data/                          # Starter profile (alpha/beta mocks) + eval datasets
├── console/index.html             # Ops console (Admin + Playground tabs)
├── docs/                          # ADRs, starter docs, OpenAPI, eval and verification reports
├── scripts/                       # smoke/load tests, routing eval, mock providers, OpenAPI generator
├── tests/                         # unit, integration, concurrency, helpers
├── .github/workflows/ci.yml       # CI: tests + Docker build
├── Dockerfile                     # Multi-stage, non-root, healthcheck
├── docker-compose.yml             # Gateway + alpha/beta mock providers
├── .env.example                   # Environment template
├── requirements.txt
└── README.md
```

---

## License

MIT. See [LICENSE](LICENSE).
</Content>



