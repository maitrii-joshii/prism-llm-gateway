# Prism LLM Gateway — Complete Project Architecture & Codebase Documentation

> **Role:** Senior Python Backend Engineer, Software Architect, Technical Mentor, and Hiring Manager  
> **Audience:** Absolute beginner in Python and FastAPI with basic programming knowledge  
> **Objective:** Teach the entire Prism LLM Gateway project from scratch, explain every architectural decision and line of code, audit requirements against actual behavior, and prepare you to confidently defend the system in a Backend Engineer interview.  
> **Source of Truth:** Expected requirements from `docs/architecture.md`, `docs/implementation-plan.md`, and Architectural Decision Records (ADRs). Actual behavior verified against the production code in `prism/`, configuration in `config/`, and automated test suites in `tests/`.

---

## Master Table of Contents

1. [Project Overview & Requirements](#1-project-overview--requirements)
   - 1.1 [What is Prism LLM Gateway?](#11-what-is-prism-llm-gateway)
   - 1.2 [What Problem Does It Solve?](#12-what-problem-does-it-solve)
   - 1.3 [Why is an LLM Gateway Required?](#13-why-is-an-llm-gateway-required)
   - 1.4 [Real-World Production Use Cases](#14-real-world-production-use-cases)
   - 1.5 [Functional Requirements (What the System Does)](#15-functional-requirements-what-the-system-does)
   - 1.6 [Non-Functional Requirements (How the System Behaves)](#16-non-functional-requirements-how-the-system-behaves)
2. [Learn Python from Scratch (Project-Relevant)](#2-learn-python-from-scratch-project-relevant)
   - 2.1 [Variables, Types, and Type Hints](#21-variables-types-and-type-hints)
   - 2.2 [Core Data Structures: Lists, Dictionaries, Tuples, Sets](#22-core-data-structures-lists-dictionaries-tuples-sets)
   - 2.3 [Functions, Signatures, and Pure Logic](#23-functions-signatures-and-pure-logic)
   - 2.4 [Classes, Objects, and `self`](#24-classes-objects-and-self)
   - 2.5 [The Four Pillars of OOP in Prism](#25-the-four-pillars-of-oop-in-prism)
   - 2.6 [Class Attributes vs Instance Attributes](#26-class-attributes-vs-instance-attributes)
   - 2.7 [Decorators Explained](#27-decorators-explained)
   - 2.8 [Exception Handling and Chaining (`raise ... from exc`)](#28-exception-handling-and-chaining-raise--from-exc)
   - 2.9 [Context Managers (`with` and `async with`)](#29-context-managers-with-and-async-with)
   - 2.10 [Dataclasses vs Pydantic Models](#210-dataclasses-vs-pydantic-models)
   - 2.11 [Async/Await, Coroutines, and Generators](#211-asyncawait-coroutines-and-generators)
   - 2.12 [Closures and Higher-Order Functions](#212-closures-and-higher-order-functions)
   - 2.13 [Modules, Packages, and Imports](#213-modules-packages-and-imports)
   - 2.14 [Virtual Environments and Dependency Management](#214-virtual-environments-and-dependency-management)
3. [Learn FastAPI from Scratch](#3-learn-fastapi-from-scratch)
   - 3.1 [What is FastAPI and Why Do We Use It?](#31-what-is-fastapi-and-why-do-we-use-it)
   - 3.2 [How FastAPI Works Internally (ASGI & Starlette)](#32-how-fastapi-works-internally-asgi--starlette)
   - 3.3 [HTTP Fundamentals: Methods, Headers, Status Codes](#33-http-fundamentals-methods-headers-status-codes)
   - 3.4 [FastAPI Application Instance and Uvicorn](#34-fastapi-application-instance-and-uvicorn)
   - 3.5 [Routers and Modular API Design](#35-routers-and-modular-api-design)
   - 3.6 [Request Parameters, Payloads, and Validation](#36-request-parameters-payloads-and-validation)
   - 3.7 [Responses, Serialization, and SSE Streaming](#37-responses-serialization-and-sse-streaming)
   - 3.8 [Middleware and Request Tracking](#38-middleware-and-request-tracking)
   - 3.9 [Centralized Exception Handlers](#39-centralized-exception-handlers)
   - 3.10 [Dependency Management: `app.state` vs FastAPI `Depends`](#310-dependency-management-appstate-vs-fastapi-depends)
   - 3.11 [Lifespan Events: Application Startup and Shutdown](#311-lifespan-events-application-startup-and-shutdown)
   - 3.12 [Async Endpoints and Concurrency Realities](#312-async-endpoints-and-concurrency-realities)
4. [Complete Project Folder Structure](#4-complete-project-folder-structure)
5. [Architecture Diagrams & File Connections](#5-architecture-diagrams--file-connections)
6. [Complete Request Lifecycle](#6-complete-request-lifecycle)
7. [Architecture Decisions — WHY?](#7-architecture-decisions--why)
8. [Explain the Actual Code](#8-explain-the-actual-code)
9. [Requirement vs Implementation Audit](#9-requirement-vs-implementation-audit)
10. [Testing & Code Quality](#10-testing--code-quality)
11. [How to Run and Debug the Project](#11-how-to-run-and-debug-the-project)
12. [Interview Preparation](#12-interview-preparation)
13. [Learning Roadmap](#13-learning-roadmap)

---

# 1. Project Overview & Requirements

## 1.1 What is Prism LLM Gateway?

**Prism LLM Gateway** is a high-performance, reverse-proxy web service designed to sit between internal client applications (tenants) and upstream Large Language Model (LLM) providers (such as OpenAI and Groq). 

In modern software organizations, applications do not call LLM providers directly. Instead, they send standard OpenAI-compatible HTTP requests to Prism. Prism intercepts every request, validates credentials, enforces rate limits and financial budgets, dynamically routes prompts to optimal models, retries on transient network errors, fails over to backup providers during outages, serves semantically identical answers from a local cache at zero cost, streams token responses with minimal latency, and records comprehensive audit logs and cost metrics.

### The Real-World Hotel Reception Desk Analogy
To build an intuitive mental model, compare Prism to a five-star hotel reception desk:

| Hotel Reception Desk | Prism LLM Gateway System | Real-World Technical Function |
|---|---|---|
| **Guest Room Card** | **Virtual API Key** | Clients authenticate with a revocable key (`prism-sk-...`). Upstream master keys remain hidden. |
| **Kitchen Order Limit** | **Rate Limiter (RPM)** | Limits how many requests a client can submit per minute using a thread-safe token bucket algorithm. |
| **Room Charge Tab** | **Monthly Budget Enforcement** | Tracks cumulative USD spend per tenant each calendar month. Blocks calls if the budget limit is reached. |
| **Head Chef Routing** | **Model & Alias Resolution** | Translates logical requests (`fast`, `smart`, `auto`) into concrete model deployments (`gpt-4o-mini`, `llama-3.3-70b-versatile`). |
| **Backup Kitchen** | **Resilient Executor (Failover)** | If Kitchen A experiences an electrical outage or backlog (500, 429), the order is instantly rerouted to Kitchen B. |
| **Pre-prepared Dish** | **Semantic Cache** | If a guest orders the exact same dish or an equivalent inquiry, it is served immediately from local storage at $0 cost. |
| **Front Desk Ledger** | **SQLite Audit Logging & Metering** | Every single interaction, token count, latency measurement, and execution step is recorded in an immutable ledger. |

---

## 1.2 What Problem Does It Solve?

When multiple engineering teams in an enterprise adopt LLMs independently, chaos quickly emerges:

1. **API Key Sprawl & Security Vulnerabilities:**  
   Every engineering team requires access to production OpenAI or Groq credentials. Keys get committed to GitHub, leaked in client-side bundles, or shared across Slack channels. Revoking a compromised key breaks all applications simultaneously.
2. **Runaway, Uncontrolled Financial Spend:**  
   Without centralized controls, an accidental infinite loop in a script can run up thousands of dollars in LLM API bills overnight. Organizations lack tenant-level billing attribution.
3. **Fragility & Provider Downtime:**  
   If OpenAI suffers an outage or returns HTTP 429 (Rate Limit Exceeded), every dependent application crashes. Individual engineering teams rarely build robust exponential backoff or multi-provider failover logic.
4. **Redundant Financial Cost:**  
   Multiple users frequently ask identical or semantically equivalent questions (e.g., customer support FAQs, document summaries). Paying upstream providers repeatedly for identical tokens is wasteful.
5. **Architectural Vendor Lock-In:**  
   Hardcoding provider-specific SDKs across 30 microservices makes migrating from OpenAI to Groq, Anthropic, or an open-weight self-hosted model a multi-month engineering effort.

Prism resolves every single one of these problems by establishing a centralized control plane.

---

## 1.3 Why is an LLM Gateway Required?

An LLM Gateway provides six non-negotiable architectural benefits:

- **Centralized Secret Management:** Master API keys exist exclusively in Prism's environment (`.env`). Tenants only possess revocable virtual keys.
- **Granular Financial Governance:** Administrators allocate hard monthly budgets (e.g., $50.00/month for Search Team, $200.00/month for Customer Support).
- **High Availability & Fault Tolerance:** Transparent failover guarantees that an upstream outage at one vendor automatically falls back to an alternate model or provider without user interruption.
- **Cost Reduction via Semantic Caching:** Local Bag-of-Words embeddings and cosine similarity checks return cached responses in under 5 milliseconds at zero API cost.
- **Drop-in Compatibility:** Exposing standard OpenAI endpoints (`/v1/chat/completions`, `/v1/models`) ensures that existing code using the official `openai` Python or TypeScript SDKs works simply by changing `base_url="http://gateway:3000/v1"`.
- **Complete Auditability:** Every request receives a unique `request_id`, generates a detailed `decision_trace`, and records prompt/completion token consumption in SQLite.

---

## 1.4 Real-World Production Use Cases

- **Internal AI Platform for Multi-Tenant Enterprises:** Platform teams provide AI capabilities to 50 product squads, isolating quotas, budgets, and allowed models.
- **B2B SaaS Metered AI Features:** A SaaS platform provides AI copywriting to its end customers. Each customer receives a virtual key with strict rate limits and usage metering tied to their subscription tier.
- **Cost-Optimized Model Routing:** Directing simple conversational queries to inexpensive models (`fast` -> `gpt-4o-mini` at $0.15/1M tokens) while routing complex reasoning or coding tasks to capable models (`smart` -> `llama-3.3-70b-versatile` or `gpt-4o`).
- **Resilient Multi-Cloud LLM Infrastructure:** Automatically routing traffic between OpenAI, Azure OpenAI, Groq, and AWS Bedrock to survive regional outages.

---

## 1.5 Functional Requirements (What the System Does)

| ID | Requirement | Plain Language Explanation | Technical Meaning & Implementation Details |
|---|---|---|---|
| **F1** | **OpenAI-Compatible API** | Any client that speaks to OpenAI can speak to Prism without changing code. | Implements `POST /v1/chat/completions` and `GET /v1/models` matching OpenAI's JSON request/response schema. |
| **F2** | **Multi-Provider Support** | Prism can dispatch requests to different AI cloud vendors. | Concrete adapters for OpenAI and Groq implemented over HTTP using `httpx.AsyncClient`. |
| **F3** | **Virtual API Key Management** | Tenants use lightweight proxy keys instead of vendor master keys. | Tenants receive keys prefixed with `prism-sk-`. The gateway stores and checks only SHA-256 hashes (`key_hash`). |
| **F4** | **Virtual Key Authentication** | Incoming requests are authenticated before any work begins. | The `x-api-key` header is hashed with SHA-256 and matched against SQLite via constant-time `hmac.compare_digest`. |
| **F5** | **Rate Limiting (RPM)** | Tenants cannot spam the gateway beyond their allocated quota. | In-memory token bucket algorithm enforces Requests Per Minute (RPM) per `key_hash` using thread locks. Returns HTTP 429 on exhaustion. |
| **F6** | **Model & Alias Resolution** | Clients can request friendly names like `fast` or `smart`. | Logical alias mapping resolves `fast` to primary (`gpt-4o-mini`) and fallback chains. Direct model names pass through. |
| **F7** | **Automatic Difficulty Routing** | Sending `model: "auto"` chooses the cheapest adequate model. | A rule-based `HeuristicClassifier` inspects linguistic markers, math symbols, and code blocks to pick `fast` or `smart`. |
| **F8** | **Model Access Control (Allowlist)** | Tenants can only call models their administrator explicitly permitted. | Validates that requested aliases, classified tiers, and resolved candidate models exist in the key's `model_allowlist` or match `*`. |
| **F9** | **Monthly Budget Enforcement** | Tenants cannot spend more money than allocated for the calendar month. | Compares current month-to-date spend against `budget_usd` in SQLite. Returns HTTP 429 if the budget is depleted. |
| **F10** | **Semantic Response Caching** | Paraphrased questions reuse previously generated responses. | Computes 256-dimension Bag-of-Words embeddings, evaluates cosine similarity in SQLite, and returns cached completions above a threshold. |
| **F11** | **Resilient Retries & Failover** | Network hiccups and provider errors do not cause request failures. | `ResilientExecutor` retries transient errors (timeouts, 5xx) with exponential backoff and fails over to backup models on 429 or connect failures. |
| **F12** | **SSE Streaming Pass-Through** | Real-time token streaming works seamlessly for chat applications. | Handles `stream: true` using Server-Sent Events (`text/event-stream`), immediately forwarding chunks via an async generator. |
| **F13** | **Usage Metering & Cost Tracking** | Accurate tracking of input/output tokens and real USD expenditures. | `CostCalculator` computes cost down to 6 decimal places based on configured prices per million tokens; atomically records usage in SQLite. |
| **F14** | **Contract Response Headers** | Transparent metadata injected into every response. | Adds `x-prism-request-id`, `x-prism-provider`, `x-prism-cache`, `x-prism-fallback`, and `x-prism-cost-usd` headers. |
| **F15** | **Administrative Inspection APIs** | Operations teams can inspect logs, usage, and cache metrics. | Endpoints `/admin/usage`, `/admin/logs`, and `/admin/cache/stats` secured by a dedicated bearer token (`PRISM_ADMIN_TOKEN`). |
| **F16** | **Operations Dashboard Console** | Browser UI for monitoring gateway activity. | Static HTML/CSS/JavaScript dashboard served at `/console` reading administrative endpoints. |
| **F17** | **Dynamic Configuration Loading** | System configuration loaded safely at boot time. | Validates `gateway_config.json`, `seed_keys.json`, and `model_pricing.json` using Pydantic; fails fast if invalid. |

---

## 1.6 Non-Functional Requirements (How the System Behaves)

| ID | Requirement | Technical Definition & Enforcement in Codebase |
|---|---|---|
| **N1** | **Security & Privacy by Default** | Virtual keys hashed with SHA-256; comparisons use timing-safe digests (`hmac.compare_digest`, `secrets.compare_digest`). Master vendor keys never leave server memory. Internal upstream error traces are masked from clients. Request logs omit raw prompts by default (ADR-006). Docker container runs as non-root user `prism`. |
| **N2** | **Concurrency & Thread Safety** | The in-memory rate limiter uses `threading.Lock()` to prevent race conditions during token acquisition. Database operations use SQLite Write-Ahead Logging (`PRAGMA journal_mode=WAL`) and atomic upserts (`INSERT ... ON CONFLICT DO UPDATE`) to eliminate lost updates. |
| **N3** | **Fail-Fast Bootstrapping** | Application refuses to start if essential configuration files are missing, malformed, or internally inconsistent (e.g., alias pointing to unpriced model, missing master API keys). Raises `ConfigLoadError` or `RuntimeError` during startup. |
| **N4** | **Testability & Inversion of Control** | Domain logic is decoupled from external infrastructure via abstract base classes (Ports). Automated test suite runs 287+ tests without making external network calls or requiring live API credentials using `FakeAdapter` and `FakeClock`. |
| **N5** | **Structured Observability** | Centralized JSON logging attaches the unique `request_id` to every log line via Python's `contextvars.ContextVar`. Every request records a sequential `decision_trace` tracking every pipeline transition. |
| **N6** | **Resilience & Fault Isolation** | Network calls protected by strict connect and read timeouts (`asyncio.timeout`). Exponential backoff with randomized jitter prevents thundering herd problems during upstream recovery. |
| **N7** | **Bounded Resource Consumption** | Request body size and token limits are strictly capped (`max_tokens_cap=4096`). In-memory cache enforces an eviction policy discarding oldest records beyond `MAX_CACHE_ENTRIES = 1000`. |
| **N8** | **Containerization & Portability** | Fully packaged with a two-stage `Dockerfile` and `docker-compose.yml` including automated health checks. |

---

# 2. Learn Python from Scratch (Project-Relevant)

This section teaches you the core Python language features used throughout the Prism codebase. Every concept is accompanied by actual production code taken directly from the project.

---

## 2.1 Variables, Types, and Type Hints

Python is dynamically typed, meaning variables can change types at runtime. However, in enterprise backend systems, dynamic typing can lead to silent runtime crashes. Prism uses **Type Hints** (introduced in Python 3.5+ and refined in 3.10+) to declare what data types functions expect and return.

### Python Code Example from `prism/domain/security.py`:
```python
import hashlib

def hash_api_key(raw_key: str) -> str:
    """Hash a raw virtual API key using SHA-256 for secure database storage."""
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
```

### Explaining the Syntax:
- `raw_key: str`: The parameter `raw_key` is expected to be a `str` (string).
- `-> str`: The function promises to return a `str`.
- `hashlib.sha256(...)`: Calls the standard library SHA-256 hashing algorithm.
- `.encode("utf-8")`: Converts the Python text string into raw bytes (necessary because hashing algorithms operate on bytes, not characters).
- `.hexdigest()`: Returns the resulting 256-bit hash as a 64-character hexadecimal string.

### Modern Type Hint Syntax in Prism:
| Type Hint Syntax | Meaning | Project Example |
|---|---|---|
| `str \| None` | Can be a string OR `None` (optional value). | `model_resolved: str \| None = None` (`RequestContext`) |
| `list[str]` | A list containing only strings. | `model_candidates: list[str]` (`RequestContext`) |
| `dict[str, Any]` | A dictionary with string keys and any value type. | `request_payload: dict[str, Any]` (`RequestContext`) |
| `tuple[str, ...]` | An immutable sequence of strings. | `TIME_SENSITIVE_KEYWORDS: tuple[str, ...]` (`cache_decision.py`) |

> [!NOTE]
> Python's standard runtime does **not** enforce type hints at execution time. If you pass an integer to `hash_api_key(123)`, Python won't prevent it until `.encode()` raises an `AttributeError`. To achieve runtime enforcement, Prism relies on **Pydantic** (explained in Section 2.10).

---

## 2.2 Core Data Structures: Lists, Dictionaries, Tuples, Sets

Python provides four primary built-in data structures. Prism selects each one deliberately based on performance characteristics:

### 1. Lists (`list`) — Ordered, Mutable Sequences
Used when order matters and items can be added, removed, or changed.
```python
# From prism/domain/models.py
context.decision_trace.append("auth ok")
context.decision_trace.append("request validation ok")
```
- In `RequestContext`, `decision_trace` is a `list[str]`. Each stage calls `.append()` to add execution milestones in chronological order.

### 2. Dictionaries (`dict`) — Key-Value Hash Maps
Used for fast $O(1)$ lookups by a unique key.
```python
# From prism/domain/limiter.py
self.buckets: dict[str, TokenBucket] = {}
```
- In `TokenBucketRateLimiter`, the `buckets` dictionary maps a tenant's `key_hash` string directly to their active `TokenBucket` object.

### 3. Tuples (`tuple`) — Ordered, Immutable Sequences
Used for fixed collections that must never be altered at runtime.
```python
# From prism/domain/cache_decision.py
TIME_SENSITIVE_KEYWORDS = (
    "now",
    "today",
    "latest",
    "current",
    "right now",
    "this moment",
)
```
- Defined as a tuple using parentheses `(...)`. Being immutable, no code can accidentally modify this list of protected keywords.

### 4. Sets (`set`) — Unordered Collections of Unique Elements
Used when duplicates must be eliminated and membership tests (`item in container`) must run in $O(1)$ time.
```python
# From prism/config/loader.py
valid_identifiers = (
    set(pricing.keys())
    | set(gateway_config.aliases.keys())
    | {"*"}
)
```
- Uses set union (`|`) to combine all pricing model names, configured alias names, and the wildcard string `"*"` into a single unique set for instantaneous validation.

---

## 2.3 Functions, Signatures, and Pure Logic

In backend architecture, **Pure Functions** are functions where the output depends solely on the input parameters, with zero side effects (no reading/writing to databases, no network calls, no modifying global variables). Pure functions are mathematically predictable and trivial to unit test.

### Pure Function Example from `prism/domain/cost.py`:
```python
class CostCalculator:
    @staticmethod
    def calculate(
        prompt_tokens: int,
        completion_tokens: int,
        model_pricing: ModelPricing,
    ) -> float:
        """Calculate the USD cost of a completion based on token counts."""
        if isinstance(prompt_tokens, bool) or not isinstance(prompt_tokens, int) or prompt_tokens < 0:
            raise ValueError("prompt_tokens must be a non-negative integer")

        if isinstance(completion_tokens, bool) or not isinstance(completion_tokens, int) or completion_tokens < 0:
            raise ValueError("completion_tokens must be a non-negative integer")

        input_cost = prompt_tokens * model_pricing.input_price_per_million
        output_cost = completion_tokens * model_pricing.output_price_per_million

        return (input_cost + output_cost) / 1_000_000.0
```

### Key Python Concepts Here:
- `@staticmethod`: A decorator telling Python that this method belongs to the class namespace but does not access or modify class or instance state (`self` or `cls`).
- `1_000_000.0`: Python allows underscores in numbers as digit separators for human readability. It behaves identically to `1000000.0`.
- The `isinstance(..., bool)` check: In Python, `bool` is actually a subclass of `int` (`isinstance(True, int)` evaluates to `True`). Because `True * 5` evaluates to `5`, a robust financial calculator must explicitly reject booleans!

---

## 2.4 Classes, Objects, and `self`

Object-Oriented Programming (OOP) groups data (attributes) and behavior (methods) together into reusable blueprints called **Classes**. An **Object** is a concrete instance of a class.

### Class Example from `prism/domain/limiter.py`:
```python
import threading
from prism.ports.clock import Clock

class TokenBucketRateLimiter:
    def __init__(self, clock: Clock) -> None:
        """The Constructor: Runs whenever a new object is created."""
        self.clock = clock                  # Instance attribute
        self.buckets: dict[str, TokenBucket] = {}
        self.lock = threading.Lock()        # Thread lock for concurrency safety

    def try_acquire(self, key_hash: str, rpm_limit: int) -> bool:
        """An Instance Method: Performs token bucket rate limiting."""
        with self.lock:
            now = self.clock.now()
            # ... rate limiting logic ...
            return True
```

### Explaining `self` and `__init__`:
- `__init__`: The initializer method. When you write `limiter = TokenBucketRateLimiter(clock)`, Python creates the object in memory and automatically calls `__init__`.
- `self`: Represents the specific instance of the class currently being operated on. When calling `limiter.try_acquire(...)`, Python automatically translates it to `TokenBucketRateLimiter.try_acquire(limiter, ...)`.

---

## 2.5 The Four Pillars of OOP in Prism

Prism adheres strictly to Object-Oriented Design principles:

### 1. Encapsulation (Hiding Internal Complexity)
Classes keep internal data structures private, exposing only clean public methods.
- In `TokenBucketRateLimiter`, the internal dictionary `self.buckets` and synchronization primitive `self.lock` are encapsulated. External callers only ever invoke `.try_acquire(key_hash, rpm_limit)`.
- Python indicates private/internal helper methods by prefixing their names with an underscore:
  ```python
  # From prism/services/executor.py
  async def _backoff(self, attempt: int) -> None: ...
  def _classify_error(self, exc: Exception) -> str: ...
  ```

### 2. Abstraction (Defining Contracts Without Implementation)
Abstraction separates *what* needs to be done from *how* it is done using Python's `abc` (Abstract Base Classes) module.
```python
# From prism/ports/provider.py
from abc import ABC, abstractmethod
from typing import Any
from collections.abc import AsyncIterator
from prism.domain.models import ProviderResponse

class ProviderAdapter(ABC):
    """Abstract Port: Declares the contract any LLM provider must fulfill."""

    @abstractmethod
    async def complete(self, request: dict[str, Any]) -> ProviderResponse:
        """Execute a non-streaming completion."""
        raise NotImplementedError

    @abstractmethod
    def stream(self, request: dict[str, Any]) -> AsyncIterator[dict[str, Any]]:
        """Execute a streaming completion yielding SSE chunks."""
        raise NotImplementedError
```
- You cannot create an instance of `ProviderAdapter` directly (`ProviderAdapter()` raises `TypeError`). It acts as a formal contract.

### 3. Inheritance (Specializing and Fulfilling Contracts)
A class inherits behavior and structure from a parent class.
```python
# From prism/adapters/openai_compatible.py
class OpenAICompatibleProvider(ProviderAdapter):
    """Concrete Adapter: Fulfills the ProviderAdapter contract for OpenAI and Groq."""

    async def complete(self, request: dict[str, Any]) -> ProviderResponse:
        # Actual HTTP network call using httpx.AsyncClient...
        ...

    async def stream(self, request: dict[str, Any]) -> AsyncIterator[dict[str, Any]]:
        # Actual SSE network streaming over HTTP...
        ...
```
- `OpenAICompatibleProvider` inherits from `ProviderAdapter`. If it failed to implement `.complete()` or `.stream()`, Python would refuse to instantiate it.

### 4. Polymorphism (Interchangeable Components)
Polymorphism allows different classes to be used through the same interface interchangeably.
- The `ResilientExecutor` class accepts a list of `ProviderAdapter` objects.
- In production, it receives instances of `OpenAICompatibleProvider` connected to OpenAI and Groq.
- In unit tests, it receives instances of `FakeAdapter` (from `tests/helpers/fake_adapter.py`).
- The executor executes `.complete()` identically on both, completely unaware of whether it is communicating with real cloud APIs or in-memory test mocks!

---

## 2.6 Class Attributes vs Instance Attributes

Understanding the difference between class attributes and instance attributes is critical:

```python
# From prism/domain/errors.py
class RateLimitError(PrismError):
    status_code = 429                       # Class attribute
    error_type = "rate_limit_exceeded"      # Class attribute

    def __init__(self, message: str = "Rate limit exceeded. Please try again later."):
        self.message = message              # Instance attribute
        super().__init__(message)
```
- **Class Attributes (`status_code`, `error_type`):** Belong to the class itself. They are shared by every instance and can be accessed without creating an object (`RateLimitError.status_code == 429`).
- **Instance Attributes (`self.message`):** Belong to a specific instance created with `RateLimitError("Custom message")`.

---

## 2.7 Decorators Explained

A **decorator** is a function that takes another function as input, extends or alters its behavior, and returns a new function without modifying the original source code. In Python, decorators are prefixed with the `@` symbol.

### Decorators Encountered in Prism:
| Decorator | Where Used | What It Does Technically |
|---|---|---|
| `@router.post("/v1/chat/completions")` | `prism/api/routes.py` | Registers the async function with FastAPI's HTTP routing table for POST requests. |
| `@abstractmethod` | `prism/ports/*.py` | Marks an interface method as required for all subclasses. |
| `@staticmethod` | `prism/domain/cost.py` | Declares a method that does not receive an automatic `self` or `cls` argument. |
| `@classmethod` | `prism/config/settings.py` | Declares a factory constructor that receives the class `cls` instead of an instance. |
| `@dataclass` | `prism/domain/limiter.py` | Auto-generates `__init__`, `__repr__`, and `__eq__` methods for pure data holders. |
| `@asynccontextmanager` | `prism/main.py` | Transforms an asynchronous generator function into an `async with` context manager. |

---

## 2.8 Exception Handling and Chaining (`raise ... from exc`)

Exceptions handle errors gracefully. When code encounters an error, it **raises** an exception. Parent callers **catch** the exception using `try...except` blocks.

### Exception Hierarchy in `prism/domain/errors.py`:
```python
class PrismError(Exception):
    """Base exception for all domain errors within Prism."""
    status_code = 500
    error_type = "internal_error"

    def __init__(self, message: str = "An unexpected internal error occurred."):
        self.message = message
        super().__init__(message)

class AuthenticationError(PrismError):
    status_code = 401
    error_type = "authentication_error"

class RateLimitError(PrismError):
    status_code = 429
    error_type = "rate_limit_exceeded"
```

### Exception Chaining with `raise ... from exc`:
When low-level library exceptions (like `httpx.ConnectError`) occur, Prism catches them and wraps them in a domain-level `UpstreamError`.
```python
# From prism/adapters/openai_compatible.py
try:
    response = await client.post(...)
    response.raise_for_status()
except httpx.TimeoutException as exc:
    raise UpstreamError(f"Provider request timed out after {self.request_timeout} seconds") from exc
```
- The `from exc` clause preserves the original exception in `__cause__`. When `ResilientExecutor._classify_error()` inspects the error, it looks at `exc.__cause__` to determine if the root failure was a connection drop or a timeout!

### The Complete `try / except / else / finally` Structure:
```python
try:
    # Code that might fail
    result = await do_work()
except SpecificError as e:
    # Runs only if SpecificError was raised
    handle_error(e)
else:
    # Runs only if NO exception was raised in the try block
    record_success(result)
finally:
    # ALWAYS runs, even if exceptions occurred, were re-raised, or returned early!
    cleanup_resources()
```
- In `prism/api/routes.py`, `format_streaming_body()` uses `finally:` to guarantee that database usage records and request logs are written even if the client abruptly closes their browser tab mid-stream.

---

## 2.9 Context Managers (`with` and `async with`)

Context managers ensure that resources (files, database connections, locks, HTTP connections) are cleanly opened and safely closed, even if errors occur.

### Synchronous Context Manager (`with`):
```python
# Thread-safe lock acquisition in prism/domain/limiter.py
with self.lock:
    # self.lock.acquire() is called automatically
    bucket.tokens -= 1.0
    # self.lock.release() is guaranteed to run when exiting this block
```

### Asynchronous Context Manager (`async with`):
```python
# Enforcing request timeouts in prism/services/executor.py
async with asyncio.timeout(self.request_timeout):
    response = await provider.complete(request)
```
- `asyncio.timeout()` monitors execution time asynchronously. If `provider.complete()` takes longer than `self.request_timeout` seconds, it cancels the coroutine and raises a `TimeoutError`.

---

## 2.10 Dataclasses vs Pydantic Models

Prism uses two different tools for structuring data: Python's built-in `@dataclass` and **Pydantic v2** (`BaseModel`).

### When Prism Uses `@dataclass`:
Used for lightweight, internal in-memory containers where performance is paramount and data is created strictly by internal trusted code:
```python
# From prism/domain/limiter.py
from dataclasses import dataclass
from datetime import datetime

@dataclass
class TokenBucket:
    tokens: float
    last_refill_at: datetime
```

### When Prism Uses Pydantic (`BaseModel`):
Used for data crossing system boundaries (JSON files, HTTP requests, database rows) that requires strict validation and type coercion:
```python
# From prism/domain/models.py
from pydantic import BaseModel, Field

class VirtualKeyConfig(BaseModel):
    key_hash: str
    tenant_id: str
    budget_usd: float = Field(ge=0)            # ge=0 means Greater than or Equal to 0
    rate_limit_rpm: int = Field(gt=0)          # gt=0 means Strictly Greater than 0
    model_allowlist: list[str]
    cache_enabled: bool
    cache_threshold: float = Field(ge=0, le=1) # Must be a float between 0.0 and 1.0
    status: str
```

### Why This Matters:
If someone configures `rate_limit_rpm = -10` in `config/seed_keys.json`, Pydantic immediately raises a `ValidationError`:
```
Input should be greater than 0 [type=greater_than, input_value=-10]
```
The gateway refuses to boot with invalid settings.

---

## 2.11 Async/Await, Coroutines, and Generators

### Synchronous vs Asynchronous Execution
In traditional **synchronous** programming, when your code makes an HTTP request to OpenAI, the operating system thread blocks and waits idle for 1.5 seconds. If you have 10 concurrent requests, you need 10 separate OS threads.

In **asynchronous** programming, Python runs an **Event Loop** on a single thread. When a coroutine hits an `await` on a network socket, it yields control back to the event loop. The event loop proceeds to process tokens for 50 other active requests while waiting for OpenAI's packet to arrive!

```
[ Thread 1 Timeline (Async) ]
Req 1: Start -> Send HTTP -> [PAUSE/YIELD] ------------------------> Receive -> Finish
Req 2:                       Start -> Send HTTP -> [PAUSE/YIELD] -> Receive -> Finish
```

### Defining and Awaiting Coroutines:
- `async def`: Defines a **coroutine function**. Calling it does *not* execute the function; it returns a coroutine object.
- `await`: Pauses execution of the current coroutine until the awaited coroutine finishes, allowing other tasks to run on the event loop in the meantime.

```python
# Defined with async def
async def authenticate_request(request: Request, context: RequestContext, key_repository: KeyRepository) -> RequestContext:
    ...

# Invoked with await
context = await authenticate_request(request, context, key_repository)
```

### Async Generators and `yield`:
Standard functions compute a result and `return` it once. A **generator** produces values one by one over time using `yield`. An **Async Generator** combines `async def` and `yield` to stream data:

```python
# From prism/adapters/openai_compatible.py
async def _read_sse_events(self, response: httpx.Response) -> AsyncIterator[dict[str, Any]]:
    async for line in response.aiter_lines():
        if line.startswith("data:"):
            data = json.loads(line[5:])
            yield data    # Produces each token chunk as soon as the network packet arrives!
```
The consumer uses `async for` to process chunks in real time:
```python
async for chunk in provider.stream(payload):
    forward_to_client(chunk)
```

---

## 2.12 Closures and Higher-Order Functions

A **Higher-Order Function** is a function that takes another function as an argument or returns a new function. A **Closure** is an inner function that remembers and retains access to variables from its parent scope even after the parent function has finished executing.

### Real Code Example from `prism/services/stages/cache.py`:
```python
def create_cache_stage(cache_service: CacheService):
    """Factory function returning an asynchronous stage closure."""
    async def cache_stage(context: RequestContext) -> RequestContext:
        # cache_stage retains access to 'cache_service' via closure!
        cache_service.get_cached_response(context)
        return context

    return cache_stage
```
### Why Prism Uses This Pattern:
Prism's execution pipeline (`Pipeline.run()`) expects all stages to match a uniform signature:
```python
Callable[[RequestContext], Awaitable[RequestContext]]
```
Stages cannot accept arbitrary extra arguments. By wrapping the stage inside a factory function (`create_cache_stage`), dependencies like `cache_service` are captured in the closure while keeping the pipeline stage signature uniform and clean.

---

## 2.13 Modules, Packages, and Imports

- **Module:** Any individual Python file (`cost.py`).
- **Package:** A directory containing an `__init__.py` file (marking it as an importable namespace).

### Import Conventions in Prism:
```python
# Absolute import from the project root package
from prism.domain.models import RequestContext, ProviderResponse
from prism.adapters.sqlite_repos import SQLiteKeyRepository
```
Every Python package in Prism (`prism/domain/`, `prism/services/`, `prism/api/`) contains an `__init__.py` file. This allows clean, absolute imports across the entire codebase.

---

## 2.14 Virtual Environments and Dependency Management

Python installations share global packages by default. If Project A requires `pydantic==1.10` and Project B requires `pydantic==2.5`, installing globally causes dependency conflicts.

A **Virtual Environment (`.venv`)** is a self-contained directory tree containing a dedicated Python binary and pip package store for a specific project.

### Managing Dependencies via `requirements.txt`:
Prism's `requirements.txt` specifies production and test dependencies:
```text
fastapi>=0.104.0
uvicorn[standard]>=0.24.0
httpx>=0.25.0
pydantic>=2.5.0
python-dotenv>=1.0.0
pytest>=7.4.0
pytest-asyncio>=0.21.0
pytest-repeat>=0.9.3
httpx2==2.16.0
```
- `>=`: Allows minor and patch updates while maintaining API compatibility.
- `uvicorn[standard]`: Installs Uvicorn along with high-performance C-based event loops (`uvloop`) and HTTP parsers (`httptools`).

---

# 3. Learn FastAPI from Scratch

This section breaks down the web framework powering Prism, explaining how HTTP requests are received, parsed, routed, processed, and returned.

---

## 3.1 What is FastAPI and Why Do We Use It?

**FastAPI** is a modern, high-performance web framework for building RESTful APIs in Python. It is built on top of two foundational open-source libraries:
1. **Starlette:** An ultra-fast, lightweight ASGI toolkit handling routing, middleware, WebSockets, and HTTP streaming.
2. **Pydantic:** Handles data validation, serialization, and automatic schema documentation.

### Why FastAPI is the Industry Standard for LLM Gateways:
- **Native Async I/O:** Built from the ground up for `asyncio`. Because an LLM gateway spends 98% of its time waiting on external network sockets from OpenAI or Groq, FastAPI handles thousands of concurrent connections with minimal memory overhead.
- **Built-in SSE Streaming:** Seamless integration with Starlette's `StreamingResponse` enables Server-Sent Events with zero buffering.
- **Automatic OpenAPI Documentation:** Generates interactive Swagger documentation at `/docs` automatically based on code type hints.

---

## 3.2 How FastAPI Works Internally (ASGI & Starlette)

To understand FastAPI, you must understand the **ASGI (Asynchronous Server Gateway Interface)** architecture:

```
[ Client Browser / SDK ]
          │  HTTP / TCP Socket
          ▼
   [ Uvicorn (ASGI Web Server) ]
          │  Parses HTTP bytes into ASGI scope dictionary
          ▼
   [ Starlette Middleware Stack ]
          │  request_id_middleware (ContextVar & Headers)
          ▼
   [ FastAPI Router ]
          │  Matches URL & Method (/v1/chat/completions, POST)
          ▼
   [ Route Handler Function ]
```

1. **Uvicorn** binds to TCP port 3000, listens for incoming TCP packets, parses the HTTP headers and body, and constructs an ASGI `scope` dictionary.
2. Uvicorn passes this scope to the FastAPI application instance.
3. The request flows through the **Middleware Stack** (where Prism injects `request_id`).
4. The router matches the URL path (`/v1/chat/completions`) and dispatches the request to the endpoint function.

---

## 3.3 HTTP Fundamentals: Methods, Headers, Status Codes

| HTTP Concept | Role in Prism | Project Example |
|---|---|---|
| **Method** | Indicates the desired action. | `POST` for completions (sends data); `GET` for models, logs, usage. |
| **Path / Endpoint** | The URI resource identifier. | `/v1/chat/completions`, `/admin/usage`, `/health`. |
| **Request Headers** | Client metadata and credentials. | `x-api-key: prism-sk-search-1a2b3c`, `Content-Type: application/json`. |
| **Response Headers** | Server metadata and contracts. | `x-prism-request-id`, `x-prism-provider`, `x-prism-cost-usd`, `x-prism-cache`. |
| **Status Code** | Communicates execution result. | `200 OK`, `400 Invalid Request`, `401 Unauthorized`, `403 Forbidden`, `404 Not Found`, `429 Throttled`, `502 Upstream Error`. |

---

## 3.4 FastAPI Application Instance and Uvicorn

In `prism/main.py`, the core application is instantiated:
```python
app = FastAPI(
    title="Prism LLM Gateway",
    lifespan=lifespan,
)
```
- `title`: Names the application in Swagger docs.
- `lifespan`: Registers startup and shutdown handlers (Section 3.11).

At the bottom of `prism/main.py`, Uvicorn starts the server:
```python
if __name__ == "__main__":
    configure_logging()
    uvicorn.run(
        "prism.main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "3000")),
        log_config=get_uvicorn_logging_config(),
        reload=True,
    )
```
- `"prism.main:app"`: Tells Uvicorn to load the `app` object from the `prism.main` module.
- `host="0.0.0.0"`: Listens on all network interfaces (required inside Docker containers).
- `reload=True`: Automatically reboots the server when source code files are modified (development mode).

---

## 3.5 Routers and Modular API Design

Instead of cluttering `main.py` with dozens of endpoints, FastAPI provides `APIRouter` to group related routes into separate files:

```python
# In prism/api/routes.py
router = APIRouter()

@router.post("/v1/chat/completions")
async def chat_completions(...): ...

# In prism/api/admin.py
router = APIRouter(prefix="/admin", tags=["Admin"])

@router.get("/usage")
async def get_admin_usage(...): ...
```
Then, `main.py` simply mounts the routers:
```python
app.include_router(router)         # Mounts client routes at root
app.include_router(admin_router)   # Mounts admin routes under /admin
```
The `prefix="/admin"` automatically prepends `/admin` to all routes in `admin.py`, producing `/admin/usage`, `/admin/logs`, and `/admin/cache/stats`.

---

## 3.6 Request Parameters, Payloads, and Validation

FastAPI inspects route function signatures to determine how parameters should be extracted:

```python
# From prism/api/routes.py
@router.post("/v1/chat/completions")
async def chat_completions(
    payload: dict[str, Any],
    request: Request,
    response: Response,
) -> Any:
```
- `payload: dict[str, Any]`: Instructs FastAPI to parse the incoming HTTP JSON body into a dictionary. If the client sends malformed JSON, FastAPI automatically returns HTTP 422 (Unprocessable Entity).
- `request: Request`: Injects the raw Starlette request object (allowing access to headers, client IP, and `request.app.state`).
- `response: Response`: Injects the outgoing response object, allowing route handlers to set custom HTTP headers.

> [!IMPORTANT]
> **Why Prism uses `dict[str, Any]` instead of a strict Pydantic Request Model:**  
> An LLM gateway must support the full OpenAI specification, including parameters that Prism does not directly inspect (e.g., `temperature`, `top_p`, `presence_penalty`, `tools`, `tool_choice`). Defining a rigid Pydantic model risks stripping or rejecting valid OpenAI parameters sent by new SDK versions. Therefore, Prism accepts a raw dictionary, validates critical gateway fields (`model`, `messages`, `stream`, `max_tokens`) manually in `validate_request()`, and passes the entire payload transparently to upstream providers.

---

## 3.7 Responses, Serialization, and SSE Streaming

FastAPI provides multiple response mechanisms:

### 1. Standard JSON Serialization:
Returning a Python dictionary from an endpoint causes FastAPI to serialize it into JSON automatically and set `Content-Type: application/json`.
```python
return format_completion_response(context.provider_response)
```

### 2. Server-Sent Events (SSE) Streaming Response:
For streaming requests (`stream: true`), returning a single JSON response is impossible because tokens arrive over several seconds. Prism returns a `StreamingResponse`:
```python
# From prism/api/routes.py
return StreamingResponse(
    streaming_body,                    # An async generator yielding SSE strings
    status_code=200,
    media_type="text/event-stream",    # Standard MIME type for Server-Sent Events
    headers=headers,
)
```
- `media_type="text/event-stream"` tells the client connection to remain open.
- The HTTP response headers include `Cache-Control: no-cache` and `X-Accel-Buffering: no` (which instructs reverse proxies like Nginx not to buffer chunks).

---

## 3.8 Middleware and Request Tracking

Middleware wraps the entire request/response lifecycle. Prism registers `request_id_middleware` in `prism/main.py`:
```python
app.middleware("http")(request_id_middleware)
```

### How `request_id_middleware` Works (`prism/api/middleware.py`):
```python
async def request_id_middleware(request: Request, call_next: RequestResponseEndpoint) -> Response:
    # 1. Generate unique request identifier
    request_id = f"req_{uuid.uuid4().hex[:12]}"
    request.state.request_id = request_id

    # 2. Store in ContextVar so all logger calls automatically include it
    token = request_id_context.set(request_id)
    start_time = time.perf_counter()

    try:
        # 3. Call next middleware or route handler
        response = await call_next(request)

        # 4. Inject request ID into outgoing response headers
        response.headers["x-prism-request-id"] = request_id
        return response
    finally:
        # 5. Reset ContextVar to prevent memory leaks across reused async tasks
        request_id_context.reset(token)
```

---

## 3.9 Centralized Exception Handlers

Instead of scattering `try...except` blocks across every endpoint, FastAPI allows registering global exception handlers.

```python
# In prism/main.py
app.add_exception_handler(PrismError, prism_error_handler)
app.add_exception_handler(Exception, unexpected_error_handler)
```

When any stage in the pipeline raises `RateLimitError`:
1. Execution halts immediately.
2. FastAPI intercepts the exception and dispatches it to `prism_error_handler` (`prism/api/error_handler.py`).
3. The handler extracts `exc.status_code` (429) and `exc.error_type` ("rate_limit_exceeded") and formats a standard OpenAI error envelope:
```json
{
  "error": {
    "message": "Rate limit exceeded. Please try again later.",
    "type": "rate_limit_exceeded",
    "code": 429
  }
}
```
4. If the error is a 429 (Rate Limit or Budget Exceeded), it automatically injects `Retry-After: 60`.

---

## 3.10 Dependency Management: `app.state` vs FastAPI `Depends`

FastAPI includes a dependency injection framework (`Depends`). However, Prism deliberately uses **`app.state`** for dependency management.

### How `app.state` Works:
During startup in `lifespan()`, singleton instances of repositories, adapters, and limiters are created once and attached to `app.state`:
```python
app.state.key_repository = key_repository
app.state.usage_repository = usage_repository
app.state.rate_limiter = rate_limiter
app.state.cache_service = cache_service
```
Route handlers access them via the `Request` object:
```python
key_repository = request.app.state.key_repository
```

### Architectural Comparison:
| Pattern | How It Works | Advantages in Prism | Trade-offs |
|---|---|---|---|
| **`app.state` (Prism)** | Objects created once at boot; attached to application container. | Simple, predictable, zero per-request allocation overhead. Single composition root in `lifespan`. | Dependencies are implicitly retrieved (`getattr`); less compile-time typing assistance. |
| **FastAPI `Depends()`** | Injected via route function parameters per request. | Highly granular; easy to override individual dependencies in lightweight test fixtures. | Extra parameter boilerplate on every endpoint; can re-evaluate dependency graphs repeatedly. |

---

## 3.11 Lifespan Events: Application Startup and Shutdown

Modern FastAPI applications manage boot logic using an **async context manager** passed to the `lifespan` parameter:

```python
# From prism/main.py
@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- STARTUP PHASE ---
    settings = Settings.from_env()
    loaded_config = load_configuration()
    init_database(settings.db_path)

    # Initialize singletons (repositories, clock, limiter, providers)
    ...
    app.state.key_repository = key_repository
    logger.info("Prism initialized successfully")

    yield  # <--- APPLICATION SERVES INCOMING TRAFFIC HERE --->

    # --- SHUTDOWN PHASE ---
    logger.info("Prism application shutting down")
```

- **Fail-Fast Safety:** Everything before `yield` runs *before* the server accepts a single network connection. If master keys are missing or config files are corrupt, an exception is raised, and Uvicorn aborts startup immediately.
- Code after `yield` executes when Uvicorn receives a termination signal (`SIGTERM` or `Ctrl+C`).

---

## 3.12 Async Endpoints and Concurrency Realities

Declaring routes as `async def chat_completions(...)` runs them directly on the main event loop thread.

> [!WARNING]
> **Critical Backend Insight: Blocking Calls in Async Code**  
> If an `async def` function executes a blocking, synchronous operation (such as `time.sleep(5)` or a slow synchronous database query), the **entire event loop freezes**. No other concurrent requests can progress during those 5 seconds.  
> Prism's SQLite repositories use Python's standard `sqlite3` library, which is synchronous. For low-to-moderate traffic, SQLite queries execute in sub-millisecond timeframes, making this acceptable. However, under high-throughput production workloads, synchronous database calls should be offloaded to a thread pool via `anyio.to_thread.run_sync()` or replaced with an asynchronous driver like `aiosqlite` or `asyncpg`. This is documented in Section 10 as an architectural trade-off.

---
# 4. Complete Project Folder Structure

This section documents the entire repository structure and provides an exhaustive, forensic breakdown of every single file in the project.

```
prism-llm-gateway/
├── config/                             # Runtime JSON configuration files
│   ├── gateway_config.json             # Gateway aliases, timeouts, and retry limits
│   ├── gateway_config.sample.json      # Sample/fallback gateway configuration
│   ├── model_pricing.json              # Upstream provider pricing per million tokens
│   └── seed_keys.json                  # Initial virtual API keys and tenant quotas
├── console/                            # Static Operations Monitoring Console
│   └── index.html                      # Single-page HTML/CSS/JS administrative dashboard
├── data/                               # Persistent runtime and evaluation data
│   ├── prism.db                        # SQLite database (tables: keys, usage, logs, cache)
│   ├── routing_eval.jsonl              # Held-out evaluation dataset for auto routing
│   └── training_examples.jsonl         # Labeled examples used to design router heuristics
├── docs/                               # System documentation and design records
│   ├── adr/                            # Architectural Decision Records (ADR-001 to ADR-008)
│   ├── verification/                   # Verification logs, load tests, smoke test outputs
│   ├── architecture.md                 # Primary system architecture document
│   ├── implementation-plan.md          # Step-by-step engineering implementation plan
│   ├── PRISM_ARCHITECTURE.md           # Extended architecture reference
│   └── script.md                       # Master educational study and interview guide
├── prism/                              # Core application source code
│   ├── __init__.py                     # Package marker
│   ├── main.py                         # Application entrypoint & composition root
│   ├── adapters/                       # Concrete implementations of external systems
│   │   ├── __init__.py
│   │   ├── bow_embedder.py             # 256-dim Bag-of-Words offline embedding & cosine similarity
│   │   ├── openai_compatible.py        # HTTP client adapter for OpenAI and Groq (httpx)
│   │   ├── sqlite_repos.py             # SQLite repositories for keys, usage, logs, and cache
│   │   └── system_clock.py             # Production UTC wall-clock adapter
│   ├── api/                            # HTTP presentation layer (FastAPI)
│   │   ├── __init__.py
│   │   ├── admin.py                    # Administrative endpoints (/admin/usage, /logs, /cache/stats)
│   │   ├── error_handler.py            # Global exception handlers translating errors to OpenAI JSON
│   │   ├── middleware.py               # Request ID generation, ContextVar tracking, timing headers
│   │   └── routes.py                   # Client routes: /v1/chat/completions, /v1/models, /health
│   ├── config/                         # Configuration and logging infrastructure
│   │   ├── __init__.py
│   │   ├── loader.py                   # Pydantic validation for seed_keys, pricing, and gateway configs
│   │   ├── logging.py                  # Structured JSON logging formatter with request ID injection
│   │   └── settings.py                 # Environment variable parser (.env)
│   ├── domain/                         # Pure business logic and domain entities (No I/O)
│   │   ├── __init__.py
│   │   ├── cache_decision.py           # Pure logic for cacheability and time-sensitive keyword detection
│   │   ├── cost.py                     # Financial calculation per million tokens
│   │   ├── errors.py                   # Domain exception hierarchy (PrismError, RateLimitError, etc.)
│   │   ├── limiter.py                  # In-memory thread-safe Token Bucket rate limiter
│   │   ├── models.py                   # Core Pydantic domain models (RequestContext, VirtualKeyConfig, etc.)
│   │   └── security.py                 # Cryptographic hashing for API keys (SHA-256)
│   ├── ports/                          # Abstract Base Classes (Contracts / Interfaces)
│   │   ├── __init__.py
│   │   ├── clock.py                    # Clock interface contract
│   │   ├── embedder.py                 # Text embedder contract
│   │   ├── provider.py                 # LLM provider adapter contract (complete, stream)
│   │   └── repositories.py             # Database repository contracts (keys, usage, logs, cache)
│   └── services/                       # Application orchestration and domain services
│       ├── __init__.py
│       ├── cache.py                    # Semantic caching coordinator service
│       ├── executor.py                 # Resilient executor (retries, backoff, jitter, failover)
│       ├── pipeline.py                 # Sequential stage pipeline runner
│       ├── router.py                   # Difficulty classifiers (LengthOnlyClassifier, HeuristicClassifier)
│       ├── streaming.py                # Server-Sent Events stream forwarder and usage observer
│       └── stages/                     # Individual pipeline stages
│           ├── __init__.py
│           ├── allowlist.py            # Model allowlist verification stage
│           ├── auth.py                 # Virtual API key authentication stage
│           ├── budget.py               # Monthly financial budget enforcement stage
│           ├── cache.py                # Semantic cache lookup stage factory
│           ├── rate_limiter.py         # RPM rate limiting stage
│           ├── resolve.py              # Model alias and auto difficulty resolution stage
│           └── validate.py             # Request payload schema and token cap validation stage
├── scripts/                            # Operational, testing, and evaluation scripts
│   ├── load_test.py                    # Concurrency and throughput load testing tool
│   ├── mock_provider.py                # Standalone FastAPI server simulating alpha/beta LLMs
│   ├── routing_eval.py                 # Accuracy evaluator comparing classifiers against eval set
│   └── smoke_test.py                   # Comprehensive end-to-end verification script
├── tests/                              # Automated test suite (287+ tests)
│   ├── concurrency/                    # Concurrency stress tests
│   │   └── test_limiter_concurrent.py  # Multi-threaded rate limiter acquisition tests
│   ├── helpers/                        # Test doubles and fixtures
│   │   ├── fake_adapter.py             # In-memory mock LLM provider simulating success and errors
│   │   └── fake_clock.py               # Controllable time double for deterministic time tests
│   ├── integration/                    # Multi-component integration tests
│   │   ├── test_error_paths.py         # End-to-end error propagation tests
│   │   ├── test_failover.py            # Multi-provider failover verification
│   │   ├── test_passthrough.py         # OpenAI-compatible API pass-through tests
│   │   ├── test_pipeline.py            # Complete request pipeline execution tests
│   │   ├── test_semantic_cache.py      # Cache hit, miss, bypass, and eviction tests
│   │   └── test_streaming.py           # SSE streaming, token counting, and disconnect tests
│   └── unit/                           # Isolated unit tests for individual modules
│       ├── test_admin.py               # Admin endpoint security and pagination tests
│       ├── test_allowlist.py           # Model allowlist enforcement tests
│       ├── test_api_routes.py          # API route routing and serialization tests
│       ├── test_auth.py                # Key hashing and authentication tests
│       ├── test_bow_embedder.py        # Tokenizer, BoW embedder, and cosine similarity tests
│       ├── test_budget.py              # Monthly spend calculation and budget block tests
│       ├── test_cache_decision.py      # Cacheability rules and keyword filter tests
│       ├── test_cache_repository.py    # SQLite cache storage and search tests
│       ├── test_clock.py               # System clock tests
│       ├── test_config.py              # Configuration loading and validation tests
│       ├── test_cost.py                # Cost calculation mathematical correctness tests
│       ├── test_database.py            # SQLite schema initialization and WAL mode tests
│       ├── test_errors.py              # Exception inheritance and status code tests
│       ├── test_executor.py            # Retry loop, backoff, and failover unit tests
│       ├── test_fake_adapter.py        # Test helper self-tests
│       ├── test_key_repository.py      # Virtual key SQLite repository tests
│       ├── test_limiter.py             # Token bucket mathematical refill tests
│       ├── test_log_repository.py      # Request log persistence and retrieval tests
│       ├── test_logging.py             # Structured JSON log formatting tests
│       ├── test_models.py              # Domain model Pydantic validation tests
│       ├── test_openai_compatible.py   # OpenAICompatibleProvider HTTP adapter tests
│       ├── test_request_id.py          # Middleware request ID propagation tests
│       ├── test_resolve.py             # Alias and auto resolution tests
│       ├── test_router.py              # Heuristic classifier signal detection tests
│       ├── test_streaming.py           # Streaming generator and SSE format tests
│       ├── test_usage_repo.py          # Atomic usage upsert tests
│       └── test_validate.py            # Request payload validator and max_tokens cap tests
├── .dockerignore                       # Files excluded from Docker container builds
├── .env                                # Local environment secrets and overrides (git-ignored)
├── .env.example                        # Template for environment variables
├── .gitignore                          # Git tracking exclusion list
├── docker-compose.yml                  # Multi-container orchestration (Gateway + Alpha/Beta Mocks)
├── Dockerfile                          # Multi-stage container definition (Builder & Production)
├── LICENSE                             # Project license
├── README.md                           # Quickstart guide and architectural summary
└── requirements.txt                    # Pinned Python package dependencies
```

---

## 4.1 Domain Layer (`prism/domain/`)

The **Domain Layer** contains the core business logic, entities, and rules of the system. It has **zero dependencies** on external frameworks, databases, or network libraries. It is pure, deterministic Python.

---

### `prism/domain/models.py`
- **What is this file?** The central data model repository defining the entities that represent the gateway's state.
- **Why does it exist?** To establish strongly typed, self-validating data structures that flow through the entire system, preventing "stringly typed" or unvalidated dictionaries from causing runtime errors.
- **What responsibility does it have?** Defining the shape and validation rules for virtual keys, requests, responses, logs, cache entries, pricing, and monthly usage.
- **What code is written inside it?** Pydantic `BaseModel` classes:
  - `VirtualKeyConfig`: Represents an authenticated tenant key, its RPM rate limit, monthly USD budget, model allowlist, and cache settings.
  - `ProviderResponse`: Normalized representation of an LLM completion (`content`, `model`, `prompt_tokens`, `completion_tokens`, `total_tokens`, `finish_reason`, `raw_response`).
  - `RequestContext`: The primary state object created per request that travels through every pipeline stage. Tracks `request_id`, `model_requested`, `model_resolved`, `model_candidates`, `messages`, `provider_response`, `cost_usd`, `cache_status`, `retry_count`, `fallback_used`, and `decision_trace`.
  - `LogEntry`: Schema for rows in the `request_logs` SQLite table.
  - `CacheEntry` & `CacheStats`: Schemas for cached responses and aggregate statistics.
  - `ModelPricing`: Defines per-million input and output token pricing for a specific model.
  - `AliasConfig`: Maps a logical alias (e.g., `fast`) to a primary model (`gpt-4o-mini`) and fallback chain.
  - `GatewayConfig`: Container for all system aliases, pricing maps, and global timeouts.
  - `MonthlyUsage`: Aggregate usage record for a tenant in a calendar month.
- **Why is the code written this way?** Written using Pydantic v2 with field constraints (`ge=0`, `gt=0`, `le=1`, `default_factory=list`). This guarantees that invalid state (such as negative token counts or negative budgets) is physically impossible to instantiate. `default_factory=list` ensures that each instance gets a fresh list rather than sharing a mutable default across instances.
- **Which other files does it import?** `pydantic`, `datetime`, `typing`.
- **Which files import or call it?** Almost every file in the project (`routes.py`, `executor.py`, `cache.py`, `pipeline.py`, all stages, all repositories).
- **Exposed classes/methods:** All domain models listed above.
- **Input/Output:** Ingests Python dictionaries or database records; outputs validated Pydantic model instances or JSON-serializable dictionaries via `.model_dump(mode="json")`.
- **What would happen if it did not exist?** Components would pass untyped dictionaries with unpredictable keys across layers. A typo like `resposne` instead of `response` would fail silently until deep in the execution stack.

---

### `prism/domain/errors.py`
- **What is this file?** The domain exception hierarchy.
- **Why does it exist?** To decouple business failure concepts (authentication failed, budget depleted) from HTTP presentation concepts (status codes).
- **What responsibility does it have?** Providing distinct exception classes carrying semantic meaning, default HTTP status codes, and error type strings.
- **What code is written inside it?**
  - `PrismError(Exception)`: Root base class (defaults to 500 `internal_error`).
  - `AuthenticationError` (401 `authentication_error`): Raised on missing/invalid keys.
  - `InvalidRequestError` (400 `invalid_request`): Raised on malformed payloads.
  - `ModelNotAllowedError` (403 `model_not_allowed`): Raised when key allowlist rejects model.
  - `ModelNotFoundError` (404 `model_not_found`): Raised when requested model/alias is unknown.
  - `RateLimitError` (429 `rate_limit_exceeded`): Raised when RPM quota is exhausted.
  - `BudgetExceededError` (429 `budget_exceeded`): Raised when monthly USD spend limit is reached.
  - `UpstreamError` (502 `upstream_error`): Raised when upstream LLMs fail or disconnect.
- **Why is the code written this way?** Uses class attributes (`status_code`, `error_type`) so that the centralized exception handler in `prism/api/error_handler.py` can inspect exceptions polymorphically without needing long `if/elif` chains.
- **Which other files does it import?** Standard Python `Exception`.
- **Which files import or call it?** Every pipeline stage, `routes.py`, `executor.py`, `error_handler.py`.
- **What would happen if it did not exist?** Code would raise generic Python `RuntimeError` or `ValueError`, or stages would construct raw HTTP JSON responses directly, tightly coupling domain logic to FastAPI.

---

### `prism/domain/limiter.py`
- **What is this file?** An in-memory, thread-safe token bucket rate limiter.
- **Why does it exist?** To enforce per-minute request quotas per virtual key without introducing an external Redis dependency.
- **What responsibility does it have?** Tracking token counts per `key_hash`, refilling tokens mathematically based on elapsed time, and atomically decrementing tokens on acquisition.
- **What code is written inside it?**
  - `TokenBucket`: Dataclass holding `tokens: float` and `last_refill_at: datetime`.
  - `TokenBucketRateLimiter`: Manages a dictionary of buckets protected by a `threading.Lock()`.
    - `try_acquire(key_hash: str, rpm_limit: int) -> bool`: Computes elapsed time, refills `tokens = min(rpm_limit, tokens + elapsed * (rpm_limit / 60.0))`, checks if `tokens >= 1.0`, decrements by 1.0, and returns `True` or `False`.
- **Why is the code written this way?** 
  - Token refill is calculated lazily on access ($O(1)$) rather than running background timer threads for every tenant.
  - The check and decrement occur inside `with self.lock:` to prevent race conditions where concurrent threads check simultaneously and both decrement, exceeding the quota.
- **Which other files does it import?** `threading`, `dataclasses`, `datetime`, `prism.ports.clock.Clock`.
- **Which files import or call it?** Instantiated in `prism/main.py`; called in `prism/services/stages/rate_limiter.py`.
- **What would happen if it did not exist?** Tenants could flood the gateway with unlimited requests, exhausting upstream provider quotas and driving up organizational costs.

---

### `prism/domain/security.py`
- **What is this file?** Cryptographic utility functions.
- **Why does it exist?** To ensure that raw virtual API keys are never stored in databases or displayed in logs.
- **What responsibility does it have?** Calculating deterministic SHA-256 hashes of virtual API keys.
- **What code is written inside it?**
  - `hash_api_key(raw_key: str) -> str`: Encodes the key to UTF-8 bytes and computes its SHA-256 hexadecimal digest.
- **Why is the code written this way?** Uses Python's standard `hashlib.sha256`. SHA-256 is deterministic (identical keys always yield identical hashes), fast, and non-reversible.
- **Which other files does it import?** `hashlib`.
- **Which files import or call it?** `prism/config/loader.py` (when parsing `seed_keys.json`), `prism/services/stages/auth.py` (when authenticating incoming requests), `prism/adapters/sqlite_repos.py`.
- **What would happen if it did not exist?** Raw API keys would be stored in plain text in `prism.db`, creating a severe security vulnerability if the database file were ever leaked or backed up insecurely.

---

### `prism/domain/cost.py`
- **What is this file?** Token financial calculation engine.
- **Why does it exist?** To calculate the exact USD cost of every completion based on provider pricing tables.
- **What responsibility does it have?** Validating token inputs and executing the formula:  
  $$\text{Cost} = \frac{(\text{prompt\_tokens} \times \text{input\_price}) + (\text{completion\_tokens} \times \text{output\_price})}{1,000,000}$$
- **What code is written inside it?**
  - `CostCalculator`: Class containing the `@staticmethod calculate(...)`.
- **Why is the code written this way?** Pure static calculation with zero side effects. Explicitly validates that token counts are non-negative integers (and not booleans) to protect financial integrity.
- **Which other files does it import?** `prism.domain.models.ModelPricing`.
- **Which files import or call it?** `prism/api/routes.py` (non-streaming), `prism/services/streaming.py` (streaming).
- **What would happen if it did not exist?** The gateway could not meter usage or enforce financial spending budgets.

---

### `prism/domain/cache_decision.py`
- **What is this file?** Pure domain rules for semantic cache eligibility.
- **Why does it exist?** To keep business rules about *what may be cached* separate from the database and embedding mechanics.
- **What responsibility does it have?** Inspecting prompts for time-sensitive keywords and checking if responses are successful.
- **What code is written inside it?**
  - `TIME_SENSITIVE_KEYWORDS`: Tuple containing `"now"`, `"today"`, `"latest"`, `"current"`, `"right now"`, `"this moment"`.
  - `is_cacheable(request_context: RequestContext) -> bool`: Returns `False` if caching is disabled for the key, prompt contains time-sensitive words, or the provider response has `finish_reason == "error"`.
  - `is_hit(similarity_score: float, threshold: float) -> bool`: Returns `True` if similarity $\ge$ threshold.
- **Why is the code written this way?** Decoupled from SQLite. ADR-005 dictates that time-sensitive queries must never be served stale answers.
- **Which other files does it import?** `prism.domain.models.RequestContext`.
- **Which files import or call it?** `prism/services/cache.py`.
- **What would happen if it did not exist?** Stale answers would be returned for questions like *"What is the stock price right now?"*, corrupting application accuracy.

---

## 4.2 Ports Layer (`prism/ports/`)

The **Ports Layer** defines the abstract boundaries of the system using Python Abstract Base Classes (`ABC`). Ports declare what external infrastructure must provide without caring how it is implemented.

---

### `prism/ports/provider.py`
- **What is this file?** Interface contract for external LLM providers.
- **Responsibility:** Declares `complete(request)` and `stream(request)`.
- **Exposed Classes:** `ProviderAdapter(ABC)`.
- **Why it matters:** Enables writing code that talks to "a provider" without knowing whether it is OpenAI, Groq, or an in-memory test fake.

### `prism/ports/repositories.py`
- **What is this file?** Interface contracts for persistence.
- **Responsibility:** Declares database contracts:
  - `KeyRepository`: `get_by_hash(key_hash)`, `seed_keys(keys)`.
  - `UsageRepository`: `record_usage(key_hash, month, cost, tokens, is_cache_hit)`, `get_usage(key_hash, month)`, `get_all_usage(month)`.
  - `LogRepository`: `save_log(log_entry)`, `get_logs(...)`, `get_log(request_id)`.
  - `CacheRepository`: `store(...)`, `search(...)`, `get_stats()`.
- **Why it matters:** Decouples the service layer from SQLite. In the future, SQLite can be swapped for PostgreSQL without altering business logic.

### `prism/ports/clock.py`
- **What is this file?** Time source interface.
- **Responsibility:** Declares `now() -> datetime`.
- **Why it matters:** In production, system time flows continuously. In tests, `FakeClock` freezes or steps time forward deterministically to test rate limiter token refills and monthly budget rollover.

### `prism/ports/embedder.py`
- **What is this file?** Text embedding interface.
- **Responsibility:** Declares `embed(text: str) -> list[float]`.
- **Why it matters:** Allows swapping the lightweight offline `BowEmbedder` for an OpenAI or HuggingFace vector embedding model without changing the cache service.

---

## 4.3 Adapters Layer (`prism/adapters/`)

The **Adapters Layer** contains the concrete implementations of external infrastructure (SQLite, HTTP clients, system clocks, embedding algorithms).

---

### `prism/adapters/openai_compatible.py`
- **What is this file?** HTTP adapter implementing `ProviderAdapter` for OpenAI, Groq, and compatible APIs.
- **Why does it exist?** Both OpenAI and Groq expose the same chat completion HTTP interface. This single adapter communicates with both.
- **What code is written inside it?**
  - `OpenAICompatibleProvider(ProviderAdapter)`:
    - Uses `httpx.AsyncClient` with separate connect and request timeouts.
    - `complete(request)`: Sends POST to `/chat/completions`, parses JSON, normalizes response into `ProviderResponse`.
    - `stream(request)`: Sends POST with `stream: true`, parses incoming SSE lines (`data: {...}`), yields chunks, captures token usage from the final `usage` event or saves it in `self.last_stream_usage`.
    - Converts HTTP/transport errors (`httpx.TimeoutException`, `httpx.HTTPStatusError`, `httpx.ConnectError`) into `UpstreamError` with exception chaining (`from exc`).
- **Why written this way?** Uses `httpx.Timeout(connect=..., read=...)` to detect hung connections quickly without blocking the event loop. Injects `stream_options: {"include_usage": True}` so providers return token metrics at the end of streams.
- **Imports:** `httpx`, `json`, `collections.abc.AsyncIterator`, `prism.domain.models`, `prism.ports.provider.ProviderAdapter`.
- **Used by:** Instantiated in `prism/main.py` for OpenAI and Groq.
- **What would happen if missing?** Prism could not make network calls to any LLM provider.

---

### `prism/adapters/sqlite_repos.py`
- **What is this file?** SQLite database initialization and repository implementations.
- **Why does it exist?** Provides persistent storage for virtual keys, usage records, request audit logs, and semantic cache entries using a single local file (`prism.db`).
- **What code is written inside it?**
  - `init_database(path)` and `create_tables(conn)`: Creates tables `virtual_keys`, `usage`, `request_logs`, `cache_entries`.
  - `get_connection(path)`: Configures SQLite connection with:
    - `PRAGMA busy_timeout = 5000`: Waits up to 5 seconds if another thread is writing before raising `OperationalError: database is locked`.
    - `PRAGMA journal_mode = WAL`: Write-Ahead Logging allows concurrent readers without blocking writers.
    - `PRAGMA synchronous = NORMAL`: Fast writes while preserving crash safety in WAL mode.
    - `PRAGMA foreign_keys = ON`.
  - `SQLiteKeyRepository(KeyRepository)`: Looks up keys by SHA-256 hash; seeds initial keys using `INSERT OR REPLACE`.
  - `SQLiteUsageRepository(UsageRepository)`: Records usage via atomic SQL upsert:
    ```sql
    INSERT INTO usage (key_hash, month, total_spend_usd, total_tokens, total_requests, cache_hits)
    VALUES (?, ?, ?, ?, 1, ?)
    ON CONFLICT(key_hash, month) DO UPDATE SET
        total_spend_usd = total_spend_usd + excluded.total_spend_usd,
        total_tokens = total_tokens + excluded.total_tokens,
        total_requests = total_requests + 1,
        cache_hits = cache_hits + excluded.cache_hits;
    ```
  - `SQLiteLogRepository(LogRepository)`: Appends request metadata rows; supports pagination via `LIMIT` and `OFFSET`.
  - `CacheRepository`: Searches cache entries scoped by `WHERE key_hash = ? AND alias = ?`, evaluates cosine similarity in Python against all stored vectors, updates `hit_count`, and evicts oldest entries when count exceeds 1000.
- **Why written this way?** SQLite with WAL mode provides zero-dependency, serverless persistence. Atomic upserts prevent concurrency lost-update bugs. Scoping cache queries by `key_hash` guarantees tenant isolation at the database level.
- **Used by:** `prism/main.py` attaches instances to `app.state`.
- **What would happen if missing?** Keys, usage, logs, and cache would vanish on every server restart.

---

### `prism/adapters/bow_embedder.py`
- **What is this file?** Lightweight, offline Bag-of-Words text embedding generator.
- **Why does it exist?** Semantic caching requires vector embeddings. Calling an external embedding API (like OpenAI `text-embedding-3-small`) on every request costs money, adds network latency, and requires another API key. This embedder runs locally in 0.2 milliseconds at zero cost.
- **What code is written inside it?**
  - `BowEmbedder(Embedder)`:
    - Fixed vector size: 256 dimensions.
    - `STOP_WORDS`: Strips common non-informative words (`"the"`, `"is"`, `"what"`, `"how"`, `"a"`, etc.).
    - `TOKEN_NORMALIZATION`: Normalizes synonyms (e.g., `"reset"` -> `"change"`).
    - `tokenize(text)`: Lowercases and extracts alphanumeric words via regex `\b[a-z0-9]+\b`.
    - `embed(text)`: Hashes each normalized token using SHA-256 modulo 256 to determine its vector index (feature hashing), incrementing the index by 1.0 (term frequency).
  - `cosine_similarity(vec_a, vec_b) -> float`: Computes dot product divided by the product of vector magnitudes, clamped between 0.0 and 1.0.
- **Used by:** `prism/services/cache.py`, `prism/adapters/sqlite_repos.py`.
- **What would happen if missing?** Semantic caching would be impossible without integrating heavy external ML models or paid APIs.

---

### `prism/adapters/system_clock.py`
- **What is this file?** Real-world time provider.
- **Responsibility:** Implements `Clock.now()` returning `datetime.now(timezone.utc)`.
- **Used by:** `prism/main.py`.

---

## 4.4 Services Layer (`prism/services/`)

The **Services Layer** orchestrates domain logic, repositories, and adapters to carry out complex use cases.

---

### `prism/services/pipeline.py`
- **What is this file?** Linear stage execution pipeline runner.
- **Why does it exist?** To decouple individual request processing steps into small, testable, composable stages executed in strict sequential order.
- **What code is written inside it?**
  - `Pipeline`: Class containing `async run(context: RequestContext, stages: Sequence[Stage]) -> RequestContext`.
  - Loops over `stages`, executes `await stage(context)`.
  - If a `PrismError` is raised, appends `"<stage_name> failed"` to `context.decision_trace` and re-raises the exception.
- **Why written this way?** Clear responsibility. The pipeline runner does not know what auth, rate limiting, or budgeting do; it simply guarantees ordered execution and failure tracing.
- **Used by:** `prism/api/routes.py`.
- **What would happen if missing?** `routes.py` would become a monolithic, untestable 1,500-line function with deeply nested `try...except` statements.

---

### `prism/services/router.py`
- **What is this file?** Difficulty classification engine for automatic model routing (`model: "auto"`).
- **Why does it exist?** ADR-007 and ADR-008 dictate that the gateway should dynamically route complex prompts to smart models and simple prompts to fast models.
- **What code is written inside it?**
  - `DifficultyClassifier(ABC)`: Strategy interface declaring `.classify(prompt: str) -> ClassificationResult`.
  - `LengthOnlyClassifier`: Baseline classifier routing prompts $> 200$ characters to `smart`, else `fast`.
  - `HeuristicClassifier`: Production classifier analyzing multiple linguistic and structural signals:
    - `HARD_SIGNALS`: `"prove"`, `"derive"`, `"why"`, `"debug"`, `"deadlock"`, `"analyze"`, `"optimize"`, `"architecture"`, etc.
    - `EASY_SIGNALS`: `"list"`, `"extract"`, `"who is"`, `"when is"`, `"summarize"`, `"translate"`, etc.
    - Code detection: Regex matching triple backticks (` ``` `), tildes (`~~~`), or inline backticks (`` `code` ``).
    - Math detection: Regex matching LaTeX notation (`\frac`, `\sqrt`, `\sum`, `\int`) or arithmetic operators.
    - Multi-part detection: Regex matching `\bfirst\b...\bthen\b...\bfinally\b`.
    - Scoring formula: $\text{score} = \frac{\text{hard\_matches}}{\text{hard\_matches} + \text{easy\_matches}}$. If $\text{score} \ge 0.5$ and $\text{hard\_count} > 0$, routes to `smart`; otherwise defaults to `fast`.
- **Why written this way?** Implements the Strategy Pattern. The heuristic classifier runs in microseconds without invoking an LLM, making routing decisions virtually free.
- **Used by:** `prism/services/stages/resolve.py`, `scripts/routing_eval.py`.
- **What would happen if missing?** Requests specifying `model: "auto"` would fail or require expensive pre-calls to an LLM evaluator.

---

### `prism/services/executor.py`
- **What is this file?** Resilient upstream request dispatcher with retries, exponential backoff, jitter, and multi-provider failover.
- **Why does it exist?** Upstream cloud APIs experience intermittent network drops, rate limits (429), and server blips (500, 502, 503). This service ensures requests succeed despite upstream instability.
- **What code is written inside it?**
  - `ExecutionResult`: Dataclass holding `response`, `retries`, `fallback_used`, `provider_name`.
  - `ResilientExecutor`:
    - Takes a list of candidate providers (`[primary, fallback_1, fallback_2]`).
    - Outer loop iterates through providers; inner loop attempts execution up to `max_retries + 1` times.
    - `_classify_error(exc)`:
      - `httpx.TimeoutException`, `TimeoutError`, HTTP $\ge 500$, `RequestError` -> `"retryable"` (retries same provider).
      - `httpx.ConnectError`, HTTP 429 (Rate Limit) -> `"failover"` (immediately moves to next provider).
      - HTTP $400 \le \text{status} < 500$ (except 429) -> `"fatal"` (aborts immediately).
    - `_backoff(attempt)`: Calculates delay = $\text{base\_delay} \times 2^{\text{attempt}} + \text{uniform}(0, 0.5 \times \text{delay})$ and calls `asyncio.sleep()`.
- **Why written this way?** Full jitter exponential backoff prevents thundering herd spikes against recovering providers. Failing over immediately on 429 prevents wasting retries on an already throttled provider.
- **Used by:** `prism/api/routes.py` (non-streaming).
- **What would happen if missing?** Any brief network timeout or upstream 503 would immediately bubble up as a 502 error to client applications.

---

### `prism/services/cache.py`
- **What is this file?** Semantic cache coordinator.
- **Why does it exist?** To connect the domain cache rules, the embedding adapter, and the SQLite cache repository into a unified workflow.
- **What code is written inside it?**
  - `CacheService`:
    - `_get_prompt(context)`: Serializes `context.messages` deterministically using `json.dumps(..., sort_keys=True)`.
    - `_is_request_eligible(context)`: Checks key cache flag and scans for `TIME_SENSITIVE_KEYWORDS`.
    - `get_cached_response(context)`: Generates embedding, searches repository above `cache_threshold`, sets `context.cache_status = "hit"` and `cost_usd = 0.0`.
    - `store_response(context)`: Embeds prompt and stores successful provider response in SQLite.
- **Used by:** `prism/services/stages/cache.py`, `prism/api/routes.py`.
- **What would happen if missing?** Every request would hit upstream providers, increasing latency and cost.

---

### `prism/services/streaming.py`
- **What is this file?** Streaming proxy service for Server-Sent Events.
- **Why does it exist?** LLM chat interfaces require immediate token streaming. This service forwards chunks in real time, observes token usage, enforces idle timeouts, handles client disconnects, and manages mid-stream provider failures.
- **What code is written inside it?**
  - `get_stream_idle_timeout()`: Reads `PRISM_STREAM_IDLE_TIMEOUT` (default 10.0s).
  - `format_sse_chunk(chunk)`: Formats dictionary as `data: {...}\n\n`.
  - `format_sse_error(message)`: Formats error as `event: error\ndata: {"error": ...}\n\n`.
  - `stream_response(...)`:
    - Reads chunks from upstream generator with `asyncio.wait_for(..., timeout=idle_timeout)`.
    - Captures `usage` metadata from chunks if present.
    - Yields formatted SSE strings immediately to client.
    - Catches `asyncio.CancelledError` (client disconnect) or upstream disconnects.
    - Enforces ADR-002: If upstream dies mid-stream, yields `format_sse_error()` and terminates (never splices models mid-stream).
    - In `finally:`, closes provider stream (`aclose()`) and records observed token usage in SQLite via `record_stream_usage()`.
- **Used by:** `prism/api/routes.py` (`format_streaming_body`).
- **What would happen if missing?** Clients would have to wait for the entire completion to finish before seeing any text.

---

## 4.5 Pipeline Stages (`prism/services/stages/`)

Each file in this folder represents an isolated, single-responsibility step in the request lifecycle:

- **`stages/auth.py` (`authenticate_request`):** Reads `x-api-key`, computes SHA-256 hash, retrieves key from SQLite, performs constant-time `hmac.compare_digest`, verifies `status == "active"`, and attaches `VirtualKeyConfig` to `context`. Raises 401 on failure.
- **`stages/validate.py` (`validate_request`):** Validates that `model` is a non-empty string, `messages` is a non-empty array of objects with valid `role` and `content`, and clamps `max_tokens = min(max_tokens, settings.max_tokens_cap)`. Raises 400 on failure.
- **`stages/rate_limiter.py` (`enforce_rate_limit`):** Calls `TokenBucketRateLimiter.try_acquire(key_hash, rpm_limit)`. Raises 429 `rate_limit_exceeded` on failure.
- **`stages/resolve.py` (`resolve_model_candidates`):** Translates requested model. If `auto`, runs `HeuristicClassifier` to pick `fast` or `smart`. Resolves aliases to primary and fallback chains. Verifies model exists in pricing table. Raises 404 if missing.
- **`stages/allowlist.py` (`enforce_model_allowlist`):** Enforces ADR-007. Checks wildcard `*`. If `auto` requested, verifies `auto` and selected tier are allowed. Verifies all candidate models exist in `model_allowlist`. Raises 403 `model_not_allowed` on failure.
- **`stages/budget.py` (`enforce_budget`):** Reads current month's spend from SQLite. If `current_spend >= budget_usd`, raises 429 `budget_exceeded`. Per ADR-001, runs before cache lookup.
- **`stages/cache.py` (`create_cache_stage`):** Factory returning an async stage closure that invokes `cache_service.get_cached_response(context)`.

---

## 4.6 Presentation Layer (`prism/api/`)

---

### `prism/api/routes.py`
- **What is this file?** The primary HTTP router for the public API.
- **Why does it exist?** Implements the OpenAI-compatible endpoints `/v1/chat/completions` and `/v1/models`.
- **What code is written inside it?**
  - `@router.get("/v1/models")`: Returns OpenAI-compatible model listing of all pricing models and aliases.
  - `@router.post("/v1/chat/completions")`: Core gateway endpoint.
    - Assembles pipeline stages (`auth`, `validate`, `rate_limit`, `resolve`, `allowlist`, `budget`, `cache`, `provider_call`, `meter`).
    - Executes `pipeline.run(context)`.
    - Handles non-streaming completions: executes `ResilientExecutor`, calculates cost, stores response in semantic cache, records usage, sets response headers, logs request, returns OpenAI JSON envelope.
    - Handles streaming completions: builds streaming headers, returns `StreamingResponse` wrapping `format_streaming_body()`.
    - Implements the **Streaming Tee Pattern**: As chunks stream to the client, buffers content tokens into an internal list; upon successful completion, constructs a `ProviderResponse`, records usage, saves request log, and stores the completion in the semantic cache!
    - Handles cached streaming replay (`format_cached_streaming_body`): Emits cached text as SSE chunks matching an LLM stream.
- **Used by:** Mounted in `prism/main.py`.
- **What would happen if missing?** No client could submit chat completions or list models.

---

### `prism/api/admin.py`
- **What is this file?** Administrative operations router.
- **Responsibility:** Exposes operations endpoints:
  - `GET /admin/usage`: Monthly usage aggregated by key.
  - `GET /admin/logs`: Paginated request logs with optional `key_hash` filter.
  - `GET /admin/cache/stats`: Total cache entries, cache hits, and accurate monthly cache hit rate.
  - `verify_admin_token(request)`: Authenticates `Authorization: Bearer <token>` against `PRISM_ADMIN_TOKEN` using `secrets.compare_digest`.
- **Used by:** Mounted in `prism/main.py`; queried by the ops console (`/console`).

---

### `prism/api/middleware.py`
- **What is this file?** HTTP middleware for request tracking.
- **Responsibility:** Generates `request_id = req_<12 hex chars>`, sets `request.state.request_id`, stores it in `request_id_context` ContextVar for logging, measures request execution time with `time.perf_counter()`, and injects `x-prism-request-id` into response headers.
- **Used by:** Registered in `prism/main.py`.

---

### `prism/api/error_handler.py`
- **What is this file?** Centralized exception handling.
- **Responsibility:**
  - `prism_error_handler`: Translates any `PrismError` subclass into OpenAI error JSON:
    `{"error": {"message": ..., "type": ..., "code": ...}}`. Injects `Retry-After: 60` for 429 status codes. Sanitizes 502 `UpstreamError` messages to avoid leaking vendor infrastructure details.
  - `unexpected_error_handler`: Catches unhandled Python exceptions, logs full tracebacks server-side, and returns a safe HTTP 500 error envelope.
- **Used by:** Registered in `prism/main.py`.

---

## 4.7 Configuration Infrastructure (`prism/config/`)

- **`prism/config/settings.py`:** Reads `.env` using `python-dotenv`. Validates integer/float environment variables (`PRISM_PROVIDER_TIMEOUT_SECONDS`, `PRISM_MAX_RETRIES`, `PRISM_CONNECT_TIMEOUT_SECONDS`, `PRISM_MAX_TOKENS_CAP`, `PRISM_DB_PATH`, master API keys). Returns immutable `Settings` dataclass.
- **`prism/config/loader.py`:** Reads and validates runtime JSON files (`seed_keys.json`, `model_pricing.json`, `gateway_config.json`). Converts raw seed keys into SHA-256 hashes. Cross-validates that all alias targets and allowlists point to known models. Raises `ConfigLoadError` on invalid configuration.
- **`prism/config/logging.py`:** Configures Python standard logging with `JSONFormatter`. Injects timestamp, level, logger name, `request_id` (from ContextVar), and arbitrary `extra={...}` dictionary fields into machine-readable JSON lines.

---

## 4.8 Application Composition Root (`prism/main.py`)

- **What is this file?** The application assembly and startup module.
- **Why does it exist?** In Clean Architecture, the **Composition Root** is the unique location where all concrete adapters, repositories, settings, and services are instantiated and wired together.
- **What code is written inside it?**
  - Defines `lifespan(app)` context manager:
    - Loads `Settings` and JSON configs.
    - Initializes SQLite schema (`init_database`).
    - Seeds virtual keys into SQLite (`seed_keys`).
    - Instantiates singletons (`SQLiteKeyRepository`, `SQLiteUsageRepository`, `SQLiteLogRepository`, `CacheRepository`, `BowEmbedder`, `CacheService`, `SystemClock`, `TokenBucketRateLimiter`, `OpenAICompatibleProvider`).
    - Validates master credentials (`OPENAI_API_KEY`, `GROQ_API_KEY`).
    - Stores singletons on `app.state`.
  - Instantiates `app = FastAPI(lifespan=lifespan)`.
  - Registers middleware, error handlers, and routers (`router`, `admin_router`).
  - Exposes `GET /health` (returns `{"status": "ok"}`).
  - Exposes `GET /console` (serves static `console/index.html`).
  - Launches Uvicorn if executed directly as `__main__`.
- **What would happen if missing?** The gateway could not boot.

---

## 4.9 Static Console, Scripts, and Test Helpers

- **`console/index.html`:** Standalone single-page web dashboard using vanilla HTML, Tailwind CSS (via CDN), and JavaScript. Prompts the operator for an Admin Bearer Token, queries `/admin/usage`, `/admin/logs`, and `/admin/cache/stats`, and renders real-time metric cards, interactive log tables, and tenant spend progress bars.
- **`scripts/mock_provider.py`:** Standalone mock server built with FastAPI. Simulates upstream LLM providers (Alpha on 9001, Beta on 9002). Can be instructed to inject simulated latency, HTTP 500 errors, or HTTP 429 rate limits to test gateway resilience locally without internet access.
- **`scripts/smoke_test.py`:** Comprehensive end-to-end Python test script verifying virtual key authentication, rate limiting, budget enforcement, alias resolution, auto routing, semantic caching, streaming pass-through, failover, and admin endpoints against a running gateway instance.
- **`scripts/load_test.py`:** Multi-threaded load testing utility sending concurrent requests to benchmark throughput (RPS), p50/p95/p99 latency, and rate limiter enforcement under load.
- **`scripts/routing_eval.py`:** Machine learning evaluation harness that runs `LengthOnlyClassifier` and `HeuristicClassifier` against `data/routing_eval.jsonl` to calculate accuracy and routing cost savings.
- **`tests/helpers/fake_adapter.py`:** In-memory test double implementing `ProviderAdapter`. Allows tests to pre-program responses, simulate streaming chunk delays, or trigger synthetic exceptions (`TimeoutError`, `HTTPStatusError`) to verify `ResilientExecutor` behavior deterministically.
- **`tests/helpers/fake_clock.py`:** Controllable time double implementing `Clock`. Allows unit tests to advance simulated time (`clock.advance(seconds=65)`) to verify token bucket refills and month rollovers without calling `time.sleep()`.
- **`Dockerfile` & `docker-compose.yml`:** Multi-stage Docker container build packaging Python dependencies into `/usr/local` and running as non-root user `prism`. Compose file spins up Prism Gateway alongside two mock upstream providers (`alpha-mock` and `beta-mock`).

---
# 5. Architecture Diagrams & File Connections

This section provides 11 detailed Mermaid diagrams visualizing every dimension of the Prism LLM Gateway. Every diagram accurately represents the **actual codebase implementation**, followed by a beginner-friendly, step-by-step technical explanation.

---

## 5.1 Diagram 1: Overall System Architecture

This diagram illustrates the high-level boundaries of the system, showing how external client applications communicate through Prism to reach upstream providers.

```mermaid
flowchart TD
    subgraph Clients["Client Layer (Tenants)"]
        ClientApp["Client Application\n(Python SDK, cURL, Frontend)"]
        OpsUser["DevOps / Administrator\n(Browser / Console)"]
    end

    subgraph Gateway["Prism LLM Gateway (:3000)"]
        subgraph HTTP["HTTP Presentation Layer"]
            Uvicorn["Uvicorn Server"]
            MW["Request ID Middleware\n(prism/api/middleware.py)"]
            ClientRoutes["Client Routes (/v1)\n(prism/api/routes.py)"]
            AdminRoutes["Admin Routes (/admin)\n(prism/api/admin.py)"]
            ErrorHandler["Central Error Handlers\n(prism/api/error_handler.py)"]
            ConsoleHost["Ops Console Static Host\n(GET /console)"]
        end

        subgraph Core["Pipeline & Services Layer"]
            Pipeline["Stage Pipeline Runner\n(prism/services/pipeline.py)"]
            RouterSvc["Difficulty Router\n(prism/services/router.py)"]
            LimiterSvc["Token Bucket Limiter\n(prism/domain/limiter.py)"]
            CacheSvc["Semantic Cache Service\n(prism/services/cache.py)"]
            Executor["Resilient Executor\n(prism/services/executor.py)"]
            StreamSvc["Streaming Proxy\n(prism/services/streaming.py)"]
        end

        subgraph Storage["Persistence Layer (SQLite)"]
            DB[(prism.db\nWAL Mode)]
            TableKeys["virtual_keys"]
            TableUsage["usage"]
            TableLogs["request_logs"]
            TableCache["cache_entries"]
        end

        subgraph Adapters["Infrastructure Adapters"]
            OpenAIAdapter["OpenAI Compatible Adapter\n(prism/adapters/openai_compatible.py)"]
            EmbedAdapter["Bag-of-Words Embedder\n(prism/adapters/bow_embedder.py)"]
        end
    end

    subgraph Providers["Upstream AI Providers"]
        OpenAI["OpenAI API\n(gpt-4o-mini)"]
        Groq["Groq API\n(llama-3.3-70b-versatile)"]
        MockA["Alpha Mock Provider (:9001)"]
        MockB["Beta Mock Provider (:9002)"]
    end

    ClientApp -->|"POST /v1/chat/completions\n(x-api-key)"| Uvicorn
    OpsUser -->|"GET /console, GET /admin/*\n(Bearer token)"| Uvicorn
    Uvicorn --> MW
    MW --> ClientRoutes
    MW --> AdminRoutes
    MW --> ConsoleHost

    ClientRoutes --> Pipeline
    Pipeline --> LimiterSvc
    Pipeline --> RouterSvc
    Pipeline --> CacheSvc
    Pipeline --> Executor
    Pipeline --> StreamSvc

    CacheSvc --> EmbedAdapter
    CacheSvc --> TableCache
    LimiterSvc -.->|"In-memory lock"| LimiterSvc
    Pipeline --> TableKeys
    Pipeline --> TableUsage
    ClientRoutes --> TableLogs

    AdminRoutes --> TableUsage
    AdminRoutes --> TableLogs
    AdminRoutes --> TableCache

    Executor --> OpenAIAdapter
    StreamSvc --> OpenAIAdapter

    OpenAIAdapter -->|"HTTPS (Bearer master key)"| OpenAI
    OpenAIAdapter -->|"HTTPS (Bearer master key)"| Groq
    OpenAIAdapter -->|"HTTP"| MockA
    OpenAIAdapter -->|"HTTP"| MockB
```

### Step-by-Step Explanation:
1. **Client Request Ingestion:** A tenant application issues an HTTP POST request to `/v1/chat/completions`, presenting their virtual key in the `x-api-key` header.
2. **Middleware Interception:** `request_id_middleware` generates a unique tracking ID (`req_...`), attaches it to a thread-safe `ContextVar`, and begins high-resolution execution timing.
3. **Pipeline Dispatch:** The request enters `Pipeline.run()`, which sequences validation, rate limiting, model resolution, access control, and budgeting.
4. **Cache & Persistence Access:** The pipeline queries `prism.db` to authenticate keys, check budgets, and inspect semantic cache records.
5. **Upstream Forwarding:** If un-cached, `ResilientExecutor` (non-streaming) or `stream_response` (streaming) uses `OpenAICompatibleProvider` to send an authenticated HTTPS request to OpenAI or Groq using the server's private master keys.
6. **Logging & Return:** The response is returned to the client with custom headers (`x-prism-request-id`, `x-prism-cost-usd`, etc.), and a complete audit row is written to `request_logs`.

---

## 5.2 Diagram 2: Complete Folder & Layer Dependency Diagram

This diagram visualizes Prism's Clean Architecture (Ports and Adapters / Hexagonal Architecture). Notice that dependencies point **inward** toward the core domain.

```mermaid
flowchart TB
    subgraph LayerPresentation["Presentation Layer (Outer)"]
        API["prism/api/\n(routes.py, admin.py, middleware.py, error_handler.py)"]
    end

    subgraph LayerServices["Services & Orchestration Layer (Middle)"]
        Services["prism/services/\n(pipeline.py, executor.py, router.py, cache.py, streaming.py)"]
        Stages["prism/services/stages/\n(auth, validate, rate_limiter, resolve, allowlist, budget, cache)"]
    end

    subgraph LayerPorts["Ports Layer (Contracts / Interfaces)"]
        Ports["prism/ports/\n(provider.py, repositories.py, clock.py, embedder.py)"]
    end

    subgraph LayerDomain["Domain Layer (Core - Pure Business Rules)"]
        Domain["prism/domain/\n(models.py, errors.py, limiter.py, security.py, cost.py, cache_decision.py)"]
    end

    subgraph LayerAdapters["Adapters & Infrastructure Layer (Outer)"]
        Adapters["prism/adapters/\n(openai_compatible.py, sqlite_repos.py, bow_embedder.py, system_clock.py)"]
        Config["prism/config/\n(settings.py, loader.py, logging.py)"]
    end

    API --> Services
    API --> Stages
    API --> Domain
    Services --> Stages
    Services --> Ports
    Services --> Domain
    Stages --> Ports
    Stages --> Domain
    Adapters --> Ports
    Adapters --> Domain
    Config --> Domain
    API -.->|"Reads configuration"| Config
```

### Step-by-Step Explanation:
1. **The Inward Dependency Rule:** The `domain` package sits at the center. It imports nothing from services, adapters, or API layers. It represents pure, framework-agnostic truth.
2. **Ports as Inversion Boundaries:** `services` and `stages` depend upon abstract interfaces in `ports` (e.g., `UsageRepository`, `ProviderAdapter`). They never directly import SQLite or HTTP client libraries.
3. **Adapters Implement Ports:** `adapters` depend upon `ports` and implement their methods. This structure allows replacing SQLite with PostgreSQL or httpx with a mock adapter without changing a single line of domain or service code.

---

## 5.3 Diagram 3: File-to-File Import and Function-Call Relationships

This diagram documents the exact code connections between specific files during a request.

```mermaid
graph LR
    main["main.py"] -->|"imports"| routes["api/routes.py"]
    main -->|"imports"| admin["api/admin.py"]
    main -->|"imports"| loader["config/loader.py"]
    main -->|"imports"| settings["config/settings.py"]
    main -->|"creates"| sqlite["adapters/sqlite_repos.py"]
    main -->|"creates"| provider["adapters/openai_compatible.py"]

    routes -->|"calls"| pipeline["services/pipeline.py"]
    routes -->|"calls"| auth_stage["stages/auth.py"]
    routes -->|"calls"| val_stage["stages/validate.py"]
    routes -->|"calls"| rate_stage["stages/rate_limiter.py"]
    routes -->|"calls"| res_stage["stages/resolve.py"]
    routes -->|"calls"| allow_stage["stages/allowlist.py"]
    routes -->|"calls"| bud_stage["stages/budget.py"]
    routes -->|"calls"| cache_stage["stages/cache.py"]
    routes -->|"calls"| executor["services/executor.py"]
    routes -->|"calls"| streaming["services/streaming.py"]

    auth_stage -->|"calls hash_api_key()"| sec["domain/security.py"]
    auth_stage -->|"calls get_by_hash()"| sqlite
    rate_stage -->|"calls try_acquire()"| limiter["domain/limiter.py"]
    res_stage -->|"calls classify()"| router["services/router.py"]
    bud_stage -->|"calls get_usage()"| sqlite
    cache_stage -->|"calls get_cached_response()"| cache_svc["services/cache.py"]

    cache_svc -->|"calls embed()"| bow["adapters/bow_embedder.py"]
    cache_svc -->|"calls search()"| sqlite

    executor -->|"calls complete()"| provider
    streaming -->|"calls stream()"| provider
    routes -->|"calls calculate()"| cost["domain/cost.py"]
    routes -->|"calls record_usage()"| sqlite
    routes -->|"calls save_log()"| sqlite
```

### Step-by-Step Explanation:
1. `main.py` bootstraps the system: it calls `loader.py` and `settings.py` to read configurations, boots `sqlite_repos.py`, initializes `openai_compatible.py`, and stores them in `app.state`.
2. `routes.py` orchestrates execution: it defines the pipeline stages and executes `pipeline.py`.
3. Each stage delegates to a specific domain or adapter component (`auth.py` calls `security.py` and `sqlite_repos.py`; `rate_limiter.py` calls `limiter.py`; `resolve.py` calls `router.py`).
4. `routes.py` calls `executor.py` for non-streaming or `streaming.py` for streaming, followed by `cost.py` and database logging.

---

## 5.4 Diagram 4: Component Interaction Diagram

This diagram shows how components communicate at runtime, sharing state via `RequestContext`.

```mermaid
flowchart TD
    Req[Incoming HTTP Request] --> Route[routes.py: chat_completions]
    
    subgraph ContextCreation["Context Initialization"]
        Route --> InitCtx["Instantiate RequestContext\n(request_id, model, messages, payload)"]
    end

    subgraph PipelineExecution["Pipeline Execution (pipeline.py)"]
        InitCtx --> S1["auth_stage (auth.py)"]
        S1 --> S2["validate_stage (validate.py)"]
        S2 --> S3["rate_limit_stage (rate_limiter.py)"]
        S3 --> S4["model_resolution_stage (resolve.py)"]
        S4 --> S5["allowlist_stage (allowlist.py)"]
        S5 --> S6["budget_stage (budget.py)"]
        S6 --> S7["cache_stage (cache.py)"]
    end

    subgraph Branching["Branching Decision"]
        S7 --> Hit{"Cache Hit?"}
        Hit -->|Yes| SkipProv["Skip Provider Call\n(cost = $0.00)"]
        Hit -->|No| StreamCheck{"stream == true?"}
        
        StreamCheck -->|No| ExecCall["ResilientExecutor.execute()"]
        StreamCheck -->|Yes| StreamCall["Format StreamingBody\n(stream_response)"]
    end

    subgraph Finalization["Response & Accounting"]
        SkipProv --> NonStreamResp["Format Completion JSON\n& Record Usage (Cache Hit)"]
        ExecCall --> NonStreamResp
        StreamCall --> StreamResp["StreamingResponse\n(SSE Chunks)"]
    end

    NonStreamResp --> Log["Save Request Log (SQLite)"]
    StreamResp --> Log
```

### Step-by-Step Explanation:
1. `chat_completions()` initializes a fresh `RequestContext` object carrying initial request data.
2. The pipeline passes `context` through stages 1 to 7 sequentially. Each stage reads from `context`, validates or modifies it, and appends to `decision_trace`.
3. If Stage 7 results in a cache hit (`context.cache_status == "hit"`), provider execution is bypassed entirely.
4. If a miss, the flow branches depending on whether `context.stream` is `True` or `False`.
5. Finally, usage is recorded, request logs are written to SQLite, and the formatted response is sent to the client.

---

## 5.5 Diagram 5: API Request Lifecycle (Sequence Diagram)

This sequence diagram traces the complete lifecycle of a `POST /v1/chat/completions` request.

```mermaid
sequenceDiagram
    autonumber
    actor Client
    participant MW as Middleware
    participant Route as routes.py
    participant Pipe as Pipeline
    participant Stages as Pipeline Stages
    participant Cache as CacheService
    participant Exec as ResilientExecutor
    participant Upstream as Upstream LLM
    participant DB as SQLite DB

    Client->>MW: POST /v1/chat/completions (x-api-key)
    MW->>MW: Generate request_id & start timer
    MW->>Route: Pass request
    Route->>Route: Build RequestContext

    Route->>Pipe: run(context, stages)
    Pipe->>Stages: 1. authenticate_request()
    Stages->>DB: Query virtual_keys by key_hash
    DB-->>Stages: Return VirtualKeyConfig
    Stages-->>Pipe: Auth OK

    Pipe->>Stages: 2. validate_request()
    Stages-->>Pipe: Validation OK (capped max_tokens)

    Pipe->>Stages: 3. enforce_rate_limit()
    Stages-->>Pipe: Rate OK (token acquired)

    Pipe->>Stages: 4. resolve_model_candidates()
    Stages-->>Pipe: Resolved candidates [gpt-4o-mini, llama-3.3]

    Pipe->>Stages: 5. enforce_model_allowlist()
    Stages-->>Pipe: Allowlist OK

    Pipe->>Stages: 6. enforce_budget()
    Stages->>DB: Query usage for current month
    DB-->>Stages: Return MonthlyUsage
    Stages-->>Pipe: Budget OK ($12.50 / $50.00)

    Pipe->>Stages: 7. cache_stage()
    Stages->>Cache: get_cached_response()
    Cache->>DB: Search cache_entries (key_hash, alias)
    DB-->>Cache: Miss (no matching vector)
    Cache-->>Stages: Cache Miss
    Stages-->>Pipe: Cache Miss

    Pipe-->>Route: Pipeline stages complete

    Route->>Exec: execute(request_payload)
    Exec->>Upstream: POST /chat/completions
    Upstream-->>Exec: 200 OK (choices, tokens)
    Exec-->>Route: ExecutionResult

    Route->>Cache: store_response(context)
    Cache->>DB: INSERT INTO cache_entries
    Route->>DB: record_usage(cost, tokens)
    Route->>DB: save_log(request_logs)

    Route-->>MW: Return completion JSON & headers
    MW-->>Client: 200 OK + x-prism-request-id + JSON body
```

---

## 5.6 Diagram 6: Provider Routing and Fallback Flow

This diagram details how `ResilientExecutor` handles transient errors, rate limits, retries with backoff, and model failovers.

```mermaid
flowchart TD
    Start["Receive Model Candidates\ne.g., ['gpt-4o-mini', 'llama-3.3-70b-versatile']"] --> PickP1["Select Candidate 1 (Primary)\nattempt = 0"]

    PickP1 --> TryCall["Invoke provider.complete() with asyncio.timeout(30s)"]

    TryCall --> Result{"Call Result?"}
    Result -->|Success 200 OK| Done["Return ExecutionResult\n(retries, fallback_used=False)"]

    Result -->|Exception Caught| Classify["_classify_error(exc)"]

    Classify --> CheckCat{"Category?"}

    CheckCat -->|"fatal\n(4xx, non-429)"| FatalErr["Raise UpstreamError immediately\n(No retry, no failover)"]

    CheckCat -->|"retryable\n(5xx, TimeoutError, RequestError)"| CheckRetry{"attempt < max_retries?"}
    CheckRetry -->|Yes| Backoff["_backoff(attempt)\nbase_delay * 2^attempt + jitter"]
    Backoff --> IncAttempt["attempt += 1\ntotal_retries += 1"]
    IncAttempt --> TryCall
    CheckRetry -->|No (Exhausted)| NextProvider{"Has more candidate providers?"}

    CheckCat -->|"failover\n(429 Rate Limit, ConnectError)"| NextProvider

    NextProvider -->|Yes| PickP2["Select Candidate 2 (Fallback)\nattempt = 0\nfallback_used = True"]
    PickP2 --> TryCall
    NextProvider -->|No| AllFailed["Raise UpstreamError\n('All configured providers failed.')"]
```

### Step-by-Step Explanation:
1. `ResilientExecutor` receives an ordered list of candidate models (e.g., `["gpt-4o-mini", "llama-3.3-70b-versatile"]`).
2. It attempts the primary model. If it succeeds, it returns immediately.
3. If an error occurs, `_classify_error()` categorizes it:
   - **Fatal (Client Error 400, 401, 404):** Aborts immediately. Retrying won't fix an invalid request.
   - **Retryable (Server 500, Timeout):** Calculates exponential backoff with jitter and retries on the *same* provider up to `max_retries` times.
   - **Failover (Rate Limit 429, Connection Failure):** Aborts retries on the current provider immediately and shifts to the fallback model.
4. If all candidate models fail, it raises `UpstreamError("All configured providers failed.")`.

---

## 5.7 Diagram 7: Streaming Request & Response Flow

This diagram shows the **Streaming Tee Pattern** used during Server-Sent Events (SSE) streaming.

```mermaid
sequenceDiagram
    autonumber
    actor Client
    participant Route as routes.py (format_streaming_body)
    participant StreamSvc as streaming.py (stream_response)
    participant Adapter as OpenAICompatibleProvider
    participant Upstream as External LLM
    participant DB as SQLite DB

    Client->>Route: POST /v1/chat/completions (stream=true)
    Route->>StreamSvc: Pass upstream provider iterator
    StreamSvc->>Adapter: provider.stream(payload)
    Adapter->>Upstream: HTTPS POST (stream=true, stream_options: include_usage)

    loop Chunks Arriving
        Upstream-->>Adapter: SSE line: data: {"choices": [{"delta": {"content": "Hello"}}]}
        Adapter-->>StreamSvc: Parsed chunk dictionary
        StreamSvc-->>Route: Yield SSE chunk
        Route-->>Client: data: {"choices": [{"delta": {"content": "Hello"}}]}\n\n
        Route->>Route: TEE: Buffer content into response_parts.append("Hello")
    end

    Upstream-->>Adapter: SSE line: data: {"usage": {"prompt_tokens": 10, "completion_tokens": 25}}
    Adapter-->>StreamSvc: Chunk with usage dictionary
    StreamSvc->>StreamSvc: update_stream_usage(context)

    Upstream-->>Adapter: SSE line: data: [DONE]
    Adapter-->>StreamSvc: {"done": True}
    StreamSvc-->>Route: Yield done chunk
    Route-->>Client: data: [DONE]\n\n

    Note over Route,DB: Stream Finished - finally block executes!
    StreamSvc->>DB: record_stream_usage(tokens, cost)
    Route->>DB: store_response() in semantic cache (assembled from buffer)
    Route->>DB: save_request_log(status=200, latency, cost)
```

---

## 5.8 Diagram 8: Semantic Cache Flow

This diagram traces how semantic caching works, including prompt normalization, time-sensitive keyword skipping, and similarity matching.

```mermaid
flowchart TD
    Start["Receive Prompt Messages"] --> CheckElig{"is_request_eligible()"}
    
    CheckElig -->|"cache_enabled == False"| SkipCache["cache_status = 'miss'\nRecord 'semantic cache lookup skipped'"]
    CheckElig -->|"Contains 'now', 'today', 'latest' etc."| SkipCache
    CheckElig -->|Eligible| GenEmbed["BowEmbedder.embed(prompt)\n256-dim feature hashed vector"]

    GenEmbed --> QuerySQL["Query SQLite: SELECT * FROM cache_entries\nWHERE key_hash = :key_hash AND alias = :alias"]

    QuerySQL --> CalcSim["For each row in DB:\nCompute cosine_similarity(query_vec, db_vec)"]

    CalcSim --> CheckBest{"Best similarity >= cache_threshold?"}

    CheckBest -->|No Match| CacheMiss["cache_status = 'miss'\nRecord 'semantic cache miss'\nForward to Provider"]
    CheckBest -->|Match Found| CacheHit["cache_status = 'hit'\nUpdate entry hit_count += 1\nLoad cached ProviderResponse\nSet cost_usd = 0.0\nSkip Provider Call!"]

    CacheMiss --> ProvDone["Provider Call Finishes Successfully"]
    ProvDone --> CheckStoreElig{"is_cacheable(context)?"}
    CheckStoreElig -->|Yes| StoreEntry["CacheRepository.store()\nINSERT INTO cache_entries\nEvict oldest if count > 1000"]
    CheckStoreElig -->|No| DiscardStore["Skip storage"]
```

---

## 5.9 Diagram 9: Virtual Key Authentication Flow

This diagram illustrates how API keys are authenticated securely without timing attacks.

```mermaid
flowchart TD
    Req["Incoming HTTP Request"] --> GetHeader["Extract 'x-api-key' Header"]

    GetHeader --> HasKey{"Key present & non-empty?"}
    HasKey -->|No| Err401Missing["Raise AuthenticationError(401)\n'Invalid or missing API key.'"]

    HasKey -->|Yes| HashKey["Compute SHA-256 Hash\nhash_api_key(raw_key)"]

    HashKey --> QueryDB["SQLiteKeyRepository.get_by_hash(hash)"]

    QueryDB --> KeyFound{"Record found in virtual_keys?"}
    KeyFound -->|No| Err401NotFound["Raise AuthenticationError(401)\n'Invalid or missing API key.'"]

    KeyFound -->|Yes| TimingSafe["hmac.compare_digest(provided_hash, db_hash)\n(Constant-time comparison)"]

    TimingSafe --> DigestMatch{"Digest matches?"}
    DigestMatch -->|No| Err401Mismatch["Raise AuthenticationError(401)\n'Invalid or missing API key.'"]

    DigestMatch -->|Yes| CheckActive{"key_config.status == 'active'?"}
    CheckActive -->|No| Err401Inactive["Raise AuthenticationError(401)\n'Invalid or missing API key.'"]

    CheckActive -->|Yes| Success["Attach VirtualKeyConfig to context.key_config\nRecord 'auth ok' in decision_trace"]
```

---

## 5.10 Diagram 10: Rate Limiting & Budget Enforcement Flow

This diagram demonstrates how rate limits and financial budgets are enforced before calling LLMs.

```mermaid
flowchart TD
    subgraph RateLimiting["Rate Limiting Stage (rate_limiter.py)"]
        RL_Start["Enforce Rate Limit"] --> RL_Lock["Acquire threading.Lock()"]
        RL_Lock --> RL_Calc["elapsed = now - last_refill_at\ntokens = min(rpm, tokens + elapsed * (rpm/60))"]
        RL_Calc --> RL_Check{"tokens >= 1.0?"}
        RL_Check -->|Yes| RL_Deduct["tokens -= 1.0\nRelease Lock\nRecord 'rate ok'"]
        RL_Check -->|No| RL_Fail["Release Lock\nRaise RateLimitError(429)\n'Rate limit exceeded'"]
    end

    subgraph BudgetEnforcement["Budget Enforcement Stage (budget.py)"]
        RL_Deduct --> B_Start["Enforce Monthly Budget"]
        B_Start --> B_Query["Query usage table for (key_hash, current_month)"]
        B_Query --> B_Check{"current_spend >= budget_usd?"}
        B_Check -->|Yes| B_Fail["Raise BudgetExceededError(429)\n'Monthly budget exceeded'"]
        B_Check -->|No| B_Success["Record 'budget ok ($spent/$limit)'\nProceed to Cache Stage"]
    end
```

---

## 5.11 Diagram 11: Centralized Error Handling Flow

This diagram illustrates how exceptions propagate from any stage or provider through to the client.

```mermaid
flowchart TD
    ExceptionRaised["Exception Raised in Stage, Executor, or Route"] --> HandlerMatch{"Exception Type?"}

    HandlerMatch -->|"PrismError Subclass\n(Auth, RateLimit, Budget, ModelNotAllowed, Upstream)"| PrismHandler["prism_error_handler"]
    HandlerMatch -->|"Any Other Python Exception\n(KeyError, ZeroDivisionError, etc.)"| UnexpHandler["unexpected_error_handler"]

    subgraph PrismProcessing["PrismError Processing"]
        PrismHandler --> ExtractMeta["status_code = exc.status_code\nerror_type = exc.error_type"]
        ExtractMeta --> Sanitize{"Is status_code == 502 (UpstreamError)?"}
        Sanitize -->|Yes| SafeMsg["message = 'An error occurred while processing your request with the upstream provider.'\n(Hide vendor internal errors)"]
        Sanitize -->|No| OrigMsg["message = str(exc)"]
        SafeMsg --> Check429{"Is status_code == 429?"}
        OrigMsg --> Check429
        Check429 -->|Yes| AddRetryHeader["Add Header: 'Retry-After: 60'"]
        Check429 -->|No| BuildJSON["Build JSON: {'error': {'message': message, 'type': error_type, 'code': status_code}}"]
        AddRetryHeader --> BuildJSON
    end

    subgraph UnexpectedProcessing["Unexpected Exception Processing"]
        UnexpHandler --> LogTrace["logger.exception('Unexpected internal server error')\n(Full traceback in server logs)"]
        LogTrace --> Build500JSON["Build 500 JSON:\n{'error': {'message': 'An unexpected internal error occurred.', 'type': 'internal_error', 'code': 500}}"]
    end

    BuildJSON --> SendResponse["Return JSONResponse to Client"]
    Build500JSON --> SendResponse
```

---
# 6. Complete Request Lifecycle

This section traces the execution path of the primary endpoint, `POST /v1/chat/completions`. We examine both the **Non-Streaming** and **Streaming** execution journeys step by step, identifying the exact files, functions, data structures, and state transitions at every stage.

---

## 6.1 Non-Streaming Request Journey (`stream: false`)

Imagine a client submits the following HTTP request:
```http
POST /v1/chat/completions HTTP/1.1
Host: localhost:3000
Content-Type: application/json
x-api-key: prism-sk-search-1a2b3c

{
  "model": "fast",
  "messages": [
    {"role": "user", "content": "What is the capital of Australia?"}
  ],
  "max_tokens": 100
}
```

Here is the exact journey this request takes through the system:

---

### Step 1: TCP Ingestion & ASGI Scope Creation
- **File:** `uvicorn` (ASGI Server)
- **Function/Class:** Internal Uvicorn TCP connection listener
- **What Happens:** Uvicorn accepts the raw TCP socket connection, parses the HTTP headers and JSON body into an ASGI connection scope, and invokes the registered FastAPI ASGI application callable.
- **Data Passed:** ASGI scope dictionary containing HTTP method (`POST`), path (`/v1/chat/completions`), and raw headers.
- **Next Component:** Starlette HTTP Middleware Stack.

---

### Step 2: Request ID Generation & Context Propagation
- **File:** `prism/api/middleware.py`
- **Function:** `request_id_middleware(request: Request, call_next)`
- **What Happens:**
  1. Generates a unique tracking identifier: `request_id = f"req_{uuid.uuid4().hex[:12]}"` (e.g., `req_9a8b7c6d5e4f`).
  2. Attaches the ID to `request.state.request_id`.
  3. Sets `request_id_context.set(request_id)` using Python's `contextvars.ContextVar`. This ensures that every subsequent log message emitted during this async task automatically prints this `request_id`.
  4. Starts high-resolution timer: `start_time = time.perf_counter()`.
  5. Calls `await call_next(request)`.
- **Data Passed:** Injected `request` object with state tracking.
- **Next Component:** FastAPI APIRouter (`prism/api/routes.py`).

---

### Step 3: Route Dispatch & `RequestContext` Initialization
- **File:** `prism/api/routes.py`
- **Function:** `chat_completions(payload: dict[str, Any], request: Request, response: Response)`
- **What Happens:**
  1. FastAPI parses the incoming JSON body into `payload: dict[str, Any]`.
  2. Extracts application singletons from `request.app.state` (`key_repository`, `usage_repository`, `log_repository`, `rate_limiter`, `clock`, `cache_service`). If any critical component is missing, raises `UpstreamError`.
  3. Records request start timestamp: `request_started_at = time.perf_counter()`.
  4. Instantiates the central state object, `RequestContext`:
     ```python
     context = RequestContext(
         request_id=request.state.request_id,
         model_requested="fast",
         messages=[{"role": "user", "content": "What is the capital of Australia?"}],
         stream=False,
         request_payload=payload.copy(),
         start_time=clock.now(),
     )
     ```
  5. Assembles the linear list of stages:
     `[auth_stage, validate_stage, rate_limit_stage, model_resolution_stage, allowlist_stage, budget_stage, cache_stage, provider_call_stage, meter_stage]`.
  6. Calls `await pipeline.run(context, stages=stages)`.
- **Data Passed:** The newly created `RequestContext` instance.
- **Next Component:** Pipeline Runner (`prism/services/pipeline.py`).

---

### Step 4: Pipeline Execution — Stage 1: Authentication
- **File:** `prism/services/stages/auth.py`
- **Function:** `authenticate_request(request, context, key_repository)`
- **What Happens:**
  1. Extracts the `x-api-key` header (`prism-sk-search-1a2b3c`).
  2. If missing or empty, raises `AuthenticationError("Invalid or missing API key.")` (HTTP 401).
  3. Computes SHA-256 hash using `hash_api_key(raw_key)` from `prism/domain/security.py`.
  4. Calls `key_repository.get_by_hash(provided_hash)` which executes:
     `SELECT * FROM virtual_keys WHERE key_hash = ?`.
  5. If not found in SQLite, raises `AuthenticationError` (401).
  6. Performs constant-time comparison: `hmac.compare_digest(provided_hash, key_config.key_hash)`.
  7. Checks `key_config.status.lower() == "active"`. If inactive/revoked, raises 401.
  8. Attaches the validated `VirtualKeyConfig` to `context.key_config`.
  9. Appends `"auth ok"` to `context.decision_trace`.
- **Data Passed:** `context` with populated `key_config`.
- **Next Component:** Validation Stage (`prism/services/stages/validate.py`).

---

### Step 5: Pipeline Execution — Stage 2: Payload Validation
- **File:** `prism/services/stages/validate.py`
- **Function:** `validate_request(payload, settings)`
- **What Happens:**
  1. Verifies `model` is a non-empty string (`"fast"`).
  2. Verifies `messages` is a non-empty array of objects, and every message has a non-empty string `role` and valid `content`.
  3. Inspects `max_tokens` (100). Enforces the maximum token cap:  
     `payload["max_tokens"] = min(max_tokens, settings.max_tokens_cap)` (e.g., `min(100, 4096) = 100`).
  4. Verifies `stream` is a boolean (defaults to `False`).
  5. Synchronizes validated values into `context.model_requested`, `context.messages`, and `context.stream`.
  6. Appends `"request validation ok"` to `context.decision_trace`.
- **Data Passed:** Validated `context`.
- **Next Component:** Rate Limiter Stage (`prism/services/stages/rate_limiter.py`).

---

### Step 6: Pipeline Execution — Stage 3: Rate Limiting (RPM)
- **File:** `prism/services/stages/rate_limiter.py`
- **Function:** `enforce_rate_limit(context, limiter)`
- **What Happens:**
  1. Extracts `key_hash` and `rpm_limit = context.key_config.rate_limit_rpm` (e.g., 60 RPM).
  2. Calls `limiter.try_acquire(key_hash, rpm_limit)` on the in-memory `TokenBucketRateLimiter`:
     - Acquires `self.lock`.
     - Calculates elapsed time since last request: `elapsed = (now - bucket.last_refill_at).total_seconds()`.
     - Refills tokens: `bucket.tokens = min(rpm_limit, bucket.tokens + elapsed * (rpm_limit / 60.0))`.
     - Checks if `bucket.tokens >= 1.0`.
     - If insufficient, releases lock and returns `False`. Stage raises `RateLimitError(429)`.
     - If sufficient, decrements `bucket.tokens -= 1.0`, releases lock, and returns `True`.
  3. Appends `"rate ok"` to `context.decision_trace`.
- **Data Passed:** Rate-checked `context`.
- **Next Component:** Model Resolution Stage (`prism/services/stages/resolve.py`).

---

### Step 7: Pipeline Execution — Stage 4: Model & Alias Resolution
- **File:** `prism/services/stages/resolve.py`
- **Function:** `resolve_model_candidates(context, loaded_config)`
- **What Happens:**
  1. Reads `context.model_requested` (`"fast"`).
  2. Checks if requested model is `"auto"`. (If `"auto"`, it would extract prompt text and invoke `HeuristicClassifier` to choose `fast` or `smart`).
  3. Looks up `"fast"` in `loaded_config.gateway_config.aliases`:
     - Finds `AliasConfig(alias_name="fast", primary_model="gpt-4o-mini", fallback_chain=["llama-3.3-70b-versatile"])`.
  4. Compiles candidate sequence: `candidates = ["gpt-4o-mini", "llama-3.3-70b-versatile"]`.
  5. Removes duplicates: `context.model_candidates = ["gpt-4o-mini", "llama-3.3-70b-versatile"]`.
  6. Assigns primary model: `context.model_resolved = "gpt-4o-mini"`.
  7. Appends `"alias 'fast' resolved"` and `"model candidates: gpt-4o-mini, llama-3.3-70b-versatile"` to `context.decision_trace`.
- **Data Passed:** `context` with resolved model candidates.
- **Next Component:** Allowlist Enforcement Stage (`prism/services/stages/allowlist.py`).

---

### Step 8: Pipeline Execution — Stage 5: Model Allowlist Check
- **File:** `prism/services/stages/allowlist.py`
- **Function:** `enforce_model_allowlist(context)`
- **What Happens:**
  1. Reads `allowed_models = context.key_config.model_allowlist`.
  2. If `"*"` is in `allowed_models`, appends `"model allowlist ok (wildcard)"` and proceeds.
  3. Otherwise, iterates over every candidate in `context.model_candidates` (`"gpt-4o-mini"`, `"llama-3.3-70b-versatile"`):
     - If any model is not in `allowed_models`, raises `ModelNotAllowedError` (HTTP 403).
  4. Appends `"model allowlist ok (gpt-4o-mini, llama-3.3-70b-versatile)"` to `context.decision_trace`.
- **Data Passed:** Permitted `context`.
- **Next Component:** Budget Enforcement Stage (`prism/services/stages/budget.py`).

---

### Step 9: Pipeline Execution — Stage 6: Monthly Budget Enforcement
- **File:** `prism/services/stages/budget.py`
- **Function:** `enforce_budget(context, usage_repository)`
- **What Happens:**
  1. Determines current calendar month: `month = datetime.now(timezone.utc).strftime("%Y-%m")` (e.g., `"2026-11"`).
  2. Queries SQLite via `usage_repository.get_usage(key_hash, month)`:
     `SELECT total_spend_usd, total_tokens, total_requests, cache_hits FROM usage WHERE key_hash = ? AND month = ?`.
  3. Checks `current_spend >= context.key_config.budget_usd`.
     - If spend has reached the limit (e.g., $50.00 spend on a $50.00 budget), raises `BudgetExceededError(429)`.
  4. If spend is within limits (e.g., $12.50 spent of $50.00), appends `"budget ok ($12.500000/$50.000000)"` to `context.decision_trace`.
- **Data Passed:** Budget-verified `context`.
- **Next Component:** Semantic Cache Stage (`prism/services/stages/cache.py`).

---

### Step 10: Pipeline Execution — Stage 7: Semantic Cache Lookup
- **File:** `prism/services/stages/cache.py` calling `prism/services/cache.py`
- **Function:** `CacheService.get_cached_response(context)`
- **What Happens:**
  1. Sets `context.cache_status = "miss"`.
  2. Checks eligibility via `_is_request_eligible(context)`:
     - Is `key_config.cache_enabled` True? Yes.
     - Scans prompt for `TIME_SENSITIVE_KEYWORDS` (`"now"`, `"today"`, etc.). None found.
  3. Serializes messages deterministically: `prompt = json.dumps(context.messages, sort_keys=True)`.
  4. Generates vector: `embedding = embedder.embed(prompt)` (256-dimension float list).
  5. Queries SQLite:
     ```sql
     SELECT id, key_hash, alias, embedding, response_body, hit_count, created_at
     FROM cache_entries
     WHERE key_hash = :key_hash AND alias = :alias
     ORDER BY hit_count DESC;
     ```
  6. Evaluates `cosine_similarity(embedding, row_embedding)` for all rows.
  7. If best similarity $\ge$ `key_config.cache_threshold` (e.g., 0.85):
     - **CACHE HIT:** Increments database `hit_count`, parses `response_body` into `ProviderResponse`, sets `context.provider_response = cached_response`, `context.cache_status = "hit"`, `context.cost_usd = 0.0`.
  8. If no entry meets the threshold:
     - **CACHE MISS:** Appends `"semantic cache miss"` to `context.decision_trace`.
- **Data Passed:** `context` with `cache_status = "miss"`.
- **Next Component:** Provider Call Stage (`prism/api/routes.py`).

---

### Step 11: Pipeline Execution — Stage 8: Resilient Upstream Execution
- **File:** `prism/api/routes.py` (inner function `provider_call_stage`)
- **What Happens:**
  1. Checks `if context.cache_status == "hit"`: If hit, skips provider call immediately.
  2. On miss: Resolves adapter mapping from `app.state.provider_adapters`:
     - Maps `"gpt-4o-mini"` to `OpenAICompatibleProvider(base_url="https://api.openai.com/v1")`.
     - Maps `"llama-3.3-70b-versatile"` to `OpenAICompatibleProvider(base_url="https://api.groq.com/openai/v1")`.
  3. Builds `providers = [ModelBoundProvider(adapter=openai, model="gpt-4o-mini"), ModelBoundProvider(adapter=groq, model="llama-3.3")]`.
  4. Instantiates `ResilientExecutor(providers=providers, max_retries=2, base_delay=1.0, request_timeout=30.0)`.
  5. Executes `execution_result = await executor.execute(context.request_payload)`.
     - **File:** `prism/services/executor.py`
     - Invokes candidate 1: `await adapter.complete(request)` inside `asyncio.timeout(30.0)`.
     - **File:** `prism/adapters/openai_compatible.py`:
       - Sends POST to `https://api.openai.com/v1/chat/completions` with `Authorization: Bearer <master_key>`.
       - Receives upstream JSON response (prompt_tokens: 15, completion_tokens: 20).
       - Constructs normalized `ProviderResponse`.
  6. Unpacks `execution_result`:
     - `context.provider_response = result`
     - `context.provider_name = "openai"`
     - `context.model_resolved = "gpt-4o-mini"`
     - `context.retry_count = 0`
     - `context.fallback_used = False`
  7. Calculates financial cost:
     - **File:** `prism/domain/cost.py`:
       `context.cost_usd = CostCalculator.calculate(15, 20, pricing["gpt-4o-mini"])`  
       $$= \frac{(15 \times 0.15) + (20 \times 0.60)}{1,000,000} = \$0.000014$$
  8. Caches the response:
     - Calls `cache_service.store_response(context)`.
     - Executes `INSERT INTO cache_entries (...)` in SQLite.
  9. Appends `"provider openai succeeded"`, `"cost: $0.000014"` to `context.decision_trace`.
- **Data Passed:** Completed `context` with response and metrics.
- **Next Component:** Meter Stage (`prism/api/routes.py`).

---

### Step 12: Pipeline Execution — Stage 9: Usage Metering
- **File:** `prism/api/routes.py` (inner function `meter_stage`)
- **What Happens:**
  1. Calls `record_usage_for_completion(context, usage_repository)`.
  2. Calls `usage_repository.record_usage()` in `prism/adapters/sqlite_repos.py`.
  3. Executes atomic upsert in SQLite:
     ```sql
     INSERT INTO usage (key_hash, month, total_spend_usd, total_tokens, total_requests, cache_hits)
     VALUES (:hash, '2026-11', 0.000014, 35, 1, 0)
     ON CONFLICT(key_hash, month) DO UPDATE SET
         total_spend_usd = total_spend_usd + 0.000014,
         total_tokens = total_tokens + 35,
         total_requests = total_requests + 1;
     ```
- **Data Passed:** Metered `context`.
- **Next Component:** Pipeline returns to `chat_completions()` in `routes.py`.

---

### Step 13: Request Audit Logging
- **File:** `prism/api/routes.py`
- **Function:** `save_request_log(request, context, log_repository, status_code=200, ...)`
- **What Happens:**
  1. Calculates total request latency: `latency_ms = int((time.perf_counter() - request_started_at) * 1000)`.
  2. Constructs `LogEntry`:
     - `request_id = "req_9a8b7c6d5e4f"`
     - `key_hash = "..."`
     - `model_requested = "fast"`
     - `model_resolved = "gpt-4o-mini"`
     - `provider = "openai"`
     - `status_code = 200`
     - `prompt_tokens = 15`, `completion_tokens = 20`, `cost_usd = 0.000014`
     - `cache_result = "miss"`, `fallback_used = False`, `retries = 0`
     - `latency_ms = 420`
     - `decision_trace = ["auth ok", ..., "cost: $0.000014"]`
  3. Writes to SQLite: `INSERT INTO request_logs (...)`.
- **Next Component:** Response Header Formatting.

---

### Step 14: Response Header Injection & Serialization
- **File:** `prism/api/routes.py`
- **Function:** `set_context_headers(response, context)` and `format_completion_response(provider_response)`
- **What Happens:**
  1. Injects required Prism response headers onto the outgoing HTTP response:
     - `x-prism-request-id: req_9a8b7c6d5e4f`
     - `x-prism-provider: openai/gpt-4o-mini`
     - `x-prism-cache: miss`
     - `x-prism-fallback: false`
     - `x-prism-cost-usd: 0.000014`
  2. Formats the completion into the standard OpenAI JSON envelope:
     ```json
     {
       "id": "chatcmpl-a1b2c3d4e5f6",
       "object": "chat.completion",
       "created": 1731408000,
       "model": "gpt-4o-mini",
       "choices": [
         {
           "index": 0,
           "message": {
             "role": "assistant",
             "content": "The capital of Australia is Canberra."
           },
           "finish_reason": "stop"
         }
       ],
       "usage": {
         "prompt_tokens": 15,
         "completion_tokens": 20,
         "total_tokens": 35
       }
     }
     ```
  3. Returns the dictionary to FastAPI.
- **Next Component:** Middleware Exit Phase.

---

### Step 15: Middleware Exit & Client Delivery
- **File:** `prism/api/middleware.py`
- **What Happens:**
  1. `await call_next(request)` completes.
  2. Calculates total duration, logs structured JSON log:
     ```json
     {"timestamp": "2026-11-12T10:50:00Z", "level": "INFO", "message": "HTTP request completed", "request_id": "req_9a8b7c6d5e4f", "method": "POST", "path": "/v1/chat/completions", "status_code": 200, "duration_ms": 421.5}
     ```
  3. In `finally:`, resets the `request_id_context` ContextVar.
  4. Uvicorn serializes HTTP response bytes and delivers them over TCP to the client.

---

## 6.2 Streaming Request Journey (`stream: true`)

When a client sends `"stream": true`, the request lifecycle branches to deliver chunks with near-zero latency while preserving financial and audit tracking.

---

### Phase 1: Upfront Verification (Identical to Non-Streaming)
Stages 1 through 7 run **identically** to non-streaming:
1. `auth_stage`: Validates virtual key (401 if invalid).
2. `validate_stage`: Validates schema, caps `max_tokens`, detects `stream=True`.
3. `rate_limit_stage`: Consumes 1 token from the RPM bucket (429 if throttled).
4. `model_resolution_stage`: Resolves `"fast"` to `["gpt-4o-mini", "llama-3.3-70b-versatile"]`.
5. `allowlist_stage`: Verifies candidate models are permitted.
6. `budget_stage`: Verifies month-to-date spend is below budget.
7. `cache_stage`: Searches semantic cache.

---

### Phase 2: Pipeline Branching for Streaming
- **File:** `prism/api/routes.py` (`provider_call_stage` and `meter_stage`)
- **What Happens:**
  1. In `provider_call_stage`: It checks `if context.stream:`.
  2. Unlike non-streaming, it **does not invoke `ResilientExecutor`**. Instead, it selects the primary model (`"gpt-4o-mini"`), retrieves its adapter, sets `context.model_resolved = "gpt-4o-mini"`, and returns immediately.
  3. In `meter_stage`: It checks `if context.stream and context.cache_status != "hit": return context`. Because the final token count of an upstream stream is unknown until the stream finishes, metering is deferred!
  4. Pipeline execution finishes.

---

### Phase 3: Response Construction
- **File:** `prism/api/routes.py`
- **What Happens:**
  1. Constructs streaming HTTP headers via `build_streaming_headers(context)`:
     - `Content-Type: text/event-stream`
     - `Cache-Control: no-cache`
     - `X-Accel-Buffering: no`
     - `x-prism-request-id`, `x-prism-provider`, `x-prism-cache`, `x-prism-fallback`
  2. **Branch A: If Semantic Cache Hit:**  
     Returns `StreamingResponse(format_cached_streaming_body(...))`. The cached response text is split and replayed as simulated SSE chunks to the client, and usage is recorded.
  3. **Branch B: If Semantic Cache Miss:**  
     Retrieves the upstream provider stream: `provider_stream = adapter.stream(context.request_payload)`.  
     Wraps it in `format_streaming_body(...)` and returns `StreamingResponse(streaming_body, media_type="text/event-stream", headers=headers)`.

---

### Phase 4: The Streaming Tee Pattern & Upstream Forwarding
- **Files:** `prism/api/routes.py` (`format_streaming_body`) and `prism/services/streaming.py` (`stream_response`)
- **What Happens:**
  1. `stream_response` requests the next chunk from the upstream provider using `asyncio.wait_for(anext(provider_stream), timeout=idle_timeout)`.
  2. When OpenAI/Groq sends an SSE chunk:
     `data: {"choices": [{"delta": {"content": "Hello"}, "finish_reason": null}]}`
  3. `stream_response` yields the formatted string `data: {...}\n\n` to `format_streaming_body`.
  4. **The TEE Operation in `format_streaming_body`:**
     - `format_streaming_body` yields the chunk immediately to FastAPI's network pipe: `yield formatted_chunk` (Client sees the word "Hello" instantly).
     - Simultaneously, it parses the JSON delta and appends `"Hello"` to an internal in-memory buffer: `response_parts.append("Hello")`.
  5. **Usage Capture:**  
     When the provider sends the final usage chunk:
     `data: {"choices": [], "usage": {"prompt_tokens": 15, "completion_tokens": 20}}`  
     `stream_response` calls `update_stream_usage(usage, context)`.
  6. **Stream Termination:**  
     Provider sends `data: [DONE]\n\n`. The loop terminates.

---

### Phase 5: Deferred Metering, Caching, and Logging in `finally:`
Even if the client closes their connection early (`asyncio.CancelledError`) or the provider crashes mid-stream, the `finally:` blocks in `streaming.py` and `routes.py` are guaranteed to execute:
1. **Closing Upstream Connection:** Calls `await close_provider_stream(provider_stream)`.
2. **Deferred Usage Metering:** Calls `await record_stream_usage(...)`. Computes real cost using observed tokens via `CostCalculator.calculate()`, and atomically updates SQLite `usage`.
3. **Semantic Cache Storage:** If the stream completed successfully (status 200), `format_streaming_body` joins `"".join(response_parts)` to reconstruct the full response, builds a `ProviderResponse`, and calls `cache_service.store_response(context)`. The completion is now cached for future users!
4. **Audit Logging:** Calls `save_request_log(...)` to record the streaming request in SQLite with final token counts, cost, and status code (200 for success, 499 for client disconnect, 502 for upstream error).

---
# 7. Architecture Decisions — WHY?

Every significant engineering decision in Prism is evaluated below using a rigorous 7-point software architecture framework:
1. **What was implemented?**
2. **Why was it necessary?**
3. **What problem does it solve?**
4. **What alternatives exist?**
5. **Why is the chosen approach better?**
6. **What are its trade-offs?**
7. **Is it implemented correctly in this project?**

---

## 7.1 Decision 1: FastAPI over Flask / Django

1. **What was implemented?**  
   FastAPI was chosen as the HTTP presentation framework, mounted on Uvicorn.
2. **Why was it necessary?**  
   An LLM gateway acts as a proxy that spends over 95% of its execution time waiting for network packets from third-party APIs (OpenAI, Groq). Handling hundreds of simultaneous long-lived connections requires an asynchronous event loop.
3. **What problem does it solve?**  
   Synchronous frameworks (like traditional Flask or Django) allocate one operating system thread per active connection. If 100 clients stream completions concurrently, 100 OS threads remain blocked, exhausting memory and context-switching capacity.
4. **What alternatives exist?**  
   Flask (WSGI), Django (traditional WSGI), Tornado, AIOHTTP, Sanic, Express.js (Node.js), Go (`net/http`).
5. **Why is the chosen approach better?**  
   FastAPI natively supports Python's `asyncio` ecosystem, integrates Starlette's high-performance `StreamingResponse` for Server-Sent Events, provides automatic OpenAPI/Swagger documentation, and natively integrates Pydantic validation.
6. **What are its trade-offs?**  
   Any synchronous call (such as Python's standard `sqlite3` driver) executed on the main thread will block the event loop, degrading concurrency. Developers must be disciplined with `async`/`await`.
7. **Is it implemented correctly in this project?**  
   **Yes.** Endpoints are defined as `async def`, streaming uses `StreamingResponse`, and exceptions are handled via Starlette exception handlers. (Caveat: SQLite queries are synchronous; see Section 10).

---

## 7.2 Decision 2: Pydantic v2 for Domain Validation & Configurations

1. **What was implemented?**  
   Pydantic v2 (`BaseModel`, `Field`) validates internal domain models (`VirtualKeyConfig`, `ProviderResponse`, `RequestContext`, `GatewayConfig`).
2. **Why was it necessary?**  
   Backend gateways ingest external untrusted data (JSON configuration files, database records, API responses). Silent type errors or negative numbers (e.g., negative budget, negative tokens) can cause severe business and financial corruption.
3. **What problem does it solve?**  
   Eliminates manual runtime validation boilerplate. Prevents malformed data from penetrating beyond the outer boundaries into the core domain.
4. **What alternatives exist?**  
   Standard Python `@dataclass`, `marshmallow`, `attrs`, manual `if/else` assertion checks.
5. **Why is the chosen approach better?**  
   Pydantic v2 has its core validation engine written in Rust, making it up to 20x faster than pure Python validators. It provides expressive constraint declarations (`Field(ge=0, gt=0, le=1)`) and seamless JSON serialization via `.model_dump(mode="json")`.
6. **What are its trade-offs?**  
   Pydantic instances incur slightly higher memory overhead than pure Python tuples or lightweight dataclasses.
7. **Is it implemented correctly in this project?**  
   **Yes.** All critical domain models use Pydantic v2 with explicit field constraints. Pure in-memory constructs (like `TokenBucket` in `limiter.py` and `ExecutionResult` in `executor.py`) use `@dataclass` where serialization is not needed.

---

## 7.3 Decision 3: Clean Architecture (Hexagonal / Ports and Adapters)

1. **What was implemented?**  
   The codebase is partitioned into distinct layers: `domain` (pure rules), `ports` (abstract interfaces), `adapters` (concrete infrastructure), `services` (orchestration), and `api` (HTTP presentation).
2. **Why was it necessary?**  
   Decoupling business logic from third-party tools ensures that infrastructure changes (e.g., migrating from SQLite to Postgres, or swapping OpenAI for Anthropic) do not require rewriting domain rules.
3. **What problem does it solve?**  
   Prevents "Spaghetti Architecture," where SQL queries, HTTP calls, rate limiting math, and JSON serialization are tangled in a single route handler.
4. **What alternatives exist?**  
   Traditional 3-tier MVC (Model-View-Controller), monolithic single-script designs, Django-style fat models.
5. **Why is the chosen approach better?**  
   Enables 100% offline, deterministic unit testing. Services interact exclusively with abstract ports, allowing tests to inject `FakeAdapter` and `FakeClock` without spinning up databases or internet connections.
6. **What are its trade-offs?**  
   Introduces indirection: creating ports and adapters requires more files and boilerplate code than writing SQL queries directly in route handlers.
7. **Is it implemented correctly in this project?**  
   **Mostly Yes, with one minor architectural violation:** In `prism/services/cache.py`, the service imports concrete classes (`BowEmbedder` and `CacheRepository`) from `prism.adapters` rather than depending exclusively on `prism.ports.embedder.Embedder` and `prism.ports.repositories.CacheRepository`. This is noted as an audit improvement in Section 9.

---

## 7.4 Decision 4: Unified OpenAI-Compatible Provider Adapter

1. **What was implemented?**  
   A single concrete adapter class, `OpenAICompatibleProvider`, implements `ProviderAdapter` and powers both OpenAI and Groq (as well as local mock servers).
2. **Why was it necessary?**  
   Modern LLM inference engines (OpenAI, Groq, Together AI, vLLM, Ollama) all adhere to OpenAI's `/v1/chat/completions` REST and SSE specification.
3. **What problem does it solve?**  
   Prevents duplicate code. Writing separate `OpenAIProvider`, `GroqProvider`, and `MockProvider` classes would duplicate hundreds of lines of identical HTTP connection management, SSE parsing, and error-handling code.
4. **What alternatives exist?**  
   Separate SDK wrappers for each vendor (e.g., `openai-python`, `groq-python`).
5. **Why is the chosen approach better?**  
   Zero external vendor SDK dependencies. The gateway talks directly to HTTP endpoints via `httpx.AsyncClient`. Switching a provider is as simple as configuring `base_url` and `api_key`.
6. **What are its trade-offs?**  
   Cannot easily leverage proprietary, vendor-specific non-OpenAI endpoints (e.g., Anthropic's native XML protocol or Google Vertex AI's gRPC protocol) without adding protocol translation logic.
7. **Is it implemented correctly in this project?**  
   **Yes.** Handles both non-streaming and streaming SSE parsing, timeout configuration, and header building cleanly.

---

## 7.5 Decision 5: Abstract Base Classes (ABCs) as Port Contracts

1. **What was implemented?**  
   Python's `abc.ABC` and `@abstractmethod` define interfaces in `prism/ports/` (`ProviderAdapter`, `KeyRepository`, `UsageRepository`, `LogRepository`, `Clock`, `Embedder`).
2. **Why was it necessary?**  
   Python does not have a native `interface` keyword like Java or TypeScript. Without formal contracts, subclasses might implement incompatible method signatures.
3. **What problem does it solve?**  
   Fails fast at instantiation time. If a new adapter fails to implement a required method (e.g., forgets to implement `.stream()`), Python raises a `TypeError` immediately upon class creation rather than failing in production.
4. **What alternatives exist?**  
   Python `typing.Protocol` (structural subtyping / duck typing), standard un-inherited classes.
5. **Why is the chosen approach better?**  
   Explicit inheritance makes system hierarchy obvious in IDEs and enforces strict signature adherence.
6. **What are its trade-offs?**  
   Requires inheriting from `ABC`, adding minor metaclass overhead.
7. **Is it implemented correctly in this project?**  
   **Partially.** `ProviderAdapter`, `KeyRepository`, `UsageRepository`, `LogRepository`, and `Embedder` are defined as ABCs. However, `CacheRepository` in `prism/adapters/sqlite_repos.py` does not explicitly inherit from `prism.ports.repositories.CacheRepository` (though it implements all matching methods).

---

## 7.6 Decision 6: Dependency Injection via `app.state` vs FastAPI `Depends`

1. **What was implemented?**  
   Application singletons (repositories, limiters, adapters, configs) are created once during startup in `lifespan(app)` and stored on `app.state`. Endpoints read them from `request.app.state`.
2. **Why was it necessary?**  
   Components like the `TokenBucketRateLimiter` maintain in-memory state that must be shared across all concurrent requests.
3. **What problem does it solve?**  
   Prevents recreating database connections, HTTP clients, and rate limiters on every single incoming HTTP request, which would destroy performance and erase rate limiting counters.
4. **What alternatives exist?**  
   FastAPI's built-in `Depends()` injection system, global module variables, dependency injection libraries (e.g., `injector`, `dependency-injector`).
5. **Why is the chosen approach better?**  
   A single, transparent **Composition Root** in `prism/main.py`. Startup sequence is crystal clear. Zero per-request dependency resolution overhead.
6. **What are its trade-offs?**  
   Attributes on `app.state` are untyped at the route level, requiring `getattr()` checks or type-casting. Overriding dependencies in tests requires setting `app.state` attributes rather than using FastAPI's `app.dependency_overrides`.
7. **Is it implemented correctly in this project?**  
   **Yes.** Route handlers safely verify singletons using `getattr(request.app.state, "key_repository", None)` and raise clean 502 errors if unconfigured.

---

## 7.7 Decision 7: Async/Await Event Loop Concurrency vs Thread Pools

1. **What was implemented?**  
   The entire gateway pipeline is built on Python's native `asyncio` event loop.
2. **Why was it necessary?**  
   LLM requests have high latency (typically 500ms to 10 seconds for streaming completions). A thread-per-request model would exhaust system thread limits under moderate traffic.
3. **What problem does it solve?**  
   Enables a single Python process to multiplex thousands of concurrent open HTTP/SSE connections with minimal RAM and CPU context-switching overhead.
4. **What alternatives exist?**  
   Thread pools (`ThreadPoolExecutor`), multi-process workers (`Gunicorn` with sync workers), reactive event loops (Node.js/Go).
5. **Why is the chosen approach better?**  
   Standard modern Python paradigm. Works seamlessly with `httpx.AsyncClient` and Starlette's asynchronous streaming generators.
6. **What are its trade-offs?**  
   Any synchronous blocking CPU work or disk I/O blocks the entire process.
7. **Is it implemented correctly in this project?**  
   **Yes.** Network calls to providers use `await` and `async for`.

---

## 7.8 Decision 8: SQLite with WAL Mode & In-Memory Limiting vs Redis

1. **What was implemented?**  
   Local persistence in a single SQLite database (`prism.db`) configured with `PRAGMA journal_mode=WAL` and `PRAGMA busy_timeout=5000`. Rate limits are stored in in-memory dictionaries.
2. **Why was it necessary?**  
   Provides a self-contained, zero-infrastructure operational deployment. The gateway runs out-of-the-box without requiring operators to provision, authenticate, and maintain external Redis or PostgreSQL clusters.
3. **What problem does it solve?**  
   Eliminates operational complexity and external points of failure for standalone gateway deployments.
4. **What alternatives exist?**  
   Redis (for distributed rate limiting and caching), PostgreSQL/MySQL (for relational storage).
5. **Why is the chosen approach better?**  
   - Zero operational overhead: Single file database.
   - WAL (Write-Ahead Logging) mode allows multiple concurrent readers to proceed without blocking writers.
   - SQLite queries execute in memory via OS page cache in sub-millisecond time.
6. **What are its trade-offs?**  
   - **Horizontal Scaling Limit:** Because rate limiting and SQLite locks are local to a single node, running multiple load-balanced instances of Prism would result in uncoordinated rate limits and database file locking conflicts.
   - For multi-instance horizontal scaling, the rate limiter must be migrated to Redis and SQLite replaced with Postgres.
7. **Is it implemented correctly in this project?**  
   **Yes.** Configures WAL mode, busy timeout, foreign keys, and atomic upsert statements.

---

## 7.9 Decision 9: The Streaming "Tee" Pattern

1. **What was implemented?**  
   In `prism/api/routes.py` (`format_streaming_body`), as SSE chunks pass through from the provider to the client, an internal buffer taps ("tees") the stream, accumulating text deltas into a complete response.
2. **Why was it necessary?**  
   In traditional architectures, streaming and caching are mutually exclusive: you either stream tokens immediately (and lose the ability to cache the completed text), or you buffer the whole response to cache it (destroying streaming latency).
3. **What problem does it solve?**  
   Allows real-time, low-latency streaming to the client while simultaneously assembling the full text so it can be stored in the semantic cache once the stream finishes successfully!
4. **What alternatives exist?**  
   - Do not cache streaming responses at all.
   - Full response buffering (delaying stream delivery until generation completes).
5. **Why is the chosen approach better?**  
   Zero compromise: The client experiences instant Time-to-First-Token (TTFT), and subsequent clients requesting the same prompt benefit from a cache hit!
6. **What are its trade-offs?**  
   Requires in-memory list buffering (`response_parts.append(content)`), consuming a few kilobytes of RAM per active stream.
7. **Is it implemented correctly in this project?**  
   **Yes.** Cleanly buffers chunks, captures usage, constructs `ProviderResponse` in `finally:`, and stores in `cache_service`.

---

## 7.10 Decision 10: Retries, Exponential Backoff, Jitter, and Failover

1. **What was implemented?**  
   `ResilientExecutor` wraps upstream calls. It categorizes errors into `fatal`, `retryable`, or `failover`. It retries transient errors on the same provider with randomized exponential backoff, and fails over to secondary candidate models when a provider is rate limited (429) or down.
2. **Why was it necessary?**  
   Third-party AI APIs suffer from frequent transient degradation. Without resilience, transient upstream errors crash client applications.
3. **What problem does it solve?**  
   Shields clients from vendor instability. Transparently fails over from OpenAI to Groq without the client noticing.
4. **What alternatives exist?**  
   No retries (fail immediately), fixed-interval retries, external circuit breaker libraries (e.g., `pybreaker`, Envoy/Istio service mesh).
5. **Why is the chosen approach better?**  
   - Full jitter prevents thundering herd spikes against recovering upstream servers.
   - Categorizing 429 as "failover" avoids wasting time retrying a vendor that has explicitly throttled the gateway.
6. **What are its trade-offs?**  
   Retries and failover increase end-to-end request latency when failures occur. Only applies to non-streaming requests (per ADR-002, mid-stream failover is rejected to prevent incoherent spliced text).
7. **Is it implemented correctly in this project?**  
   **Yes.** Fully verified by automated test suites in `tests/integration/test_failover.py` and `tests/unit/test_executor.py`.

---

## 7.11 Decision 11: Virtual API Keys with SHA-256 Hashing

1. **What was implemented?**  
   Tenants authenticate using proxy keys (`prism-sk-...`). Keys are hashed using SHA-256 before storage or comparison, and validated using constant-time `hmac.compare_digest`.
2. **Why was it necessary?**  
   Stops vendor key sprawl. Master vendor keys remain strictly in server environment variables.
3. **What problem does it solve?**  
   Prevents credential leakage. Even if an attacker gains read access to `prism.db`, they only obtain one-way SHA-256 hashes, from which original keys cannot be recovered.
4. **What alternatives exist?**  
   Storing raw keys in SQLite; OAuth2 / JWT tokens; API gateway plugins (Kong, AWS API Gateway).
5. **Why is the chosen approach better?**  
   Emulates standard developer expectations (OpenAI/Stripe style keys). `hmac.compare_digest` eliminates timing attack vulnerabilities.
6. **What are its trade-offs?**  
   Because keys are hashed, lost keys cannot be recovered; they must be revoked and regenerated.
7. **Is it implemented correctly in this project?**  
   **Yes.** Implemented in `prism/domain/security.py`, `prism/services/stages/auth.py`, and `prism/config/loader.py`.

---

## 7.12 Decision 12: In-Memory Rate Limiting & Bounded Budget Overshoot

1. **What was implemented?**  
   - ADR-001: Cache hits consume rate limits but are allowed even if the budget is exhausted.
   - ADR-003: "Admit-then-record" budget enforcement for streaming requests, accepting a bounded overshoot.
2. **Why was it necessary?**  
   - Rate limiting must protect internal gateway infrastructure (cache lookup still costs CPU).
   - In streaming, token counts and costs are unknown until the final SSE chunk arrives.
3. **What problem does it solve?**  
   Solves the timing paradox of enforcing budgets on streaming requests without buffering.
4. **What alternatives exist?**  
   - Pre-flight token reservation (unreliable and requires complex tokenizers).
   - Buffer full streaming responses (destroys streaming latency).
5. **Why is the chosen approach better?**  
   Streaming remains instant. The maximum potential financial overshoot is strictly bounded:  
   $$\text{Max Overshoot} \approx \text{Concurrent Streams} \times \text{max\_tokens\_cap} \times \text{output\_price}$$  
   For typical models, this represents less than $0.05 per concurrent stream.
6. **What are its trade-offs?**  
   A tenant can slightly exceed their configured budget limit if multiple streams run concurrently as the budget is exhausted.
7. **Is it implemented correctly in this project?**  
   **Yes.** Budget stage runs before cache, and streaming records usage in `finally:`.

---

## 7.13 Decision 13: Strict Separation of Boot Configuration from Runtime Logic

1. **What was implemented?**  
   `prism/config/loader.py` validates all JSON configuration files (`seed_keys.json`, `model_pricing.json`, `gateway_config.json`) during application startup, raising `ConfigLoadError` on any defect.
2. **Why was it necessary?**  
   Runtime configuration errors (e.g., a key referencing an unpriced model, or duplicate model pricing) should never surface as 500 errors during client requests hours after deployment.
3. **What problem does it solve?**  
   Enforces "Fail-Fast" behavior: the gateway refuses to start if configuration is invalid.
4. **What alternatives exist?**  
   Lazy loading config files on demand during requests; hardcoding models in code.
5. **Why is the chosen approach better?**  
   Guarantees that once the server is running, all aliases, pricing maps, and key structures are 100% valid and verified.
6. **What are its trade-offs?**  
   Updating configuration files requires restarting the server (or implementing hot-reloading).
7. **Is it implemented correctly in this project?**  
   **Yes.** Validates cross-references between aliases and pricing tables at boot.

---

## 7.14 Decision 14: Heuristic Intent Routing with Train/Eval Separation

1. **What was implemented?**  
   - ADR-007: Requests for `auto` route through `HeuristicClassifier` to pick `fast` or `smart`. The tenant's allowlist must explicitly permit both `auto` and the resolved model.
   - ADR-008: Router heuristics were developed strictly against `training_examples.jsonl`, keeping `routing_eval.jsonl` as an untouched, held-out evaluation exam.
2. **Why was it necessary?**  
   To evaluate prompt difficulty without paying for an upstream LLM call, while maintaining machine learning evaluation integrity.
3. **What problem does it solve?**  
   Prevents "overfitting" or "peeking at the exam" during classifier development, ensuring accuracy measurements reflect true generalization.
4. **What alternatives exist?**  
   Calling an LLM (e.g., `gpt-4o-mini`) to classify every prompt; using a length-only heuristic.
5. **Why is the chosen approach better?**  
   The heuristic classifier executes in microseconds using compiled regex patterns for math, code, and keywords, outperforming length-only baselines by over 20% on the eval set at zero financial cost.
6. **What are its trade-offs?**  
   Keyword heuristics can be tricked by adversarial or ambiguous phrasing that lacks obvious keyword markers.
7. **Is it implemented correctly in this project?**  
   **Yes.** Implemented in `prism/services/router.py` and evaluated via `scripts/routing_eval.py`.

---
# 8. Explain the Actual Code

This section walks through the core production implementation files block by block. We explain what each code block does, why specific variables and imports exist, how data moves across layers, and how errors propagate.

---

## 8.1 Composition Root: `prism/main.py`

`main.py` is the application entrypoint. Its sole architectural responsibility is assembling and wiring the system dependencies.

### Block 1: Imports and Application Setup
```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from prism.adapters.sqlite_repos import init_database, SQLiteKeyRepository, ...
from prism.config.settings import Settings
from prism.config.loader import load_configuration
...
logger = get_logger(__name__)
```
- **Why these imports?** `asynccontextmanager` enables modern FastAPI startup/shutdown lifecycles. It imports concrete adapters from `prism.adapters` and configuration loaders from `prism.config`.
- Notice that while inner services (`executor.py`, `pipeline.py`) do not import concrete adapters, `main.py` **must** import them because this is the **Composition Root** where concrete instances are instantiated.

### Block 2: The Lifespan Context Manager
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Load configuration and settings
    settings = Settings.from_env()
    loaded_config = load_configuration()

    # 2. Initialize database schema
    database_path = settings.db_path
    init_database(database_path)

    # 3. Seed virtual keys
    key_repository = SQLiteKeyRepository(database_path)
    key_repository.seed_keys(loaded_config.seed_keys)

    # 4. Instantiate singletons
    usage_repository = SQLiteUsageRepository(database_path)
    log_repository = SQLiteLogRepository(database_path)
    cache_repository = CacheRepository(database_path)
    cache_embedder = BowEmbedder()
    cache_service = CacheService(embedder=cache_embedder, repository=cache_repository)
    clock = SystemClock()
    rate_limiter = TokenBucketRateLimiter(clock)

    # 5. Validate master credentials
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is missing. Add it to your .env file.")
    if not settings.groq_api_key:
        raise RuntimeError("GROQ_API_KEY is missing. Add it to your .env file.")

    # 6. Initialize provider adapters
    openai_provider = OpenAICompatibleProvider(
        base_url=settings.openai_base_url,
        api_key=settings.openai_api_key,
        connect_timeout=settings.connect_timeout_seconds,
        request_timeout=settings.provider_timeout_seconds,
    )
    groq_provider = OpenAICompatibleProvider(
        base_url=settings.groq_base_url,
        api_key=settings.groq_api_key,
        connect_timeout=settings.connect_timeout_seconds,
        request_timeout=settings.provider_timeout_seconds,
    )

    provider_adapters = {
        "gpt-4o-mini": openai_provider,
        "llama-3.3-70b-versatile": groq_provider,
    }

    # 7. Attach to application state
    app.state.key_repository = key_repository
    app.state.usage_repository = usage_repository
    app.state.log_repository = log_repository
    app.state.cache_service = cache_service
    app.state.rate_limiter = rate_limiter
    app.state.provider_adapters = provider_adapters
    app.state.admin_token = settings.admin_token
    ...
    yield
    logger.info("Prism application shutting down")
```
- **How data moves:** Environment variables flow through `Settings.from_env()`; JSON files flow through `load_configuration()`.
- **Fail-Fast Mechanism:** If `OPENAI_API_KEY` is missing or `seed_keys.json` is corrupt, this code raises an exception *before* `yield`. Uvicorn halts immediately, preventing the server from running in a half-configured state.
- **Why `provider_adapters` dictionary?** Maps the exact model name string (`"gpt-4o-mini"`) to its corresponding physical HTTP adapter instance.

### Block 3: App Instantiation, Middleware, and Route Mounting
```python
app = FastAPI(title="Prism LLM Gateway", lifespan=lifespan)

app.middleware("http")(request_id_middleware)
app.add_exception_handler(PrismError, prism_error_handler)
app.add_exception_handler(Exception, unexpected_error_handler)

app.include_router(router)
app.include_router(admin_router)
```
- Middleware is attached first so it wraps all requests.
- Exception handlers are registered globally.
- Routers are mounted to expose endpoints.

---

## 8.2 Core Domain State: `prism/domain/models.py`

This file defines the domain models. The most important class in the entire gateway is **`RequestContext`**.

```python
class RequestContext(BaseModel):
    request_id: str
    key_config: VirtualKeyConfig | None = None

    model_requested: str = ""
    model_resolved: str | None = None
    provider_name: str | None = None

    model_candidates: list[str] = Field(default_factory=list)
    retry_count: int = Field(default=0, ge=0)

    messages: list[dict[str, Any]] = Field(default_factory=list)
    stream: bool = False

    request_payload: dict[str, Any] = Field(default_factory=dict)
    provider_response: ProviderResponse | None = None

    stream_prompt_tokens: int = Field(default=0, ge=0)
    stream_completion_tokens: int = Field(default=0, ge=0)

    decision_trace: list[str] = Field(default_factory=list)
    start_time: datetime

    cache_status: str = "miss"
    fallback_used: bool = False
    cost_usd: float = Field(default=0.0, ge=0)
```

### Why this class exists and what its variables represent:
- `RequestContext` is a **Parameter Object** / **Context Object**. Instead of passing 15 individual arguments between pipeline stages, a single `context` reference is passed.
- `key_config`: Initially `None`. Stage 1 (`auth`) sets this after validating the API key. Subsequent stages (`rate_limit`, `budget`, `allowlist`) read tenant limits directly from it.
- `model_requested` vs `model_resolved`: If the client requests `"fast"`, `model_requested` is `"fast"`, but Stage 4 (`resolve`) sets `model_resolved = "gpt-4o-mini"`.
- `model_candidates`: Ordered list of models (`["gpt-4o-mini", "llama-3.3-70b-versatile"]`).
- `decision_trace`: An audit trail of strings (`["auth ok", "request validation ok", "rate ok", "alias 'fast' resolved", "budget ok", "semantic cache miss", "provider openai succeeded"]`). If a request fails or returns an unexpected answer, the operator can inspect this trace in `request_logs` to see the exact decision-making process.
- `cost_usd`: Tracks calculated cost. Defaults to `0.0`. If a cache hit occurs, it remains `0.0`. On completion, it is set to the true cost.

---

## 8.3 In-Memory Rate Limiting: `prism/domain/limiter.py`

`TokenBucketRateLimiter` enforces per-minute quotas using the standard Token Bucket algorithm.

```python
@dataclass
class TokenBucket:
    tokens: float
    last_refill_at: datetime

class TokenBucketRateLimiter:
    def __init__(self, clock: Clock) -> None:
        self.clock = clock
        self.buckets: dict[str, TokenBucket] = {}
        self.lock = threading.Lock()

    def try_acquire(self, key_hash: str, rpm_limit: int) -> bool:
        if rpm_limit <= 0:
            raise ValueError("rpm_limit must be greater than zero")

        with self.lock:
            now = self.clock.now()
            bucket = self.buckets.get(key_hash)

            if bucket is None:
                # Brand new tenant: start with a full bucket
                bucket = TokenBucket(tokens=float(rpm_limit), last_refill_at=now)
                self.buckets[key_hash] = bucket
            else:
                elapsed_seconds = (now - bucket.last_refill_at).total_seconds()
                if elapsed_seconds > 0:
                    refill_rate = rpm_limit / 60.0
                    tokens_to_add = elapsed_seconds * refill_rate
                    bucket.tokens = min(float(rpm_limit), bucket.tokens + tokens_to_add)
                    bucket.last_refill_at = now

                bucket.tokens = min(bucket.tokens, float(rpm_limit))

            if bucket.tokens < 1.0:
                return False

            bucket.tokens -= 1.0
            return True
```

### Explaining the Mechanics:
1. **Mathematical Refill on Access:** Rather than having background threads constantly updating buckets every second, the limiter computes tokens lazily upon access:
   $$\text{tokens\_to\_add} = \text{elapsed\_seconds} \times \frac{\text{rpm\_limit}}{60.0}$$
2. **Cap at Capacity:** `min(float(rpm_limit), ...)` guarantees tokens never accumulate beyond the maximum burst capacity.
3. **Synchronization with `self.lock`:** In Python, multiple async tasks running on threads or thread pools could interleave. Wrapping the refill, condition check, and decrement inside `with self.lock:` guarantees that token deduction is atomic.
4. **Acquisition:** If `bucket.tokens < 1.0`, it returns `False` without decrementing. If $\ge 1.0$, it deducts 1.0 and returns `True`.

---

## 8.4 Pipeline Runner: `prism/services/pipeline.py`

This file coordinates the execution of stages.

```python
Stage = Callable[[RequestContext], Awaitable[RequestContext]]

class Pipeline:
    async def run(
        self,
        context: RequestContext,
        stages: Sequence[Stage],
    ) -> RequestContext:
        for stage in stages:
            stage_name = getattr(stage, "__name__", "stage")
            try:
                context = await stage(context)
            except PrismError as exc:
                context.decision_trace.append(f"{stage_name} failed")
                raise
        return context
```

### Explaining the Mechanics:
- `Stage` type alias: Declares that a stage is an async function that receives `RequestContext` and returns an updated `RequestContext`.
- In the `for stage in stages:` loop, it invokes each stage sequentially using `await stage(context)`.
- If any stage raises a `PrismError` (e.g., `RateLimitError`), it intercepts the exception, logs `"<stage_name> failed"` into `context.decision_trace`, and **re-raises** the exception immediately with `raise`.
- This ensures that execution halts instantly upon the first failure while preserving the exact failure step in the decision trace.

---

## 8.5 Resilient Executor: `prism/services/executor.py`

`ResilientExecutor` implements retry loops, backoff calculation, and provider failover.

### Block 1: Error Classification
```python
@staticmethod
def _classify_error(exc: Exception) -> str:
    if isinstance(exc, TimeoutError):
        return "retryable"

    cause = exc.__cause__

    if isinstance(cause, httpx.TimeoutException):
        return "retryable"

    # Connection refused or DNS failure -> Provider is down!
    if isinstance(cause, httpx.ConnectError):
        return "failover"

    if isinstance(cause, httpx.RequestError):
        return "retryable"

    if isinstance(cause, httpx.HTTPStatusError):
        status_code = cause.response.status_code
        if status_code == 429:
            return "failover"       # Rate limited: Fail over immediately!
        if status_code >= 500:
            return "retryable"      # Server blip: Retry same provider!
        if 400 <= status_code < 500:
            return "fatal"          # Client error: Abort immediately!

    if isinstance(exc, UpstreamError):
        return "retryable"

    return "fatal"
```
- **Why inspect `exc.__cause__`?** In `OpenAICompatibleProvider`, low-level `httpx` exceptions are caught and wrapped in `UpstreamError` using `raise UpstreamError(...) from exc`. Python saves the original cause in `__cause__`. `_classify_error` reads this underlying cause to understand the root network failure.

### Block 2: The Two-Tiered Retry & Failover Loop
```python
async def execute(self, request: dict[str, Any]) -> ExecutionResult:
    total_retries = 0
    last_error: Exception | None = None

    # Outer Loop: Iterate through candidate providers
    for provider_index, provider in enumerate(self.providers):
        provider_name = getattr(provider, "name", provider.__class__.__name__)

        # Inner Loop: Retry attempts on the current provider
        for attempt in range(self.max_retries + 1):
            try:
                async with asyncio.timeout(self.request_timeout):
                    response = await provider.complete(request)

                return ExecutionResult(
                    response=response,
                    retries=total_retries,
                    fallback_used=provider_index > 0,
                    provider_name=provider_name,
                )

            except asyncio.CancelledError:
                raise

            except Exception as exc:
                category = self._classify_error(exc)
                last_error = exc

                if category == "fatal":
                    raise UpstreamError(f"Provider request failed: {exc}") from exc

                if category == "retryable":
                    if attempt < self.max_retries:
                        total_retries += 1
                        await self._backoff(attempt)
                        continue

                # Category is "failover" OR retries are exhausted:
                # Break out of inner loop to try the NEXT provider!
                break

    raise UpstreamError("All configured providers failed.") from last_error
```
- **Inner Loop (`attempt`):** Retries transient errors on the same provider up to `max_retries` times.
- **Outer Loop (`provider_index`):** If an error is categorized as `"failover"` (HTTP 429 or connection failure), the inner loop breaks immediately, and the outer loop shifts to candidate 2 (`fallback_used = True`).
- If all providers and all retries are exhausted, it raises `UpstreamError("All configured providers failed.")`.

---

## 8.6 Semantic Caching: `prism/services/cache.py` & `bow_embedder.py`

### Feature Hashing in `BowEmbedder.embed()` (`prism/adapters/bow_embedder.py`):
```python
def embed(self, text: str) -> list[float]:
    tokens = self.tokenize(text)
    normalized_tokens = [self.TOKEN_NORMALIZATION.get(token, token) for token in tokens]

    vector = [0.0] * self.VECTOR_SIZE  # 256 zeros

    if not normalized_tokens:
        return vector

    for token in normalized_tokens:
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        index = int(token_hash, 16) % self.VECTOR_SIZE
        vector[index] += 1.0

    return vector
```
- **How it works:** Instead of maintaining a fixed dictionary of 50,000 English words, it uses the **Hashing Trick** (feature hashing).
- It takes each token (e.g., `"australia"`), computes its SHA-256 hash, converts the hex to an integer, and takes modulo 256. This maps any string deterministically to an index between 0 and 255.
- It increments that position by 1.0, producing a 256-dimensional frequency vector in 0.1 milliseconds!

### Cosine Similarity:
```python
def cosine_similarity(vector_a: list[float], vector_b: list[float]) -> float:
    dot_product = sum(a * b for a, b in zip(vector_a, vector_b))
    magnitude_a = math.sqrt(sum(a * a for a in vector_a))
    magnitude_b = math.sqrt(sum(b * b for b in vector_b))

    if magnitude_a == 0 or magnitude_b == 0:
        return 0.0

    similarity = dot_product / (magnitude_a * magnitude_b)
    return max(0.0, min(1.0, similarity))
```
- Computes the cosine of the angle between two 256-dimensional vectors.
- If two prompts use the same keywords, their vectors point in the same direction, yielding similarity $\approx 1.0$.

---

## 8.7 Streaming Forwarding & Caching: `prism/api/routes.py`

The Streaming Tee implementation in `format_streaming_body()`:

```python
async def format_streaming_body(
    provider_stream: AsyncIterator[dict[str, Any]],
    context: RequestContext,
    usage_repository: Any,
    loaded_config: Any,
    adapter: Any,
    request: Request,
    log_repository: Any,
    request_started_at: float,
    cache_service: Any = None,
) -> AsyncIterator[str]:
    streaming_generator = stream_response(...)
    status_code = 200
    response_parts: list[str] = []
    finish_reason: str | None = None
    stream_completed = False

    try:
        async for formatted_chunk in streaming_generator:
            # Parse chunk lines
            for line in formatted_chunk.splitlines():
                if line.startswith("data:"):
                    data = line.removeprefix("data:").strip()
                    event = json.loads(data)
                    for choice in event.get("choices", []):
                        content = choice.get("delta", {}).get("content")
                        if isinstance(content, str):
                            # TEE OPERATION: Buffer content while streaming!
                            response_parts.append(content)

            yield formatted_chunk  # Deliver immediately to client!

        stream_completed = True

    except (asyncio.CancelledError, GeneratorExit):
        status_code = 499          # Client disconnected
        raise
    except Exception:
        status_code = 502          # Upstream failure
        raise
    finally:
        # ALWAYS runs upon stream termination!
        if stream_completed and cache_service and context.key_config.cache_enabled:
            # Reconstruct complete response from buffered parts
            cached_response = ProviderResponse(
                content="".join(response_parts),
                model=context.model_resolved or "",
                prompt_tokens=context.stream_prompt_tokens,
                completion_tokens=context.stream_completion_tokens,
                total_tokens=context.stream_prompt_tokens + context.stream_completion_tokens,
                finish_reason=finish_reason or "stop",
                raw_response={},
            )
            context.provider_response = cached_response
            # Store in semantic cache!
            cache_service.store_response(context)

        # Record audit log in SQLite
        save_request_log(request, context, log_repository, status_code, request_started_at)
```

### Why this is elegant engineering:
- Chunks flow to the client with zero latency via `yield formatted_chunk`.
- As chunks pass through, `response_parts.append(content)` accumulates the full text.
- In `finally:`, if the stream succeeded, the buffered text is assembled into a `ProviderResponse` and saved to `cache_service`.
- If the client disconnects halfway through, `GeneratorExit` is caught, `status_code` becomes 499, cache storage is skipped (preventing caching partial text), and the log row records the client disconnect.

---
# 9. Requirement vs Implementation Audit

This section presents a forensic audit comparing expected requirements from `docs/architecture.md`, `docs/implementation-plan.md`, and Architectural Decision Records (ADRs) against the actual source code and automated tests.

---

## 9.1 Comprehensive Requirement vs Implementation Audit Table

| Requirement | Expected Behaviour | Actual Implementation in Codebase | Files Involved | Status | Gap / Identified Improvement |
|---|---|---|---|---|---|
| **Unified OpenAI-Compatible API** | Expose `POST /v1/chat/completions` and `GET /v1/models` matching the OpenAI REST specification. | Implements both endpoints in FastAPI router. Serializes responses into standard OpenAI JSON format with `id`, `object`, `created`, `choices`, and `usage`. | `prism/api/routes.py`, `prism/domain/models.py` | **Fully Implemented** | None. Works with official OpenAI Python and Node SDKs by changing `base_url`. |
| **Multiple LLM Providers** | Connect to at least two distinct real LLM providers behind a single interface. | Configures two independent instances of `OpenAICompatibleProvider` targeting OpenAI (`gpt-4o-mini`) and Groq (`llama-3.3-70b-versatile`). | `prism/main.py`, `prism/adapters/openai_compatible.py` | **Fully Implemented** | None. Master credentials validated at startup. |
| **Model Alias Resolution** | Support friendly aliases (`fast`, `smart`) mapping to primary and fallback candidate chains. | Reads `gateway_config.json`. Maps aliases to `primary_model` and `fallback_chain`. Passes direct model names through unchanged. | `prism/services/stages/resolve.py`, `prism/config/loader.py` | **Fully Implemented** | None. Deduplicates candidate lists while preserving order. |
| **Automatic Difficulty Routing (`auto`)** | Sending `model: "auto"` routes prompts to `fast` or `smart` based on complexity. | Implements `HeuristicClassifier` scanning for code blocks, LaTeX math, multi-part directives, and keywords. Resolves `auto` to `fast` or `smart`. | `prism/services/router.py`, `prism/services/stages/resolve.py` | **Fully Implemented** | Exceeds length-only baseline by >20% accuracy on held-out eval set. |
| **Header Contracts** | Return metadata headers: `x-prism-request-id`, `x-prism-provider`, `x-prism-cache`, `x-prism-fallback`, `x-prism-cost-usd`, and `Retry-After: 60`. | Injects headers via `set_context_headers()`, `build_streaming_headers()`, and `prism_error_handler()`. | `prism/api/routes.py`, `prism/api/error_handler.py`, `prism/api/middleware.py` | **Fully Implemented** | Complete adherence to architecture contract. |
| **Streaming Pass-Through (SSE)** | Stream Server-Sent Events (`text/event-stream`) immediately to the client with token usage captured. | Implements async generator in `streaming.py` yielding SSE chunks as they arrive. Implements Streaming Tee pattern in `routes.py` to buffer tokens for cache storage. | `prism/services/streaming.py`, `prism/api/routes.py` | **Fully Implemented** | Includes idle timeout detection (10s) and clean client disconnect handling (HTTP 499). |
| **Virtual API Keys** | Issue lightweight keys (`prism-sk-...`); store only one-way SHA-256 hashes in database. | `seed_keys.json` keys are converted to SHA-256 hashes during load and stored in `virtual_keys` SQLite table. | `prism/domain/security.py`, `prism/config/loader.py`, `prism/adapters/sqlite_repos.py` | **Fully Implemented** | Raw keys never touch persistent storage. |
| **Virtual Key Authentication** | Authenticate incoming requests by checking key hash in database using constant-time comparison. | Reads `x-api-key` header, hashes value, queries SQLite, verifies with `hmac.compare_digest`, and checks `status == "active"`. | `prism/services/stages/auth.py` | **Implemented but Needs Improvement** | **Minor Gap:** Only inspects the `x-api-key` header. Does not support standard `Authorization: Bearer <key>` on `/v1/chat/completions` (some third-party SDKs prefer sending Bearer tokens). |
| **Rate Limiting (RPM)** | Enforce per-key Requests Per Minute quota using Token Bucket algorithm. Cache hits consume rate limits (ADR-001). | `TokenBucketRateLimiter` enforces RPM in memory using `threading.Lock()`. Pipeline runs rate limit stage *before* cache stage. | `prism/domain/limiter.py`, `prism/services/stages/rate_limiter.py` | **Fully Implemented** | Mathematical lazy refill; thread-safe atomic token deduction. |
| **Monthly Budget Enforcement** | Enforce per-key monthly spending limit in USD. Cache hits allowed even when budget exhausted (ADR-001). Bounded overshoot on streams (ADR-003). | Queries month-to-date spend in SQLite `usage` table. Blocks request if `current_spend >= budget_usd`. Runs before cache stage. Streaming records cost in `finally:`. | `prism/services/stages/budget.py`, `prism/adapters/sqlite_repos.py` | **Fully Implemented** | Adheres strictly to ADR-001 and ADR-003 specifications. |
| **Model Allowlist Enforcement** | Restrict tenants to authorized models and aliases. Support wildcard `*`. Enforce ADR-007 for `auto`. | Verifies requested model, classifier-selected tier, and all candidate fallback models against `model_allowlist`. | `prism/services/stages/allowlist.py` | **Fully Implemented** | Strictly enforces ADR-007; prevents privilege escalation via `auto`. |
| **Resilient Retries and Failover** | Retry transient errors with exponential backoff and jitter. Fail over to next provider on 429/ConnectError. Mid-stream failures terminate with error event (ADR-002). | `ResilientExecutor` handles non-streaming retries and failover. `stream_response` emits `format_sse_error()` on mid-stream failure. | `prism/services/executor.py`, `prism/services/streaming.py` | **Fully Implemented** | Verified by tests in `test_failover.py` and `test_executor.py`. |
| **Semantic Response Caching** | Cache completions using vector similarity. Enforce tenant isolation (ADR-004), skip time-sensitive queries (ADR-005), evict > 1000 entries. | Computes 256-dim BoW embeddings; searches SQLite scoped by `WHERE key_hash = ? AND alias = ?`; calculates cosine similarity; checks `TIME_SENSITIVE_KEYWORDS`; evicts oldest entries. | `prism/services/cache.py`, `prism/adapters/bow_embedder.py`, `prism/adapters/sqlite_repos.py`, `prism/domain/cache_decision.py` | **Implemented but Needs Improvement** | **Identified Gaps:**<br>1. In `services/cache.py`, concrete classes (`BowEmbedder`, `CacheRepository`) are imported directly, bypassing port interfaces.<br>2. `CacheService._get_prompt` embeds `json.dumps(messages)` instead of `system + last_user` (ADR-004). (Works well, but deviates from ADR text). |
| **Usage Tracking & Metering** | Track total tokens, prompt/completion tokens, requests, and cache hits per key per month. | `SQLiteUsageRepository.record_usage()` executes atomic upsert (`INSERT ... ON CONFLICT DO UPDATE`). | `prism/adapters/sqlite_repos.py` | **Fully Implemented** | Atomic upsert eliminates concurrency lost-update bugs. |
| **Cost Calculation** | Calculate USD cost per request to 6 decimal places based on token counts and model pricing tables. | `CostCalculator.calculate()` computes financial cost. Strictly validates that inputs are non-negative integers (rejects booleans). | `prism/domain/cost.py` | **Fully Implemented** | Accurate mathematical enforcement. |
| **Admin APIs** | Expose `/admin/usage`, `/admin/logs`, `/admin/cache/stats` secured by dedicated admin token. | Endpoints exposed in `admin.py`. Authenticates `Authorization: Bearer` against `PRISM_ADMIN_TOKEN` using `secrets.compare_digest`. Computes accurate monthly cache hit rate. | `prism/api/admin.py` | **Fully Implemented** | Constant-time digest comparison prevents timing attacks. |
| **Operations Console** | Provide a browser dashboard to view logs, usage, and cache metrics. | Serves static single-page app at `/console` reading admin endpoints. | `console/index.html`, `prism/main.py` | **Fully Implemented** | Clean UI with token authentication and responsive tables. |
| **Error Handling & Privacy** | Sanitize 502 error messages to hide vendor internals. Omit raw prompts from logs by default (ADR-006). | `prism_error_handler` returns generic text on 502. SQLite `request_logs` schema stores metadata and decision traces, omitting prompt text. | `prism/api/error_handler.py`, `prism/adapters/sqlite_repos.py` | **Fully Implemented** | Adheres to ADR-006 privacy standards. |
| **Fail-Fast Configuration Loading** | Validate configuration files at startup; fail immediately on invalid config. | `load_configuration()` uses Pydantic to validate `seed_keys`, `pricing`, and `gateway_config`. Raises `ConfigLoadError` on invalid references. | `prism/config/loader.py` | **Fully Implemented** | Prevents booting with invalid configuration. |
| **Concurrency & Database Safety** | Support concurrent async requests without database locking errors or data corruption. | Configures SQLite with `PRAGMA journal_mode=WAL` and `PRAGMA busy_timeout=5000`. In-memory rate limiter uses `threading.Lock()`. | `prism/adapters/sqlite_repos.py`, `prism/domain/limiter.py` | **Implemented but Needs Improvement** | **Scalability Risk:** SQLite queries run synchronously on the event loop thread. Under high load, disk I/O could cause micro-stalls on the main thread. |
| **Automated Testing** | Comprehensive automated test coverage across unit, integration, and concurrency scenarios. | 287 automated tests across `tests/unit`, `tests/integration`, `tests/concurrency`. Test helpers (`FakeAdapter`, `FakeClock`) enable offline execution. | `tests/` | **Fully Implemented** | Robust test suite testing edge cases, timeouts, and failovers. |

---

## 9.2 Summary of Gaps & Technical Debt

While the Prism LLM Gateway implements nearly 100% of its required functionality, a Senior Architect must honestly document technical debt and improvement opportunities:

1. **Authentication Header Flexibility (`prism/services/stages/auth.py`):**  
   The gateway currently only checks `request.headers.get("x-api-key")`. To provide 100% drop-in compatibility with all OpenAI SDK configurations, it should also accept `Authorization: Bearer <virtual_key>` if `x-api-key` is omitted.
2. **Clean Architecture Port Violation in Cache Service (`prism/services/cache.py`):**  
   `CacheService` imports `from prism.adapters.bow_embedder import BowEmbedder` and `from prism.adapters.sqlite_repos import CacheRepository` directly. It should import `Embedder` and `CacheRepository` from `prism.ports` to maintain strict dependency inversion.
3. **Synchronous Database Driver in Async Context:**  
   `prism/adapters/sqlite_repos.py` uses the standard library `sqlite3` driver. Although WAL mode and sub-millisecond queries make this acceptable for moderate loads, running synchronous I/O inside `async def` routes can block the event loop under heavy load. A production upgrade should wrap calls in `anyio.to_thread.run_sync()` or adopt `aiosqlite`.
4. **Single-Node In-Memory Limiter:**  
   `TokenBucketRateLimiter` stores state in local memory (`self.buckets`). If Prism is deployed behind a round-robin load balancer across 3 Docker containers, a tenant could exceed their RPM quota by 3x. Migrating the token bucket to Redis (using Lua scripts) is the recommended path for horizontal clustering.

---
# 10. Testing & Code Quality

This section analyzes the automated testing architecture, test doubles, edge-case coverage, security controls, and production risks within the Prism LLM Gateway.

---

## 10.1 The Testing Pyramid in Prism

Prism adheres to the standard software engineering testing pyramid:

```
          / \
         /   \     End-to-End Smoke Tests (scripts/smoke_test.py)
        /-----\
       /       \    Integration Tests (tests/integration/ - 6 test suites)
      /---------\
     /           \   Concurrency Tests (tests/concurrency/ - multi-threaded)
    /-------------\
   /               \ Unit Tests (tests/unit/ - 26 test suites)
  /-----------------\
```

### 1. Unit Tests (`tests/unit/`)
Test individual functions, domain models, or pipeline stages in strict isolation from external infrastructure:
- **`test_models.py`:** Validates Pydantic constraints (`VirtualKeyConfig`, `RequestContext`, `ProviderResponse`).
- **`test_limiter.py`:** Tests the mathematical token bucket refill formula and RPM boundary conditions.
- **`test_cost.py`:** Validates token cost calculations across standard models, ensuring booleans and negative numbers raise errors.
- **`test_router.py`:** Tests `HeuristicClassifier` against prompts containing code blocks, LaTeX math formulas, multi-part steps, and simple lookups.
- **`test_auth.py`:** Verifies SHA-256 key hashing, missing header rejection, inactive key blocking, and `hmac.compare_digest` validation.
- **`test_bow_embedder.py`:** Tests tokenization, stop-word removal, normalization, vector dimensions (256), and cosine similarity clamping.
- **`test_cache_decision.py`:** Tests `is_cacheable()` against prompts containing `TIME_SENSITIVE_KEYWORDS` (`"now"`, `"today"`).
- **`test_executor.py`:** Verifies that `_classify_error()` correctly categorizes timeouts, connect errors, 429s, and 500s.

### 2. Integration Tests (`tests/integration/`)
Test multiple real components collaborating together across layer boundaries:
- **`test_pipeline.py`:** Runs `Pipeline.run()` through all 9 stages in sequence, verifying that state accumulates in `RequestContext.decision_trace`.
- **`test_failover.py`:** Configures multiple providers; verifies that when Provider 1 throws HTTP 429 or connection refused, `ResilientExecutor` fails over to Provider 2 and records `fallback_used = True`.
- **`test_streaming.py`:** Tests `StreamingResponse`, verifying that SSE tokens flow in real time and usage metrics are accurately metered upon stream completion.
- **`test_semantic_cache.py`:** Verifies the full cache lifecycle: storing a completion, executing an identical or paraphrased query to get a cache hit (`x-prism-cache: hit`, cost: $0.00), and testing eviction when entries exceed 1000.
- **`test_error_paths.py`:** Verifies that 400, 401, 403, 404, 429, and 502 errors return standard OpenAI JSON error envelopes with correct HTTP status codes.

### 3. Concurrency Tests (`tests/concurrency/`)
- **`test_limiter_concurrent.py`:** Spawns 20 concurrent threads attempting to acquire tokens from a single `TokenBucketRateLimiter` simultaneously, proving that `threading.Lock()` prevents race conditions and strictly caps acquisitions at the configured RPM limit.

### 4. End-to-End Verification (`scripts/smoke_test.py`)
A standalone Python script that boots against a live running gateway instance, executing 12 comprehensive checks: authentication, models list, non-streaming completion, streaming SSE pass-through, alias resolution, auto difficulty routing, rate limit throttling, budget exhaustion, failover execution, semantic caching, and admin endpoints.

---

## 10.2 Test Doubles: Fakes, Mocks, and Deterministic Time

Prism's test suite achieves **100% offline execution** with zero external network dependencies using two custom test doubles:

### 1. `FakeAdapter` (`tests/helpers/fake_adapter.py`)
An in-memory class implementing `ProviderAdapter`:
```python
class FakeAdapter(ProviderAdapter):
    def __init__(self, responses=None, stream_chunks=None, error_to_raise=None):
        self.responses = responses or []
        self.stream_chunks = stream_chunks or []
        self.error_to_raise = error_to_raise
        self.calls = []

    async def complete(self, request):
        self.calls.append(request)
        if self.error_to_raise:
            raise self.error_to_raise
        return self.responses.pop(0)

    async def stream(self, request):
        self.calls.append(request)
        if self.error_to_raise:
            raise self.error_to_raise
        for chunk in self.stream_chunks:
            yield chunk
```
- **Why this is powerful:** Allows test writers to simulate complex failure modes deterministically:
  - *"Simulate an OpenAI timeout on attempt 0, followed by a 200 OK on attempt 1."*
  - *"Simulate an immediate HTTP 429 on Provider A to verify instant failover to Provider B."*

### 2. `FakeClock` (`tests/helpers/fake_clock.py`)
An in-memory class implementing `Clock`:
```python
class FakeClock(Clock):
    def __init__(self, initial_time=None):
        self._current_time = initial_time or datetime(2026, 11, 12, 10, 0, 0, tzinfo=timezone.utc)

    def now(self) -> datetime:
        return self._current_time

    def advance(self, seconds: float = 0, days: float = 0):
        self._current_time += timedelta(seconds=seconds, days=days)
```
- **Why this is powerful:** Testing a rate limiter or monthly budget rollover usually requires waiting real wall-clock time (`time.sleep(60)`). With `FakeClock`, tests advance simulated time instantly:
  ```python
  limiter.try_acquire("key_hash", rpm_limit=10) # Bucket drops to 9
  clock.advance(seconds=60)                      # Instant 1-minute jump!
  # Bucket is mathematically full again, in 0.001 seconds of test time!
  ```

---

## 10.3 How to Run the Test Suite

Prism uses `pytest` with `pytest-asyncio`. Run tests from the repository root:

### Running All Tests:
```powershell
pytest
```

### Running with Verbose Output:
```powershell
pytest -v
```

### Running a Specific Test Folder:
```powershell
pytest tests/unit
pytest tests/integration
pytest tests/concurrency
```

### Running a Specific Test File or Function:
```powershell
pytest tests/integration/test_failover.py -k "test_failover_to_secondary"
```

---

## 10.4 Missing Test Coverage & Edge Cases

An audit of the test suite reveals several real-world edge cases that are not currently covered:

1. **Mid-Stream Database Connection Drops:**  
   What happens if SQLite becomes unavailable *while* an SSE stream is active? `format_streaming_body()` catches the error in `finally:`, but tests should explicitly verify that logging failures in `finally:` do not crash the ASGI worker process.
2. **Concurrent Cache Writes for Identical Prompts:**  
   If 10 concurrent requests with the exact same prompt arrive simultaneously on a cold cache, all 10 will experience a cache miss, call upstream, and attempt to write identical entries to `cache_entries`. The test suite should verify that concurrent inserts do not hit SQLite lock contention.
3. **Database Corruption / WAL Checkpoint Recovery:**  
   No automated test verifies behavior when the WAL file grows exceptionally large under heavy sustained write loads.

---

## 10.5 Security Analysis & Controls

Prism implements robust defensive engineering:

| Security Vector | Implementation in Prism | Verification in Codebase |
|---|---|---|
| **API Key Protection** | Raw virtual keys are never saved in SQLite. Converted to SHA-256 hashes immediately upon load. | `prism/domain/security.py`, `prism/config/loader.py` |
| **Timing Attacks** | Key comparisons use `hmac.compare_digest` and admin token checks use `secrets.compare_digest` (constant-time). | `prism/services/stages/auth.py`, `prism/api/admin.py` |
| **Information Disclosure** | Upstream provider error messages (e.g., DNS failures, internal IP addresses) are sanitized. Clients receive generic error text for 502s. | `prism/api/error_handler.py` (`prism_error_handler`) |
| **Data Privacy & PII (ADR-006)** | The `request_logs` SQLite table strictly omits raw prompt and response text by default, recording only metadata, token counts, and decision traces. | `prism/adapters/sqlite_repos.py` (`create_tables`) |
| **Resource Exhaustion (DoS)** | Request body token count is clamped to `PRISM_MAX_TOKENS_CAP` (4096). Semantic cache is hard-capped at 1000 entries. | `prism/services/stages/validate.py`, `prism/adapters/sqlite_repos.py` |
| **Container Isolation** | Dockerfile creates a non-root system user and group (`prism:prism`) and executes the process under `USER prism`. | `Dockerfile` |

---

## 10.6 Performance & Production Risks

A Senior Backend Engineer must recognize the production limitations of the current architecture:

1. **Synchronous SQLite Calls in Async Context:**  
   The standard `sqlite3` module blocks the operating system thread during disk writes. Although Write-Ahead Logging (`WAL`) allows concurrent reads, only one write transaction can execute at a time. Under high write throughput (e.g., 500 requests/sec writing logs and usage), the main event loop will experience latency spikes.  
   *Production Mitigation:* Migrate to `aiosqlite`, wrap synchronous calls in `anyio.to_thread.run_sync()`, or offload audit logging to an asynchronous message queue (e.g., RabbitMQ, Kafka, Celery).
2. **In-Memory Rate Limiter in Multi-Instance Deployments:**  
   `TokenBucketRateLimiter` stores token buckets in a Python process memory dictionary (`self.buckets`). If Prism is scaled horizontally across 4 Kubernetes pods behind a load balancer, each pod has an independent rate limiter. A tenant configured for 60 RPM could make 240 requests per minute without being throttled.  
   *Production Mitigation:* Replace in-memory token buckets with Redis using an atomic Lua script.
3. **Memory Buffering in Streaming Tee Pattern:**  
   Accumulating content deltas in `response_parts.append(content)` consumes memory. For very long generations (e.g., 10,000 tokens), 1,000 concurrent active streams would hold tens of megabytes of raw text strings in Python memory. This is bounded by `max_tokens_cap=4096`, but remains a factor under extreme concurrency.

---
# 11. How to Run and Debug the Project

This section provides a complete, beginner-friendly guide to installing, configuring, running, testing, and debugging the Prism LLM Gateway on Windows and cross-platform environments.

---

## 11.1 Step-by-Step Environment Setup

### Prerequisites
- Python 3.11, 3.12, or 3.14 installed on your machine.
- Git installed.
- Windows PowerShell or Command Prompt (for Windows users) or Bash/Zsh (for Linux/macOS users).

### Step 1: Clone the Repository & Navigate to Root
```powershell
git clone <repository_url>
cd prism-llm-gateway
```

### Step 2: Create a Python Virtual Environment
A virtual environment keeps project dependencies isolated from your operating system:
```powershell
python -m venv .venv
```

### Step 3: Activate the Virtual Environment
- **On Windows (PowerShell):**
  ```powershell
  .venv\Scripts\Activate.ps1
  ```
  *(If PowerShell displays an execution policy error saying scripts are disabled, run: `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` and then run the activate command again).*
- **On Windows (Command Prompt):**
  ```cmd
  .venv\Scripts\activate.bat
  ```
- **On Linux / macOS:**
  ```bash
  source .venv/bin/activate
  ```
When activated, `(.venv)` will appear at the start of your terminal prompt.

### Step 4: Install Dependencies
Install all required runtime and testing packages:
```powershell
pip install --upgrade pip
pip install -r requirements.txt
```

---

## 11.2 Environment Variables Configuration (`.env`)

Prism requires an environment file to store secrets and configuration overrides.

Copy the template file:
```powershell
cp .env.example .env
```

Open `.env` in your text editor and configure the parameters:
```ini
# ============================================================
# Prism LLM Gateway - Environment Configuration
# ============================================================

# 1. SERVER CONFIGURATION
PORT=3000
PRISM_PORT=3000
PRISM_LOG_LEVEL=INFO

# 2. DATABASE CONFIGURATION
PRISM_DB_PATH=data/prism.db
PRISM_CONFIG_DIR=config

# 3. UPSTREAM PROVIDER MASTER KEYS
# For live cloud providers, add your real API keys:
OPENAI_API_KEY=sk-proj-your-real-openai-key-here
OPENAI_BASE_URL=https://api.openai.com/v1

GROQ_API_KEY=gsk_your-real-groq-key-here
GROQ_BASE_URL=https://api.groq.com/openai/v1

# 4. ADMIN CONSOLE AUTHENTICATION
PRISM_ADMIN_TOKEN=admin-secret-change-me

# 5. TIMEOUTS & RESILIENCE
PRISM_CONNECT_TIMEOUT_SECONDS=5.0
PRISM_PROVIDER_TIMEOUT_SECONDS=30.0
PRISM_STREAM_IDLE_TIMEOUT=10.0
PRISM_MAX_RETRIES=2
PRISM_RETRY_BASE_DELAY_SECONDS=1.0

# 6. SECURITY & CAPS
PRISM_MAX_TOKENS_CAP=4096
```

> [!TIP]
> **Developing Completely Offline Without Real API Keys:**  
> If you do not have OpenAI or Groq keys, you can point Prism to the local mock providers included in `scripts/mock_provider.py`! Set:  
> `OPENAI_API_KEY=mock-alpha-key`  
> `OPENAI_BASE_URL=http://localhost:9001/v1`  
> `GROQ_API_KEY=mock-beta-key`  
> `GROQ_BASE_URL=http://localhost:9002/v1`

---

## 11.3 Reviewing Runtime Configuration Files

Prism relies on three JSON configuration files in the `config/` directory:

1. **`config/seed_keys.json`:**  
   Defines pre-seeded tenant virtual keys, monthly USD budgets, RPM rate limits, model allowlists, and cache settings:
   ```json
   [
     {
       "key": "prism-sk-search-1a2b3c",
       "tenant_id": "search-team",
       "budget_usd": 50.0,
       "rate_limit_rpm": 60,
       "model_allowlist": ["*"],
       "cache_enabled": true,
       "cache_threshold": 0.85,
       "status": "active"
     }
   ]
   ```
2. **`config/model_pricing.json`:**  
   Defines per-million token pricing for financial metering:
   ```json
   [
     {
       "model_name": "gpt-4o-mini",
       "input_price_per_million": 0.15,
       "output_price_per_million": 0.60
     },
     {
       "model_name": "llama-3.3-70b-versatile",
       "input_price_per_million": 0.59,
       "output_price_per_million": 0.79
     }
   ]
   ```
3. **`config/gateway_config.json`:**  
   Maps logical aliases to physical model candidate chains:
   ```json
   {
     "aliases": {
       "fast": {
         "alias_name": "fast",
         "primary_model": "gpt-4o-mini",
         "fallback_chain": ["llama-3.3-70b-versatile"]
       },
       "smart": {
         "alias_name": "smart",
         "primary_model": "llama-3.3-70b-versatile",
         "fallback_chain": ["gpt-4o-mini"]
       }
     },
     "provider_timeout_seconds": 30.0,
     "max_retries": 2
   }
   ```

---

## 11.4 Starting the Server

### Option A: Running Locally with Uvicorn
Start the gateway with auto-reloading enabled:
```powershell
python -m uvicorn prism.main:app --host 0.0.0.0 --port 3000 --reload
```
You will see output confirming successful startup:
```text
INFO:     Started server process [12345]
INFO:     Waiting for application startup.
INFO:     Prism initialized successfully extra={'database_path': 'data/prism.db', 'providers': ['openai', 'groq']}
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:3000 (Press CTRL+C to quit)
```

### Option B: Running with Docker Compose
To run Prism alongside isolated Alpha and Beta mock servers in Docker containers:
```powershell
docker-compose up --build
```

### Verifying Gateway Health:
In a new terminal window:
```powershell
curl http://localhost:3000/health
```
Response:
```json
{"status": "ok"}
```

---

## 11.5 Running Local Mock Upstream Providers

To test failovers, latency, or offline operations without making real API calls, launch the mock provider scripts:

**In Terminal 2 (Start Alpha Mock on 9001):**
```powershell
python scripts/mock_provider.py --port 9001 --name alpha
```

**In Terminal 3 (Start Beta Mock on 9002):**
```powershell
python scripts/mock_provider.py --port 9002 --name beta
```

---

## 11.6 Running Tests and Verification Tools

### Running Automated Test Suites:
```powershell
pytest
```

### Running the End-to-End Smoke Test:
Verify all gateway features against a running instance:
```powershell
python scripts/smoke_test.py
```

### Running the Router ML Evaluation:
Measure accuracy of `HeuristicClassifier` vs `LengthOnlyClassifier` against `data/routing_eval.jsonl`:
```powershell
python scripts/routing_eval.py
```

### Running the Concurrency Load Test:
Benchmark requests-per-second, latency, and rate limiter enforcement:
```powershell
python scripts/load_test.py --concurrency 10 --requests 100
```

---

## 11.7 Calling Endpoints via cURL & PowerShell

### 1. List Available Models (`GET /v1/models`)
**cURL:**
```bash
curl -X GET http://localhost:3000/v1/models \
  -H "x-api-key: prism-sk-search-1a2b3c"
```
**PowerShell:**
```powershell
Invoke-RestMethod -Uri "http://localhost:3000/v1/models" -Headers @{"x-api-key"="prism-sk-search-1a2b3c"}
```

---

### 2. Standard Non-Streaming Chat Completion
**cURL:**
```bash
curl -X POST http://localhost:3000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "x-api-key: prism-sk-search-1a2b3c" \
  -d '{
    "model": "fast",
    "messages": [
      {"role": "user", "content": "What is the capital of France?"}
    ]
  }' -i
```
*Notice the `-i` flag prints response headers! Observe `x-prism-request-id`, `x-prism-provider: openai/gpt-4o-mini`, and `x-prism-cost-usd`!*

---

### 3. Server-Sent Events (SSE) Streaming Completion
**cURL:**
```bash
curl -N -X POST http://localhost:3000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "x-api-key: prism-sk-search-1a2b3c" \
  -d '{
    "model": "fast",
    "messages": [
      {"role": "user", "content": "Count from 1 to 5 slowly."}
    ],
    "stream": true
  }'
```
*Notice the `-N` flag disables curl's output buffering, showing tokens streaming in real time!*

---

### 4. Automatic Difficulty Routing (`model: "auto"`)
**cURL:**
```bash
curl -X POST http://localhost:3000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "x-api-key: prism-sk-search-1a2b3c" \
  -d '{
    "model": "auto",
    "messages": [
      {"role": "user", "content": "Explain deadlock detection algorithms in distributed databases with a code example."}
    ]
  }' -i
```
*Inspect headers: The heuristic classifier detects code and complexity signals, automatically routing to `smart` (`llama-3.3-70b-versatile`)!*

---

### 5. Demonstrating Semantic Caching
Submit the exact same question twice:

**Call 1:**
```bash
curl -X POST http://localhost:3000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "x-api-key: prism-sk-search-1a2b3c" \
  -d '{"model": "fast", "messages": [{"role": "user", "content": "What is the speed of light?"}]}' -i
```
*Response Header:* `x-prism-cache: miss`, `x-prism-cost-usd: 0.000018`

**Call 2 (Paraphrased or Identical):**
```bash
curl -X POST http://localhost:3000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "x-api-key: prism-sk-search-1a2b3c" \
  -d '{"model": "fast", "messages": [{"role": "user", "content": "What is the speed of light?"}]}' -i
```
*Response Header:* `x-prism-cache: hit`, `x-prism-cost-usd: 0`  
*Response Latency:* Under 5 milliseconds! Upstream API call skipped!

---

### 6. Admin API Endpoints & Ops Console
**Inspect Monthly Usage:**
```bash
curl -X GET "http://localhost:3000/admin/usage" \
  -H "Authorization: Bearer admin-secret-change-me"
```

**Inspect Request Logs:**
```bash
curl -X GET "http://localhost:3000/admin/logs?limit=10" \
  -H "Authorization: Bearer admin-secret-change-me"
```

**Open the Operations Console:**  
Open your web browser and navigate to:  
`http://localhost:3000/console`  
Enter the admin token (`admin-secret-change-me`) to view the interactive real-time dashboard.

---

## 11.8 Debugging Common Errors

| Error Code & Message | Root Cause | Exact Resolution |
|---|---|---|
| **401 Unauthorized**<br>`"Invalid or missing API key."` | The `x-api-key` header was omitted, contained an unknown key, or referenced an inactive key. | Ensure the request includes `-H "x-api-key: prism-sk-search-1a2b3c"`. Check `config/seed_keys.json` to confirm the key is defined with `"status": "active"`. |
| **403 Forbidden**<br>`"Model '...' is not allowed for this API key."` | The tenant's `model_allowlist` does not include the requested model or alias. | In `config/seed_keys.json`, add the model/alias to `model_allowlist` (or add `"*"` for full access). |
| **429 Too Many Requests**<br>`"Rate limit exceeded. Please try again later."` | The tenant submitted more requests within the current minute than their `rate_limit_rpm` allows. | Wait 60 seconds for the token bucket to refill, or increase `rate_limit_rpm` in `seed_keys.json`. Observe the `Retry-After: 60` response header. |
| **429 Too Many Requests**<br>`"Monthly budget exceeded. Please try again next month."` | The tenant's cumulative USD spend for the current calendar month reached `budget_usd`. | Check `/admin/usage`. In `seed_keys.json`, increase `budget_usd` or wait for the calendar month to roll over. |
| **502 Bad Gateway**<br>`"An error occurred while processing your request with the upstream provider."` | All candidate providers failed or timed out. | Check server logs for the underlying traceback. Ensure `OPENAI_API_KEY` and `GROQ_API_KEY` are valid. If working offline, ensure mock providers are running on ports 9001 and 9002. |
| **`sqlite3.OperationalError: database is locked`** | Multiple processes or threads attempted concurrent write transactions without waiting. | Ensure connections are opened via `get_connection()` which configures `PRAGMA busy_timeout = 5000` and `PRAGMA journal_mode = WAL`. |
| **PowerShell script activation error** | Windows restricts PowerShell script execution by default. | Run: `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` in your PowerShell terminal, then re-run `.venv\Scripts\Activate.ps1`. |

---
# 12. Interview Preparation

This section prepares you to explain, defend, and ace a technical backend engineering interview based on the Prism LLM Gateway.

---

## 12.1 Project Explanation: The 2-Minute Elevator Pitch

> *"Prism LLM Gateway is an asynchronous, high-performance reverse proxy that sits between enterprise client applications and upstream LLM providers like OpenAI and Groq.*
>
> *When organizations adopt AI, they face immediate challenges: API key sprawl, unpredictable runaway cloud costs, lack of fallback resilience during vendor outages, and paying repeatedly for identical queries across teams.*
>
> *I built Prism to solve these problems through a unified OpenAI-compatible API. Clients authenticate using virtual API keys, leaving vendor master keys securely on the server. The gateway enforces in-memory token bucket rate limiting and monthly financial budgets per tenant. It features an automated difficulty router that analyzes prompt complexity to pick cheap or smart models, an offline 256-dimension semantic cache that serves paraphrased answers in under 5 milliseconds at zero cost, and a resilient executor that automatically retries network hiccups with jittered exponential backoff and fails over to secondary providers during outages.*
>
> *For chat applications, it implements a Streaming 'Tee' pattern over Server-Sent Events, forwarding tokens with zero latency while simultaneously buffering deltas so successful streams are cached. It's built with Clean Architecture in Python and FastAPI, uses SQLite in WAL mode for persistent audit logging and usage metering, and has a test suite of 287 automated tests running completely offline."*

---

## 12.2 Project Explanation: The 5-Minute Technical Pitch

> *"To explain Prism's technical architecture, I structure it around three core design goals: **Protocol Transparency**, **Enterprise Governance**, and **Fault Resilience**.*
>
> *First, **Protocol Transparency**: Prism exposes standard `/v1/chat/completions` and `/v1/models` endpoints. Any application using the official `openai` SDK in Python or TypeScript works with Prism simply by changing its `base_url`. We deliberately accept dynamic request payloads rather than rigid Pydantic models so that parameters like temperature, tools, and custom flags pass through unhindered.*
>
> *Second, **Enterprise Governance**: Every incoming request passes through an ordered, 9-stage linear pipeline:
> 1. **Authentication:** The `x-api-key` header is hashed via SHA-256 and matched against SQLite using constant-time `hmac.compare_digest` to prevent timing attacks.
> 2. **Validation:** Checks schema and clamps `max_tokens` to a hard ceiling (4096) to prevent denial-of-wallet attacks.
> 3. **Rate Limiting:** A thread-safe, in-memory Token Bucket rate limiter computes token refills mathematically on access, returning HTTP 429 if depleted.
> 4. **Model Resolution:** Maps friendly aliases like `fast` to primary models and fallback chains. If the client asks for `auto`, a heuristic classifier uses compiled regex patterns to scan for code blocks, LaTeX math, and multi-part directives to route to `fast` or `smart`.
> 5. **Allowlist:** Strictly enforces tenant permissions, requiring explicit access to requested models and classifier-selected tiers.
> 6. **Budget Enforcement:** Compares month-to-date spend against the key's budget in SQLite. Per ADR-001, budget checks run before cache lookups, but cache hits are allowed even if the budget is empty because their cost is $0.
> 7. **Semantic Caching:** If enabled, prompts are normalized and embedded using a zero-dependency 256-dimensional Bag-of-Words feature hashing algorithm. We query SQLite scoped strictly by tenant key hash and alias, preventing cross-tenant data leaks. If cosine similarity meets the threshold, the cached completion is returned immediately.
>
> *Third, **Fault Resilience**:
> - For non-streaming calls, `ResilientExecutor` wraps upstream providers. It classifies exceptions into fatal (client 4xx), retryable (5xx, timeouts), or failover (rate limits 429, connect errors). Retryable errors use exponential backoff with full jitter; failover errors shift immediately to backup providers.
> - For streaming calls, we implement the Streaming Tee pattern: chunks stream to the client via SSE with zero latency, while an internal generator buffers text deltas. In the `finally:` block, token usage is atomically upserted into SQLite, and the assembled completion is stored in the cache. Per ADR-002, if a provider dies mid-stream, we send an SSE error event and close the connection rather than attempting to splice together two different models mid-sentence.*
>
> *The entire codebase is structured using Ports and Adapters, decoupling domain logic from external libraries, and the test suite includes 287 automated tests using `FakeAdapter` and `FakeClock` for 100% offline, deterministic execution."*

---

## 12.3 Architecture Explanation (Whiteboard Walkthrough)

When asked to draw Prism on a whiteboard:
1. **Draw the Ingestion Boundary:**  
   Draw a box labeled **Prism Gateway (:3000)**. Show client applications sending `POST /v1/chat/completions` with `x-api-key`. Show the `request_id_middleware` generating `req_<hex>` and setting a Python `ContextVar`.
2. **Draw the Linear Pipeline:**  
   Draw a sequential box representing `Pipeline.run()` containing the ordered stages:  
   `Auth -> Validate -> RateLimit -> Resolve -> Allowlist -> Budget -> Cache -> Provider -> Meter`.
3. **Draw the Persistence Box:**  
   Draw a cylinder labeled `prism.db (SQLite WAL Mode)`. Draw arrows showing:
   - `Auth` reading `virtual_keys`.
   - `Budget` reading `usage`.
   - `Cache` querying `cache_entries` (scoped by `key_hash + alias`).
   - `Meter` executing atomic upsert `ON CONFLICT DO UPDATE`.
   - `routes.py` appending to `request_logs`.
4. **Draw the Upstream Provider Boundary:**  
   Draw two external boxes labeled **OpenAI (`gpt-4o-mini`)** and **Groq (`llama-3.3-70b-versatile`)**. Show `ResilientExecutor` managing retries and failover chains over HTTPS using private server master keys.
5. **Draw the Streaming Tee Flow:**  
   Draw a branch for `stream=true`. Show an arrow streaming SSE chunks directly to the client, with a side branch accumulating tokens into an in-memory buffer that writes to `cache_entries` upon stream completion.

---

## 12.4 Thirty Technical Interview Questions & Answers

### Python & FastAPI Fundamentals (Questions 1–10)

#### Q1: Why did you use `contextvars.ContextVar` for tracking `request_id` instead of a global variable?
> **Answer:** Python's `asyncio` runs multiple concurrent requests on a single operating system thread. A standard global variable would be overwritten every time another concurrent request yielded at an `await`. `ContextVar` provides task-local storage: each concurrent asynchronous task maintains its own isolated copy of `request_id`, ensuring structured log messages never cross-contaminate request IDs.

#### Q2: What is the difference between a coroutine and an asynchronous generator in Python?
> **Answer:** A coroutine function is defined with `async def` and yields a single return value via `return` when `await`ed. An asynchronous generator is defined with `async def` but contains one or more `yield` statements; it produces a stream of values over time that the consumer reads using `async for`. In Prism, `complete()` is a coroutine returning a single `ProviderResponse`, whereas `stream()` is an async generator producing real-time SSE chunks.

#### Q3: In `prism/domain/cost.py`, why do you explicitly check `if isinstance(prompt_tokens, bool)` before checking `int`?
> **Answer:** In Python, the `bool` class is an internal subclass of `int` (`issubclass(bool, int) == True`). As a result, `isinstance(True, int)` evaluates to `True`, and expressions like `True * 10` evaluate to `10`. Because this is a financial metering engine, accepting a boolean as a token count would cause silent billing corruption. We explicitly reject booleans.

#### Q4: Why did you use `threading.Lock()` inside the rate limiter if FastAPI is asynchronous?
> **Answer:** While the event loop runs on one thread, Uvicorn can run multiple worker threads, or synchronous functions can run on worker thread pools. Using `with self.lock:` guarantees that token calculation, capacity capping, and token decrement happen as an indivisible, atomic transaction, preventing race conditions under high concurrency.

#### Q5: What is the difference between `model_validate` and `model_dump` in Pydantic v2?
> **Answer:** `model_validate(data)` parses and validates raw input (like a dictionary or database row), coercing types and enforcing field constraints to construct a strongly-typed Pydantic instance. `model_dump(mode="json")` does the reverse: it converts a Pydantic object back into a standard Python dictionary containing JSON-serializable types (converting `datetime` objects to ISO 8601 strings).

#### Q6: Why did you use `asynccontextmanager` for the `lifespan` handler instead of FastAPI's deprecated `@app.on_event("startup")`?
> **Answer:** `@app.on_event("startup")` and `"shutdown"` are deprecated in modern Starlette and FastAPI. The `@asynccontextmanager lifespan` pattern unifies startup and shutdown into a single clean Python context manager. Everything before `yield` is startup; everything after `yield` is shutdown. It provides better exception handling and guarantees shutdown logic runs even during fatal startup aborts.

#### Q7: Why does `format_streaming_body()` catch `asyncio.CancelledError`?
> **Answer:** In an HTTP streaming connection, if the end user cancels the request or abruptly closes their browser tab, the underlying ASGI socket cancels the coroutine, raising `asyncio.CancelledError`. Catching this allows Prism to mark the request status as HTTP 499 (Client Closed Request), prevent partial or corrupt responses from being saved to the semantic cache, and ensure observed tokens are still billed in the `finally:` block.

#### Q8: What does `raise UpstreamError(...) from exc` do technically?
> **Answer:** The `from exc` syntax performs explicit **Exception Chaining** (PEP 3134). It sets the `__cause__` attribute of the newly created `UpstreamError` to the original exception (e.g., `httpx.ConnectError`). This preserves the complete diagnostic traceback for server logs and allows `_classify_error()` to inspect the root cause to decide between retrying or failing over.

#### Q9: Why did Prism implement custom dictionary validation in `validate_request()` instead of a strict Pydantic model on the route signature?
> **Answer:** OpenAI's chat completions API has dozens of optional parameters (`temperature`, `tools`, `presence_penalty`, etc.), and vendors frequently introduce new experimental fields. If we bound the route to a rigid Pydantic model, any valid parameter not explicitly modeled would be rejected or stripped. By validating essential fields (`model`, `messages`, `max_tokens`) manually, we pass arbitrary OpenAI-compliant fields through to upstream providers without breaking compatibility.

#### Q10: How does `get_connection()` in `sqlite_repos.py` ensure SQLite is safe for concurrent reads and writes?
> **Answer:** It executes `PRAGMA journal_mode=WAL` (Write-Ahead Logging), which decouples reads from writes: readers do not block writers, and writers do not block readers. It also sets `PRAGMA busy_timeout = 5000`, instructing SQLite to wait up to 5 seconds for write locks to clear before raising a `database is locked` error.

---

### System Design, Resilience & Concurrency (Questions 11–20)

#### Q11: What is the "Streaming Tee Pattern" and why is it necessary?
> **Answer:** Streaming and caching normally conflict: streaming requires forwarding chunks immediately, while caching requires the complete response text. The Streaming Tee pattern splits the stream into two paths: one path yields chunks to the client in real time with zero latency; the second path buffers content deltas into an in-memory list. When the stream finishes, the buffer is joined into a complete string and saved to the semantic cache.

#### Q12: Why did you choose Bag-of-Words and feature hashing instead of OpenAI `text-embedding-3-small` for semantic caching?
> **Answer:** Calling an external embedding API for every incoming request adds 100ms of network latency, costs money, requires another API key, and creates an external point of failure. The offline `BowEmbedder` executes locally in 0.2 milliseconds using SHA-256 feature hashing and term frequency, achieving near-instant vector generation at zero cost.

#### Q13: How does Prism prevent cross-tenant cache leakage?
> **Answer:** Cache isolation is enforced at the database query level (ADR-004). The SQL query that searches for matching vectors contains `WHERE key_hash = :key_hash AND alias = :alias`. It is physically impossible for Team A's cache entries to match Team B's queries because tenant key hash is a hard SQL query predicate, not an application post-filter.

#### Q14: Why does the rate limiter run BEFORE the semantic cache, but budget enforcement allows cache hits with zero budget?
> **Answer:** Per ADR-001: Rate limiting protects internal gateway infrastructure. A malicious or looping script sending 10,000 requests/second that all hit the cache still consumes gateway CPU, memory, and database connections, so rate limiting must apply to all requests. However, cache hits cost $0.00 in provider spend, so tenants with depleted budgets are allowed to receive cached answers for business continuity.

#### Q15: Why did ADR-002 reject mid-stream provider failover?
> **Answer:** If Provider A dies after emitting 50 tokens, connecting to Provider B and continuing would create a "Franken-answer." Model B has no context of what Model A generated, producing semantically incoherent output. Furthermore, debugging and reproducibility would become impossible. Therefore, we fail over only *before* the first byte is sent. Once streaming starts, mid-stream failures emit an SSE error event and terminate cleanly.

#### Q16: How does Prism handle budget overshoot during streaming requests?
> **Answer:** Per ADR-003, Prism uses an "admit-then-record" pattern. Because final token counts are unknown until generation completes, requests are admitted if the budget has remaining funds at the start of the call. The true cost is recorded in the `finally:` block. The maximum potential overshoot is strictly bounded by concurrent streams multiplied by `max_tokens_cap` and output price (typically < $0.05 per stream).

#### Q17: What is the difference between Exponential Backoff with Jitter vs plain Exponential Backoff?
> **Answer:** Plain exponential backoff doubles the delay on every attempt ($1s, 2s, 4s$). If an upstream provider recovers from a blip, hundreds of clients waiting on the exact same 2-second timer will retry simultaneously, creating a "Thundering Herd" spike that crashes the provider again. Adding randomized jitter spreads retries evenly across a time window, smoothing the traffic curve.

#### Q18: Why does `ResilientExecutor` treat HTTP 429 as "failover" rather than "retryable"?
> **Answer:** A 500 error is typically a transient server blip that resolves on an immediate retry. An HTTP 429 indicates that the upstream provider has actively throttled your account or quota. Hammering an already throttled provider with retries wastes time and delays the client. Failing over immediately shifts traffic to an alternate vendor with fresh quotas.

#### Q19: How does SQLite handle atomic usage tracking under high concurrency?
> **Answer:** In `prism/adapters/sqlite_repos.py`, `record_usage()` uses an atomic SQL upsert:  
> `INSERT INTO usage (...) ON CONFLICT(key_hash, month) DO UPDATE SET total_spend_usd = total_spend_usd + excluded.total_spend_usd, total_tokens = total_tokens + excluded.total_tokens...`  
> This performs the read-modify-write operation entirely inside SQLite's internal row lock, eliminating race conditions.

#### Q20: Why are prompts containing words like "now", "today", or "latest" never cached?
> **Answer:** Per ADR-005, questions asking about the current state of the world (e.g., *"What is the Bitcoin price right now?"*) have volatile answers. Serving a cached answer from last week would be actively harmful. The domain function `is_cacheable()` scans for `TIME_SENSITIVE_KEYWORDS` and bypasses the cache entirely.

---

### Gateway Governance, Security & LLM Operations (Questions 21–30)

#### Q21: Why are raw virtual API keys hashed with SHA-256 before storage?
> **Answer:** Storing raw API keys violates security best practices. If an unauthorized actor gains access to `prism.db` or database backups, plain-text keys would allow them to impersonate any tenant. One-way SHA-256 hashing ensures that database compromises never reveal usable API keys.

#### Q22: Why does `auth.py` use `hmac.compare_digest` instead of `==` to compare hashes?
> **Answer:** The standard `==` string equality operator terminates as soon as the first non-matching character is found. Attackers can measure response times down to nanoseconds to guess characters one by one (a **timing attack**). `hmac.compare_digest` performs a constant-time comparison, executing in the exact same number of clock cycles regardless of where characters differ.

#### Q23: Why does `request_logs` omit raw prompt and response text by default?
> **Answer:** Per ADR-006, prompt text frequently contains PII (Personally Identifiable Information), passwords, internal source code, or confidential customer data. Storing full prompts creates severe compliance risks (GDPR, HIPAA, SOC 2) and bloats database storage. Prism logs only metadata, token counts, and execution traces.

#### Q24: What is the purpose of `HeuristicClassifier` in `prism/services/router.py`?
> **Answer:** When a tenant requests `model: "auto"`, the gateway must decide whether to route to a cheap model (`fast`) or a capable model (`smart`). Calling an LLM to evaluate prompt difficulty costs money and adds latency. `HeuristicClassifier` inspects text features (code blocks, LaTeX math, multi-part steps, reasoning keywords) to classify difficulty in microseconds at zero cost.

#### Q25: What was the significance of separating `training_examples.jsonl` from `routing_eval.jsonl` (ADR-008)?
> **Answer:** In machine learning engineering, evaluating a classifier against the data used to design it creates false, overfitted results. We developed heuristics strictly against `training_examples.jsonl`, keeping `routing_eval.jsonl` as an untouched, held-out test exam. This proved our classifier generalizes to unseen prompts, beating baseline accuracy by >20%.

#### Q26: Why does `enforce_model_allowlist` check both `auto` and the resolved model?
> **Answer:** Per ADR-007, this prevents privilege escalation. If a tenant is only permitted to use cheap models (`model_allowlist: ["fast"]`), they must not be allowed to bypass this constraint by requesting `auto` and submitting a complex prompt that resolves to `smart`. Both `auto` and the resulting target model must be explicitly authorized.

#### Q27: How does `prism_error_handler` sanitize HTTP 502 Upstream Errors?
> **Answer:** When an upstream provider call fails, internal exceptions may contain raw provider URLs, internal IP addresses, or vendor error traces. Exposing these to clients aids attackers. The error handler replaces upstream error text with a clean, standardized message: *"An error occurred while processing your request with the upstream provider."*

#### Q28: What is the purpose of `scripts/mock_provider.py`?
> **Answer:** It is a standalone mock LLM server built with FastAPI that simulates OpenAI/Groq endpoints on ports 9001 and 9002. It allows developers to test streaming, inject artificial latency, and trigger synthetic 500 errors or 429 rate limits to verify gateway failover without an internet connection or real API billing.

#### Q29: How does the admin console calculate an accurate cache hit rate?
> **Answer:** In `prism/api/admin.py`, dividing total cache hits by total entries in `cache_entries` would be mathematically misleading because `cache_entries` only stores unique prompts. Instead, it aggregates total requests and total cache hits across all tenant `usage` records for the month:  
> $$\text{Hit Rate} = \frac{\sum \text{cache\_hits}}{\sum \text{total\_requests}}$$

#### Q30: Why does the Dockerfile use a multi-stage build?
> **Answer:** Stage 1 (`builder`) compiles dependencies and installs packages. Stage 2 (`production`) copies only the compiled `/usr/local` artifacts and application code, discarding compiler tools and intermediate build caches. This reduces container image size by over 60%, decreases attack surface, and executes under an unprivileged `prism` user.

---

## 12.5 Senior Engineer & Hiring Manager Tough Questions

### Question 1: "Why did you use SQLite and in-memory rate limiting instead of Redis and PostgreSQL?"
> **How to answer:**  
> *"That was a deliberate architectural trade-off based on deployment ergonomics and system scope. Prism is designed as a standalone, zero-dependency gateway that can boot instantly via Docker Compose without managing distributed infrastructure.  
> However, as a Senior Architect, I recognize the horizontal scaling boundary: in-memory token buckets cannot coordinate across multiple load-balanced gateway nodes, and concurrent SQLite writes are bottlenecked by single-writer locks.  
> If our throughput requirements exceed 1,000 RPS across a clustered deployment, my immediate migration roadmap would be:
> 1. Move the `TokenBucketRateLimiter` to Redis using an atomic Lua script (or Redis Cell).
> 2. Swap `SQLiteUsageRepository` and `SQLiteLogRepository` for PostgreSQL using an async driver like `asyncpg`.
> 3. Store vector embeddings in pgvector or a dedicated vector database like Qdrant.  
> Because the codebase strictly follows Clean Architecture Ports and Adapters, swapping these repositories requires zero changes to the core domain or pipeline stages."*

---

### Question 2: "Doesn't calling SQLite synchronously inside an async route block the Python event loop?"
> **How to answer:**  
> *"Yes, that is an accurate technical observation and a known trade-off in the current implementation. In `prism/adapters/sqlite_repos.py`, we use the standard library `sqlite3` driver, which executes synchronously on the main thread.  
> In our current benchmark profile, because we configure `PRAGMA journal_mode=WAL` and queries are indexed primary key lookups or simple upserts, transactions execute in sub-millisecond timeframes (under 0.5ms), which is virtually unnoticeable under moderate loads.  
> However, to make this fully production-hardened under high write concurrency, I would wrap all repository database calls in `anyio.to_thread.run_sync()`, offloading disk I/O to a background worker thread pool so the main asyncio event loop never stalls."*

---

### Question 3: "How would you defend the system against cache poisoning or malicious cache collisions?"
> **How to answer:**  
> *"We defend against this on three distinct levels:
> 1. **Tenant Isolation:** Cache lookups are scoped by `key_hash`. An attacker cannot poison another team's cache because queries cannot cross key boundaries.
> 2. **Verification of Provider Responses:** The cache stage never stores responses that contain `finish_reason == 'error'` or HTTP status codes other than 200.
> 3. **High Similarity Thresholds:** The default cache threshold is set conservatively at 0.85 to 0.90. To further prevent false collisions in high-risk environments, we can combine semantic similarity with an exact SHA-256 hash check of the system prompt to guarantee persona alignment."*

---

# 13. Learning Roadmap

To master this project from absolute zero to interview readiness, follow this structured 11-step sequence:

```
[ Step 1: Python Fundamentals ] -> [ Step 2: OOP & Clean Architecture ] -> [ Step 3: FastAPI & ASGI ]
                                                                                   │
[ Step 6: Core Domain & Config ] <- [ Step 5: Architecture Diagrams ]  <- [ Step 4: Folder Structure ]
      │
[ Step 7: Request Lifecycle (Trace) ] -> [ Step 8: Advanced Services (Router/Executor/Cache) ]
                                                                                   │
[ Step 11: Interview Mastery ]   <- [ Step 10: Requirement Audit ]    <- [ Step 9: Testing & Running ]
```

### Step 1: Basic Python Syntax & Types
- Study Section 2.1 through 2.3.
- Focus on type hints (`str | None`, `dict[str, Any]`), pure functions, and the `bool` vs `int` distinction in `prism/domain/cost.py`.

### Step 2: OOP & Clean Architecture Concepts
- Study Section 2.4 through 2.6.
- Understand Abstraction via `abc.ABC` in `prism/ports/provider.py` and Polymorphism via `ResilientExecutor` using `FakeAdapter`.

### Step 3: FastAPI & ASGI Fundamentals
- Study Section 3.
- Understand Uvicorn, ASGI scope, APIRouters, global exception handlers, and the `lifespan` startup/shutdown manager.

### Step 4: Folder Structure Exploration
- Study Section 4.
- Read through each file's responsibility, imports, and outputs to build a mental map of the project layout.

### Step 5: Visualizing Architecture & Data Flows
- Study Section 5.
- Walk through Diagrams 1, 5, 6, 7, and 8. Make sure you can sketch the pipeline flow and streaming tee pattern on paper.

### Step 6: Step-by-Step Code Walkthrough (Domain & Config)
- Study Section 8.1 through 8.4.
- Read `prism/domain/models.py` (`RequestContext`) and `prism/domain/limiter.py` (`TokenBucketRateLimiter`).

### Step 7: Tracing the Request Lifecycle
- Study Section 6.
- Trace a non-streaming and streaming call from client to Uvicorn, middleware, pipeline stages, provider, and response headers.

### Step 8: Understanding Advanced Services
- Study Section 8.5 through 8.7.
- Master `ResilientExecutor` (error classification, backoff with jitter, failover), `HeuristicClassifier` (regex signals), and `BowEmbedder` (feature hashing).

### Step 9: Running Tests & Debugging Locally
- Study Section 11.
- Activate `.venv`, run `pytest`, launch mock providers, and submit cURL requests to observe response headers and cache hits.

### Step 10: Architectural Decisions & Requirement Audit
- Study Sections 7, 9, and 10.
- Understand the 7-question framework for each decision and review identified gaps (such as synchronous SQLite and in-memory limiting).

### Step 11: Interview Rehearsal & System Defense
- Study Section 12.
- Practice the 2-minute elevator pitch aloud. Memorize answers to the 30 technical questions and practice answering the hiring manager tough questions.

---
