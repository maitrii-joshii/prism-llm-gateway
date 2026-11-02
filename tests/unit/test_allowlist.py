"""Unit tests for the model allowlist enforcement stage."""

from datetime import datetime, timezone

import pytest

from prism.domain.errors import (
    AuthenticationError,
    ModelNotAllowedError,
)
from prism.domain.models import RequestContext, VirtualKeyConfig
from prism.services.stages.allowlist import enforce_model_allowlist


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
async def test_allows_model_in_allowlist(context):
    """Allows a request when the requested model is in the allowlist."""

    result = await enforce_model_allowlist(context)

    assert result is context
    assert "model allowlist ok (gpt-4o-mini)" in result.decision_trace


@pytest.mark.asyncio
async def test_rejects_model_not_in_allowlist(context):
    """Rejects a request when the requested model is not allowed."""

    context.model_requested = "llama-3.3-70b-versatile"

    with pytest.raises(ModelNotAllowedError) as exc_info:
        await enforce_model_allowlist(context)

    assert exc_info.value.status_code == 403
    assert exc_info.value.error_type == "model_not_allowed"
    assert "model not allowed" in context.decision_trace


@pytest.mark.asyncio
async def test_wildcard_allows_any_model(context):
    """A wildcard allowlist allows any requested model."""

    context.key_config.model_allowlist = ["*"]
    context.model_requested = "some-other-model"

    result = await enforce_model_allowlist(context)

    assert result is context
    assert "model allowlist ok (wildcard)" in result.decision_trace


@pytest.mark.asyncio
async def test_rejects_request_without_authenticated_key():
    """Allowlist checking requires an authenticated virtual key."""

    context = RequestContext(
        request_id="request-2",
        model_requested="gpt-4o-mini",
        start_time=datetime(2026, 11, 2, 10, 0, tzinfo=timezone.utc),
    )

    with pytest.raises(AuthenticationError):
        await enforce_model_allowlist(context)