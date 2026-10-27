# Prism Architecture: A Beginner's Guide

> Written for someone who has never built a gateway, a cache, or a rate limiter.
> Read top to bottom once. After that, use it as a reference while you build.

---

## Table of Contents

1. [What are we building? (the 2-minute version)](#1-what-are-we-building)
2. [Words you need to know](#2-words-you-need-to-know)
3. [The big picture](#3-the-big-picture)
4. [The journey of one request](#4-the-journey-of-one-request)
5. [The building blocks, one by one](#5-the-building-blocks)
6. [How streaming works](#6-how-streaming-works)
7. [What happens when things break](#7-what-happens-when-things-break)
8. [Where data lives](#8-where-data-lives)
9. [Security, in plain words](#9-security-in-plain-words)
10. [Debugging: how you will find bugs fast](#10-debugging)
11. [The rules that keep code clean](#11-the-rules-that-keep-code-clean)
12. [Folder layout](#12-folder-layout)
13. [Decisions you must write down](#13-decisions-you-must-write-down)
14. [Build order and time estimate](#14-build-order-and-time-estimate)

---

## 1. What are we building?

### The problem

Imagine a company with 40 teams. Each team wants to use AI models (like ChatGPT-style models). If every team connects to the AI providers on its own:

- Everyone needs their own secret passwords (API keys) for each provider, and those leak.
- Nobody knows who is spending how much money.
- If one provider goes down, every team's app breaks.
- Ten teams ask the same question and the company pays ten times.

### The solution

Put **one middleman** between the teams and the AI providers. That middleman is **Prism**.

Think of Prism as a **hotel reception desk**:

| Hotel reception | Prism |
|---|---|
| Checks your room card at the door | Checks your **virtual key** (who are you?) |
| "Only 10 requests to the kitchen per minute" | **Rate limit** |
| "Your room's tab is full" | **Budget** |
| Sends your order to the right kitchen | **Routing** (cheap model or strong model) |
| Kitchen A is closed, uses Kitchen B | **Failover** |
| "Someone already ordered this exact dish, here you go" | **Semantic cache** |
| Writes every order in a ledger | **Request log + metering** |

### The one-sentence summary

> Prism receives an AI request, checks it is allowed, picks the right model, forwards it, streams the answer back, and writes down what it cost.

---

## 2. Words you need to know

You will see these words everywhere. Learn them now.

| Word | Plain meaning |
|---|---|
| **LLM** | Large Language Model: the AI that writes text (e.g. GPT, Gemini). |
| **Provider** | A company/server that hosts LLMs. In our project: two fake ones called `alpha` and `beta`. |
| **Gateway** | A single front door that sits in front of many services. Prism is a gateway. |
| **Virtual key** | A fake password Prism gives to each team (e.g. `prism-sk-search-1a2b3c`). The team never sees the real provider password. |
| **Tenant** | One customer/team using the gateway. "Per tenant" = "per team". |
| **Alias** | A nickname for a model. `fast` = cheap model, `smart` = strong model. Callers use nicknames so *we* can change the real model later. |
| **Token** | A chunk of text (about 3/4 of a word). Providers charge per token. |
| **Prompt** | The question/instruction sent to the AI. |
| **Completion** | The AI's answer. |
| **Streaming** | Sending the answer piece by piece as it is written, instead of waiting for the whole thing. |
| **SSE** | Server-Sent Events: the simple format used for streaming (`data: ...` lines). |
| **Rate limit** | A cap on how many requests are allowed per minute. |
| **Budget** | A cap on how many dollars a team can spend per month. |
| **Cache** | A saved copy of an earlier answer so we do not pay again. |
| **Semantic cache** | A cache that matches by *meaning*, not exact words. "Reset my password" and "How do I change my password?" count as the same. |
| **Embedding** | Turning text into a list of numbers so a computer can measure how similar two texts are. |
| **Cosine similarity** | A score from 0 to 1 for how alike two embeddings are. 1 = identical meaning. |
| **Threshold** | The score above which we say "same question". E.g. 0.85. |
| **Failover** | If provider A fails, automatically try provider B. |
| **Retry / backoff** | Try again after a failure, waiting a bit longer each time (1s, 2s, 4s...). |
| **Timeout** | "If no answer after N seconds, give up." Prevents hanging forever. |
| **Atomic** | An operation that happens completely or not at all, with nobody able to sneak in the middle. |
| **Race condition** | A bug where two things happening at the same time produce a wrong result. |
| **Idempotent** | Doing it twice has the same effect as doing it once. |

### The race condition, explained with a story

Rate limit: 10 requests per minute. The counter says 9.

- Request A reads the counter: 9. "OK, under 10."
- Request B reads the counter: 9. "OK, under 10."
- A writes 10. B writes 10.

Both got in, so 11 requests were actually served. This is called **over-admission** and it is the bug the load test is designed to catch. The fix is to make *check and increment one single step* that nobody can interrupt.

---

## 3. The big picture

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

### Three layers, like a sandwich

| Layer | Job | Knows about |
|---|---|---|
| **Outer (edges)** | Talk to the outside world: HTTP, database, providers | Frameworks, SQL, network |
| **Middle (services)** | Orchestrate: "do auth, then limit, then route..." | The *order* of steps |
| **Inner (domain)** | Pure rules: cost math, limiter, router decision | Nothing external, only plain data |

**The golden rule: arrows point inward.** The inner layer never imports the web framework or the database. Why? Because pure logic can be tested in milliseconds with no setup, and you can swap SQLite for something else without touching business rules.

---

## 4. The journey of one request

Follow one request from start to finish. Each step is a small, separate piece of code ("a stage"). A stage either **passes the request along** or **rejects it with a specific error**.

```
 1. Give it an ID, start a stopwatch
 2. Authenticate        → fail: 401 authentication_error
 3. Validate the body   → fail: 400 invalid_request
 4. Rate limit          → fail: 429 rate_limit_exceeded
 5. Resolve the model   → fail: 404 not_found_error
        (if "auto": classify difficulty first)
 6. Allowlist           → fail: 403 model_not_allowed
 7. Budget check        → fail: 429 budget_exceeded
 8. Cache lookup        → HIT? skip to step 11
 9. Call the provider   → fail: 502 upstream_error
        (timeout, retry, failover)
10. Meter the cost
11. Save to cache (success only) + write the log + return response
```

### Why this order?

| Step | Why it sits here |
|---|---|
| Auth first | Without knowing *who*, no other check means anything. |
| Validate before spending | Reject garbage cheaply. |
| Rate limit before budget | The limiter is in-memory and fast; the budget needs a database read. Cheap checks first protects the expensive ones. |
| Resolve model **before** allowlist | If a team sends `auto`, we must know the final tier (`fast`/`smart`) or `auto` becomes a loophole around the allowlist. |
| Budget before the call | Check money *before* spending it. |
| Cache before the call | A hit means we never contact the provider. |
| Cache save only on success | Never store errors: you would serve a broken answer forever. |

### Every response carries these headers

| Header | Meaning |
|---|---|
| `x-prism-provider` | Who answered, e.g. `alpha/alpha-small` |
| `x-prism-cache` | `hit` or `miss` |
| `x-prism-fallback` | `true` only if a backup provider answered |
| `x-prism-cost-usd` | Cost in dollars (`0` for a cache hit) |
| `x-prism-request-id` | Our own ID so you can find this request in the logs |

### The pattern behind it: Chain of Responsibility

A bucket brigade. Each person (stage) takes the bucket (the `RequestContext`), does one job, and passes it on. If a stage fails, it throws a typed error and the chain stops. To add a new stage later (e.g. a guardrail), you add one new person to the line without touching anyone else.

---

## 5. The building blocks

Each block has: **what it is**, **why it exists**, **an analogy**, and **what to watch out for**.

### 5.1 Config & Seed Loader

- **What:** On startup, reads `seed_keys.json`, `model_pricing.json`, `gateway_config.sample.json` and turns them into typed, read-only objects.
- **Why:** These files are the source of truth. If they are wrong, the gateway should refuse to start rather than fail an hour later.
- **Analogy:** A pilot's pre-flight checklist. You do not discover a missing engine mid-air.
- **Watch out:** Check that every alias points to a model that exists in the price table. Crash loudly at boot if not ("fail fast").

### 5.2 Key Store & Authentication

- **What:** Looks up a virtual key and returns the team's settings (budget, rate limit, allowlist, cache config).
- **Why:** Every other feature is "per key". This is the foundation.
- **Analogy:** The door guard who checks your badge.
- **Watch out:** Store only a **hash** of each key (a one-way scramble), never the raw key. Compare using a constant-time function so attackers cannot learn the key by timing.

### 5.3 Rate Limiter

- **What:** Counts requests per key per minute; says allow or reject.
- **Why:** Protects providers and stops one noisy team from starving others.
- **Analogy:** A bouncer with a clicker and a rule: "only 10 people per minute".
- **How it works (token bucket):** Each key owns a bucket holding up to 10 tokens. Each request removes one. Tokens refill over time. Empty bucket = rejected.
- **Watch out:** The "check and remove" must be **one atomic step** (use a lock). Time must come from an injected `Clock` so tests can fast-forward without waiting 60 real seconds.

### 5.4 Budget & Usage Service

- **What:** Tracks dollars and tokens spent per key per month. Refuses new requests once the budget is gone.
- **Why:** This is money. It must be exact.
- **Analogy:** A prepaid phone balance.
- **Two sub-parts, kept separate:**
  1. **CostCalculator**, a pure math function: `(prompt_tokens × input_price + completion_tokens × output_price) / 1,000,000`. No database, no network. Easiest thing in the project to test.
  2. **UsageRepository**, which saves totals using a single atomic SQL statement: `UPDATE usage SET spend = spend + ?` (never "read, add in code, write back").
- **Monthly reset:** The usage row is keyed by month (`2026-10`). A new month = a new row = fresh budget. No scheduled job needed.
- **Streaming wrinkle:** For a stream, the final cost is unknown when it starts. So: admit if budget remains at the start, and record the true cost at the end. A few in-flight requests may overshoot slightly. Document the bound.
- **Rule:** Cost comes from the provider's `usage` object, **never** from numbers the client claims.

### 5.5 Model Resolver and Smart Router (`auto`)

- **What:**
  - **AliasResolver:** `fast` → primary model + ordered backup list. Plain lookup.
  - **DifficultyClassifier:** reads a prompt and decides `fast` or `smart`.
- **Why:** Cheap models for easy questions, strong models for hard ones, saving money without the caller thinking about it.
- **Analogy:** A hospital triage nurse. A scraped knee goes to the nurse; a heart attack goes to the surgeon. The nurse judges **severity, not how long the patient talks**.
- **The trap in this project:** Length is a bad signal.
  - Short but hard: *"Prove that √2 is irrational."*
  - Long but trivial: a huge on-call roster where you only need one name.
  - A length-only rule scores about 60%. You need to look at **what is being asked**.
- **Ideas for signals:**
  - Hard: "prove", "derive", "why does this deadlock", code or math, multi-step reasoning.
  - Easy: "list", "extract", "look up", "what is the name of".
- **Design:** `DifficultyClassifier` is an **interface**. You write several versions (heuristic, embedding-based) and swap them. That is the **Strategy pattern**.
- **Critical learning rule:** The file `routing_eval.jsonl` is your **exam**. You may not peek at its answers when building the router. Write your own 30-50 labeled examples to "study" from, then test on the exam. This is the train/test discipline from real machine learning.
- **Every decision is logged:** which tier, a score, and a reason like `"proof request; judged complex"`.

### 5.6 Semantic Cache

- **What:** Saves past answers. For a new prompt, converts it to an embedding, compares to saved ones **from the same team**, and returns a saved answer if similarity ≥ threshold.
- **Why:** Same question twice should cost nothing.
- **Analogy:** A librarian who recognises "that's the same question Priya asked yesterday, just worded differently".
- **Parts:**
  - **Embedder (interface):** Start simple, with a bag-of-words approach (count the words, ignore filler like "the/a/how", compare with cosine similarity). It works offline, needs no downloads, and you can explain it fully. Later, swap in a real embedding model without changing anything else.
  - **CacheStore:** saves and searches entries.
  - **CacheDecision (pure function):** "Is this cacheable? Is this a hit?"
- **The biggest danger: leaking between teams.** If Team A asks about their secret product and Team B gets that cached answer, that is a data breach. The fix is **structural**: the team's key is part of the lookup itself, so searching another team's entries is impossible by construction, rather than "search everything, then filter".
- **Tuning the threshold:** Too low = wrong answers served ("password reset" vs "2FA reset" must **not** match). Too high = no benefit. Tune until the paraphrase pairs hit and the near-miss does not.
- **Do not cache:** errors, time-sensitive prompts ("what's the weather now"), or keys with cache disabled.
- **Multi-turn chats:** Decide what forms the cache key (suggestion: system prompt + last user message) and write it down.

### 5.7 Provider Adapter

- **What:** A small translator between Prism and one provider. Exposes two methods: `complete(request)` and `stream(request)`.
- **Why:** Providers differ. The rest of Prism should not care.
- **Analogy:** A travel plug adapter. Your laptop (Prism) has one plug shape; the adapter fits any wall socket (provider).
- **In this project:** One `OpenAICompatibleAdapter` serves both mocks, because they speak the same language.
- **For tests:** A `FakeAdapter` returns canned responses instantly, with no network. Because both obey the same interface, the rest of the code cannot tell the difference (the **Liskov Substitution Principle**).
- **Secrets:** Provider API keys come from **environment variables**, never from files in git.

### 5.8 Resilient Executor (retry, timeout, failover)

- **What:** Wraps provider calls with safety nets.
- **Why:** Networks and providers fail. Users should not notice.
- **Analogy:** A delivery driver with a plan: "If the road is blocked, wait and retry. If still blocked, take another route."
- **Three error categories (this is the key idea):**

| Category | Examples | What to do |
|---|---|---|
| **Retryable** | 500s, timeout, connection reset | Wait, retry the same provider (backoff + a bit of random jitter) |
| **Failover-worthy** | Provider says 429, provider is down | Skip straight to the next provider in the chain |
| **Fatal** | 400 (your request is malformed) | Stop. Retrying or failing over will not fix it |

- **Timeouts everywhere:** a connect timeout, a total timeout, and for streams an **idle timeout** ("no new chunk for N seconds = dead").
- **Recording:** `retries` count and a `fallback` flag go into the log and headers.

### 5.9 Streaming Proxy

See [Section 6](#6-how-streaming-works).

### 5.10 Request Logger

- **What:** Two separate records:
  1. **Request log table**: one row per request (including rejected ones). This is the audit and billing record.
  2. **Application logs**: JSON lines printed to the terminal, each with the `request_id`.
- **Why:** When something goes wrong, you want to answer "what happened to request X?" in seconds.
- **Decision trace:** Each request builds a short story, saved to the log:
  ```
  auth ok → rate ok → auto→smart (score 0.82, "proof request") → cache miss → alpha-large 200 (0 retries)
  ```
- **Never log:** raw virtual keys, provider keys, or full prompts (by default).

### 5.11 Admin API and Ops Console

- **What:** A few read-only endpoints (`/admin/usage`, `/admin/logs`, `/admin/cache/stats`, `/health`) plus **one static HTML page** that calls them and shows tables.
- **Why:** The platform team needs to see what is happening.
- **Keep it tiny:** No React, no build step. One HTML file with a bit of JavaScript. Polish is not graded.
- **Protected** by a separate admin token.

---

## 6. How streaming works

### Without streaming

```
Client ──ask──► Prism ──ask──► Provider
Client ◄─────── (waits 5 seconds... all text arrives at once) ◄── Provider
```

### With streaming

```
Client ──ask──► Prism ──ask──► Provider
Client ◄─ "Hel" ◄─ "Hel" ◄──── Provider writes "Hel"
Client ◄─ "lo"  ◄─ "lo"  ◄──── Provider writes "lo"
Client ◄─ "!"   ◄─ "!"   ◄──── Provider writes "!"
Client ◄─ [DONE]
```

### The rule: never buffer

The wrong way is to collect all pieces, then send them together. That defeats streaming. The right way is a **pass-through**: every chunk that arrives gets forwarded immediately.

### The tee pattern

Like a water pipe with a tap on the side. Water flows through to the client untouched, while we peek at each chunk on the side, looking for the final one that carries the `usage` numbers.

```
Provider ──chunk──► [ Prism ] ──chunk──► Client
                       │
                       └─ peek: is this the usage chunk? save the numbers
```

### The `finally` safety net

Whatever happens (finished normally, client closed the tab, provider crashed), Prism must **always** record the usage and write the log. In code this is a `try/finally` block. Without it, interrupted streams become free, and your accounting drifts.

### Headers go first, problem

HTTP headers are sent *before* the body. So `x-prism-provider` and `x-prism-fallback` must be decided before the first chunk. That is why **failover must happen before streaming starts**.

### What if the provider dies mid-stream?

Decision (documented): **we do not switch providers halfway.** Splicing two providers' outputs would produce a franken-answer.

- Before the first byte reached the client → failover is fine.
- After the first byte → send a final SSE error event, close the stream, log it as `upstream_error`.

### Cache hit on a stream

Replay the saved answer as one chunk followed by `[DONE]`, and set `x-prism-cache: hit`.

---

## 7. What happens when things break

| Situation | What Prism does | What the client sees |
|---|---|---|
| Alpha is down (connection refused) | Skip to beta immediately | Normal answer, `x-prism-fallback: true` |
| Alpha returns a 500 once | Wait, retry alpha, success | Normal answer, `retries: 1` in the log |
| Alpha is slow (3s+) | Timeout fires, fail over to beta | Normal answer, a bit slower |
| Alpha is flaky (30% failures) | Retries absorb most failures | Almost always success |
| Both providers fail | Give up cleanly | 502 `upstream_error` JSON |
| Alpha restored | Next request goes to alpha again | Back to normal |
| Alpha dies mid-stream | Send an SSE error event, close | Stream ends with an error event |
| Client disconnects mid-stream | Stop reading upstream, settle usage in `finally` | n/a |
| Provider returns garbage JSON | Treat as a retryable upstream error | Fallback or a clean 502 |

---

## 8. Where data lives

### Database: SQLite (a single file, no server to install)

You can open it with any viewer and read the rows with your own eyes. That makes debugging far easier.

| Table | Contains | Notes |
|---|---|---|
| `virtual_keys` | key hash, team, budget, rpm, allowlist, cache settings, status | Seeded at startup |
| `usage` | per key + month: spend, tokens, requests, cache hits | Updated **atomically** |
| `request_logs` | one row per request incl. rejections | Never store prompt bodies by default |
| `cache_entries` | key, alias, embedding, response, hit_count, created_at | Always filtered by key |

### In memory (lost on restart)

- Rate limiter buckets. This is allowed for the single-instance Must Have; note it as a known limitation.

### What survives a restart?

Keys, usage, logs, cache. All in SQLite.

### A note on concurrency

SQLite allows **one writer at a time**. For a learning project this is a gift: writes line up in a queue, so atomic updates are simple to reason about. Use short transactions and a busy timeout.

---

## 9. Security, in plain words

| Risk | Plain-English defence |
|---|---|
| A stolen database reveals every team's key | Store **hashes**, not keys |
| Timing attacks guess keys letter by letter | Compare with a **constant-time** function |
| Provider secrets leak in an error message | Keys only in **env vars**; errors to callers are generic |
| One team reads another's cached answers | Cache lookup is **scoped by key**, structurally |
| `auto` sneaks past the allowlist | Allowlist is checked on the **resolved** model too |
| A caller sends a 500 MB body | **Body size limit** |
| A caller requests `max_tokens: 10,000,000` | **Cap** `max_tokens` |
| Anyone can open the admin pages | **Separate admin token**, bound to `localhost` |
| Logs expose secrets or private prompts | Log key **prefix/hash** only; no prompt bodies |
| Malicious data in the database runs code | Use **JSON** for stored embeddings; never `pickle`/`eval` |
| Detailed errors help attackers | Detail goes in **server logs**, not client responses |

---

## 10. Debugging

You asked for debugging to be as easy as possible. These are the habits that get you there:

1. **Every request gets an ID**, returned as `x-prism-request-id` and printed on every log line. Given a bug report, you search that one ID.
2. **Decision trace** per request (see 5.10). One line tells the whole story.
3. **Structured JSON logs.** Machine-searchable: `grep '"request_id":"abc123"'`.
4. **Inspectable database.** Open `prism.db` in any SQLite viewer and look at the rows.
5. **Typed errors.** Each failure type has its own class and its own `type` string. No mystery "something went wrong".
6. **Debug mode** (env var `PRISM_LOG_LEVEL=DEBUG`) prints more detail, but still never secrets.
7. **Fake clock and fake adapter** in tests make bugs reproducible instead of "sometimes".

---

## 11. The rules that keep code clean

### SOLID, in one sentence each

| Letter | Principle | Prism example |
|---|---|---|
| **S** | Single Responsibility | `CostCalculator` only does cost math. Nothing else. |
| **O** | Open/Closed | Add a new pipeline stage without editing existing ones. |
| **L** | Liskov Substitution | `FakeAdapter` works wherever `OpenAICompatibleAdapter` does. |
| **I** | Interface Segregation | The limiter does not need to know about databases. Keep interfaces small. |
| **D** | Dependency Inversion | Services depend on `Clock`/`Repository` interfaces, not concrete classes. |

### Patterns we use (and why)

| Pattern | Where | Plain meaning |
|---|---|---|
| Chain of Responsibility | Request pipeline | Pass-it-along stages |
| Strategy | Classifier, Embedder | Swappable algorithms behind one interface |
| Adapter | Provider layer | Translate one interface into another |
| Repository | Database access | Hide SQL behind `get/save` methods |
| Decorator | Retry around adapter | Wrap something to add behaviour |
| Composition root | `main` file | The **one place** where objects are created and connected |

### DRY (Don't Repeat Yourself), with a warning

Do not copy-paste the same logic in many places. But also do not invent abstractions before you need them. A good rule: **duplicate twice, abstract on the third time.** Wrong abstractions are harder to fix than duplication.

### Dependency Injection (DI), explained

Do not let a class create its own dependencies:

```text
# Hard to test: creates its own clock
class Limiter:
    def __init__(self):
        self.clock = RealClock()

# Easy to test: receives a clock from outside
class Limiter:
    def __init__(self, clock):
        self.clock = clock
```

In production, pass in the real clock. In tests, pass in a fake one you control.

### Error handling

One base class `PrismError`. One subclass per rejection (`AuthenticationError`, `RateLimitError`, `BudgetExceededError`, ...). Each knows its own HTTP status and `type`. A **single handler** converts any `PrismError` into the OpenAI-style JSON body. You will never write `return 429` scattered across the code.

---

## 12. Folder layout

```
prism/
├── domain/              # PURE logic. No web, no DB, no network.
│   ├── models.py            # data shapes (VirtualKey, RequestContext, ...)
│   ├── errors.py            # PrismError and subclasses
│   ├── cost.py              # CostCalculator
│   ├── limiter.py           # token bucket
│   └── cache_decision.py    # "cacheable? hit?"
│
├── ports/               # INTERFACES (contracts) only
│   ├── provider.py          # ProviderAdapter
│   ├── embedder.py          # Embedder
│   ├── repositories.py      # KeyRepo, UsageRepo, LogRepo, CacheRepo
│   └── clock.py             # Clock
│
├── adapters/            # REAL implementations of the ports
│   ├── sqlite_repos.py
│   ├── openai_compatible.py
│   ├── bow_embedder.py
│   └── system_clock.py
│
├── services/            # Orchestration and pipeline stages
│   ├── pipeline.py
│   ├── stages/              # auth.py, ratelimit.py, resolve.py, allowlist.py, ...
│   ├── router.py            # DifficultyClassifier implementations
│   ├── executor.py          # retry / timeout / failover
│   ├── streaming.py
│   └── cache_service.py
│
├── api/                 # HTTP: routes, SSE, error mapping, admin
├── config/              # loaders + startup validation
└── main.py              # composition root (wires everything together)

console/                 # one static HTML page
tests/                   # unit/ integration/ concurrency/ contract/
scripts/  data/          # provided
docs/adr/                # one short file per design decision
```

### How to read the folders

- `domain` knows **nothing** about the outside world.
- `ports` says **what** is needed ("I need something that can store keys").
- `adapters` says **how** ("here is the SQLite way").
- `services` decides **when** and in what order.
- `api` translates HTTP to and from all of the above.

---

## 13. Decisions you must write down

Before coding, make each of these decisions and record it in `docs/adr/` (ADR = Architecture Decision Record, a half-page note: *context, decision, consequences*).

| # | Question | Suggested answer |
|---|---|---|
| 1 | Does a cache hit consume rate-limit quota? Is it served if the budget is empty? | Consumes rate limit: yes. Budget: cost is $0, so allow it, and document this. |
| 2 | What happens if a stream fails midway? | Error event + close. No splicing. |
| 3 | How far may a stream overshoot the budget? | By the cost of the requests in flight at that moment. |
| 4 | Cache scope and multi-turn keying? | Scope by key + alias. Key on system prompt + last user message. |
| 5 | What is "time-sensitive" (never cached)? | Words like "now", "today", "latest", "current" (document the list). |
| 6 | Do we store prompts in logs? | No, by default. |
| 7 | How does `auto` interact with the allowlist? | Check both `auto` and the resolved tier. |
| 8 | Where does the router get its training examples? | Your own written examples; the eval set is the exam only. |

---

## 14. Build order and time estimate

Build in thin vertical slices. Always have something that runs end to end.

| Phase | What you build | Why this order | Hours |
|---|---|---|---|
| 1. Foundations | Config loader, errors, logging, one provider, non-streaming pass-through, headers | Headers added later touch every code path | 10-12 |
| 2. Keys & limits | Auth, allowlist, limiter, cost calc, budget, request logs | Gets "money" correct before anything fancy | 8-10 |
| 3. Streaming & reliability | SSE pass-through, timeouts, retry, failover | Needs auth + metering to be trustworthy first | 11-14 |
| 4. Intelligence | Semantic cache, `auto` router, routing eval | Both share embedding ideas | 12-16 |
| 5. Console & proof | Ops page, smoke test, load test, docs, demo | Verification and polish | 8-10 |
| **Total** | | | **~50-60 hrs** |

### Your definition of done for each phase

- The tests for that phase pass.
- You can demo it with `curl`.
- You can explain every file you wrote, out loud, to someone else.

---

## Quick recap

1. Prism = a **reception desk** for AI requests.
2. Requests flow through a **fixed pipeline** of small stages.
3. **Pure logic in the middle, messy stuff at the edges**; arrows point inward.
4. Everything external (providers, DB, embedder, clock) hides behind an **interface**, so tests can swap in fakes.
5. **Atomic** operations prevent races; the cache is scoped per team by construction.
6. Streaming is a **pass-through with a tee** and a `finally` that always settles the bill.
7. Failures are sorted into **retry / failover / fatal**.
8. Every request has an **ID and a decision trace**, which makes debugging quick.
