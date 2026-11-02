"""Budget enforcement stage for the Prism request pipeline."""

from datetime import datetime, timezone

from prism.domain.errors import AuthenticationError, BudgetExceededError
from prism.domain.models import RequestContext
from prism.ports.repositories import UsageRepository


async def enforce_budget(
    context: RequestContext,
    usage_repository: UsageRepository,
    now: datetime | None = None,
) -> RequestContext:
    """Reject requests when the authenticated key has exhausted its budget."""

    if context.key_config is None:
        raise AuthenticationError(
            "Request must be authenticated before budget checking."
        )

    # Use the supplied time when testing; otherwise use current UTC time.
    current_time = now or datetime.now(timezone.utc)
    month = current_time.strftime("%Y-%m")

    key_hash = context.key_config.key_hash
    budget_limit = context.key_config.budget_usd

    usage = usage_repository.get_usage(
        key_hash=key_hash,
        month=month,
    )

    current_spend = usage.total_spend_usd

    if current_spend >= budget_limit:
        context.decision_trace.append("budget exceeded")
        raise BudgetExceededError(
            "Monthly budget exceeded. Please try again next month."
        )

    context.decision_trace.append(
        f"budget ok (${current_spend:.6f}/${budget_limit:.6f})"
    )

    return context
