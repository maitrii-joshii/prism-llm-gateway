# Prism LLM Gateway — Architecture Document

> **Version:** 1.0  
> **Last Updated:** October 25, 2026  
> **Status:** Living document — update as design decisions evolve  
> **Timeline:** 15 working days × 2.5 hours/day = **37.5 hours total**

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Problem Statement & Goals](#2-problem-statement--goals)
3. [System Overview](#3-system-overview)
4. [High-Level Architecture](#4-high-level-architecture)
5. [Layered Architecture (Hexagonal / Ports & Adapters)](#5-layered-architecture-hexagonal--ports--adapters)
6. [Request Pipeline — Chain of Responsibility](#6-request-pipeline--chain-of-responsibility)
7. [Core Components (Building Blocks)](#7-core-components-building-blocks)
   - 7.1 [Config & Seed Loader](#71-config--seed-loader)
   - 7.2 [Key Store & Authentication](#72-key-store--authentication)
   - 7.3 [Rate Limiter (Token Bucket)](#73-rate-limiter-token-bucket)
   - 7.4 [Budget & Usage Service](#74-budget--usage-service)
   - 7.5 [Model Resolver & Smart Router (`auto`)](#75-model-resolver--smart-router-auto)
   - 7.6 [Semantic Cache](#76-semantic-cache)
   - 7.7 [Provider Adapter](#77-provider-adapter)
   - 7.8 [Resilient Executor (Retry, Timeout, Failover)](#78-resilient-executor-retry-timeout-failover)
   - 7.9 [Streaming Proxy (SSE Pass-Through)](#79-streaming-proxy-sse-pass-through)
   - 7.10 [Request Logger & Metering](#710-request-logger--metering)
   - 7.11 [Admin API & Ops Console](#711-admin-api--ops-console)
8. [Streaming Architecture](#8-streaming-architecture)
9. [Failure Handling Matrix](#9-failure-handling-matrix)
10. [Data Architecture](#10-data-architecture)
11. [Security Architecture](#11-security-architecture)
12. [API Contract](#12-api-contract)
13. [Design Patterns & Principles](#13-design-patterns--principles)
14. [Folder Structure](#14-folder-structure)
15. [Docker Architecture](#15-docker-architecture)
16. [Development Timeline (15 Days × 2.5 hrs/day)](#16-development-timeline-15-days--25-hrsday)
17. [Architecture Decision Records (ADRs)](#17-architecture-decision-records-adrs)
18. [Testing Strategy](#18-testing-strategy)
19. [Debugging & Observability](#19-debugging--observability)
20. [Known Limitations & Future Work](#20-known-limitations--future-work)

---

## 1. Executive Summary

**Prism** is a production-grade LLM Gateway that sits between internal teams (tenants) and AI model providers, serving as a single, intelligent middleman. It provides:

- **Unified API** — One OpenAI-compatible endpoint for all teams
- **Smart Routing** — AI-driven prompt difficulty classification routing to optimal model tiers
- **Semantic Caching** — Meaning-based deduplication of repeated questions
- **Multi-Tenant Governance** — Per-team virtual keys, rate limits, model allowlists, and cost budgets
- **Resilient Execution** — Automatic retries, failover, and timeout management
- **Full Observability** — Per-request metering, decision tracing, and an ops console

### The Hotel Reception Analogy

| Hotel Reception Desk       | Prism Gateway                    |
|----------------------------|----------------------------------|
| Checks your room card      | Validates your **virtual key**   |
| "Max 10 kitchen orders/min"| **Rate limiting** per tenant     |
| "Your room tab is full"    | **Budget enforcement**           |
| Routes order to a kitchen  | **Model routing** (fast/smart)   |
| Kitchen A closed → Kitchen B | **Automatic failover**         |
| "Same order as yesterday"  | **Semantic cache hit**           |
| Writes every order in ledger| **Request log + cost metering** |

---

## 2. Problem Statement & Goals

### The Problem

When 40+ teams independently connect to AI providers:

- **Key sprawl** — Every team manages their own API keys; secrets leak
- **No cost visibility** — Nobody knows who is spending how much
- **No resilience** — If a provider goes down, every team's app breaks
- **Duplicate spend** — Ten teams asking the same question pay ten times

### The Solution

A **single gateway** (Prism) that all teams route through, providing centralized authentication, cost management, intelligent routing, caching, and resilience.

### One-Sentence Summary

> Prism receives an AI request, checks it is allowed, picks the right model, forwards it, streams the answer back, and writes down what it cost.

### Key Objectives

| Objective                  | Metric                                    |
|----------------------------|--------------------------------------------|
| OpenAI API compatibility   | Pass `smoke_test.py` with all assertions   |
| Correct usage accounting   | Zero over-admission under load test        |
| Smart routing accuracy     | Beat length-only baseline on `routing_eval.jsonl` |
| Semantic cache effectiveness | Hit on paraphrased prompts, zero cross-tenant leaks |
| Failover reliability       | Seamless switchover when a provider is killed |
| Streaming correctness      | Token-by-token pass-through, proper `[DONE]` termination |

---

## 3. System Overview

```
 ┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
 │  Team A (search) │     │ Team B (support) │     │ Team C (content)│
 │  prism-sk-search │     │ prism-sk-support │     │ prism-sk-content│
 └────────┬────────┘     └────────┬────────┘     └────────┬────────┘
          │                       │                       │
          │     HTTP POST /v1/chat/completions            │
          │        + x-api-key: prism-sk-xxx              │
          └───────────────────────┼───────────────────────┘
                                  │
                                  ▼
                    ┌──────────────────────────┐
                    │      PRISM GATEWAY       │
                    │      (port 3000)         │
                    │                          │
                    │  ┌────────────────────┐  │
                    │  │  Request Pipeline  │  │
                    │  │  (Chain of Resp.)  │  │
                    │  └─────────┬──────────┘  │
                    │            │              │
                    │  ┌─────────┼──────────┐  │
                    │  │ Domain  │ Services │  │
                    │  │ Logic   │ Layer    │  │
                    │  └─────────┼──────────┘  │
                    │            │              │
                    │  ┌─────────┴──────────┐  │
                    │  │   Provider Layer   │  │
                    │  │  (Adapter Pattern) │  │
                    │  └─────────┬──────────┘  │
                    └────────────┼──────────────┘
                                 │
              ┌──────────────────┼──────────────────┐
              ▼                                     ▼
     ┌─────────────────┐                   ┌─────────────────┐
     │   Alpha Mock    │                   │   Beta Mock     │
     │   (port 9001)   │                   │   (port 9002)   │
     └─────────────────┘                   └─────────────────┘
```

### Component Inventory

| Component          | Type          | Purpose                                  |
|--------------------|---------------|------------------------------------------|
| Prism Gateway      | HTTP Server   | Core gateway, runs the request pipeline  |
| Alpha Mock         | Mock Provider | Primary LLM provider (OpenAI-compatible) |
| Beta Mock          | Mock Provider | Fallback LLM provider                    |
| SQLite Database    | Persistence   | Keys, usage, logs, cache                 |
| Ops Console        | Static HTML   | Admin dashboard (single HTML page)       |

---

## 4. High-Level Architecture

```
   ┌────────────┐
   │ Team's app │  (sends: "Hello, AI" + their virtual key)
   └─────┬──────┘
         │  HTTP  POST /v1/chat/completions
         ▼
 ┌────────────────────────────────────────────────────────────┐
 │                         PRISM                              │
 │                                                            │
 │   ┌──────────┐   ┌─────────────────────────────────────┐   │
 │   │ HTTP     │──►│         REQUEST PIPELINE            │   │
 │   │ layer    │   │ auth → limit → route → allow →      │   │
 │   │ (routes) │   │ budget → cache → CALL → meter → log │   │
 │   └──────────┘   └───────────────┬─────────────────────┘   │
 │                                  │                         │
 │            ┌─────────────────────┼───────────────────┐     │
 │            ▼                     ▼                   ▼     │
 │     ┌────────────┐      ┌──────────────┐     ┌───────────┐ │
 │     │ Domain     │      │  Executor    │     │ Storage   │ │
 │     │ logic      │      │ retry/timeout│     │ (SQLite)  │ │
 │     │ (cost,     │      │ /failover    │     └───────────┘ │
 │     │ limiter,   │      └──────┬───────┘                   │
 │     │ router,    │             │                           │
 │     │ cache)     │             ▼                           │
 │     └────────────┘      ┌──────────────┐                   │
 │                         │ Provider     │                   │
 │                         │ adapters     │                   │
 │                         └──────┬───────┘                   │
 └────────────────────────────────┼───────────────────────────┘
                                  │
                   ┌──────────────┴──────────────┐
                   ▼                             ▼
            ┌────────────┐                ┌────────────┐
            │ alpha mock │                │ beta mock  │
            │ port 9001  │                │ port 9002  │
            └────────────┘                └────────────┘
```

---

## 5. Layered Architecture (Hexagonal / Ports & Adapters)

Prism follows a **Hexagonal Architecture** (Ports & Adapters), organized in three concentric layers:

```
┌──────────────────────────────────────────────────────────────┐
│                    OUTER LAYER (Adapters)                     │
│   HTTP Routes · SQLite Repos · OpenAI Adapter · System Clock │
│                                                              │
│   ┌──────────────────────────────────────────────────────┐   │
│   │                 MIDDLE LAYER (Services)               │   │
│   │   Pipeline Orchestration · Stage Sequencing            │   │
│   │   "auth → limit → route → allow → budget → cache →    │   │
│   │    call → meter → log"                                 │   │
│   │                                                        │   │
│   │   ┌──────────────────────────────────────────────┐     │   │
│   │   │            INNER LAYER (Domain)               │     │   │
│   │   │   Pure Rules · No I/O · No Frameworks         │     │   │
│   │   │                                               │     │   │
│   │   │   CostCalculator · TokenBucket · CacheDecision│     │   │
│   │   │   DifficultyClassifier · Error Types           │     │   │
│   │   │   Data Models (VirtualKey, RequestContext)      │     │   │
│   │   └──────────────────────────────────────────────┘     │   │
│   └──────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────┘
```

### The Golden Rule: Arrows Point Inward

| Layer           | Responsibility              | Knows About              |
|-----------------|-----------------------------|--------------------------|
| **Outer (Edges)** | HTTP, Database, Network    | Frameworks, SQL, I/O     |
| **Middle (Services)** | Orchestrate pipeline steps | Order of operations    |
| **Inner (Domain)** | Pure business rules       | Nothing external — only plain data |

> The inner layer **never** imports the web framework or the database driver. Pure logic can be tested in milliseconds with zero setup, and you can swap SQLite for PostgreSQL without touching business rules.

---

## 6. Request Pipeline — Chain of Responsibility

Each request flows through a fixed sequence of stages. A stage either **passes the request along** or **rejects it with a typed error**.

```
 ┌──────────────────────────────────────────────────────────────────────┐
 │                        REQUEST PIPELINE                              │
 │                                                                      │
 │  ①  Assign request ID + start stopwatch                              │
 │  │                                                                   │
 │  ②  Authenticate (virtual key)            → fail: 401                │
 │  │                                                                   │
 │  ③  Validate request body                 → fail: 400                │
 │  │                                                                   │
 │  ④  Rate limit check                      → fail: 429 rate_limited   │
 │  │                                                                   │
 │  ⑤  Resolve model alias                   → fail: 404 not_found     │
 │  │   (if "auto" → classify difficulty first)                         │
 │  │                                                                   │
 │  ⑥  Allowlist check                       → fail: 403 not_allowed   │
 │  │                                                                   │
 │  ⑦  Budget check                          → fail: 429 budget_exceeded│
 │  │                                                                   │
 │  ⑧  Cache lookup                          → HIT? skip to ⑪          │
 │  │                                                                   │
 │  ⑨  Call provider (timeout/retry/failover)→ fail: 502 upstream_error │
 │  │                                                                   │
 │  ⑩  Meter the cost                                                   │
 │  │                                                                   │
 │  ⑪  Save to cache + write log + return response                      │
 └──────────────────────────────────────────────────────────────────────┘
```

### Why This Exact Order?

| Step | Rationale |
|------|-----------|
| **Auth first** | Without knowing *who*, no other check means anything |
| **Validate before spending** | Reject garbage cheaply |
| **Rate limit before budget** | Limiter is in-memory and fast; budget needs a DB read. Cheap checks protect expensive ones |
| **Resolve model before allowlist** | If a team sends `auto`, we must know the final tier. Otherwise `auto` becomes a loophole around the allowlist |
| **Budget before the call** | Check money *before* spending it |
| **Cache before the call** | A hit means zero provider contact |
| **Cache save only on success** | Never store errors — you'd serve broken answers forever |

### Response Headers Contract

Every response from Prism carries these custom headers:

| Header              | Description                           | Example                |
|---------------------|---------------------------------------|------------------------|
| `x-prism-request-id`  | Unique request trace ID              | `req_a1b2c3d4`         |
| `x-prism-provider`    | Which provider+model answered        | `alpha/alpha-small`    |
| `x-prism-cache`       | Cache result                         | `hit` or `miss`        |
| `x-prism-fallback`    | Whether fallback was used            | `true` or absent       |
| `x-prism-cost-usd`    | Cost in dollars (0 for cache hits)   | `0.000234`             |

---

## 7. Core Components (Building Blocks)

### 7.1 Config & Seed Loader

```
┌─────────────────────────────────────────────────┐
│                CONFIG & SEED LOADER              │
│                                                  │
│  Reads at startup:                               │
│  ├── seed_keys.json        → Virtual key configs │
│  ├── model_pricing.json    → Cost per token      │
│  └── gateway_config.json   → Aliases, providers  │
│                                                  │
│  Validates:                                      │
│  ├── Every alias → valid model in price table    │
│  ├── Every provider → reachable endpoint config  │
│  └── Required fields are present and typed       │
│                                                  │
│  On failure: CRASH LOUDLY (fail-fast principle)  │
└─────────────────────────────────────────────────┘
```

**Analogy:** A pilot's pre-flight checklist. You do not discover a missing engine mid-air.

**Key decisions:**
- Configs become **typed, read-only objects** after loading
- All alias-to-model mappings are validated against the price table at boot
- Seed keys are preserved exactly — demo flows and scripts reference them

---

### 7.2 Key Store & Authentication

```
┌────────────────────────────────────────┐
│           KEY STORE & AUTH              │
│                                        │
│  Virtual Key: prism-sk-search-1a2b3c   │
│                    │                   │
│                    ▼                   │
│  ┌──────────────────────────────────┐  │
│  │  Hash (SHA-256) → stored hash   │  │
│  │  Compare with constant-time fn  │  │
│  └──────────────────────────────────┘  │
│                    │                   │
│                    ▼                   │
│  ┌──────────────────────────────────┐  │
│  │  Return TenantConfig:            │  │
│  │  • tenant_id                     │  │
│  │  • budget_limit_usd              │  │
│  │  • rate_limit_rpm                │  │
│  │  • model_allowlist               │  │
│  │  • cache_enabled                 │  │
│  │  • cache_threshold               │  │
│  └──────────────────────────────────┘  │
└────────────────────────────────────────┘
```

**Critical security rules:**
- Store only **hashes** of keys, never raw values
- Compare using **constant-time** functions to prevent timing attacks
- The virtual key is the foundation — every other feature is "per key"

---

### 7.3 Rate Limiter (Token Bucket)

```
┌──────────────────────────────────────────────────┐
│              TOKEN BUCKET RATE LIMITER             │
│                                                    │
│  Key: prism-sk-search     Capacity: 10 tokens/min │
│                                                    │
│  ┌─────────────────────────────────────────────┐   │
│  │ Bucket: [●●●●●●●○○○]  7/10 tokens remain   │   │
│  │                                              │   │
│  │  Request arrives → ATOMIC check-and-decrement│   │
│  │  ├── tokens > 0 → ALLOW, decrement          │   │
│  │  └── tokens = 0 → REJECT (429)              │   │
│  │                                              │   │
│  │  Tokens refill over time via injected Clock  │   │
│  └─────────────────────────────────────────────┘   │
│                                                    │
│  ⚠ In-memory only (lost on restart)               │
│  ⚠ Must use lock for atomicity (prevent races)     │
└──────────────────────────────────────────────────┘
```

**The race condition problem:**
```
Rate limit: 10 RPM. Counter says 9.

  Request A reads counter: 9 → "OK, under 10"
  Request B reads counter: 9 → "OK, under 10"
  A writes 10. B writes 10.

  Result: 11 requests served (over-admission bug)

Fix: check-and-increment must be ONE ATOMIC STEP (use a lock)
```

**Design decisions:**
- Time comes from an **injected `Clock` interface** so tests can fast-forward without real delays
- In-memory storage is acceptable for single-instance deployment (documented as known limitation)

---

### 7.4 Budget & Usage Service

```
┌─────────────────────────────────────────────────────────────┐
│                    BUDGET & USAGE SERVICE                     │
│                                                              │
│  ┌─────────────────────┐    ┌────────────────────────────┐   │
│  │   CostCalculator    │    │     UsageRepository        │   │
│  │   (PURE FUNCTION)   │    │     (ATOMIC SQL)           │   │
│  │                     │    │                            │   │
│  │  prompt_tokens      │    │  UPDATE usage              │   │
│  │    × input_price    │    │  SET spend = spend + ?     │   │
│  │  + completion_tokens│    │  WHERE key = ?             │   │
│  │    × output_price   │    │    AND month = '2026-10'   │   │
│  │  ─────────────────  │    │                            │   │
│  │     ÷ 1,000,000     │    │  Monthly reset: new month  │   │
│  │                     │    │  = new row = fresh budget   │   │
│  └─────────────────────┘    └────────────────────────────┘   │
│                                                              │
│  Rule: Cost comes from provider's `usage` object, NEVER     │
│        from numbers the client claims.                       │
│                                                              │
│  Streaming wrinkle: Admit if budget remains at start;        │
│  record true cost at end. In-flight requests may overshoot   │
│  slightly — document the bound.                              │
└─────────────────────────────────────────────────────────────┘
```

**Two deliberately separated sub-parts:**
1. **CostCalculator** — Pure math function, no database, no network. Easiest thing to test.
2. **UsageRepository** — Atomic SQL updates. Never "read, add in code, write back."

---

### 7.5 Model Resolver & Smart Router (`auto`)

```
┌─────────────────────────────────────────────────────────────────┐
│                  MODEL RESOLVER & SMART ROUTER                   │
│                                                                  │
│  ┌──────────────────────────────┐                                │
│  │       AliasResolver          │   "fast" → alpha-small + beta  │
│  │   (plain lookup table)       │   "smart" → alpha-large + beta │
│  └──────────────────────────────┘                                │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │       DifficultyClassifier (Strategy Pattern)            │    │
│  │                                                          │    │
│  │   Input: "Prove that √2 is irrational"                   │    │
│  │                                                          │    │
│  │   ┌──────────────────┐  ┌──────────────────────────┐     │    │
│  │   │ HeuristicClassif.│  │ EmbeddingBasedClassif.   │     │    │
│  │   │ (keyword signals)│  │ (similarity to examples) │     │    │
│  │   └──────────────────┘  └──────────────────────────┘     │    │
│  │                                                          │    │
│  │   Signals for HARD: prove, derive, deadlock, code, math  │    │
│  │   Signals for EASY: list, extract, look up, name of      │    │
│  │                                                          │    │
│  │   Output: { tier: "smart", score: 0.82,                  │    │
│  │             reason: "proof request; judged complex" }     │    │
│  └──────────────────────────────────────────────────────────┘    │
│                                                                  │
│  ⚠ The trap: Length is a BAD signal                              │
│    • Short but hard: "Prove that √2 is irrational."             │
│    • Long but trivial: huge on-call roster, need one name       │
│                                                                  │
│  ⚠ Train/test discipline:                                       │
│    • Write your own 30-50 labeled examples to "study" from      │
│    • Test on routing_eval.jsonl (the exam) — NEVER peek at it   │
│    • Must beat a length-only baseline                            │
│                                                                  │
│  Every routing decision is LOGGED: tier, score, reason           │
└─────────────────────────────────────────────────────────────────┘
```

**Analogy:** A hospital triage nurse. A scraped knee → nurse; a heart attack → surgeon. The nurse judges *severity*, not *how long the patient talks*.

---

### 7.6 Semantic Cache

```
┌──────────────────────────────────────────────────────────────────┐
│                       SEMANTIC CACHE                              │
│                                                                   │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │ STEP 1: Is this cacheable?                                   │ │
│  │ ├── Cache enabled for this key?                              │ │
│  │ ├── Not an error response?                                   │ │
│  │ └── Not time-sensitive? ("now", "today", "latest", "current")│ │
│  └──────────────────────────────────────────────────────────────┘ │
│                                                                   │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │ STEP 2: Generate embedding                                   │ │
│  │                                                               │ │
│  │  Embedder (Interface / Strategy Pattern):                     │ │
│  │  ├── BagOfWordsEmbedder (default, offline, explainable)       │ │
│  │  │   count words → remove stop words → cosine similarity      │ │
│  │  └── [Future] RealEmbeddingModelEmbedder (swap without change)│ │
│  └──────────────────────────────────────────────────────────────┘ │
│                                                                   │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │ STEP 3: Search (SCOPED BY KEY — structural isolation)         │ │
│  │                                                               │ │
│  │  SELECT * FROM cache_entries                                  │ │
│  │  WHERE key_hash = ? AND alias = ?     ◄── SCOPE IS THE QUERY │ │
│  │  ORDER BY similarity DESC                                     │ │
│  │                                                               │ │
│  │  if similarity >= threshold → CACHE HIT                       │ │
│  │  else                       → CACHE MISS                      │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                                                                   │
│  ⚠ BIGGEST DANGER: Cross-tenant data leakage                     │
│    Fix: key is part of the query itself (impossible by            │
│    construction, not "search everything, then filter")            │
│                                                                   │
│  Cache key composition: system_prompt + last_user_message         │
│                                                                   │
│  Threshold tuning:                                                │
│  • Too low → wrong answers ("password reset" ≠ "2FA reset")      │
│  • Too high → no benefit                                         │
│  • Recommended starting point: 0.85                               │
└──────────────────────────────────────────────────────────────────┘
```

---

### 7.7 Provider Adapter

```
┌──────────────────────────────────────────────────────────┐
│                    PROVIDER ADAPTER                        │
│                                                           │
│  ┌──────────────────────────────────────────────────────┐ │
│  │           ProviderAdapter (Interface / Port)          │ │
│  │                                                       │ │
│  │  + complete(request) → CompletionResponse             │ │
│  │  + stream(request)   → AsyncIterator<Chunk>           │ │
│  └──────────────────┬────────────────────────────────────┘ │
│                     │                                      │
│         ┌───────────┼───────────────────┐                  │
│         │           │                   │                  │
│         ▼           ▼                   ▼                  │
│  ┌────────────┐ ┌────────────┐  ┌────────────────┐        │
│  │OpenAI      │ │OpenAI      │  │ FakeAdapter    │        │
│  │Compatible  │ │Compatible  │  │ (tests only)   │        │
│  │(alpha)     │ │(beta)      │  │ canned replies │        │
│  └────────────┘ └────────────┘  └────────────────┘        │
│                                                           │
│  Provider API keys: from ENV VARS only, never from git    │
│                                                           │
│  Liskov Substitution: FakeAdapter works wherever          │
│  OpenAICompatibleAdapter does — rest of code can't tell   │
└──────────────────────────────────────────────────────────┘
```

**Analogy:** A travel plug adapter. Your laptop (Prism) has one plug shape; the adapter fits any wall socket (provider).

---

### 7.8 Resilient Executor (Retry, Timeout, Failover)

```
┌────────────────────────────────────────────────────────────────┐
│                    RESILIENT EXECUTOR                            │
│                                                                 │
│  Three error categories (the key idea):                         │
│                                                                 │
│  ┌───────────────┬──────────────────────┬─────────────────────┐ │
│  │   RETRYABLE    │   FAILOVER-WORTHY    │      FATAL          │ │
│  ├───────────────┼──────────────────────┼─────────────────────┤ │
│  │ 500s, timeout │ 429 from provider    │ 400 (bad request)   │ │
│  │ conn. reset   │ Provider is down     │ Malformed input     │ │
│  ├───────────────┼──────────────────────┼─────────────────────┤ │
│  │ Wait + retry  │ Skip to next         │ STOP immediately    │ │
│  │ same provider │ provider in chain    │ Retrying won't help │ │
│  │ (exp. backoff │                      │                     │ │
│  │  + jitter)    │                      │                     │ │
│  └───────────────┴──────────────────────┴─────────────────────┘ │
│                                                                 │
│  Timeouts (all configurable):                                   │
│  ├── Connect timeout        (e.g., 5s)                          │
│  ├── Total request timeout  (e.g., 30s)                         │
│  └── Stream idle timeout    (e.g., 10s — no new chunk = dead)   │
│                                                                 │
│  Recording: retries count + fallback flag → log + headers       │
└────────────────────────────────────────────────────────────────┘
```

**Analogy:** A delivery driver with a plan: "If the road is blocked, wait and retry. If still blocked, take another route."

---

### 7.9 Streaming Proxy (SSE Pass-Through)

```
┌──────────────────────────────────────────────────────────────────┐
│                    STREAMING PROXY (The Tee Pattern)              │
│                                                                   │
│  Without streaming:                                               │
│  Client ──ask──► Prism ──ask──► Provider                          │
│  Client ◄─────── (5 sec wait, all at once) ◄────── Provider      │
│                                                                   │
│  With streaming:                                                  │
│  Client ──ask──► Prism ──ask──► Provider                          │
│  Client ◄─ "Hel" ◄─ "Hel" ◄── Provider writes "Hel"             │
│  Client ◄─ "lo"  ◄─ "lo"  ◄── Provider writes "lo"              │
│  Client ◄─ "!"   ◄─ "!"   ◄── Provider writes "!"              │
│  Client ◄─ [DONE]                                                │
│                                                                   │
│  The Tee:                                                         │
│  Provider ──chunk──► [ Prism ] ──chunk──► Client                  │
│                         │                                         │
│                         └─ peek: is this the usage chunk?         │
│                            save the numbers for metering          │
│                                                                   │
│  Rules:                                                           │
│  1. NEVER BUFFER — forward each chunk immediately                 │
│  2. try/finally ALWAYS records usage (even if client disconnects) │
│  3. Headers go first — failover decided BEFORE first chunk        │
│  4. Mid-stream provider death → SSE error event + close           │
│     (NO mid-stream provider switching — franken-answers)          │
│  5. Cache hit on stream → replay as one chunk + [DONE]            │
└──────────────────────────────────────────────────────────────────┘
```

---

### 7.10 Request Logger & Metering

```
┌──────────────────────────────────────────────────────────────────┐
│                   REQUEST LOGGER & METERING                       │
│                                                                   │
│  Two separate record types:                                       │
│                                                                   │
│  1. Request Log Table (SQLite)                                    │
│     One row per request (including rejections)                    │
│     Fields: request_id, key_hash, model, provider, status,        │
│             tokens, cost, cache_result, fallback, latency_ms      │
│                                                                   │
│  2. Application Logs (stdout, JSON lines)                         │
│     Structured, machine-searchable                                │
│     Every line includes request_id                                │
│                                                                   │
│  Decision Trace (per request):                                    │
│  "auth ok → rate ok → auto→smart (score 0.82, proof request)     │
│   → cache miss → alpha-large 200 (0 retries)"                    │
│                                                                   │
│  NEVER LOG: raw virtual keys, provider keys, or full prompts     │
└──────────────────────────────────────────────────────────────────┘
```

---

### 7.11 Admin API & Ops Console

```
┌──────────────────────────────────────────────────────────────────┐
│                   ADMIN API & OPS CONSOLE                         │
│                                                                   │
│  Endpoints (read-only, protected by admin token):                 │
│  ├── GET /admin/usage         → Usage by key and month            │
│  ├── GET /admin/logs          → Recent request logs               │
│  ├── GET /admin/cache/stats   → Cache hit rates                   │
│  └── GET /health              → Health check                      │
│                                                                   │
│  Console: ONE static HTML page with vanilla JavaScript            │
│  ├── No React, no build step                                      │
│  ├── Calls admin endpoints, renders tables                        │
│  └── Shows: usage by key, recent requests, cache hit rate         │
│                                                                   │
│  Protection: separate admin token, bound to localhost              │
└──────────────────────────────────────────────────────────────────┘
```

---

## 8. Streaming Architecture

### SSE (Server-Sent Events) Flow

```
                    ┌─────────────┐
                    │   Client    │
                    └──────┬──────┘
                           │ POST /v1/chat/completions
                           │ { "stream": true }
                           ▼
                    ┌─────────────┐
                    │   Prism     │
                    │ (pipeline)  │
                    └──────┬──────┘
                           │ Forwarded request
                           ▼
                    ┌─────────────┐
                    │  Provider   │
                    └──────┬──────┘
                           │
                           ▼
              ┌────────────────────────┐
              │  SSE Chunk Stream      │
              │                        │
              │  data: {"choices":[    │ ──► Forward to client immediately
              │    {"delta":{"content":│
              │    "Hel"}}]}           │
              │                        │
              │  data: {"choices":[    │ ──► Forward to client immediately
              │    {"delta":{"content":│
              │    "lo"}}]}            │
              │                        │
              │  data: {"choices":[    │ ──► Forward + PEEK at usage
              │    {"delta":{},        │
              │    "usage":{...}}]}    │
              │                        │
              │  data: [DONE]          │ ──► Forward + trigger finally{} block
              └────────────────────────┘

              finally {
                  record_usage()     // ALWAYS runs
                  write_log()        // even if client disconnected
              }
```

### Key Streaming Decisions

| Scenario | Decision |
|----------|----------|
| Provider dies mid-stream (after first byte sent) | Send SSE error event, close stream. **No provider switching** |
| Provider dies before first byte | Failover to next provider is allowed |
| Client disconnects mid-stream | Stop reading upstream, settle usage in `finally` |
| Cache hit on `stream: true` request | Replay cached answer as one chunk + `[DONE]` |
| Headers (x-prism-*) | Sent before first chunk — failover decided beforehand |

---

## 9. Failure Handling Matrix

| Situation | What Prism Does | Client Sees |
|-----------|-----------------|-------------|
| Alpha is down (connection refused) | Skip to beta immediately | Normal answer, `x-prism-fallback: true` |
| Alpha returns a 500 once | Wait, retry alpha, success | Normal answer, `retries: 1` in log |
| Alpha is slow (3s+) | Timeout fires, failover to beta | Normal answer, slightly slower |
| Alpha is flaky (30% failures) | Retries absorb most failures | Almost always success |
| Both providers fail | Give up cleanly | `502 upstream_error` JSON |
| Alpha restored after outage | Next request goes to alpha again | Back to normal |
| Alpha dies mid-stream | Send SSE error event, close | Stream ends with error event |
| Client disconnects mid-stream | Stop reading upstream, settle usage in `finally` | N/A |
| Provider returns garbage JSON | Treat as retryable upstream error | Fallback or clean 502 |

---

## 10. Data Architecture

### SQLite Database Schema

```sql
-- Virtual keys (seeded at startup)
CREATE TABLE virtual_keys (
    key_hash        TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    budget_usd      REAL NOT NULL,
    rate_limit_rpm  INTEGER NOT NULL,
    allowlist       TEXT NOT NULL,       -- JSON array of allowed models/aliases
    cache_enabled   BOOLEAN DEFAULT 1,
    cache_threshold REAL DEFAULT 0.85,
    status          TEXT DEFAULT 'active'
);

-- Usage tracking (per key per month)
CREATE TABLE usage (
    key_hash        TEXT NOT NULL,
    month           TEXT NOT NULL,       -- '2026-10' format
    total_spend_usd REAL DEFAULT 0,
    total_tokens    INTEGER DEFAULT 0,
    total_requests  INTEGER DEFAULT 0,
    cache_hits      INTEGER DEFAULT 0,
    PRIMARY KEY (key_hash, month)
);

-- Request logs (one row per request, including rejections)
CREATE TABLE request_logs (
    request_id      TEXT PRIMARY KEY,
    key_hash        TEXT,
    model_requested TEXT,
    model_resolved  TEXT,
    provider        TEXT,
    status_code     INTEGER,
    prompt_tokens   INTEGER,
    completion_tokens INTEGER,
    cost_usd        REAL,
    cache_result    TEXT,               -- 'hit', 'miss', 'skip'
    fallback_used   BOOLEAN DEFAULT 0,
    retries         INTEGER DEFAULT 0,
    latency_ms      INTEGER,
    decision_trace  TEXT,               -- JSON decision log
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Semantic cache entries
CREATE TABLE cache_entries (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    key_hash        TEXT NOT NULL,      -- Scoping by tenant
    alias           TEXT NOT NULL,
    prompt_hash     TEXT NOT NULL,
    embedding       TEXT NOT NULL,      -- JSON array (never pickle/eval)
    response_body   TEXT NOT NULL,      -- Full response JSON
    hit_count       INTEGER DEFAULT 0,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### Data Residency Map

| Data | Storage | Survives Restart? |
|------|---------|-------------------|
| Virtual keys | SQLite (`virtual_keys`) | ✅ Yes |
| Usage totals | SQLite (`usage`) | ✅ Yes |
| Request logs | SQLite (`request_logs`) | ✅ Yes |
| Cache entries | SQLite (`cache_entries`) | ✅ Yes |
| Rate limiter buckets | **In-memory** | ❌ No (known limitation) |

### Concurrency Notes

SQLite allows **one writer at a time**. This is a feature for a single-instance learning project:
- Writes queue up sequentially → atomic updates are simple
- Use short transactions and a **busy timeout** (e.g., 5 seconds)
- Atomic budget updates: `UPDATE usage SET spend = spend + ?` (never read-add-write)

---

## 11. Security Architecture

| Risk | Defence |
|------|---------|
| Stolen database reveals all keys | Store **SHA-256 hashes**, not raw keys |
| Timing attacks guess keys letter by letter | Compare with a **constant-time** function |
| Provider secrets leak in error messages | Keys only in **environment variables**; client errors are generic |
| One team reads another's cached answers | Cache lookup is **scoped by key** structurally |
| `auto` sneaks past the allowlist | Allowlist is checked on the **resolved** model, not just `auto` |
| A caller sends a 500 MB body | **Body size limit** on the HTTP server |
| A caller requests `max_tokens: 10,000,000` | **Cap** `max_tokens` in validation |
| Anyone can open the admin pages | **Separate admin token**, bind to `localhost` |
| Logs expose secrets or private prompts | Log key **prefix/hash** only; no prompt bodies by default |
| Malicious data in database runs code | Use **JSON** for stored embeddings; never `pickle`/`eval` |
| Detailed errors help attackers | Detail goes in **server logs**, not client responses |

---

## 12. API Contract

### Data Plane

#### `POST /v1/chat/completions`

OpenAI-compatible chat completions endpoint.

**Request:**
```json
{
    "model": "fast",           // alias: "fast", "smart", "auto", or direct model name
    "messages": [
        { "role": "system", "content": "You are a helpful assistant." },
        { "role": "user", "content": "What is the capital of France?" }
    ],
    "stream": false,           // true for SSE streaming
    "max_tokens": 500,
    "temperature": 0.7
}
```

**Headers:**
```
x-api-key: prism-sk-search-1a2b3c
Content-Type: application/json
```

**Response (non-streaming):**
```json
{
    "id": "chatcmpl-abc123",
    "object": "chat.completion",
    "model": "alpha-small",
    "choices": [
        {
            "index": 0,
            "message": { "role": "assistant", "content": "The capital of France is Paris." },
            "finish_reason": "stop"
        }
    ],
    "usage": {
        "prompt_tokens": 25,
        "completion_tokens": 10,
        "total_tokens": 35
    }
}
```

**Response Headers:**
```
x-prism-request-id: req_a1b2c3d4
x-prism-provider: alpha/alpha-small
x-prism-cache: miss
x-prism-cost-usd: 0.000035
```

**Error Responses:**

| Status | Type | Cause |
|--------|------|-------|
| 400 | `invalid_request` | Malformed body, missing fields |
| 401 | `authentication_error` | Invalid or missing virtual key |
| 403 | `model_not_allowed` | Model not in key's allowlist |
| 404 | `not_found_error` | Unknown model or alias |
| 429 | `rate_limit_exceeded` | RPM limit exceeded |
| 429 | `budget_exceeded` | Monthly budget exhausted |
| 502 | `upstream_error` | All providers failed |

### Admin Plane

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/admin/usage` | GET | Usage summary by key and month |
| `/admin/logs` | GET | Recent request logs with filters |
| `/admin/cache/stats` | GET | Cache hit rates and stats |
| `/health` | GET | Health check (no auth required) |

---

## 13. Design Patterns & Principles

### SOLID Principles Applied

| Principle | Application in Prism |
|-----------|---------------------|
| **S** — Single Responsibility | `CostCalculator` only does cost math. Nothing else. |
| **O** — Open/Closed | Add a new pipeline stage without editing existing ones |
| **L** — Liskov Substitution | `FakeAdapter` works wherever `OpenAICompatibleAdapter` does |
| **I** — Interface Segregation | The limiter doesn't need to know about databases |
| **D** — Dependency Inversion | Services depend on `Clock`/`Repository` interfaces, not concretes |

### Design Patterns Used

| Pattern | Where | Purpose |
|---------|-------|---------|
| **Chain of Responsibility** | Request pipeline | Pass-it-along stages, each doing one job |
| **Strategy** | Classifier, Embedder | Swappable algorithms behind one interface |
| **Adapter** | Provider layer | Translate provider-specific APIs into one interface |
| **Repository** | Database access | Hide SQL behind `get`/`save` methods |
| **Decorator** | Retry around adapter | Wrap to add behavior without modifying the original |
| **Composition Root** | `main.py` | The ONE place where objects are created and wired together |

### Key Practices

- **Dependency Injection:** Every class receives its dependencies from outside (enables testing with fakes)
- **DRY with caution:** Duplicate twice, abstract on the third. Wrong abstractions are worse than duplication.
- **Fail fast:** Config errors crash at boot, not at runtime under load
- **Typed errors:** One base `PrismError`, one subclass per rejection type. Single error handler maps to HTTP responses.

---

## 14. Folder Structure

```
prism-llm-gateway/
├── prism/                       # Main application package
│   ├── domain/                  # PURE logic. No web, no DB, no network.
│   │   ├── models.py            #   Data shapes (VirtualKey, RequestContext, ...)
│   │   ├── errors.py            #   PrismError and subclasses
│   │   ├── cost.py              #   CostCalculator (pure math)
│   │   ├── limiter.py           #   Token bucket rate limiter
│   │   └── cache_decision.py    #   "Is this cacheable? Is this a hit?"
│   │
│   ├── ports/                   # INTERFACES (contracts) only
│   │   ├── provider.py          #   ProviderAdapter interface
│   │   ├── embedder.py          #   Embedder interface
│   │   ├── repositories.py      #   KeyRepo, UsageRepo, LogRepo, CacheRepo
│   │   └── clock.py             #   Clock interface
│   │
│   ├── adapters/                # REAL implementations of the ports
│   │   ├── sqlite_repos.py      #   SQLite-backed repositories
│   │   ├── openai_compatible.py #   OpenAI-compatible provider adapter
│   │   ├── bow_embedder.py      #   Bag-of-words embedder
│   │   └── system_clock.py      #   System clock (real time)
│   │
│   ├── services/                # Orchestration and pipeline stages
│   │   ├── pipeline.py          #   Pipeline orchestrator
│   │   ├── stages/              #   Individual stages:
│   │   │   ├── auth.py          #     Authentication stage
│   │   │   ├── ratelimit.py     #     Rate limiting stage
│   │   │   ├── resolve.py       #     Model resolution stage
│   │   │   ├── allowlist.py     #     Allowlist check stage
│   │   │   ├── budget.py        #     Budget check stage
│   │   │   └── cache.py         #     Cache lookup stage
│   │   ├── router.py            #   DifficultyClassifier implementations
│   │   ├── executor.py          #   Retry / timeout / failover logic
│   │   ├── streaming.py         #   SSE streaming proxy
│   │   └── cache_service.py     #   Cache orchestration
│   │
│   ├── api/                     # HTTP: routes, SSE, error mapping, admin
│   │   ├── routes.py            #   Chat completions endpoint
│   │   ├── admin.py             #   Admin endpoints
│   │   └── error_handler.py     #   PrismError → HTTP JSON mapping
│   │
│   ├── config/                  # Loaders + startup validation
│   │   ├── loader.py            #   Config file parser
│   │   └── settings.py          #   Typed configuration objects
│   │
│   └── main.py                  # Composition root (wires everything together)
│
├── console/                     # One static HTML page (ops dashboard)
│   └── index.html
│
├── data/                        # Seed data files (provided)
│   ├── seed_keys.json
│   ├── model_pricing.json
│   └── gateway_config.sample.json
│
├── scripts/                     # Provided verification scripts
│   ├── smoke_test.py
│   ├── load_test.py
│   └── routing_eval.py
│
├── tests/                       # Test suites
│   ├── unit/                    #   Pure domain logic tests
│   ├── integration/             #   DB + HTTP integration tests
│   ├── concurrency/             #   Race condition tests
│   └── contract/                #   Provider contract tests
│
├── docs/                        # Documentation
│   ├── architecture.md          #   This file
│   ├── PRISM_ARCHITECTURE.md    #   Detailed beginner's guide
│   ├── Prism.pdf                #   Project specification
│   └── adr/                     #   Architecture Decision Records
│
├── Dockerfile                   # Multi-stage production Docker build
├── docker-compose.yml           # Full stack: gateway + mock providers
├── .dockerignore
├── .env.example                 # Environment variable template
├── requirements.txt             # Python dependencies
├── README.md                    # Detailed setup, API docs, design decisions
└── LICENSE
```

### How to Read the Folders

| Folder | Role | Analogy |
|--------|------|---------|
| `domain/` | Knows **nothing** about the outside world | Pure brain |
| `ports/` | Declares **what** is needed | Job postings |
| `adapters/` | Provides **how** | Hired workers |
| `services/` | Decides **when** and in what order | Manager |
| `api/` | Translates HTTP to/from all of the above | Receptionist |

---

## 15. Docker Architecture

### Container Topology

```
┌─────────────────────────────────────────────────────────┐
│                    docker-compose.yml                     │
│                                                          │
│  ┌──────────────────────────────────────────────────┐   │
│  │              prism-gateway                        │   │
│  │              (port 3000:3000)                      │   │
│  │                                                    │   │
│  │  Python app + SQLite                               │   │
│  │  Depends on: alpha-mock, beta-mock                 │   │
│  │  Volumes: ./data:/app/data (persistence)           │   │
│  │  Env: .env file                                    │   │
│  └──────────────────────────────────────────────────┘   │
│                                                          │
│  ┌────────────────────┐  ┌────────────────────┐         │
│  │    alpha-mock       │  │    beta-mock        │        │
│  │   (port 9001:9001)  │  │   (port 9002:9002)  │        │
│  │                     │  │                     │        │
│  │  Mock LLM provider  │  │  Mock LLM provider  │        │
│  │  (OpenAI-compatible) │  │  (OpenAI-compatible) │       │
│  └────────────────────┘  └────────────────────┘         │
│                                                          │
│  Network: prism-network (bridge)                         │
└─────────────────────────────────────────────────────────┘
```

### Dockerfile (Multi-Stage Build)

```dockerfile
# === Stage 1: Builder ===
FROM python:3.12-slim AS builder

WORKDIR /app

# Install dependencies first for layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Copy application code
COPY . .

# === Stage 2: Production ===
FROM python:3.12-slim AS production

# Create non-root user for security
RUN groupadd -r prism && useradd -r -g prism prism

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /root/.local /root/.local
COPY --from=builder /app .

# Ensure scripts in .local are available
ENV PATH=/root/.local/bin:$PATH

# Set environment defaults
ENV PRISM_PORT=3000 \
    PRISM_LOG_LEVEL=INFO \
    PRISM_DB_PATH=/app/data/prism.db

# Create data directory for SQLite persistence
RUN mkdir -p /app/data && chown -R prism:prism /app/data

# Expose the gateway port
EXPOSE 3000

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:3000/health')" || exit 1

# Run as non-root
USER prism

# Start the gateway
CMD ["python", "-m", "prism.main"]
```

### docker-compose.yml

```yaml
version: "3.9"

services:
  alpha-mock:
    image: python:3.12-slim
    container_name: prism-alpha-mock
    working_dir: /app
    volumes:
      - ./scripts:/app/scripts
    command: python scripts/mock_provider.py --port 9001 --name alpha
    ports:
      - "9001:9001"
    networks:
      - prism-network
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:9001/health')"]
      interval: 10s
      timeout: 5s
      retries: 3

  beta-mock:
    image: python:3.12-slim
    container_name: prism-beta-mock
    working_dir: /app
    volumes:
      - ./scripts:/app/scripts
    command: python scripts/mock_provider.py --port 9002 --name beta
    ports:
      - "9002:9002"
    networks:
      - prism-network
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:9002/health')"]
      interval: 10s
      timeout: 5s
      retries: 3

  prism-gateway:
    build:
      context: .
      dockerfile: Dockerfile
      target: production
    container_name: prism-gateway
    ports:
      - "3000:3000"
    volumes:
      - prism-data:/app/data       # Persist SQLite database
      - ./data:/app/seed-data:ro   # Mount seed data as read-only
    env_file:
      - .env
    environment:
      - ALPHA_PROVIDER_URL=http://alpha-mock:9001
      - BETA_PROVIDER_URL=http://beta-mock:9002
      - PRISM_PORT=3000
      - PRISM_LOG_LEVEL=INFO
    depends_on:
      alpha-mock:
        condition: service_healthy
      beta-mock:
        condition: service_healthy
    networks:
      - prism-network
    restart: unless-stopped

volumes:
  prism-data:
    driver: local

networks:
  prism-network:
    driver: bridge
```

### .env.example

```env
# === Prism Gateway Configuration ===

# Server
PRISM_PORT=3000
PRISM_LOG_LEVEL=INFO          # DEBUG | INFO | WARNING | ERROR

# Database
PRISM_DB_PATH=/app/data/prism.db

# Provider Endpoints (set automatically by Docker Compose)
ALPHA_PROVIDER_URL=http://localhost:9001
ALPHA_PROVIDER_KEY=mock-alpha-key
BETA_PROVIDER_URL=http://localhost:9002
BETA_PROVIDER_KEY=mock-beta-key

# Admin
PRISM_ADMIN_TOKEN=admin-secret-change-me

# Timeouts (seconds)
PRISM_CONNECT_TIMEOUT=5
PRISM_REQUEST_TIMEOUT=30
PRISM_STREAM_IDLE_TIMEOUT=10

# Retry
PRISM_MAX_RETRIES=2
PRISM_RETRY_BASE_DELAY=1

# Cache
PRISM_DEFAULT_CACHE_THRESHOLD=0.85

# Security
PRISM_MAX_BODY_SIZE=1048576   # 1 MB
PRISM_MAX_TOKENS_CAP=4096
```

### Docker Commands Quick Reference

```bash
# Build and start all services
docker-compose up --build -d

# View logs
docker-compose logs -f prism-gateway

# Run smoke tests against the running stack
docker-compose exec prism-gateway python scripts/smoke_test.py

# Run load tests
docker-compose exec prism-gateway python scripts/load_test.py

# Stop all services
docker-compose down

# Stop and remove volumes (fresh start)
docker-compose down -v

# Rebuild only the gateway
docker-compose up --build -d prism-gateway

# Simulate provider failure (stop alpha)
docker-compose stop alpha-mock

# Restore provider
docker-compose start alpha-mock

# View database
docker-compose exec prism-gateway sqlite3 /app/data/prism.db ".tables"
```

---

## 16. Development Timeline (15 Days × 2.5 hrs/day)

**Total available time: 37.5 hours**

### Phase Overview

```
┌──────────────────────────────────────────────────────────────────┐
│                    15-DAY DEVELOPMENT TIMELINE                    │
│                                                                   │
│  Phase 1: Foundations          │ Days 1-3   │  7.5 hrs │  20%    │
│  Phase 2: Auth & Governance    │ Days 4-6   │  7.5 hrs │  20%    │
│  Phase 3: Streaming & Resil.   │ Days 7-9   │  7.5 hrs │  20%    │
│  Phase 4: Intelligence         │ Days 10-12 │  7.5 hrs │  20%    │
│  Phase 5: Docker, Console, Docs│ Days 13-15 │  7.5 hrs │  20%    │
└──────────────────────────────────────────────────────────────────┘
```

### Detailed Daily Plan

#### Phase 1: Foundations (Days 1–3, 7.5 hrs)

| Day | Time | Tasks | Deliverables |
|-----|------|-------|--------------|
| **Day 1** | 2.5h | Project setup, folder structure, domain models (`models.py`, `errors.py`), config loader | Typed config objects, error hierarchy, project compiles |
| **Day 2** | 2.5h | Provider adapter (OpenAI-compatible), basic HTTP server, non-streaming pass-through | `POST /v1/chat/completions` works end-to-end with one provider |
| **Day 3** | 2.5h | Response headers (`x-prism-*`), request ID generation, basic request logging, health endpoint | Headers on every response, `request_id` in logs, `/health` works |

**✅ Phase 1 Definition of Done:**
- `curl` a non-streaming request → get a response with correct headers
- Config validation crashes on bad data at startup
- Basic unit tests for error types and config loader

---

#### Phase 2: Auth & Governance (Days 4–6, 7.5 hrs)

| Day | Time | Tasks | Deliverables |
|-----|------|-------|--------------|
| **Day 4** | 2.5h | Key store, virtual key hashing, authentication stage, seed loader | Auth works: valid key → 200, bad key → 401 |
| **Day 5** | 2.5h | Rate limiter (token bucket with lock), rate limit stage, injected `Clock` | Rate limiting works: 11th request in 1 minute → 429 |
| **Day 6** | 2.5h | Cost calculator (pure function), budget service (atomic SQL), allowlist stage, usage table | Budget enforcement: exceeded → 429, allowlist: wrong model → 403 |

**✅ Phase 2 Definition of Done:**
- All rejection types return correct error codes
- Rate limiter passes concurrent test (no over-admission)
- Cost calculation matches expected values for known inputs
- Unit tests for limiter, cost calculator, auth

---

#### Phase 3: Streaming & Resilience (Days 7–9, 7.5 hrs)

| Day | Time | Tasks | Deliverables |
|-----|------|-------|--------------|
| **Day 7** | 2.5h | SSE streaming proxy (tee pattern), `stream: true` support, usage extraction from final chunk | Streaming works token-by-token, proper `[DONE]` termination |
| **Day 8** | 2.5h | Resilient executor: retry with exponential backoff, failover logic, timeout management | Retry on 500, failover on provider down, `x-prism-fallback` header |
| **Day 9** | 2.5h | Stream error handling (mid-stream failure), `try/finally` safety net, request log table (all requests including rejections) | `finally` always records usage, mid-stream errors handled gracefully |

**✅ Phase 3 Definition of Done:**
- Streaming responses flow token-by-token (not buffered)
- Killing alpha mock → requests succeed via beta with fallback header
- `finally` block records usage even on client disconnect
- Load test shows no dropped requests under concurrency

---

#### Phase 4: Intelligence (Days 10–12, 7.5 hrs)

| Day | Time | Tasks | Deliverables |
|-----|------|-------|--------------|
| **Day 10** | 2.5h | Model resolver (alias → model chain), `auto` alias, difficulty classifier (heuristic v1), training examples | `model: "auto"` routes to correct tier, routing decisions logged |
| **Day 11** | 2.5h | Semantic cache: bag-of-words embedder, cache store, cache decision logic, tenant scoping | Cache hit on paraphrased prompt, no cross-tenant leakage |
| **Day 12** | 2.5h | Refine classifier (beat length-only baseline), run routing eval, tune cache threshold, integration tests | Routing eval accuracy > baseline, cache hit rate on paraphrase pairs |

**✅ Phase 4 Definition of Done:**
- `auto` routing beats length-only baseline on `routing_eval.jsonl`
- "Reset my password" and "How do I change my password?" produce cache hit
- "Password reset" and "2FA reset" do NOT produce cache hit
- Team A's cache entries are invisible to Team B

---

#### Phase 5: Docker, Console & Docs (Days 13–15, 7.5 hrs)

| Day | Time | Tasks | Deliverables |
|-----|------|-------|--------------|
| **Day 13** | 2.5h | Dockerfile (multi-stage), docker-compose.yml, `.env.example`, `.dockerignore` | `docker-compose up --build` starts entire stack |
| **Day 14** | 2.5h | Admin API endpoints, ops console (single HTML page), ADRs | Console shows usage by key, recent requests, cache hit rate |
| **Day 15** | 2.5h | README.md (comprehensive), smoke test pass, load test report, final polish | All verification scripts pass, documentation complete |

**✅ Phase 5 Definition of Done:**
- `docker-compose up` → full stack running, smoke test passes
- Ops console accessible at `/console`
- README covers: setup, API docs, architecture, design decisions, known limitations
- Load test report and routing eval results documented
- ADRs written for all 8 required decisions

---

### Risk Buffer

The timeline allocates exactly 37.5 hours to 37.5 hours of estimated work. If any phase runs over, apply these mitigation strategies:

| Risk | Mitigation |
|------|------------|
| Streaming is harder than expected | Start with non-streaming first, streaming is an incremental add |
| Classifier accuracy is low | Heuristic approach is faster to iterate than ML; start with keyword signals |
| Docker issues | Docker is in Phase 5; the app works locally even without it |
| Scope creep | The admin console is intentionally minimal — no React, no build step |

---

## 17. Architecture Decision Records (ADRs)

Each ADR is a half-page note with: **Context → Decision → Consequences**.

### ADR-001: Cache Hits and Rate Limits / Budgets

- **Context:** Should a cache hit consume rate-limit quota? Should it be served if the budget is empty?
- **Decision:** Cache hits **do** consume rate-limit quota (to prevent abuse). Budget: cost is $0, so **allow** cache hits even if budget is spent.
- **Consequences:** Teams get free answers from cache even after budget exhaustion. Rate limiter prevents cache flooding.

### ADR-002: Mid-Stream Provider Failure

- **Context:** What happens if a provider dies while streaming?
- **Decision:** Send an SSE error event and close the stream. **No mid-stream provider switching** — splicing two outputs produces incoherent answers.
- **Consequences:** Some streams will end with an error. Before first byte → failover is fine. Document clearly.

### ADR-003: Budget Overshoot During Streaming

- **Context:** For streaming, the final cost is unknown when the request starts.
- **Decision:** Admit the request if budget remains. Record true cost at the end. Accept slight overshoot.
- **Consequences:** A few concurrent in-flight requests can overshoot the budget by the sum of their costs. Document the bound.

### ADR-004: Cache Scope and Multi-Turn Keying

- **Context:** What constitutes a cache key for multi-turn conversations?
- **Decision:** Scope by `key_hash + alias`. Cache key is composed of `system_prompt + last_user_message`.
- **Consequences:** Changing the system prompt creates a new cache entry. Very long conversations with different early messages but same final question may match.

### ADR-005: Time-Sensitive Content (Never Cached)

- **Context:** Some prompts ask about current state and should never return cached answers.
- **Decision:** If the prompt contains any of: "now", "today", "latest", "current", "right now", "this moment" → skip cache.
- **Consequences:** Simple keyword filter. May have false positives. Document the list and allow configuration.

### ADR-006: Prompt Storage in Logs

- **Context:** Should request logs store the full prompt text?
- **Decision:** **No**, by default. Log metadata only (key hash, model, tokens, cost, latency). Enable prompt logging via env var for debugging.
- **Consequences:** Privacy-safe by default. Debugging may require enabling prompt logging temporarily.

### ADR-007: `auto` and Allowlist Interaction

- **Context:** If a team's allowlist says `["fast"]` and they send `model: "auto"`, what happens if auto resolves to `smart`?
- **Decision:** Check **both** `auto` and the resolved tier against the allowlist. The allowlist should explicitly include `auto` if the team is allowed to use smart routing.
- **Consequences:** Prevents `auto` from being an allowlist bypass. Teams must be explicitly granted `auto` access.

### ADR-008: Router Training Data Source

- **Context:** Where does the difficulty classifier get its training examples?
- **Decision:** Write your own 30-50 labeled examples. The `routing_eval.jsonl` file is the **exam only** — never peek at its answers during development.
- **Consequences:** Maintains train/test integrity. Classifier quality depends on the quality of hand-written examples.

---

## 18. Testing Strategy

### Test Pyramid

```
            ┌───────────┐
            │  Contract  │     Provider API compliance (few)
            │   Tests    │
            └─────┬─────┘
          ┌───────┴───────┐
          │  Integration   │   DB + HTTP end-to-end (moderate)
          │    Tests       │
          └───────┬───────┘
      ┌───────────┴───────────┐
      │     Concurrency        │  Race conditions, over-admission
      │       Tests            │
      └───────────┬───────────┘
  ┌───────────────┴───────────────┐
  │          Unit Tests            │  Domain logic, pure functions (many)
  │   cost, limiter, cache, router │
  └───────────────────────────────┘
```

### What to Test

| Component | Test Type | What to Assert |
|-----------|-----------|----------------|
| CostCalculator | Unit | Math is correct for known inputs |
| TokenBucket | Unit + Concurrency | Allows exactly N requests, no over-admission |
| CacheDecision | Unit | Hit/miss/skip for various similarity scores |
| DifficultyClassifier | Unit | Correct tier for labeled examples |
| Authentication | Unit | Valid key → ok, invalid → 401 |
| Allowlist | Unit | Allowed model → ok, disallowed → 403 |
| Full pipeline | Integration | End-to-end request → response with headers |
| Streaming | Integration | Chunks arrive incrementally, `[DONE]` sent |
| Failover | Integration | Kill provider → fallback works |
| Load test | Concurrency | No over-admission under concurrent requests |
| Cross-tenant cache | Integration | Team A's cache invisible to Team B |

### Test Tooling

- **Unit tests:** pytest with dependency injection (fake clock, fake adapter, fake repos)
- **Integration tests:** Real HTTP requests against a test server with in-memory SQLite
- **Concurrency tests:** Multi-threaded test hitting rate limiter simultaneously
- **Verification scripts:** `smoke_test.py`, `load_test.py`, `routing_eval.py` (provided)

---

## 19. Debugging & Observability

### Debugging Workflow

```
Bug report: "Request X returned the wrong answer"

Step 1: Get the request ID from x-prism-request-id header
Step 2: Search logs → grep '"request_id":"req_X"' 
Step 3: Read the decision trace:
        "auth ok → rate ok → auto→smart (score 0.82, proof request)
         → cache miss → alpha-large 200 (0 retries)"
Step 4: If needed, open prism.db and query request_logs table
Step 5: Check usage table for budget/cost anomalies
```

### Observability Pillars

| Pillar | Implementation |
|--------|---------------|
| **Request tracing** | Every request gets a unique `request_id`, returned in headers and logged |
| **Decision trace** | One-line story per request capturing every pipeline decision |
| **Structured logs** | JSON lines to stdout, machine-searchable with `grep`/`jq` |
| **Inspectable database** | Open `prism.db` in any SQLite viewer |
| **Typed errors** | Each failure has its own class and `type` string — no mystery errors |
| **Debug mode** | `PRISM_LOG_LEVEL=DEBUG` for verbose output (still never logs secrets) |
| **Fake clock + fake adapter** | Makes bugs reproducible in tests |

---

## 20. Known Limitations & Future Work

### Known Limitations (Current Scope)

| Limitation | Why It's Acceptable | Future Fix |
|------------|---------------------|------------|
| Rate limiter is in-memory | Single-instance deployment only | Redis-backed distributed limiter |
| SQLite single-writer | One gateway instance | PostgreSQL or Redis for multi-instance |
| Bag-of-words embedder | Simple, explainable, offline | Swap in real embedding model via interface |
| No authentication for `/health` | Standard practice for health checks | N/A |
| Budget can slightly overshoot during concurrent streams | Documented bound | Pre-reserve estimated cost before streaming |
| No HTTPS | Development/demo only | Reverse proxy (nginx) or TLS termination |

### Future Work (Out of Scope)

- **Multi-instance deployment** with shared state (Redis/PostgreSQL)
- **Real embedding models** for higher cache accuracy
- **Guardrail pipeline stage** (content safety, PII detection)
- **Usage dashboards** with charts and time-series graphs
- **Webhook notifications** for budget alerts
- **A/B testing** of model configurations
- **Request queuing** for high-load scenarios
- **Kubernetes deployment** manifests

---

## Appendix A: Glossary

| Term | Definition |
|------|-----------|
| **LLM** | Large Language Model — the AI that writes text (e.g., GPT, Gemini) |
| **Provider** | A company/server hosting LLMs. In this project: `alpha` and `beta` (mocks) |
| **Gateway** | A single front door that sits in front of many services |
| **Virtual Key** | A Prism-issued API key for a tenant (e.g., `prism-sk-search-1a2b3c`) |
| **Tenant** | One customer/team using the gateway |
| **Alias** | A model nickname (`fast`, `smart`, `auto`) — decouples callers from real models |
| **Token** | A chunk of text (~¾ of a word). Providers charge per token |
| **SSE** | Server-Sent Events — the format used for streaming (`data: ...` lines) |
| **Semantic Cache** | A cache matching by meaning, not exact words |
| **Embedding** | Text → list of numbers for similarity comparison |
| **Cosine Similarity** | Score (0–1) measuring how alike two embeddings are |
| **Failover** | Automatic switch to a backup provider when the primary fails |
| **Backoff** | Retrying with increasing delays (1s → 2s → 4s...) |
| **Atomic** | An operation that completes fully or not at all, with no interruption |
| **Idempotent** | Doing it twice produces the same result as doing it once |

---

## Appendix B: Reference Architecture Diagram

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                         PRISM LLM GATEWAY — FULL VIEW                        │
│                                                                              │
│   ┌─────────┐ ┌─────────┐ ┌─────────┐                                       │
│   │ Team A  │ │ Team B  │ │ Team C  │   ← Tenants (with virtual keys)        │
│   └────┬────┘ └────┬────┘ └────┬────┘                                        │
│        └───────────┼───────────┘                                             │
│                    │                                                         │
│                    ▼                                                         │
│   ┌──────────────────────────────────────────────────────────────────────┐   │
│   │                        API LAYER (HTTP)                              │   │
│   │   POST /v1/chat/completions  │  GET /admin/*  │  GET /health        │   │
│   └───────────────────┬──────────────────────────────────────────────────┘   │
│                       │                                                      │
│   ┌───────────────────▼──────────────────────────────────────────────────┐   │
│   │                    REQUEST PIPELINE (Services)                        │   │
│   │                                                                      │   │
│   │  ┌─────┐ ┌──────┐ ┌──────┐ ┌───────┐ ┌──────┐ ┌─────┐ ┌─────────┐  │   │
│   │  │Auth │→│Rate  │→│Route │→│Allow  │→│Budget│→│Cache│→│Provider │  │   │
│   │  │     │ │Limit │ │      │ │list   │ │      │ │     │ │Call     │  │   │
│   │  └─────┘ └──────┘ └──────┘ └───────┘ └──────┘ └─────┘ └────┬────┘  │   │
│   │                                                              │       │   │
│   │  ┌──────────────────────────────────────────────────────────┐│       │   │
│   │  │              Post-Call: Meter → Log → Respond            ││       │   │
│   │  └──────────────────────────────────────────────────────────┘│       │   │
│   └──────────────────────────────────────────────────────────────┘       │   │
│                       │                                                  │   │
│   ┌───────────────────▼──────────────────────────────────────────────┐   │   │
│   │                 DOMAIN LAYER (Pure Logic)                        │   │   │
│   │  CostCalculator │ TokenBucket │ CacheDecision │ Classifier       │   │   │
│   │  DataModels     │ ErrorTypes  │ AliasResolver  │                  │   │   │
│   └──────────────────────────────────────────────────────────────────┘   │   │
│                       │                                                  │   │
│   ┌───────────────────▼──────────────────────────────────────────────┐   │   │
│   │               ADAPTER LAYER (Implementations)                    │   │   │
│   │  SQLiteRepos │ OpenAIAdapter │ BoWEmbedder │ SystemClock         │   │   │
│   └───────────────┬──────────────────────────────────────────────────┘   │   │
│                   │                                                      │   │
│   ┌───────────────▼──────────────────────────────────────────────────┐   │   │
│   │               INFRASTRUCTURE                                     │   │   │
│   │  ┌──────────┐  ┌──────────────┐  ┌──────────────┐               │   │   │
│   │  │ SQLite   │  │ Alpha Mock   │  │ Beta Mock    │               │   │   │
│   │  │ prism.db │  │ (port 9001)  │  │ (port 9002)  │               │   │   │
│   │  └──────────┘  └──────────────┘  └──────────────┘               │   │   │
│   └──────────────────────────────────────────────────────────────────┘   │   │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

> **Document maintainer:** Update this architecture document whenever a significant design decision changes. All ADRs should be cross-referenced with the corresponding section in this document.
