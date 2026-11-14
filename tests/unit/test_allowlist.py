"""Unit tests for the model allowlist enforcement stage."""

from datetime import datetime, timezone

import pytest

from prism.domain.errors import (
    AuthenticationError,
    ModelNotAllowedError,
)
from prism.domain.models import RequestContext, VirtualKeyConfig
from prism.services.stages.allowlist import enforce_model_allowlist


FAST_MODEL = "gpt-4o-mini"
SMART_MODEL = "llama-3.3-70b-versatile"


@pytest.fixture
def context():
    """Create an authenticated request context."""

    key_config = VirtualKeyConfig(
        key_hash="test-key-hash",
        tenant_id="tenant-1",
        budget_usd=10.0,
        rate_limit_rpm=100,
        model_allowlist=[FAST_MODEL],
        cache_enabled=True,
        cache_threshold=0.9,
        status="active",
    )

    return RequestContext(
        request_id="request-1",
        key_config=key_config,
        model_requested=FAST_MODEL,
        start_time=datetime(2026, 11, 2, 10, 0, tzinfo=timezone.utc),
    )


@pytest.mark.asyncio
async def test_allows_model_in_allowlist(context):
    """Allows a request when the requested model is in the allowlist."""

    result = await enforce_model_allowlist(context)

    assert result is context
    assert f"model allowlist ok ({FAST_MODEL})" in result.decision_trace


@pytest.mark.asyncio
async def test_rejects_model_not_in_allowlist(context):
    """Rejects a request when the requested model is not allowed."""

    context.model_requested = SMART_MODEL

    with pytest.raises(ModelNotAllowedError) as exc_info:
        await enforce_model_allowlist(context)

    assert exc_info.value.status_code == 403
    assert exc_info.value.error_type == "model_not_allowed"
    assert "model not allowed" in context.decision_trace


@pytest.mark.asyncio
async def test_allows_alias_name_in_allowlist(context):
    """Allows request when the requested alias itself is in the allowlist."""

    context.model_requested = "fast"
    context.model_resolved = FAST_MODEL
    context.model_candidates = [FAST_MODEL, SMART_MODEL]
    context.key_config.model_allowlist = ["fast"]

    result = await enforce_model_allowlist(context)

    assert result is context
    assert "model allowlist ok (fast)" in result.decision_trace


@pytest.mark.asyncio
async def test_allows_all_aliases_key_accessing_candidate_models(context):
    """Allows candidates when the key contains aliases covering all candidates."""

    context.model_requested = "fast"
    context.model_resolved = FAST_MODEL
    context.model_candidates = [FAST_MODEL, SMART_MODEL]
    context.key_config.model_allowlist = ["fast", "smart", "quality"]

    result = await enforce_model_allowlist(context)

    assert result is context
    assert "model allowlist ok (fast)" in result.decision_trace


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
        model_requested=FAST_MODEL,
        start_time=datetime(2026, 11, 2, 10, 0, tzinfo=timezone.utc),
    )

    with pytest.raises(AuthenticationError):
        await enforce_model_allowlist(context)


@pytest.mark.asyncio
async def test_allows_auto_when_tier_and_candidates_are_allowed(context):
    """Allows auto when the selected tier and all candidates are allowed."""

    context.model_requested = "auto"
    context.model_resolved = FAST_MODEL
    context.model_candidates = [FAST_MODEL, SMART_MODEL]
    context.key_config.model_allowlist = [
        "auto",
        "fast",
        FAST_MODEL,
        SMART_MODEL,
    ]
    context.decision_trace.append(
        "auto→fast (score 0.00, list; judged simple)"
    )

    result = await enforce_model_allowlist(context)

    assert result is context
    assert any(
        "model allowlist ok" in trace
        for trace in result.decision_trace
    )


@pytest.mark.asyncio
async def test_rejects_auto_when_auto_alias_is_not_allowed(context):
    """Rejects auto when the key cannot request automatic routing."""

    context.model_requested = "auto"
    context.model_resolved = FAST_MODEL
    context.model_candidates = [FAST_MODEL]
    context.key_config.model_allowlist = [
        "fast",
        FAST_MODEL,
    ]
    context.decision_trace.append(
        "auto→fast (score 0.00, list; judged simple)"
    )

    with pytest.raises(ModelNotAllowedError):
        await enforce_model_allowlist(context)

    assert "model not allowed" in context.decision_trace


@pytest.mark.asyncio
async def test_rejects_auto_when_selected_tier_is_not_allowed(context):
    """Rejects auto when the selected tier is not in the allowlist."""

    context.model_requested = "auto"
    context.model_resolved = FAST_MODEL
    context.model_candidates = [FAST_MODEL]
    context.key_config.model_allowlist = [
        "auto",
        FAST_MODEL,
    ]
    context.decision_trace.append(
        "auto→fast (score 0.00, list; judged simple)"
    )

    with pytest.raises(ModelNotAllowedError):
        await enforce_model_allowlist(context)

    assert "model not allowed" in context.decision_trace


@pytest.mark.asyncio
async def test_rejects_auto_when_resolved_fallback_is_not_allowed(context):
    """Rejects auto if any resolved candidate is not allowed."""

    context.model_requested = "auto"
    context.model_resolved = FAST_MODEL
    context.model_candidates = [FAST_MODEL, SMART_MODEL]
    context.key_config.model_allowlist = [
        "auto",
        "fast",
        FAST_MODEL,
    ]
    context.decision_trace.append(
        "auto→fast (score 0.00, list; judged simple)"
    )

    with pytest.raises(ModelNotAllowedError):
        await enforce_model_allowlist(context)

    assert "model not allowed" in context.decision_trace


@pytest.mark.asyncio
async def test_allows_alias_name_in_allowlist(context):
    """Allows request when the requested alias itself is in the allowlist."""

    context.model_requested = "fast"
    context.model_resolved = FAST_MODEL
    context.model_candidates = [FAST_MODEL, SMART_MODEL]
    context.key_config.model_allowlist = ["fast"]

    result = await enforce_model_allowlist(context)

    assert result is context
    assert "model allowlist ok (fast)" in result.decision_trace


@pytest.mark.asyncio
async def test_allows_all_aliases_key_accessing_candidate_models(context):
    """Allows candidates when the key contains aliases covering all candidates."""

    context.model_requested = "fast"
    context.model_resolved = FAST_MODEL
    context.model_candidates = [FAST_MODEL, SMART_MODEL]
    context.key_config.model_allowlist = ["fast", "smart", "quality"]

    result = await enforce_model_allowlist(context)

    assert result is context
    assert "model allowlist ok (fast)" in result.decision_trace
