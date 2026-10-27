# Prism LLM Gateway — Task-by-Task Implementation Plan

> **Version:** 1.0  
> **Created:** October 25, 2026  
> **Timeline:** 15 working days × 2.5 hours/day = **37.5 hours total**  
> **Approach:** Thin vertical slices — always have something that runs end-to-end  
> **Reference:** [architecture.md](file:///c:/Users/MJ/Desktop/Projects/Airtribe/prism-llm-gateway/docs/architecture.md) · [PRISM_ARCHITECTURE.md](file:///c:/Users/MJ/Desktop/Projects/Airtribe/prism-llm-gateway/docs/PRISM_ARCHITECTURE.md)

---

## How to Use This Plan

- Each **Day** has a theme and a set of **numbered tasks**.
- Each task has: **what to do**, **files to create/modify**, **acceptance criteria**, and **verify** commands.
- Tasks within a day are **sequential** — complete them in order.
- A ✅ checkbox tracks completion. Mark each done before moving on.
- **Do not skip ahead** — later tasks depend on earlier ones being solid.
- If a task takes longer than estimated, borrow time from the same phase's buffer, not from a future phase.

---

## Progress Tracker

| Phase | Days | Hours | Status |
|-------|------|-------|--------|
| **Phase 1:** Foundations | Days 1–3 | 7.5h | ⬜ Not Started |
| **Phase 2:** Auth & Governance | Days 4–6 | 7.5h | ⬜ Not Started |
| **Phase 3:** Streaming & Resilience | Days 7–9 | 7.5h | ⬜ Not Started |
| **Phase 4:** Intelligence | Days 10–12 | 7.5h | ⬜ Not Started |
| **Phase 5:** Docker, Console & Docs | Days 13–15 | 7.5h | ⬜ Not Started |

---

## Phase 1: Foundations (Days 1–3)

> **Goal:** Get a bare-bones gateway that can forward one non-streaming request to one provider and return a response with custom headers. Everything else will be layered on top of this working skeleton.

---

### Day 1 — Project Scaffolding & Domain Core (2.5 hours)

**Theme:** Set up the project structure, define data models, error hierarchy, and config loader. By the end of today, the project compiles and you can import every module without errors.

---

#### Task 1.1: Initialize Project & Install Dependencies
**Time:** 20 min  
**Depends on:** Nothing (starting point)

**What to do:**
1. Initialize a Python project with a virtual environment
2. Create `requirements.txt` with core dependencies
3. Create the top-level folder structure matching the architecture
4. Create `__init__.py` files in all packages

**Files to create:**
```
requirements.txt
prism/__init__.py
prism/domain/__init__.py
prism/ports/__init__.py
prism/adapters/__init__.py
prism/services/__init__.py
prism/services/stages/__init__.py
prism/api/__init__.py
prism/config/__init__.py
tests/__init__.py
tests/unit/__init__.py
tests/integration/__init__.py
```

**Requirements to include:**
```
fastapi>=0.104.0
uvicorn[standard]>=0.24.0
httpx>=0.25.0
pydantic>=2.5.0
python-dotenv>=1.0.0
pytest>=7.4.0
pytest-asyncio>=0.21.0
```

**Acceptance criteria:**
- [ ] `pip install -r requirements.txt` succeeds
- [ ] `python -c "import prism"` runs without error
- [ ] Every subdirectory has an `__init__.py`

**Verify:**
```bash
pip install -r requirements.txt
python -c "import prism; import prism.domain; import prism.ports; import prism.adapters"
```

---

#### Task 1.2: Define Domain Models
**Time:** 30 min  
**Depends on:** Task 1.1

**What to do:**
1. Create `prism/domain/models.py` with all core data classes
2. Use Python dataclasses or Pydantic models for type safety
3. Define: `VirtualKeyConfig`, `RequestContext`, `ProviderResponse`, `ModelPricing`, `GatewayConfig`, `AliasConfig`, `UsageRecord`

**File to create:** `prism/domain/models.py`

**Key models to define:**
```python
# VirtualKeyConfig — what we know about one tenant
#   key_hash, tenant_id, budget_usd, rate_limit_rpm,
#   model_allowlist, cache_enabled, cache_threshold, status

# RequestContext — travels through the pipeline
#   request_id, key_config, model_requested, model_resolved,
#   provider_name, messages, stream, decision_trace, start_time

# ProviderResponse — what comes back from a provider
#   content, model, prompt_tokens, completion_tokens,
#   total_tokens, finish_reason, raw_response

# ModelPricing — cost per token for a model
#   model_name, input_price_per_million, output_price_per_million

# AliasConfig — alias → model chain
#   alias_name, primary_model, fallback_chain
```

**Acceptance criteria:**
- [ ] All models can be instantiated with test data
- [ ] Models enforce required fields (errors on missing data)
- [ ] `RequestContext` can accumulate a `decision_trace` list

**Verify:**
```bash
python -c "from prism.domain.models import VirtualKeyConfig, RequestContext; print('Models OK')"
```

---

#### Task 1.3: Define Error Hierarchy
**Time:** 20 min  
**Depends on:** Task 1.1

**What to do:**
1. Create `prism/domain/errors.py` with `PrismError` base class
2. Create one subclass per rejection type
3. Each error knows its own HTTP status code and OpenAI-compatible `type` string
4. Errors carry a human-readable `message`

**File to create:** `prism/domain/errors.py`

**Error classes to define:**

| Class | HTTP Status | Type String |
|-------|-------------|-------------|
| `PrismError` (base) | 500 | `internal_error` |
| `AuthenticationError` | 401 | `authentication_error` |
| `InvalidRequestError` | 400 | `invalid_request` |
| `ModelNotAllowedError` | 403 | `model_not_allowed` |
| `ModelNotFoundError` | 404 | `not_found_error` |
| `RateLimitError` | 429 | `rate_limit_exceeded` |
| `BudgetExceededError` | 429 | `budget_exceeded` |
| `UpstreamError` | 502 | `upstream_error` |

**Acceptance criteria:**
- [ ] Each error has `status_code`, `error_type`, and `message` attributes
- [ ] `PrismError` is the parent of all custom errors
- [ ] Errors can be raised and caught by type

**Verify:**
```bash
python -c "
from prism.domain.errors import RateLimitError
e = RateLimitError('Too many requests')
assert e.status_code == 429
assert e.error_type == 'rate_limit_exceeded'
print('Errors OK')
"
```

---

#### Task 1.4: Create Port Interfaces (Contracts)
**Time:** 25 min  
**Depends on:** Task 1.2

**What to do:**
1. Create `prism/ports/clock.py` — `Clock` interface with `now()` method
2. Create `prism/ports/provider.py` — `ProviderAdapter` interface with `complete()` and `stream()` methods
3. Create `prism/ports/repositories.py` — `KeyRepository`, `UsageRepository`, `LogRepository`, `CacheRepository` interfaces
4. Create `prism/ports/embedder.py` — `Embedder` interface with `embed()` method
5. Use Python's `abc.ABC` and `abstractmethod` for all interfaces

**Files to create:**
```
prism/ports/clock.py
prism/ports/provider.py
prism/ports/repositories.py
prism/ports/embedder.py
```

**Acceptance criteria:**
- [ ] All interfaces are abstract classes that cannot be instantiated directly
- [ ] Method signatures match what the architecture document specifies
- [ ] No implementation logic — only contracts

**Verify:**
```bash
python -c "
from prism.ports.provider import ProviderAdapter
try:
    ProviderAdapter()
    print('FAIL: should not instantiate abstract class')
except TypeError:
    print('Ports OK: abstract classes work correctly')
"
```

---

#### Task 1.5: Build Config Loader & Settings
**Time:** 30 min  
**Depends on:** Tasks 1.2, 1.3

**What to do:**
1. Create `prism/config/settings.py` — typed settings class reading from env vars (with dotenv fallback)
2. Create `prism/config/loader.py` — functions to load `seed_keys.json`, `model_pricing.json`, and `gateway_config.sample.json`
3. Validate: every alias must point to a model in the pricing table
4. **Fail fast** — crash with a clear message if validation fails

**Files to create:**
```
prism/config/settings.py
prism/config/loader.py
```

**Validation rules to implement:**
- All required fields present in each JSON file
- Every alias resolves to a model that exists in the pricing table
- Budget values are positive numbers
- Rate limits are positive integers

**Acceptance criteria:**
- [ ] Loader reads all three JSON files and returns typed objects
- [ ] Missing file → clear error message and exit
- [ ] Alias pointing to non-existent model → crash at startup with explanation
- [ ] Environment variables override defaults

**Verify:**
```bash
python -c "
from prism.config.loader import load_gateway_config
# Should fail if files don't exist yet — that's correct fail-fast behavior
print('Config loader module OK')
"
```

---

#### Task 1.6: Write Unit Tests for Day 1
**Time:** 25 min  
**Depends on:** Tasks 1.2–1.5

**What to do:**
1. Create `tests/unit/test_models.py` — test model instantiation, required fields
2. Create `tests/unit/test_errors.py` — test error hierarchy, status codes, type strings
3. Create `tests/unit/test_config.py` — test config loader with sample data, test validation failures

**Files to create:**
```
tests/unit/test_models.py
tests/unit/test_errors.py
tests/unit/test_config.py
```

**Acceptance criteria:**
- [ ] All tests pass with `pytest tests/unit/ -v`
- [ ] At least 3 tests per file
- [ ] Tests cover both success and failure paths

**Verify:**
```bash
pytest tests/unit/ -v --tb=short
```

---

### 📋 Day 1 Checklist

- [ ] Project structure matches architecture diagram
- [ ] All domain models defined and importable
- [ ] Error hierarchy complete (7 error types)
- [ ] All 4 port interfaces defined as abstract classes
- [ ] Config loader reads JSON files with validation
- [ ] All unit tests pass
- [ ] **Can run:** `python -c "from prism.config.loader import *; from prism.domain.models import *"`

---

### Day 2 — Provider Adapter & HTTP Server (2.5 hours)

**Theme:** Build the provider adapter, create the HTTP server, and wire up a basic non-streaming pass-through. By end of today, `curl` works against the gateway.

---

#### Task 2.1: Implement System Clock
**Time:** 10 min  
**Depends on:** Task 1.4

**What to do:**
1. Create `prism/adapters/system_clock.py` — implements `Clock` interface with real `datetime.now()`
2. Create `tests/unit/test_clock.py` — also create a `FakeClock` test helper that returns controlled timestamps

**Files to create:**
```
prism/adapters/system_clock.py
tests/helpers/__init__.py
tests/helpers/fake_clock.py
```

**Acceptance criteria:**
- [ ] `SystemClock.now()` returns current UTC time
- [ ] `FakeClock` allows advancing time for tests
- [ ] Both implement the same `Clock` interface

---

#### Task 2.2: Implement OpenAI-Compatible Provider Adapter
**Time:** 40 min  
**Depends on:** Tasks 1.4, 1.2

**What to do:**
1. Create `prism/adapters/openai_compatible.py`
2. Implement `ProviderAdapter` interface with `complete(request)` method (streaming later)
3. Use `httpx.AsyncClient` for HTTP calls
4. Parse OpenAI-compatible response format into `ProviderResponse`
5. Handle HTTP errors and timeouts gracefully
6. Provider URL and API key come from constructor (injected, not hardcoded)

**File to create:** `prism/adapters/openai_compatible.py`

**Key implementation details:**
- `POST {base_url}/v1/chat/completions` with the request body
- Set `Authorization: Bearer {api_key}` header
- Parse `choices[0].message.content`, `usage.prompt_tokens`, `usage.completion_tokens`
- Raise `UpstreamError` on non-200 responses

**Acceptance criteria:**
- [ ] Can send a request to a mock provider and parse the response
- [ ] Timeout is configurable (default 30s)
- [ ] Non-200 responses raise `UpstreamError`
- [ ] Connection errors raise `UpstreamError`

---

#### Task 2.3: Create Fake Provider Adapter for Tests
**Time:** 15 min  
**Depends on:** Task 2.2

**What to do:**
1. Create `tests/helpers/fake_adapter.py` — implements `ProviderAdapter`
2. Returns canned responses instantly with no network call
3. Can be configured to return specific responses, raise errors, or simulate latency

**File to create:** `tests/helpers/fake_adapter.py`

**Acceptance criteria:**
- [ ] Implements same interface as `OpenAICompatibleAdapter`
- [ ] Can be configured with custom responses
- [ ] Can simulate failures (raise `UpstreamError`)

---

#### Task 2.4: Build the HTTP Server & Chat Completions Route
**Time:** 45 min  
**Depends on:** Tasks 2.2, 1.3

**What to do:**
1. Create `prism/api/routes.py` — define `POST /v1/chat/completions` endpoint
2. Create `prism/api/error_handler.py` — global error handler that converts `PrismError` → OpenAI-style JSON
3. Accept the request body, validate required fields (`model`, `messages`)
4. For now: forward directly to the provider adapter (no pipeline stages yet)
5. Return the provider's response in OpenAI-compatible format

**Files to create:**
```
prism/api/routes.py
prism/api/error_handler.py
```

**OpenAI error format:**
```json
{
    "error": {
        "message": "Invalid API key",
        "type": "authentication_error",
        "code": 401
    }
}
```

**Acceptance criteria:**
- [ ] `POST /v1/chat/completions` accepts a valid request body
- [ ] Missing `model` or `messages` → 400 with structured error
- [ ] Provider errors are caught and returned as 502
- [ ] All `PrismError` subclasses produce correct JSON error responses

---

#### Task 2.5: Create the Composition Root (main.py)
**Time:** 25 min  
**Depends on:** Tasks 2.4, 1.5, 2.2

**What to do:**
1. Create `prism/main.py` — the ONE place where all objects are created and wired together
2. Load config, create provider adapter, create the FastAPI app
3. Register routes and error handlers
4. Add `GET /health` endpoint (returns `{"status": "ok"}`)
5. Start uvicorn server

**File to create:** `prism/main.py`

**Wiring order:**
1. Load environment variables (dotenv)
2. Load config files (seed keys, pricing, gateway config)
3. Create `SystemClock`
4. Create `OpenAICompatibleAdapter` for alpha provider
5. Create FastAPI app with routes
6. Register global error handler
7. Start uvicorn

**Acceptance criteria:**
- [ ] `python -m prism.main` starts the server on configured port
- [ ] `GET /health` returns `{"status": "ok"}`
- [ ] `POST /v1/chat/completions` forwards to alpha mock (if running)

**Verify:**
```bash
# Terminal 1: Start mock provider (if available)
# Terminal 2: Start Prism
python -m prism.main

# Terminal 3: Test
curl http://localhost:3000/health
curl -X POST http://localhost:3000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "alpha-small", "messages": [{"role": "user", "content": "Hello"}]}'
```

---

#### Task 2.6: Write Integration Test for Pass-Through
**Time:** 15 min  
**Depends on:** Tasks 2.5, 2.3

**What to do:**
1. Create `tests/integration/test_passthrough.py`
2. Use `FakeAdapter` to test the full flow without real providers
3. Test: valid request → 200 with response body
4. Test: missing model field → 400 error
5. Test: health endpoint → 200

**File to create:** `tests/integration/test_passthrough.py`

**Acceptance criteria:**
- [ ] All integration tests pass
- [ ] Tests do not require running providers

**Verify:**
```bash
pytest tests/integration/test_passthrough.py -v
```

---

### 📋 Day 2 Checklist

- [ ] `SystemClock` and `FakeClock` implemented
- [ ] `OpenAICompatibleAdapter` can talk to a provider
- [ ] `FakeAdapter` returns canned responses for tests
- [ ] `POST /v1/chat/completions` works end-to-end
- [ ] Error handler converts all `PrismError` types to JSON
- [ ] `GET /health` returns OK
- [ ] Integration test passes with `FakeAdapter`
- [ ] **Can demo:** `curl` a request and get a real response back

---

### Day 3 — Request ID, Headers & Logging (2.5 hours)

**Theme:** Add request ID tracking, custom response headers, and structured JSON logging. Every request gets traceable.

---

#### Task 3.1: Request ID Generation & Middleware
**Time:** 30 min  
**Depends on:** Task 2.4

**What to do:**
1. Generate a unique `request_id` for every incoming request (e.g., `req_` + UUID short)
2. Create middleware that assigns the ID at the start of each request
3. Attach the ID to `RequestContext`
4. Add `x-prism-request-id` to every response header

**Files to modify:** `prism/api/routes.py`, `prism/domain/models.py`  
**Files to create:** `prism/api/middleware.py` (if using middleware pattern)

**Acceptance criteria:**
- [ ] Every response has `x-prism-request-id` header
- [ ] Each request gets a unique ID
- [ ] ID format: `req_` followed by 8+ hex characters

**Verify:**
```bash
curl -i http://localhost:3000/health
# Check for x-prism-request-id in response headers
```

---

#### Task 3.2: Add All Custom Response Headers
**Time:** 25 min  
**Depends on:** Task 3.1

**What to do:**
1. Add `x-prism-provider` header (format: `provider/model`, e.g., `alpha/alpha-small`)
2. Add `x-prism-cache` header (value: `miss` for now — cache comes later)
3. Add `x-prism-fallback` header (value: `false` for now — failover comes later)
4. Add `x-prism-cost-usd` header (value: `0` for now — metering comes later)
5. Headers are set from `RequestContext` after the pipeline runs

**Files to modify:** `prism/api/routes.py`

**Acceptance criteria:**
- [ ] All 5 custom headers present on every successful response
- [ ] `x-prism-provider` shows actual provider and model name
- [ ] Headers are set even on error responses (at minimum `request-id`)

**Verify:**
```bash
curl -i -X POST http://localhost:3000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "alpha-small", "messages": [{"role": "user", "content": "Hi"}]}'
# Should see all x-prism-* headers
```

---

#### Task 3.3: Implement Structured JSON Logging
**Time:** 30 min  
**Depends on:** Task 3.1

**What to do:**
1. Configure Python's `logging` module to output JSON lines to stdout
2. Every log line includes: `timestamp`, `level`, `request_id`, `message`
3. Create a `get_logger(name)` helper that returns a pre-configured logger
4. Add log statements at key points: request received, response sent, errors
5. Log level controlled by `PRISM_LOG_LEVEL` env var

**Files to create:** `prism/config/logging.py`

**Log format example:**
```json
{"timestamp": "2026-10-26T10:30:00Z", "level": "INFO", "request_id": "req_abc123", "message": "Request received", "model": "fast", "path": "/v1/chat/completions"}
```

**Acceptance criteria:**
- [ ] All logs are valid JSON (one object per line)
- [ ] `request_id` appears on every log line during a request
- [ ] Log level is configurable via env var
- [ ] No secrets (keys, tokens) appear in logs

---

#### Task 3.4: Build the Decision Trace
**Time:** 20 min  
**Depends on:** Tasks 3.1, 3.3

**What to do:**
1. Add a `decision_trace` list to `RequestContext`
2. As each pipeline stage runs, append a short string describing the outcome
3. After the pipeline completes, log the full trace as one line
4. Format: `"auth ok → rate ok → cache miss → alpha-small 200 (0 retries)"`

**Files to modify:** `prism/domain/models.py`, `prism/api/routes.py`

**Acceptance criteria:**
- [ ] Decision trace builds up as stages execute
- [ ] Final trace logged at INFO level when response is sent
- [ ] Trace is included in the request log record (once DB logging exists)

---

#### Task 3.5: Set Up SQLite Database & Schema
**Time:** 25 min  
**Depends on:** Tasks 1.2, 1.4

**What to do:**
1. Create `prism/adapters/sqlite_repos.py` — database initialization
2. Implement `create_tables()` function that creates all 4 tables:
   - `virtual_keys` — key hash, tenant, budget, rpm, allowlist, cache settings
   - `usage` — per key + month spending/token tracking
   - `request_logs` — one row per request
   - `cache_entries` — cached responses with embeddings
3. Create tables on first run, skip if they exist
4. Use `busy_timeout` for concurrency safety

**File to create/modify:** `prism/adapters/sqlite_repos.py`

**Acceptance criteria:**
- [ ] Database file is created at configured path
- [ ] All 4 tables are created with correct schemas
- [ ] Running initialization twice does not error (idempotent)
- [ ] `busy_timeout` is set (e.g., 5000ms)

**Verify:**
```bash
python -c "
from prism.adapters.sqlite_repos import init_database
init_database('test.db')
import sqlite3
conn = sqlite3.connect('test.db')
tables = conn.execute(\"SELECT name FROM sqlite_master WHERE type='table'\").fetchall()
print('Tables:', [t[0] for t in tables])
"
```

---

#### Task 3.6: Write Tests for Day 3
**Time:** 20 min  
**Depends on:** Tasks 3.1–3.5

**What to do:**
1. Test request ID generation (uniqueness, format)
2. Test response headers are present
3. Test JSON log format
4. Test database schema creation

**Files to create:**
```
tests/unit/test_request_id.py
tests/unit/test_database.py
```

**Verify:**
```bash
pytest tests/ -v --tb=short
```

---

### 📋 Day 3 Checklist

- [ ] Every response has all 5 `x-prism-*` headers
- [ ] Request IDs are unique and well-formatted
- [ ] Logs output valid JSON to stdout
- [ ] Decision trace accumulates through the pipeline
- [ ] SQLite database initializes with all 4 tables
- [ ] All tests pass
- [ ] **Can demo:** `curl -i` a request and see all custom headers + request ID in logs

---

### 🏁 Phase 1 Gate

**Before moving to Phase 2, verify ALL of the following:**
- [ ] `python -m prism.main` starts successfully
- [ ] `curl /health` → 200
- [ ] `curl /v1/chat/completions` → response with all headers
- [ ] Config loader validates and fails fast on bad config
- [ ] SQLite database is initialized
- [ ] `pytest tests/ -v` — all green

---

## Phase 2: Auth & Governance (Days 4–6)

> **Goal:** Add virtual key authentication, rate limiting, cost calculation, budget enforcement, and model allowlists. After this phase, the gateway correctly controls who can do what.

---

### Day 4 — Authentication & Key Store (2.5 hours)

**Theme:** Virtual keys become the foundation. Every subsequent feature depends on knowing which tenant is making a request.

---

#### Task 4.1: Implement Key Repository (SQLite)
**Time:** 30 min  
**Depends on:** Tasks 3.5, 1.4

**What to do:**
1. Implement `KeyRepository` interface in `prism/adapters/sqlite_repos.py`
2. Methods: `get_by_hash(key_hash) → VirtualKeyConfig | None`, `seed_keys(keys_list)`
3. Store keys as SHA-256 hashes, never raw
4. Seed keys from `seed_keys.json` at startup

**Files to modify:** `prism/adapters/sqlite_repos.py`

**Acceptance criteria:**
- [ ] Keys are stored as SHA-256 hashes
- [ ] `get_by_hash()` returns `VirtualKeyConfig` or `None`
- [ ] Seeding is idempotent (running twice doesn't duplicate)

---

#### Task 4.2: Build Authentication Stage
**Time:** 30 min  
**Depends on:** Task 4.1

**What to do:**
1. Create `prism/services/stages/auth.py`
2. Extract virtual key from `x-api-key` header
3. Hash the key with SHA-256
4. Look up in `KeyRepository`
5. If not found or key is disabled → raise `AuthenticationError` (401)
6. If found → attach `VirtualKeyConfig` to `RequestContext`
7. Use **constant-time comparison** for hash matching

**File to create:** `prism/services/stages/auth.py`

**Acceptance criteria:**
- [ ] Missing `x-api-key` header → 401
- [ ] Invalid key → 401 (no distinction between missing and invalid, for security)
- [ ] Valid key → `RequestContext` populated with key config
- [ ] Decision trace: `"auth ok"` or `"auth failed"`

**Verify:**
```bash
# No key
curl -i http://localhost:3000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "fast", "messages": [{"role": "user", "content": "Hi"}]}'
# → 401

# Valid key (from seed_keys.json)
curl -i http://localhost:3000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "x-api-key: prism-sk-search-1a2b3c" \
  -d '{"model": "fast", "messages": [{"role": "user", "content": "Hi"}]}'
# → 200
```

---

#### Task 4.3: Build Request Validation Stage
**Time:** 20 min  
**Depends on:** Task 2.4

**What to do:**
1. Create `prism/services/stages/validate.py`
2. Validate the request body:
   - `model` is present and is a non-empty string
   - `messages` is present and is a non-empty array
   - Each message has `role` and `content` fields
   - `max_tokens` if present is a positive integer, capped at `PRISM_MAX_TOKENS_CAP`
3. Reject with `InvalidRequestError` (400) on validation failure

**File to create:** `prism/services/stages/validate.py`

**Acceptance criteria:**
- [ ] Missing `model` → 400
- [ ] Empty `messages` array → 400
- [ ] `max_tokens: -1` → 400
- [ ] `max_tokens: 10000000` → capped to configured limit

---

#### Task 4.4: Build the Pipeline Orchestrator
**Time:** 30 min  
**Depends on:** Tasks 4.2, 4.3

**What to do:**
1. Create `prism/services/pipeline.py`
2. Define pipeline as an ordered list of stages
3. Each stage takes a `RequestContext` and either returns it (pass) or raises a `PrismError` (reject)
4. Pipeline runs stages sequentially: `auth → validate → [future stages] → call provider`
5. Connect pipeline to the HTTP route in `routes.py`

**File to create:** `prism/services/pipeline.py`  
**Files to modify:** `prism/api/routes.py`, `prism/main.py`

**Current pipeline order (Day 4):**
```python
stages = [
    auth_stage,
    validate_stage,
    # (rate_limit, resolve, allowlist, budget, cache — added later)
    provider_call_stage,
]
```

**Acceptance criteria:**
- [ ] Stages execute in order
- [ ] First failing stage stops the chain
- [ ] Decision trace captures each stage's result
- [ ] Pipeline is easy to extend (just add a stage to the list)

---

#### Task 4.5: Write Tests for Authentication & Validation
**Time:** 30 min  
**Depends on:** Tasks 4.2, 4.3, 4.4

**What to do:**
1. Create `tests/unit/test_auth.py` — test auth stage with valid key, invalid key, missing header
2. Create `tests/unit/test_validate.py` — test validation with valid body, missing fields, bad values
3. Create `tests/integration/test_pipeline.py` — test full pipeline with `FakeAdapter`

**Files to create:**
```
tests/unit/test_auth.py
tests/unit/test_validate.py
tests/integration/test_pipeline.py
```

**Acceptance criteria:**
- [ ] Auth tests cover: valid key, invalid key, missing key, disabled key
- [ ] Validation tests cover: valid body, missing model, empty messages, bad max_tokens
- [ ] Pipeline integration test: full happy path + each rejection type

**Verify:**
```bash
pytest tests/ -v --tb=short
```

---

### 📋 Day 4 Checklist

- [ ] Virtual keys are hashed and stored in SQLite
- [ ] Authentication stage validates keys from `x-api-key` header
- [ ] Request body validation catches malformed inputs
- [ ] Pipeline orchestrator chains stages in order
- [ ] First failing stage stops the chain and returns correct error
- [ ] All tests pass
- [ ] **Can demo:** `curl` with bad key → 401, good key → 200

---

### Day 5 — Rate Limiter (2.5 hours)

**Theme:** Implement the token bucket rate limiter with atomic check-and-decrement, then wire it into the pipeline.

---

#### Task 5.1: Implement Token Bucket Rate Limiter (Domain)
**Time:** 50 min  
**Depends on:** Tasks 1.4, 2.1

**What to do:**
1. Create `prism/domain/limiter.py`
2. Implement a token bucket algorithm:
   - Each key gets a bucket with capacity = their RPM limit
   - Tokens refill over time (one per `60/rpm` seconds)
   - `try_acquire(key_hash, rpm_limit) → bool` — atomic check-and-decrement
3. Use `threading.Lock` for atomicity (prevent the race condition)
4. Time comes from injected `Clock` (not `datetime.now()`)
5. Bucket is stored in-memory (dict of key → bucket state)

**File to create:** `prism/domain/limiter.py`

**Critical implementation notes:**
- The lock must cover BOTH the check AND the decrement as ONE step
- Use the injected Clock so tests can fast-forward time
- When refilling: calculate tokens added since last request based on elapsed time

**Acceptance criteria:**
- [ ] Allows exactly N requests per minute (not N+1)
- [ ] Refills tokens over time
- [ ] Uses lock for atomicity
- [ ] Uses injected Clock (not system time)

---

#### Task 5.2: Build Rate Limit Pipeline Stage
**Time:** 20 min  
**Depends on:** Task 5.1

**What to do:**
1. Create `prism/services/stages/ratelimit.py`
2. Call `limiter.try_acquire()` with the key's configured RPM
3. If rejected → raise `RateLimitError` (429)
4. Add to decision trace: `"rate ok"` or `"rate limited"`
5. Wire into pipeline (after auth, before other stages)

**File to create:** `prism/services/stages/ratelimit.py`  
**Files to modify:** `prism/services/pipeline.py`, `prism/main.py`

**Acceptance criteria:**
- [ ] Under-limit requests pass through
- [ ] Over-limit requests get 429
- [ ] Pipeline order: auth → validate → **rate limit** → provider call

---

#### Task 5.3: Write Rate Limiter Unit Tests
**Time:** 30 min  
**Depends on:** Task 5.1

**What to do:**
1. Create `tests/unit/test_limiter.py`
2. Test with `FakeClock`:
   - Allow exactly N requests, reject N+1
   - Fast-forward time → tokens refill
   - Different keys have independent buckets
3. Test edge cases: 0 RPM, 1 RPM

**File to create:** `tests/unit/test_limiter.py`

**Acceptance criteria:**
- [ ] No test waits real time (all use FakeClock)
- [ ] Tests prove exactly-N semantics
- [ ] Tests prove refill after time advance

---

#### Task 5.4: Write Concurrency Test for Rate Limiter
**Time:** 30 min  
**Depends on:** Task 5.1

**What to do:**
1. Create `tests/concurrency/test_limiter_concurrent.py`
2. Launch 20 threads, each trying to acquire from the same key (RPM=10)
3. Assert exactly 10 succeed and 10 fail
4. This is the over-admission test — the most important correctness test

**File to create:**
```
tests/concurrency/__init__.py
tests/concurrency/test_limiter_concurrent.py
```

**Acceptance criteria:**
- [ ] With RPM=10 and 20 concurrent requests: exactly 10 allowed, 10 rejected
- [ ] Run the test 5 times in a row — result is always consistent (no flakiness)

**Verify:**
```bash
pytest tests/concurrency/test_limiter_concurrent.py -v --count=5
# (if pytest-repeat installed, or just run 5 times manually)
```

---

#### Task 5.5: Integration Test — Rate Limit via HTTP
**Time:** 20 min  
**Depends on:** Task 5.2

**What to do:**
1. Add test to `tests/integration/test_pipeline.py`
2. Send RPM+1 requests with the same key → last one gets 429
3. Verify error response has correct format

**Acceptance criteria:**
- [ ] HTTP-level test shows 429 after exceeding RPM

**Verify:**
```bash
pytest tests/integration/ -v
```

---

### 📋 Day 5 Checklist

- [ ] Token bucket rate limiter implemented with atomic lock
- [ ] FakeClock allows time-travel in tests
- [ ] Rate limit stage wired into pipeline
- [ ] Unit tests prove exactly-N semantics
- [ ] Concurrency test proves no over-admission (10/20 test)
- [ ] Integration test shows 429 via HTTP
- [ ] **Can demo:** Rapidly curl 11 requests → 11th returns 429

---

### Day 6 — Cost Calculator, Budget & Allowlist (2.5 hours)

**Theme:** Implement the money layer — cost calculation, budget tracking, and model allowlist.

---

#### Task 6.1: Implement Cost Calculator (Pure Domain)
**Time:** 25 min  
**Depends on:** Task 1.2

**What to do:**
1. Create `prism/domain/cost.py`
2. Implement `CostCalculator.calculate(prompt_tokens, completion_tokens, model_pricing) → float`
3. Formula: `(prompt_tokens × input_price + completion_tokens × output_price) / 1,000,000`
4. Cost always comes from provider's `usage` object, never from client claims
5. **Pure function** — no database, no network, no side effects

**File to create:** `prism/domain/cost.py`

**Acceptance criteria:**
- [ ] Math matches expected values for known inputs
- [ ] Returns 0.0 for 0 tokens
- [ ] Handles all models in the pricing table

---

#### Task 6.2: Implement Usage Repository (Atomic SQL)
**Time:** 30 min  
**Depends on:** Task 3.5

**What to do:**
1. Add `UsageRepository` implementation to `prism/adapters/sqlite_repos.py`
2. Methods:
   - `record_usage(key_hash, month, cost, tokens, is_cache_hit)` — atomic increment
   - `get_usage(key_hash, month) → UsageRecord`
   - `get_all_usage(month) → list[UsageRecord]`
3. **Critical:** Use `UPDATE usage SET spend = spend + ?` (atomic SQL), never read-add-write
4. Monthly reset: usage row keyed by month string (`2026-10`), new month = new row

**File to modify:** `prism/adapters/sqlite_repos.py`

**Acceptance criteria:**
- [ ] `record_usage` uses atomic SQL increment
- [ ] New month automatically creates a new row
- [ ] Concurrent updates don't lose data (SQLite serializes writes)

---

#### Task 6.3: Build Budget Check Stage
**Time:** 25 min  
**Depends on:** Tasks 6.1, 6.2

**What to do:**
1. Create `prism/services/stages/budget.py`
2. Read current month's usage for this key
3. If `total_spend >= budget_limit` → raise `BudgetExceededError` (429)
4. Add to decision trace: `"budget ok ($X/$Y)"` or `"budget exceeded"`

**File to create:** `prism/services/stages/budget.py`  
**Files to modify:** `prism/services/pipeline.py`

**Pipeline order update:** auth → validate → rate limit → **budget** → provider call

**Acceptance criteria:**
- [ ] Under-budget requests pass
- [ ] Over-budget requests get 429 with `budget_exceeded` type
- [ ] Cost is $0 for cache hits (when cache is implemented)

---

#### Task 6.4: Build Allowlist Check Stage
**Time:** 20 min  
**Depends on:** Task 4.2

**What to do:**
1. Create `prism/services/stages/allowlist.py`
2. Check if the requested model (or alias) is in the key's `model_allowlist`
3. If not allowed → raise `ModelNotAllowedError` (403)
4. Once model resolution exists: check the **resolved** model too (prevents `auto` bypass)

**File to create:** `prism/services/stages/allowlist.py`  
**Files to modify:** `prism/services/pipeline.py`

**Pipeline order update:** auth → validate → rate limit → **allowlist** → budget → provider call

**Acceptance criteria:**
- [ ] Model in allowlist → pass
- [ ] Model not in allowlist → 403
- [ ] Wildcard `["*"]` allowlist allows everything

---

#### Task 6.5: Wire Metering into the Response Path
**Time:** 20 min  
**Depends on:** Tasks 6.1, 6.2

**What to do:**
1. After provider responds, calculate cost using `CostCalculator`
2. Record usage via `UsageRepository.record_usage()`
3. Set `x-prism-cost-usd` header to the actual cost value
4. Update decision trace: `"cost: $0.000123"`

**Files to modify:** `prism/api/routes.py` or `prism/services/pipeline.py`

**Acceptance criteria:**
- [ ] `x-prism-cost-usd` shows the real calculated cost
- [ ] Usage is recorded in the database after every successful request
- [ ] Cost is computed from provider's reported tokens, not request body

---

#### Task 6.6: Write Tests for Cost, Budget & Allowlist
**Time:** 30 min  
**Depends on:** Tasks 6.1–6.5

**What to do:**
1. `tests/unit/test_cost.py` — test cost calculation with known inputs, edge cases (0 tokens, large numbers)
2. `tests/unit/test_budget.py` — test budget stage with under/over budget scenarios
3. `tests/unit/test_allowlist.py` — test allowlist with allowed, disallowed, wildcard
4. `tests/unit/test_usage_repo.py` — test atomic updates, monthly reset

**Files to create:**
```
tests/unit/test_cost.py
tests/unit/test_budget.py
tests/unit/test_allowlist.py
tests/unit/test_usage_repo.py
```

**Verify:**
```bash
pytest tests/ -v --tb=short
```

---

### 📋 Day 6 Checklist

- [ ] CostCalculator is pure math, fully tested
- [ ] Usage repository uses atomic SQL increments
- [ ] Budget stage rejects over-budget requests (429)
- [ ] Allowlist stage rejects disallowed models (403)
- [ ] `x-prism-cost-usd` header shows real cost
- [ ] Monthly usage resets automatically
- [ ] All tests pass
- [ ] **Can demo:** Exhaust a key's budget → subsequent requests get 429

---

### 🏁 Phase 2 Gate

**Before moving to Phase 3, verify ALL of the following:**
- [ ] Auth: bad key → 401, good key → 200
- [ ] Rate limit: 11th request within 1 minute → 429
- [ ] Budget: requests after budget exhaustion → 429
- [ ] Allowlist: disallowed model → 403
- [ ] Cost is calculated and header is set correctly
- [ ] Concurrency test: no over-admission
- [ ] `pytest tests/ -v` — all green

---

## Phase 3: Streaming & Resilience (Days 7–9)

> **Goal:** Add SSE streaming, retry/failover logic, timeout management, and request logging. The gateway becomes production-quality resilient.

---

### Day 7 — SSE Streaming Pass-Through (2.5 hours)

**Theme:** Make `"stream": true` work — tokens flow from provider → gateway → client in real-time, never buffered.

---

#### Task 7.1: Implement Streaming in Provider Adapter
**Time:** 40 min  
**Depends on:** Task 2.2

**What to do:**
1. Add `stream(request)` method to `OpenAICompatibleAdapter`
2. Use `httpx` streaming response to yield SSE chunks
3. Parse each chunk: extract `data:` lines, handle `data: [DONE]`
4. Look for the `usage` object in the final chunk (for metering)
5. Return an async generator of chunks

**Files to modify:** `prism/adapters/openai_compatible.py`

**SSE chunk format from provider:**
```
data: {"id":"chatcmpl-abc","choices":[{"delta":{"content":"Hel"}}]}

data: {"id":"chatcmpl-abc","choices":[{"delta":{"content":"lo"}}]}

data: {"id":"chatcmpl-abc","choices":[{"delta":{}}],"usage":{"prompt_tokens":10,"completion_tokens":5}}

data: [DONE]
```

**Acceptance criteria:**
- [ ] Chunks yielded as they arrive (never buffered)
- [ ] `usage` object extracted from final data chunk
- [ ] `[DONE]` signal detected and handled
- [ ] Connection errors during streaming raise `UpstreamError`

---

#### Task 7.2: Build Streaming Proxy (Tee Pattern)
**Time:** 40 min  
**Depends on:** Task 7.1

**What to do:**
1. Create `prism/services/streaming.py`
2. Implement the "tee pattern": chunks flow through to client while Prism peeks at each one
3. Forward each chunk immediately (never collect then send)
4. Extract usage from final chunk for metering
5. Use `try/finally` to ALWAYS record usage, even on errors or client disconnect

**File to create:** `prism/services/streaming.py`

**The `finally` safety net:**
```python
async def stream_response(provider_stream, context):
    try:
        async for chunk in provider_stream:
            yield format_sse_chunk(chunk)  # forward immediately
            if chunk.has_usage:
                context.usage = chunk.usage
    finally:
        # ALWAYS runs: normal end, client disconnect, provider crash
        record_usage(context)
        write_log(context)
```

**Acceptance criteria:**
- [ ] Chunks are forwarded immediately (no buffering)
- [ ] Usage is extracted from the final chunk
- [ ] `finally` block always executes
- [ ] Client disconnect doesn't prevent usage recording

---

#### Task 7.3: Wire Streaming into the HTTP Route
**Time:** 30 min  
**Depends on:** Task 7.2

**What to do:**
1. Modify `POST /v1/chat/completions` to check for `"stream": true`
2. If streaming: return `StreamingResponse` with `text/event-stream` content type
3. Set response headers BEFORE streaming starts (they go in HTTP headers, before body)
4. `x-prism-cache: miss` (hardcoded for now)
5. `x-prism-provider` must be decided before first chunk

**Files to modify:** `prism/api/routes.py`

**Acceptance criteria:**
- [ ] `"stream": true` → SSE streaming response
- [ ] `"stream": false` → normal JSON response (existing behavior unchanged)
- [ ] All `x-prism-*` headers present on streaming responses
- [ ] Content-Type is `text/event-stream` for streaming
- [ ] Stream ends with `data: [DONE]\n\n`

**Verify:**
```bash
curl -N http://localhost:3000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "x-api-key: prism-sk-search-1a2b3c" \
  -d '{"model": "alpha-small", "messages": [{"role": "user", "content": "Count to 5"}], "stream": true}'
# Should see chunks arriving one by one
```

---

#### Task 7.4: Add FakeAdapter Streaming Support
**Time:** 15 min  
**Depends on:** Task 7.1

**What to do:**
1. Update `FakeAdapter` to support `stream()` method
2. Yield canned chunks with configurable delay
3. Include a usage object in the final chunk

**Files to modify:** `tests/helpers/fake_adapter.py`

**Acceptance criteria:**
- [ ] FakeAdapter produces realistic SSE chunks
- [ ] Tests can verify streaming behavior without real providers

---

#### Task 7.5: Write Streaming Tests
**Time:** 25 min  
**Depends on:** Tasks 7.3, 7.4

**What to do:**
1. Create `tests/integration/test_streaming.py`
2. Test: streaming response arrives in chunks (not all at once)
3. Test: usage is recorded after stream ends
4. Test: `[DONE]` is the final event
5. Test: non-streaming still works (regression)

**File to create:** `tests/integration/test_streaming.py`

**Verify:**
```bash
pytest tests/integration/test_streaming.py -v
```

---

### 📋 Day 7 Checklist

- [ ] Provider adapter supports streaming
- [ ] Tee pattern forwards chunks without buffering
- [ ] `finally` block always records usage
- [ ] `"stream": true` returns SSE response
- [ ] `"stream": false` still works (regression)
- [ ] All headers present on streaming responses
- [ ] FakeAdapter supports streaming for tests
- [ ] All tests pass
- [ ] **Can demo:** `curl -N` shows tokens arriving one by one

---

### Day 8 — Retry, Failover & Timeouts (2.5 hours)

**Theme:** Wrap provider calls with retry, exponential backoff, failover to backup providers, and configurable timeouts.

---

#### Task 8.1: Implement the Resilient Executor
**Time:** 60 min  
**Depends on:** Tasks 2.2, 1.3

**What to do:**
1. Create `prism/services/executor.py`
2. Implement the three error categories:
   - **Retryable** (500, timeout, connection reset) → retry same provider with exponential backoff + jitter
   - **Failover-worthy** (429 from provider, provider down) → try next provider in chain
   - **Fatal** (400) → stop immediately
3. Accept an ordered list of provider adapters (primary + fallbacks)
4. Configurable: `max_retries`, `base_delay`, `connect_timeout`, `request_timeout`
5. Track: `retries` count, `fallback_used` flag
6. On all providers exhausted → raise `UpstreamError`

**File to create:** `prism/services/executor.py`

**Retry with backoff:**
```
Attempt 1: wait 0s
Attempt 2: wait 1s + random(0, 0.5s)
Attempt 3: wait 2s + random(0, 1s)
→ Give up, try next provider
```

**Acceptance criteria:**
- [ ] Retries on 500 with exponential backoff
- [ ] Fails over to next provider on connection errors
- [ ] Stops on 400 errors (no retry)
- [ ] Respects connect and request timeouts
- [ ] Reports retry count and fallback flag
- [ ] `UpstreamError` when all providers fail

---

#### Task 8.2: Integrate Executor with Pipeline
**Time:** 25 min  
**Depends on:** Tasks 8.1, 4.4

**What to do:**
1. Replace direct provider call in pipeline with executor
2. Pass ordered provider list based on resolved model's fallback chain
3. Set `x-prism-fallback: true` header when fallback was used
4. Set `x-prism-provider` to the provider that actually responded
5. Record retry count and fallback flag in decision trace

**Files to modify:** `prism/services/pipeline.py`, `prism/api/routes.py`, `prism/main.py`

**Acceptance criteria:**
- [ ] Primary provider called first
- [ ] On failure, fallback provider called
- [ ] `x-prism-fallback` header accurate
- [ ] `x-prism-provider` shows the actual responder

---

#### Task 8.3: Add Stream Idle Timeout
**Time:** 15 min  
**Depends on:** Task 7.2

**What to do:**
1. In streaming proxy, add an idle timeout: if no new chunk arrives for N seconds, abort
2. Default: 10 seconds (configurable via `PRISM_STREAM_IDLE_TIMEOUT`)
3. On idle timeout: send SSE error event, close stream, log as `upstream_error`

**Files to modify:** `prism/services/streaming.py`

**Acceptance criteria:**
- [ ] Stream aborts if provider stops sending chunks
- [ ] Error event sent to client
- [ ] Usage still recorded in `finally`

---

#### Task 8.4: Write Resilience Tests
**Time:** 30 min  
**Depends on:** Tasks 8.1, 8.2

**What to do:**
1. Create `tests/unit/test_executor.py`:
   - Provider returns 500 once → retry succeeds
   - Provider returns 500 3x → failover to backup
   - Provider returns 400 → immediate stop (no retry)
   - All providers fail → `UpstreamError`
   - Timeout → failover
2. Create `tests/integration/test_failover.py`:
   - FakeAdapter primary fails → FakeAdapter backup succeeds
   - Both fail → 502 response

**Files to create:**
```
tests/unit/test_executor.py
tests/integration/test_failover.py
```

**Verify:**
```bash
pytest tests/unit/test_executor.py tests/integration/test_failover.py -v
```

---

### 📋 Day 8 Checklist

- [ ] Resilient executor retries on transient errors
- [ ] Failover works: primary down → backup serves
- [ ] Fatal errors (400) stop immediately
- [ ] Timeouts fire on slow providers
- [ ] Stream idle timeout aborts dead streams
- [ ] `x-prism-fallback` and `x-prism-provider` headers accurate
- [ ] All tests pass
- [ ] **Can demo:** Kill alpha mock → requests still succeed via beta

---

### Day 9 — Request Log Table & Error Handling Polish (2.5 hours)

**Theme:** Complete the request log, handle mid-stream errors, and polish all failure paths.

---

#### Task 9.1: Implement Log Repository
**Time:** 30 min  
**Depends on:** Task 3.5

**What to do:**
1. Implement `LogRepository` in `prism/adapters/sqlite_repos.py`
2. Methods:
   - `save_log(log_entry)` — insert one row into `request_logs`
   - `get_logs(limit, offset, key_hash=None) → list[LogEntry]`
   - `get_log(request_id) → LogEntry | None`
3. Log entry includes ALL request metadata (see schema in architecture.md)
4. Log EVERY request, including rejected ones (auth failures, rate limit, etc.)

**Files to modify:** `prism/adapters/sqlite_repos.py`

**Acceptance criteria:**
- [ ] Every request creates a log entry (success and failure)
- [ ] Log entries have all fields: request_id, key_hash, model, provider, status, tokens, cost, cache_result, fallback, retries, latency_ms, decision_trace
- [ ] Logs are queryable by key_hash

---

#### Task 9.2: Wire Logging into Pipeline (Success + Failure)
**Time:** 30 min  
**Depends on:** Task 9.1

**What to do:**
1. After every request (success or failure), save to log repository
2. Capture start time → end time → compute latency_ms
3. On pipeline errors: still log with the error status code
4. Include the full decision trace in the log entry
5. **Never log:** raw virtual keys, provider keys, or full prompts

**Files to modify:** `prism/api/routes.py`, `prism/services/pipeline.py`

**Acceptance criteria:**
- [ ] Successful requests logged with full details
- [ ] Failed requests (401, 403, 429, 502) also logged
- [ ] Latency is measured end-to-end
- [ ] Decision trace saved with each log entry

---

#### Task 9.3: Handle Mid-Stream Failures Gracefully
**Time:** 25 min  
**Depends on:** Tasks 7.2, 8.1

**What to do:**
1. If provider dies mid-stream (after first byte sent to client):
   - Send an SSE error event: `data: {"error": {"message": "Provider disconnected", "type": "upstream_error"}}`
   - Terminate the stream
   - Log as `upstream_error` with partial usage
2. If client disconnects mid-stream:
   - Stop reading from provider
   - Record whatever usage was observed
3. Implement in `prism/services/streaming.py`

**Files to modify:** `prism/services/streaming.py`

**Decision (ADR-002):** No mid-stream provider switching — splicing two outputs produces incoherent answers.

**Acceptance criteria:**
- [ ] Provider crash mid-stream → client receives error event
- [ ] Client disconnect → usage still recorded
- [ ] No franken-answers from splicing providers

---

#### Task 9.4: Polish Error Response Format
**Time:** 15 min  
**Depends on:** Task 2.4

**What to do:**
1. Ensure ALL error responses follow the OpenAI error format consistently
2. Include `x-prism-request-id` on error responses too
3. Internal errors (uncaught exceptions) → 500 with generic message (detail in server logs only)
4. Never expose stack traces or internal details to clients

**Files to modify:** `prism/api/error_handler.py`

**Error format:**
```json
{
    "error": {
        "message": "Monthly budget of $5.00 has been exceeded",
        "type": "budget_exceeded",
        "code": 429
    }
}
```

**Acceptance criteria:**
- [ ] All error responses have consistent JSON structure
- [ ] `request_id` header on errors
- [ ] No stack traces in client responses
- [ ] Uncaught exceptions produce generic 500

---

#### Task 9.5: Write End-to-End Tests for All Error Paths
**Time:** 30 min  
**Depends on:** Tasks 9.1–9.4

**What to do:**
1. Create `tests/integration/test_error_paths.py`
2. Test every error code:
   - 400: bad request body
   - 401: missing/invalid key
   - 403: disallowed model
   - 404: unknown model (after resolver is added)
   - 429: rate limit + budget exceeded
   - 502: all providers fail
3. Verify error JSON format, headers, and log entries

**File to create:** `tests/integration/test_error_paths.py`

**Verify:**
```bash
pytest tests/ -v --tb=short
```

---

### 📋 Day 9 Checklist

- [ ] Request log table captures every request (success + failure)
- [ ] Latency tracked and logged
- [ ] Mid-stream provider failure sends SSE error event
- [ ] Client disconnect doesn't prevent usage recording
- [ ] All error responses follow OpenAI format
- [ ] No secrets or stack traces in client responses
- [ ] All tests pass
- [ ] **Can demo:** Check `request_logs` table → every request is there

---

### 🏁 Phase 3 Gate

**Before moving to Phase 4, verify ALL of the following:**
- [ ] Streaming: `curl -N` with `"stream": true` shows real-time tokens
- [ ] Retry: provider 500 → gateway retries and succeeds
- [ ] Failover: kill primary → requests served by backup
- [ ] Timeouts: slow provider → gateway doesn't hang forever
- [ ] Logs: every request in `request_logs` table
- [ ] All errors produce correct JSON format
- [ ] `pytest tests/ -v` — all green

---

## Phase 4: Intelligence (Days 10–12)

> **Goal:** Add model alias resolution, the `auto` smart router, and the semantic cache. These are the AI-first features that make Prism intelligent.

---

### Day 10 — Model Resolver & Smart Router (2.5 hours)

**Theme:** Resolve aliases (`fast`, `smart`, `auto`) to real models, and build the difficulty classifier.

---

#### Task 10.1: Implement Alias Resolver
**Time:** 25 min  
**Depends on:** Task 1.5

**What to do:**
1. Create resolution logic in `prism/services/stages/resolve.py`
2. `resolve(alias) → (primary_model, fallback_chain)`
3. Lookup from gateway config: `fast → alpha-small`, `smart → alpha-large`
4. Direct model names pass through unchanged
5. Unknown alias/model → raise `ModelNotFoundError` (404)

**File to create:** `prism/services/stages/resolve.py`

**Acceptance criteria:**
- [ ] `"fast"` → resolves to primary + fallback chain
- [ ] `"smart"` → resolves to primary + fallback chain
- [ ] `"alpha-small"` → passes through as-is
- [ ] `"nonexistent"` → 404

---

#### Task 10.2: Build Difficulty Classifier (Heuristic V1)
**Time:** 45 min  
**Depends on:** Task 1.4

**What to do:**
1. Create `prism/services/router.py`
2. Define `DifficultyClassifier` interface (Strategy pattern)
3. Implement `HeuristicClassifier`:
   - Analyze the prompt for difficulty signals
   - Hard signals: "prove", "derive", "why", "explain the logic", "debug", "deadlock", code blocks, math notation, multi-step reasoning words
   - Easy signals: "list", "extract", "what is the name", "look up", "translate", "summarize"
   - Score: proportion of hard vs easy signals
   - Output: `{tier: "fast"|"smart", score: 0.0-1.0, reason: "proof request; judged complex"}`
4. Write 30–50 labeled training examples (NOT from `routing_eval.jsonl`!)

**Files to create:**
```
prism/services/router.py
data/training_examples.jsonl
```

**Training examples format:**
```jsonl
{"prompt": "What is the capital of France?", "expected_tier": "fast"}
{"prompt": "Prove that the square root of 2 is irrational", "expected_tier": "smart"}
```

**Critical rule:** The `routing_eval.jsonl` file is the **exam**. Never look at its answers during development.

**Acceptance criteria:**
- [ ] Classifier returns tier, score, and reason
- [ ] Short but hard prompts classified as `smart`
- [ ] Long but easy prompts classified as `fast`
- [ ] 30+ hand-written training examples

---

#### Task 10.3: Wire `auto` into the Pipeline
**Time:** 25 min  
**Depends on:** Tasks 10.1, 10.2

**What to do:**
1. Update `resolve` stage: when `model: "auto"`, run classifier first
2. Classifier decides `fast` or `smart` → then resolve that alias
3. **Critical:** check allowlist on BOTH `auto` AND the resolved tier
4. Log the routing decision: tier, score, reason
5. Update decision trace: `"auto→smart (score 0.82, proof request)"`

**Files to modify:** `prism/services/stages/resolve.py`, `prism/services/stages/allowlist.py`

**Pipeline order (updated):**
```
auth → validate → rate limit → resolve (with auto) → allowlist → budget → provider call
```

**Acceptance criteria:**
- [ ] `"model": "auto"` routes to correct tier
- [ ] Allowlist checked on resolved model, not just `auto`
- [ ] Routing decision logged with score and reason

---

#### Task 10.4: Write Router Tests
**Time:** 25 min  
**Depends on:** Tasks 10.2, 10.3

**What to do:**
1. Create `tests/unit/test_router.py`
2. Test classifier with known examples:
   - "What is 2+2?" → `fast`
   - "Prove P != NP" → `smart`
   - Long but trivial → `fast`
   - Short but hard → `smart`
3. Create `tests/unit/test_resolve.py` — alias resolution, unknown model, auto routing

**Files to create:**
```
tests/unit/test_router.py
tests/unit/test_resolve.py
```

**Verify:**
```bash
pytest tests/unit/test_router.py tests/unit/test_resolve.py -v
```

---

### 📋 Day 10 Checklist

- [ ] Alias resolver maps `fast`, `smart` to real models
- [ ] Difficulty classifier scores prompts with reasons
- [ ] `auto` routing picks correct tier based on prompt content
- [ ] Allowlist checks resolved model (no `auto` bypass)
- [ ] Routing decisions logged with score and reason
- [ ] 30+ training examples written
- [ ] All tests pass
- [ ] **Can demo:** `curl` with `"model": "auto"` → see routing decision in logs

---

### Day 11 — Semantic Cache (2.5 hours)

**Theme:** Build the semantic cache — matching by meaning, not exact strings, with strict tenant isolation.

---

#### Task 11.1: Implement Bag-of-Words Embedder
**Time:** 30 min  
**Depends on:** Task 1.4

**What to do:**
1. Create `prism/adapters/bow_embedder.py`
2. Implement `Embedder` interface:
   - Tokenize text (split on whitespace, lowercase)
   - Remove stop words ("the", "a", "is", "how", "do", "I", "what", "to", ...)
   - Build a term-frequency vector
   - Return as a list of floats (sparse vector)
3. Implement cosine similarity function
4. Pure, offline, no downloads needed

**File to create:** `prism/adapters/bow_embedder.py`

**Acceptance criteria:**
- [ ] "Reset my password" and "How do I change my password?" → high similarity
- [ ] "Reset my password" and "What is quantum computing?" → low similarity
- [ ] Stop words removed
- [ ] Cosine similarity returns 0.0–1.0

---

#### Task 11.2: Implement Cache Decision Logic (Domain)
**Time:** 20 min  
**Depends on:** Task 11.1

**What to do:**
1. Create `prism/domain/cache_decision.py`
2. Pure functions:
   - `is_cacheable(request_context) → bool` — cache enabled? not time-sensitive? not an error?
   - `is_hit(similarity_score, threshold) → bool`
3. Time-sensitive keywords: "now", "today", "latest", "current", "right now", "this moment"

**File to create:** `prism/domain/cache_decision.py`

**Acceptance criteria:**
- [ ] Cache disabled key → not cacheable
- [ ] "What's the weather now?" → not cacheable
- [ ] Similarity above threshold → hit
- [ ] Similarity below threshold → miss

---

#### Task 11.3: Implement Cache Repository
**Time:** 30 min  
**Depends on:** Task 3.5

**What to do:**
1. Add `CacheRepository` to `prism/adapters/sqlite_repos.py`
2. Methods:
   - `store(key_hash, alias, embedding, response_body)`
   - `search(key_hash, alias, embedding, threshold) → CacheEntry | None`
   - `get_stats(key_hash=None) → CacheStats`
3. **Critical:** `search()` query includes `WHERE key_hash = ?` — tenant scoping is structural
4. Store embeddings as JSON arrays (never pickle/eval)
5. Cosine similarity computed in Python after fetching candidates

**Files to modify:** `prism/adapters/sqlite_repos.py`

**Acceptance criteria:**
- [ ] Cache entries scoped by key_hash in the query itself
- [ ] Team A's entries invisible to Team B
- [ ] Embeddings stored as JSON
- [ ] Hit count incremented on cache hits

---

#### Task 11.4: Build Cache Service & Pipeline Stage
**Time:** 25 min  
**Depends on:** Tasks 11.1, 11.2, 11.3

**What to do:**
1. Create `prism/services/cache_service.py` — orchestrates embedder + cache repo + cache decision
2. Create `prism/services/stages/cache.py` — pipeline stage
3. Before provider call: check cache → if hit, return cached response, skip provider
4. After successful provider call: store in cache
5. Set `x-prism-cache: hit` or `x-prism-cache: miss`
6. On cache hit: cost is $0, still record usage

**Files to create:**
```
prism/services/cache_service.py
prism/services/stages/cache.py
```

**Pipeline order (final):**
```
auth → validate → rate limit → resolve → allowlist → budget → CACHE → provider call → meter → log
```

**Cache hit on streaming request:** Replay the cached answer as one chunk followed by `[DONE]`

**Acceptance criteria:**
- [ ] Same prompt twice → second is a cache hit
- [ ] Paraphrased prompt → cache hit (above threshold)
- [ ] Different team's prompt → cache miss (tenant isolation)
- [ ] `x-prism-cache` header set correctly

---

#### Task 11.5: Write Cache Tests
**Time:** 25 min  
**Depends on:** Tasks 11.1–11.4

**What to do:**
1. Create `tests/unit/test_embedder.py` — similarity scores for known pairs
2. Create `tests/unit/test_cache_decision.py` — cacheable check, hit/miss, time-sensitive
3. Create `tests/integration/test_cache.py`:
   - Same prompt → hit
   - Paraphrased → hit
   - Different topic → miss
   - Different key → miss (tenant isolation!)
   - "What's the weather now?" → skip cache

**Files to create:**
```
tests/unit/test_embedder.py
tests/unit/test_cache_decision.py
tests/integration/test_cache.py
```

**Verify:**
```bash
pytest tests/unit/test_embedder.py tests/unit/test_cache_decision.py tests/integration/test_cache.py -v
```

---

### 📋 Day 11 Checklist

- [ ] BoW embedder computes similarity for text pairs
- [ ] Cache decision logic handles time-sensitive prompts
- [ ] Cache repository is structurally scoped per tenant
- [ ] Cache pipeline stage works for both streaming and non-streaming
- [ ] Paraphrased prompts produce cache hits
- [ ] Cross-tenant cache leakage is impossible
- [ ] `x-prism-cache` header accurate
- [ ] All tests pass
- [ ] **Can demo:** Send same question twice → second returns instantly with `x-prism-cache: hit`

---

### Day 12 — Classifier Refinement & Eval (2.5 hours)

**Theme:** Refine the difficulty classifier to beat the length-only baseline, tune cache thresholds, and run the eval.

---

#### Task 12.1: Build the Length-Only Baseline Classifier
**Time:** 15 min  
**Depends on:** Task 10.2

**What to do:**
1. Create a `LengthOnlyClassifier` that routes solely based on prompt length
2. Threshold: >200 chars → `smart`, else → `fast`
3. This is the bar your heuristic classifier must beat

**Files to modify:** `prism/services/router.py`

**Acceptance criteria:**
- [ ] Baseline runs against training examples → record accuracy
- [ ] Use this as the minimum bar

---

#### Task 12.2: Refine the Heuristic Classifier
**Time:** 45 min  
**Depends on:** Tasks 10.2, 12.1

**What to do:**
1. Run current heuristic against your training examples → measure accuracy
2. Analyze misclassifications
3. Add more signals:
   - Presence of code blocks (triple backticks)
   - Question complexity indicators ("compare", "contrast", "analyze")
   - Mathematical notation
   - Multi-part questions ("first... then... finally...")
4. Iterate until accuracy > baseline on training set
5. Optionally implement a scoring system with weighted signals

**Files to modify:** `prism/services/router.py`, `data/training_examples.jsonl`

**Acceptance criteria:**
- [ ] Heuristic accuracy > length-only baseline on training examples
- [ ] Short but hard cases handled correctly
- [ ] Long but easy cases handled correctly

---

#### Task 12.3: Run the Routing Eval
**Time:** 20 min  
**Depends on:** Task 12.2

**What to do:**
1. Run classifier against `routing_eval.jsonl` (the exam)
2. Record accuracy per case
3. Compare to baseline
4. Save results to `docs/routing_eval_results.md`

**Files to create:** `docs/routing_eval_results.md`

**Acceptance criteria:**
- [ ] Eval runs with one command
- [ ] Results show accuracy percentage
- [ ] Heuristic beats baseline

**Verify:**
```bash
python scripts/routing_eval.py
```

---

#### Task 12.4: Tune Cache Threshold
**Time:** 20 min  
**Depends on:** Task 11.4

**What to do:**
1. Create test pairs:
   - **Should match:** "Reset my password" / "How do I change my password?"
   - **Should NOT match:** "Reset my password" / "Enable 2FA on my account"
2. Try thresholds: 0.80, 0.85, 0.90
3. Find the sweet spot where paraphrases hit and near-misses don't
4. Document the chosen threshold and reasoning

**Acceptance criteria:**
- [ ] Paraphrase pairs → hit at chosen threshold
- [ ] Near-miss pairs → miss at chosen threshold
- [ ] Threshold documented with examples

---

#### Task 12.5: Full Integration Smoke Test
**Time:** 30 min  
**Depends on:** Everything in Phases 1–4

**What to do:**
1. Start the full stack (gateway + mock providers)
2. Run through ALL features with curl:
   - Auth (valid/invalid key)
   - Rate limiting (exceed RPM)
   - Budget (exhaust and reject)
   - Model resolution (fast, smart, auto)
   - Streaming
   - Cache hit on paraphrase
   - Failover (stop alpha mock)
3. Check logs, database, headers

**Acceptance criteria:**
- [ ] All features work end-to-end
- [ ] No regressions from earlier phases

**Verify:**
```bash
# Run the provided smoke test
python scripts/smoke_test.py
```

---

### 📋 Day 12 Checklist

- [ ] Length-only baseline established
- [ ] Heuristic classifier beats baseline
- [ ] Routing eval results documented
- [ ] Cache threshold tuned with evidence
- [ ] Full integration smoke test passes
- [ ] All unit, integration, and concurrency tests pass
- [ ] **Can demo:** `model: "auto"` routes correctly, cache hits on paraphrases

---

### 🏁 Phase 4 Gate

**Before moving to Phase 5, verify ALL of the following:**
- [ ] `auto` routes to correct tier (verified by eval)
- [ ] Classifier beats length-only baseline
- [ ] Cache hits on paraphrased prompts
- [ ] No cross-tenant cache leakage
- [ ] All pipeline stages execute in correct order
- [ ] `pytest tests/ -v` — all green
- [ ] `python scripts/smoke_test.py` — passes

---

## Phase 5: Docker, Console & Docs (Days 13–15)

> **Goal:** Dockerize the solution, build the ops console, write comprehensive documentation, and run all verification scripts.

---

### Day 13 — Docker Setup (2.5 hours)

**Theme:** Containerize everything — one command to start the entire stack.

---

#### Task 13.1: Create `.env.example`
**Time:** 10 min  
**Depends on:** Task 1.5

**What to do:**
1. Create `.env.example` with all configurable environment variables
2. Include comments explaining each variable
3. Group by category: Server, Database, Providers, Admin, Timeouts, Retry, Cache, Security

**File to create:** `.env.example`

**Content:** (see architecture.md Section 15 for full template)

**Acceptance criteria:**
- [ ] Every env var used in the code is documented
- [ ] Sensible defaults provided
- [ ] Comments explain each variable

---

#### Task 13.2: Create `.dockerignore`
**Time:** 5 min  
**Depends on:** Nothing

**What to do:**
1. Create `.dockerignore` to exclude unnecessary files from Docker context

**File to create:** `.dockerignore`

**Content:**
```
.git
__pycache__
*.pyc
.env
*.db
.pytest_cache
tests/
docs/
*.pdf
.venv
node_modules
```

**Acceptance criteria:**
- [ ] Docker context is minimal
- [ ] Secrets (`.env`) are excluded
- [ ] Test files excluded from production image

---

#### Task 13.3: Create the Dockerfile
**Time:** 30 min  
**Depends on:** All application code

**What to do:**
1. Create `Dockerfile` — multi-stage build
2. **Stage 1 (builder):** Install dependencies for layer caching
3. **Stage 2 (production):** Copy app + deps, create non-root user, set up health check
4. Use `python:3.12-slim` base image
5. Expose port 3000
6. Health check against `/health` endpoint

**File to create:** `Dockerfile`

**Content:** (see architecture.md Section 15 for full template)

**Acceptance criteria:**
- [ ] Multi-stage build (small final image)
- [ ] Non-root user (`prism`)
- [ ] Health check configured
- [ ] Layer caching: changing code doesn't re-install dependencies

**Verify:**
```bash
docker build -t prism-gateway .
docker images prism-gateway  # Check size
```

---

#### Task 13.4: Create `docker-compose.yml`
**Time:** 30 min  
**Depends on:** Task 13.3

**What to do:**
1. Create `docker-compose.yml` with 3 services:
   - `alpha-mock` — mock provider on port 9001
   - `beta-mock` — mock provider on port 9002
   - `prism-gateway` — the gateway on port 3000
2. Gateway depends on both mocks (health check condition)
3. Named volume for SQLite persistence
4. Seed data mounted read-only
5. Custom bridge network for inter-container communication
6. Environment variables for provider URLs (use container names)

**File to create:** `docker-compose.yml`

**Content:** (see architecture.md Section 15 for full template)

**Acceptance criteria:**
- [ ] `docker-compose up --build -d` starts all 3 services
- [ ] Gateway can reach mocks via container names
- [ ] SQLite data persists across restarts
- [ ] Health checks pass for all services

**Verify:**
```bash
docker-compose up --build -d
docker-compose ps  # All services healthy
curl http://localhost:3000/health
```

---

#### Task 13.5: Test Docker Compose Stack
**Time:** 30 min  
**Depends on:** Task 13.4

**What to do:**
1. Build and start the full stack
2. Run basic verification:
   - Health check
   - Non-streaming request
   - Streaming request
   - Auth failure
3. Test failover: `docker-compose stop alpha-mock` → requests still work
4. Test persistence: `docker-compose down && docker-compose up` → data persists

**Verify:**
```bash
# Start stack
docker-compose up --build -d

# Test health
curl http://localhost:3000/health

# Test request
curl http://localhost:3000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "x-api-key: prism-sk-search-1a2b3c" \
  -d '{"model": "fast", "messages": [{"role": "user", "content": "Hello"}]}'

# Test failover
docker-compose stop alpha-mock
curl http://localhost:3000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "x-api-key: prism-sk-search-1a2b3c" \
  -d '{"model": "fast", "messages": [{"role": "user", "content": "Hello"}]}'
# Should succeed with x-prism-fallback: true

docker-compose start alpha-mock
```

---

#### Task 13.6: Create Mock Provider Script (if not provided)
**Time:** 25 min  
**Depends on:** Task 13.4

**What to do:**
1. If mock providers aren't already in `scripts/`, create `scripts/mock_provider.py`
2. Simple HTTP server that responds to OpenAI chat completions format
3. Supports both streaming and non-streaming
4. Accepts `--port` and `--name` command line args
5. Has a `/health` endpoint

**File to create (if needed):** `scripts/mock_provider.py`

**Acceptance criteria:**
- [ ] Responds to `/v1/chat/completions` with OpenAI-compatible format
- [ ] Supports `stream: true` with SSE
- [ ] Returns realistic `usage` object
- [ ] `GET /health` returns 200

---

### 📋 Day 13 Checklist

- [ ] `.env.example` documents all environment variables
- [ ] `.dockerignore` excludes unnecessary files
- [ ] Dockerfile builds successfully (multi-stage, non-root)
- [ ] `docker-compose up --build` starts all 3 services
- [ ] Gateway reaches mock providers via Docker network
- [ ] Failover works within Docker
- [ ] Data persists across container restarts
- [ ] **Can demo:** `docker-compose up --build -d && curl localhost:3000/health`

---

### Day 14 — Admin API & Ops Console (2.5 hours)

**Theme:** Build the admin endpoints and a simple HTML ops console.

---

#### Task 14.1: Build Admin API Endpoints
**Time:** 45 min  
**Depends on:** Tasks 9.1, 6.2, 11.3

**What to do:**
1. Create `prism/api/admin.py`
2. Implement endpoints:
   - `GET /admin/usage` — usage summary by key and month
   - `GET /admin/logs?limit=50&key_hash=...` — recent request logs with filters
   - `GET /admin/cache/stats` — cache hit rates and entry counts
3. Protect all admin endpoints with `PRISM_ADMIN_TOKEN` (separate from virtual keys)
4. Return JSON responses

**File to create:** `prism/api/admin.py`  
**Files to modify:** `prism/main.py`

**Acceptance criteria:**
- [ ] Missing admin token → 401
- [ ] `/admin/usage` returns per-key usage data
- [ ] `/admin/logs` supports pagination and key filter
- [ ] `/admin/cache/stats` shows hit count and entry count

**Verify:**
```bash
curl http://localhost:3000/admin/usage \
  -H "Authorization: Bearer admin-secret-change-me"

curl "http://localhost:3000/admin/logs?limit=10" \
  -H "Authorization: Bearer admin-secret-change-me"
```

---

#### Task 14.2: Build the Ops Console (Static HTML)
**Time:** 45 min  
**Depends on:** Task 14.1

**What to do:**
1. Create `console/index.html` — single HTML file with embedded JavaScript and CSS
2. **No React, no build step** — just vanilla HTML/JS
3. Features:
   - Usage table by key (spend, tokens, requests, cache hits)
   - Recent requests table (last 20)
   - Cache hit rate display
   - Auto-refresh button
4. Calls the admin API endpoints via `fetch()`
5. Include admin token input field

**File to create:** `console/index.html`

**Acceptance criteria:**
- [ ] Opens in a browser, loads data from admin API
- [ ] Shows usage by key in a table
- [ ] Shows recent requests
- [ ] Shows cache hit rate
- [ ] Works without any build step or npm install

---

#### Task 14.3: Serve the Console from the Gateway
**Time:** 10 min  
**Depends on:** Task 14.2

**What to do:**
1. Mount the console HTML as a static file route: `GET /console` or `GET /console/index.html`
2. No auth required for the static file (admin token entered in the UI)

**Files to modify:** `prism/main.py`

**Acceptance criteria:**
- [ ] `http://localhost:3000/console` loads the ops page

---

#### Task 14.4: Write Architecture Decision Records (ADRs)
**Time:** 30 min  
**Depends on:** All implementation experience

**What to do:**
1. Create `docs/adr/` directory
2. Write 8 ADR files (one per decision from architecture.md Section 17):
   - `ADR-001-cache-hits-and-limits.md`
   - `ADR-002-mid-stream-failure.md`
   - `ADR-003-budget-overshoot.md`
   - `ADR-004-cache-scope-and-keying.md`
   - `ADR-005-time-sensitive-content.md`
   - `ADR-006-prompt-storage-in-logs.md`
   - `ADR-007-auto-and-allowlist.md`
   - `ADR-008-router-training-data.md`

**ADR format:**
```markdown
# ADR-001: Cache Hits and Rate Limits / Budgets

## Context
[What is the question?]

## Decision
[What did we decide?]

## Consequences
[What follows from this decision?]
```

**Files to create:** 8 files in `docs/adr/`

**Acceptance criteria:**
- [ ] All 8 ADRs written with context, decision, and consequences
- [ ] Decisions are consistent with the implementation

---

### 📋 Day 14 Checklist

- [ ] Admin API endpoints return correct data
- [ ] Admin endpoints protected by admin token
- [ ] Ops console loads in browser
- [ ] Console shows usage, requests, cache stats
- [ ] Console served from `/console`
- [ ] All 8 ADRs written
- [ ] **Can demo:** Open `/console` in browser → see live data

---

### Day 15 — README, Verification & Polish (2.5 hours)

**Theme:** Write the comprehensive README, run all verification scripts, and polish everything.

---

#### Task 15.1: Write Comprehensive README.md
**Time:** 60 min  
**Depends on:** All implementation

**What to do:**
1. Create `README.md` at the project root
2. Sections to include:
   - **Overview** — what Prism is, one-paragraph summary
   - **Features** — bulleted list of capabilities
   - **Quick Start** — Docker Compose (3 commands to get running)
   - **Manual Setup** — without Docker (virtualenv, pip install, start providers, start gateway)
   - **API Documentation** — request/response examples for all endpoints
   - **Configuration** — all environment variables explained
   - **Architecture** — link to `docs/architecture.md`, brief layer description
   - **Design Decisions** — link to ADRs, summary of key decisions
   - **Routing Logic** — how `auto` works, classifier approach
   - **Cache Scoping** — how tenant isolation works
   - **Failover Behavior** — retry/failover strategy
   - **Testing** — how to run tests
   - **Docker** — build, run, stop, failover simulation
   - **Ops Console** — how to access and use
   - **Known Limitations** — what's missing, what could be improved
   - **Verification** — how to run smoke test, load test, routing eval
   - **Project Structure** — folder layout with descriptions

**File to create:** `README.md`

**Acceptance criteria:**
- [ ] A new developer can get the project running by following the README
- [ ] All API endpoints documented with curl examples
- [ ] All env vars documented
- [ ] Architecture explained at high level
- [ ] Design decisions summarized (with links to ADRs)
- [ ] Known limitations listed honestly

---

#### Task 15.2: Run Smoke Test
**Time:** 15 min  
**Depends on:** Task 15.1

**What to do:**
1. Start the full stack (Docker or local)
2. Run `python scripts/smoke_test.py`
3. Fix any failures
4. Save output to `docs/verification/smoke_test_output.txt`

**File to create:** `docs/verification/smoke_test_output.txt`

**Acceptance criteria:**
- [ ] All smoke test assertions pass
- [ ] Output saved

**Verify:**
```bash
python scripts/smoke_test.py > docs/verification/smoke_test_output.txt 2>&1
```

---

#### Task 15.3: Run Load Test & Document Results
**Time:** 15 min  
**Depends on:** Task 15.2

**What to do:**
1. Run `python scripts/load_test.py`
2. Record results:
   - Over-admission count (should be 0)
   - Accounting accuracy (usage totals match)
   - Latency summary (p50, p95, p99)
3. Save to `docs/verification/load_test_report.md`

**File to create:** `docs/verification/load_test_report.md`

**Acceptance criteria:**
- [ ] Zero over-admission
- [ ] Usage accounting accurate
- [ ] Latency metrics documented

---

#### Task 15.4: Run Routing Eval & Document Results
**Time:** 10 min  
**Depends on:** Task 12.3

**What to do:**
1. Run the routing eval one final time
2. Ensure results beat baseline
3. Save to `docs/verification/routing_eval_results.md` (if not already done)

**Verify:**
```bash
python scripts/routing_eval.py
```

---

#### Task 15.5: Final Polish & Code Cleanup
**Time:** 20 min  
**Depends on:** Everything

**What to do:**
1. Run all tests one final time: `pytest tests/ -v`
2. Remove any TODO comments that were completed
3. Ensure no secrets in committed files
4. Check that `.env.example` has all variables but no real secrets
5. Verify `.gitignore` excludes: `.env`, `*.db`, `__pycache__`, `.venv`
6. Run a final `curl` walkthrough of all features

**File to create/verify:** `.gitignore`

**Acceptance criteria:**
- [ ] All tests pass
- [ ] No secrets in code
- [ ] `.gitignore` is comprehensive
- [ ] Code is clean and well-commented

---

#### Task 15.6: Final Verification Walkthrough
**Time:** 30 min  
**Depends on:** Everything

**What to do — demonstrate each feature with `curl`:**

```bash
# 1. Start stack
docker-compose up --build -d

# 2. Health check
curl http://localhost:3000/health

# 3. Non-streaming request
curl http://localhost:3000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "x-api-key: prism-sk-search-1a2b3c" \
  -d '{"model": "fast", "messages": [{"role": "user", "content": "Hello"}]}'

# 4. Streaming request
curl -N http://localhost:3000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "x-api-key: prism-sk-search-1a2b3c" \
  -d '{"model": "fast", "messages": [{"role": "user", "content": "Count to 5"}], "stream": true}'

# 5. Smart routing (auto)
curl http://localhost:3000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "x-api-key: prism-sk-search-1a2b3c" \
  -d '{"model": "auto", "messages": [{"role": "user", "content": "Prove that sqrt(2) is irrational"}]}'

# 6. Cache hit (repeat same question)
curl http://localhost:3000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "x-api-key: prism-sk-search-1a2b3c" \
  -d '{"model": "fast", "messages": [{"role": "user", "content": "Hello"}]}'
# Check x-prism-cache: hit

# 7. Auth failure
curl http://localhost:3000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "x-api-key: invalid-key" \
  -d '{"model": "fast", "messages": [{"role": "user", "content": "Hello"}]}'
# → 401

# 8. Rate limiting (send many rapid requests)
for i in $(seq 1 15); do
  curl -s -o /dev/null -w "%{http_code}\n" http://localhost:3000/v1/chat/completions \
    -H "Content-Type: application/json" \
    -H "x-api-key: prism-sk-search-1a2b3c" \
    -d '{"model": "fast", "messages": [{"role": "user", "content": "Hi"}]}'
done
# Eventually → 429

# 9. Failover (stop alpha)
docker-compose stop alpha-mock
curl -i http://localhost:3000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "x-api-key: prism-sk-search-1a2b3c" \
  -d '{"model": "fast", "messages": [{"role": "user", "content": "Hello"}]}'
# Check x-prism-fallback: true
docker-compose start alpha-mock

# 10. Ops console
# Open http://localhost:3000/console in browser

# 11. Admin API
curl http://localhost:3000/admin/usage \
  -H "Authorization: Bearer admin-secret-change-me"
```

**Acceptance criteria:**
- [ ] All 11 steps work as described
- [ ] Every feature is demonstrable

---

### 📋 Day 15 Checklist

- [ ] Comprehensive README.md written
- [ ] Smoke test passes → output saved
- [ ] Load test passes → report saved (zero over-admission)
- [ ] Routing eval → results saved (beats baseline)
- [ ] No secrets in committed code
- [ ] `.gitignore` comprehensive
- [ ] All tests pass
- [ ] Final walkthrough all 11 demo steps
- [ ] **DONE:** Project is complete and demo-ready 🎉

---

### 🏁 Phase 5 Gate (FINAL)

**The project is complete when ALL of the following are true:**
- [ ] `docker-compose up --build -d` → full stack running
- [ ] `python scripts/smoke_test.py` → passes
- [ ] `python scripts/load_test.py` → zero over-admission
- [ ] `python scripts/routing_eval.py` → beats baseline
- [ ] `pytest tests/ -v` → all green
- [ ] README enables a new developer to run the project
- [ ] Ops console shows live data
- [ ] All 8 ADRs written
- [ ] All custom headers present on every response
- [ ] Failover works when a provider is killed

---

## Summary: All Tasks at a Glance

| Day | Tasks | Total Tasks | Key Deliverable |
|-----|-------|-------------|-----------------|
| **1** | 1.1–1.6 | 6 | Project scaffolding, models, errors, config |
| **2** | 2.1–2.6 | 6 | Provider adapter, HTTP server, pass-through |
| **3** | 3.1–3.6 | 6 | Request ID, headers, logging, database |
| **4** | 4.1–4.5 | 5 | Authentication, validation, pipeline |
| **5** | 5.1–5.5 | 5 | Rate limiter (token bucket), concurrency test |
| **6** | 6.1–6.6 | 6 | Cost calculator, budget, allowlist, metering |
| **7** | 7.1–7.5 | 5 | SSE streaming pass-through |
| **8** | 8.1–8.4 | 4 | Retry, failover, timeouts |
| **9** | 9.1–9.5 | 5 | Request logging, error polish |
| **10** | 10.1–10.4 | 4 | Model resolver, `auto` router, classifier |
| **11** | 11.1–11.5 | 5 | Semantic cache (BoW, tenant isolation) |
| **12** | 12.1–12.5 | 5 | Classifier refinement, eval, integration test |
| **13** | 13.1–13.6 | 6 | Docker (Dockerfile, compose, mock providers) |
| **14** | 14.1–14.4 | 4 | Admin API, ops console, ADRs |
| **15** | 15.1–15.6 | 6 | README, verification, polish, demo |
| **Total** | | **78 tasks** | **Complete Prism LLM Gateway** |

---

## Risk Mitigation Strategy

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Streaming harder than expected | Medium | High | Start non-streaming first (Day 2); streaming is incremental (Day 7) |
| Classifier accuracy is low | Medium | Medium | Heuristic is fast to iterate; add signals one by one |
| Docker issues on Windows | Medium | Low | App works locally without Docker; Docker is Day 13 |
| SQLite concurrency under load | Low | Medium | Use busy timeout; single-writer is fine for single instance |
| Time overrun on any phase | Medium | High | Each phase has a clear gate; skip polish before features |
| Mock providers missing | Low | High | Build mock provider script on Day 13 if needed |

---

## Emergency Prioritization

**If running out of time, complete in this priority order:**

1. ✅ **Must have:** Non-streaming pass-through + auth + rate limit + budget + cost (Days 1–6)
2. ✅ **Must have:** Streaming + failover (Days 7–8)
3. ✅ **Must have:** Cache + auto routing (Days 10–11)
4. ⚠️ **Should have:** Docker + README (Days 13, 15)
5. ⚠️ **Should have:** Request logging + admin console (Days 9, 14)
6. 💡 **Nice to have:** Classifier refinement, ops console polish (Days 12, 14)

---

> **Remember:** Build in thin vertical slices. Always have something that runs end-to-end. The worst outcome is 80% of features at 100% quality. The best outcome is 100% of features at 100% quality. Never build 100% of features at 50% quality.
