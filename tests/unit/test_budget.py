"""Unit tests for the monthly budget enforcement stage."""

from datetime import datetime, timezone

import pytest

from prism.domain.errors import BudgetExceededError
from prism.domain.models import (
    MonthlyUsage,
    RequestContext,
    VirtualKeyConfig,
)
from prism.services.stages.budget import enforce_budget


class FakeUsageRepository:
    """In-memory usage repository for budget-stage tests."""

    def __init__(self, total_spend_usd: float):
        self.total_spend_usd = total_spend_usd

    def get_usage(self, key_hash: str, month: str) -> MonthlyUsage:
        return MonthlyUsage(
            key_hash=key_hash,
            month=month,
            total_spend_usd=self.total_spend_usd,
            total_tokens=1000,
            total_requests=5,
            cache_hits=0,
        )


@pytest.fixture
def context():
    """Create an authenticated request context."""

    key_config = VirtualKeyConfig(
        key_hash="test-key-hash",
        tenant_id="tenant-1",
        budget_usd=10.0,
        rate_limit_rpm=100,
        model_allowlist=["gpt-4o-mini"],
        cache_enabled=True,
        cache_threshold=0.9,
        status="active",
    )

    return RequestContext(
        request_id="request-1",
        key_config=key_config,
        model_requested="gpt-4o-mini",
        start_time=datetime(2026, 11, 2, 10, 0, tzinfo=timezone.utc),
    )


@pytest.mark.asyncio
async def test_allows_request_when_spend_is_below_budget(context):
    """Allows a request when monthly spend is below the budget."""

    repository = FakeUsageRepository(total_spend_usd=5.0)

    result = await enforce_budget(
        context=context,
        usage_repository=repository,
        now=context.start_time,
    )

    assert result is context
    assert "budget ok ($5.000000/$10.000000)" in result.decision_trace


@pytest.mark.asyncio
async def test_rejects_request_when_spend_equals_budget(context):
    """Rejects a request when monthly spend reaches the budget."""

    repository = FakeUsageRepository(total_spend_usd=10.0)

    with pytest.raises(BudgetExceededError) as exc_info:
        await enforce_budget(
            context=context,
            usage_repository=repository,
            now=context.start_time,
        )

    assert exc_info.value.status_code == 429
    assert exc_info.value.error_type == "budget_exceeded"
    assert "budget exceeded" in context.decision_trace


@pytest.mark.asyncio
async def test_rejects_request_when_spend_exceeds_budget(context):
    """Rejects a request when monthly spend is above the budget."""

    repository = FakeUsageRepository(total_spend_usd=12.0)

    with pytest.raises(BudgetExceededError):
        await enforce_budget(
            context=context,
            usage_repository=repository,
            now=context.start_time,
        )

    assert "budget exceeded" in context.decision_trace


@pytest.mark.asyncio
async def test_rejects_request_without_authenticated_key():
    """Budget checking requires an authenticated virtual key."""

    from prism.domain.errors import AuthenticationError

    context = RequestContext(
        request_id="request-2",
        start_time=datetime(2026, 11, 2, 10, 0, tzinfo=timezone.utc),
    )

    repository = FakeUsageRepository(total_spend_usd=0.0)

    with pytest.raises(AuthenticationError):
        await enforce_budget(
            context=context,
            usage_repository=repository,
            now=context.start_time,
        )
