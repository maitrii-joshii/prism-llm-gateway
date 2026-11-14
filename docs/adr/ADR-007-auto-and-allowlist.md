# ADR-007: `auto` and Allowlist Interaction

**Status:** Accepted  
**Date:** 2026-11-10

---

## Context

Prism supports a special model alias `auto` that uses a difficulty classifier to route requests to either the `fast` or `smart` tier. Separately, each virtual key has a `model_allowlist` — an explicit list of model aliases the tenant is permitted to use.

This creates an ambiguity: **if a tenant's allowlist contains only `["fast"]`, and they send `model: "auto"`, what should happen if the classifier routes the request to `smart`?**

Three interpretations are possible:

1. **`auto` is a bypass** — if `auto` is not in the allowlist, reject immediately with 403.
2. **`auto` inherits its resolved tier's permission** — allow `auto` only if the resolved tier (`fast` or `smart`) is in the allowlist.
3. **`auto` requires explicit allowlisting, plus the resolved tier must also be allowed** — both `auto` itself and the final resolved model must be in the allowlist.

The concern with interpretation 2: a tenant granted only `["fast"]` could send `model: "auto"` and, if the classifier ever routes them to `smart`, they would access a model they were not explicitly granted. This makes `auto` a potential loophole.

---

## Decision

**Check both `auto` and the resolved tier against the allowlist (a form of option 3, simplified).**

The allowlist check runs **after** model resolution. At that point, `request_context.model_requested` is `"auto"` and `request_context.model_resolved` is the final alias (e.g., `"fast"` or `"smart"`).

The allowlist stage checks **both**:

```python
# Allowlist check for auto routing
if context.model_requested == "auto":
    if "auto" not in allowlist:
        raise ModelNotAllowedError(
            f"'auto' routing is not permitted for this key. "
            f"Add 'auto' to the allowlist to enable smart routing."
        )
# Always check the resolved model too
if context.model_resolved not in allowlist:
    raise ModelNotAllowedError(
        f"Model '{context.model_resolved}' is not in this key's allowlist."
    )
```

This means:
- A tenant with `["fast", "auto"]` can use `auto`, and it will route to `fast` or `smart` based on the classifier.
- A tenant with `["fast"]` cannot use `auto` at all — they must explicitly request `fast` or `smart`.
- A tenant with `["auto"]` but not `["smart"]` can use `auto` only if the classifier routes them to a model they're allowed. If the classifier says `smart` but `smart` is not in the allowlist, the request is rejected.

---

## Consequences

**Positive:**
- **`auto` cannot be used as an allowlist bypass** — tenants cannot access `smart` by sending `auto` if they were not granted `smart`.
- Operators have precise control: grant `auto` to teams trusted with dynamic routing; withhold it from cost-sensitive tenants who must stay on `fast`.
- The behavior is consistent and auditable — the decision trace records both the original `auto` request and the resolved tier.

**Negative / Trade-offs:**
- Operators must explicitly add `auto` to allowlists for teams that should use smart routing. This is a non-obvious onboarding step that must be documented.
- A tenant with `["fast", "auto"]` might be surprised when their `auto` request is rejected because the classifier resolved to `smart` and `smart` is not in their list. The error message must be clear.

**Recommended allowlist configurations:**

| Use Case | Allowlist |
|---|---|
| Cost-controlled, fast only | `["fast"]` |
| Flexible within budget | `["fast", "smart", "auto"]` |
| Smart model only | `["smart"]` |
| Smart routing, any tier | `["fast", "smart", "auto"]` |

**Documentation requirement:** The seed keys file and onboarding guide must explain that `auto` requires explicit allowlist inclusion.

