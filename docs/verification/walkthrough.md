# Prism LLM Gateway — Final Verification Walkthrough

> **Date:** 2026-11-10  
> **Purpose:** Demonstrate every gateway feature end-to-end with `curl` commands  
> **Stack:** `docker-compose up --build -d` (or local via `python -m prism.main`)

---

## Pre-requisites

```bash
# Start the full stack
docker-compose up --build -d
docker-compose ps          # Verify all services are healthy

# Or run locally (providers must be running):
python scripts/mock_provider.py --port 9001 --name alpha   # Terminal 1
python scripts/mock_provider.py --port 9002 --name beta    # Terminal 2
python -m prism.main                                        # Terminal 3
```

---

## Step 1 — Health Check

```bash
curl http://localhost:3000/health
```

**Expected:**
```json
{"status": "ok"}
```

---

## Step 2 — Non-Streaming Request

```bash
curl -i http://localhost:3000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "x-api-key: prism-sk-search-1a2b3c" \
  -d '{"model": "fast", "messages": [{"role": "user", "content": "Hello!"}]}'
```

**Expected response headers:**
```
HTTP/1.1 200 OK
x-prism-request-id: req_...
x-prism-provider: openai/gpt-4o-mini
x-prism-cache: miss
x-prism-cost-usd: 0.000...
```

**Expected body:** OpenAI-compatible JSON with `choices[0].message.content`

---

## Step 3 — Streaming Request (SSE)

```bash
curl -N http://localhost:3000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "x-api-key: prism-sk-search-1a2b3c" \
  -d '{"model": "fast", "messages": [{"role": "user", "content": "Count to five."}], "stream": true}'
```

**Expected:** Token-by-token SSE chunks, terminated with `data: [DONE]`

```
data: {"choices":[{"delta":{"content":"1"},...}]}
data: {"choices":[{"delta":{"content":", 2"},...}]}
...
data: [DONE]
```

---

## Step 4 — Smart Routing (`auto`)

```bash
curl -i http://localhost:3000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "x-api-key: prism-sk-search-1a2b3c" \
  -d '{"model": "auto", "messages": [{"role": "user", "content": "Prove that the square root of 2 is irrational."}]}'
```

**Expected:** Classifier routes to `smart` tier — check `x-prism-provider` header shows `groq/llama-3.3-70b-versatile`

---

## Step 5 — Semantic Cache Hit

Send the same question twice:

```bash
# First request → cache miss
curl -i http://localhost:3000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "x-api-key: prism-sk-search-1a2b3c" \
  -d '{"model": "fast", "messages": [{"role": "user", "content": "How do I reset my password?"}]}'
# x-prism-cache: miss

# Second request (paraphrase) → cache hit
curl -i http://localhost:3000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "x-api-key: prism-sk-search-1a2b3c" \
  -d '{"model": "fast", "messages": [{"role": "user", "content": "Please help me change my password."}]}'
# x-prism-cache: hit
# x-prism-cost-usd: 0
```

---

## Step 6 — Auth Failure (Missing Key)

```bash
curl -i http://localhost:3000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "fast", "messages": [{"role": "user", "content": "Hi"}]}'
```

**Expected:**
```
HTTP/1.1 401 Unauthorized
{"error": {"message": "...", "type": "authentication_error", "code": 401}}
```

---

## Step 7 — Auth Failure (Invalid Key)

```bash
curl -i http://localhost:3000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "x-api-key: not-a-real-key" \
  -d '{"model": "fast", "messages": [{"role": "user", "content": "Hi"}]}'
```

**Expected:** `401 Unauthorized` — same error as missing key (no information leakage)

---

## Step 8 — Rate Limiting

The demo key `prism-demo-rate-limit-10` has RPM = 10. Send 11 rapid requests:

```bash
for i in 1 2 3 4 5 6 7 8 9 10 11; do
  curl -s -o /dev/null -w "Request $i: %{http_code}\n" \
    http://localhost:3000/v1/chat/completions \
    -H "Content-Type: application/json" \
    -H "x-api-key: prism-demo-rate-limit-10" \
    -d '{"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "Hi"}]}'
done
```

**Expected:** First 10 → `200`, 11th → `429 rate_limit_exceeded`

---

## Step 9 — Provider Failover

```bash
# (Docker only) Stop the primary provider
docker-compose stop alpha-mock

# Send a request — should succeed via the beta fallback
curl -i http://localhost:3000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "x-api-key: prism-sk-search-1a2b3c" \
  -d '{"model": "fast", "messages": [{"role": "user", "content": "Hello after failover"}]}'
```

**Expected:**
```
x-prism-fallback: true
x-prism-provider: groq/llama-3.3-70b-versatile
```

```bash
# Restore primary
docker-compose start alpha-mock
```

---

## Step 10 — Ops Console

Open in a browser:

```
http://localhost:3000/console
```

1. Enter your `PRISM_ADMIN_TOKEN` in the token field
2. Click **Connect**
3. Verify:
   - Cache hit rate stat card shows the hit from Step 5
   - Usage table shows the demo key with spend and token counts
   - Recent requests table shows all test requests from Steps 2–8

---

## Step 11 — Admin API

```bash
# Usage summary
curl http://localhost:3000/admin/usage \
  -H "Authorization: Bearer admin-secret-change-me"

# Recent logs
curl "http://localhost:3000/admin/logs?limit=10" \
  -H "Authorization: Bearer admin-secret-change-me"

# Cache statistics
curl http://localhost:3000/admin/cache/stats \
  -H "Authorization: Bearer admin-secret-change-me"
```

**Expected:** JSON with live data from the requests made in Steps 2–8

---

## Verification Scripts

```bash
# Full smoke test (no live server needed — uses TestClient)
python scripts/smoke_test.py

# Load test (over-admission, usage accuracy, latency)
python scripts/load_test.py

# Routing classifier eval (heuristic vs length-only baseline)
python scripts/routing_eval.py

# Full test suite
pytest tests/ -v
```

---

## Checklist

| Step | Feature | Status |
|---|---|---|
| 1 | Health check (`/health`) | ☐ |
| 2 | Non-streaming request + all custom headers | ☐ |
| 3 | Streaming SSE pass-through + `[DONE]` | ☐ |
| 4 | `auto` routing → smart tier | ☐ |
| 5 | Semantic cache hit on paraphrase | ☐ |
| 6 | Auth failure — missing key → 401 | ☐ |
| 7 | Auth failure — invalid key → 401 | ☐ |
| 8 | Rate limiting → 429 on 11th request | ☐ |
| 9 | Provider failover → `x-prism-fallback: true` | ☐ |
| 10 | Ops console loads at `/console` with live data | ☐ |
| 11 | Admin API returns usage, logs, cache stats | ☐ |

