"""Unit tests for the Prism authentication stage."""

from datetime import datetime, timezone
from unittest.mock import Mock

import pytest
from starlette.requests import Request

from prism.domain.errors import AuthenticationError
from prism.domain.models import RequestContext, VirtualKeyConfig
from prism.domain.security import hash_api_key
from prism.services.stages.auth import authenticate_request


RAW_API_KEY = "prism-sk-search-1a2b3c"


@pytest.fixture
def key_config() -> VirtualKeyConfig:
    """Return a valid virtual key configuration."""

    return VirtualKeyConfig(
        key_hash=hash_api_key(RAW_API_KEY),
        tenant_id="tenant-demo",
        budget_usd=100.0,
        rate_limit_rpm=60,
        model_allowlist=["gpt-4o-mini"],
        cache_enabled=True,
        cache_threshold=0.8,
        status="active",
    )


@pytest.fixture
def context() -> RequestContext:
    """Return a request context before authentication."""

    return RequestContext(
        request_id="req_test_001",
        model_requested="fast",
        messages=[{"role": "user", "content": "Hi"}],
        stream=False,
        start_time=datetime.now(timezone.utc),
    )


def create_request(api_key: str | None = None) -> Request:
    """Create a Starlette request with an optional API key header."""

    headers = []

    if api_key is not None:
        headers.append((b"x-api-key", api_key.encode("utf-8")))

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/v1/chat/completions",
        "headers": headers,
        "query_string": b"",
        "server": ("testserver", 80),
        "client": ("testclient", 12345),
        "scheme": "http",
        "http_version": "1.1",
    }

    return Request(scope)


@pytest.mark.asyncio
async def test_missing_api_key_raises_authentication_error(context):
    """A missing API key must return HTTP 401."""

    repository = Mock()

    with pytest.raises(AuthenticationError) as exc_info:
        await authenticate_request(
            create_request(),
            context,
            repository,
        )

    assert exc_info.value.status_code == 401
    assert str(exc_info.value) == "Invalid or missing API key."
    assert context.decision_trace == ["auth failed"]
    repository.get_by_hash.assert_not_called()


@pytest.mark.asyncio
async def test_invalid_api_key_raises_authentication_error(context):
    """An unknown API key must return HTTP 401."""

    repository = Mock()
    repository.get_by_hash.return_value = None

    with pytest.raises(AuthenticationError) as exc_info:
        await authenticate_request(
            create_request("invalid-api-key"),
            context,
            repository,
        )

    assert exc_info.value.status_code == 401
    assert str(exc_info.value) == "Invalid or missing API key."
    assert context.decision_trace == ["auth failed"]
    repository.get_by_hash.assert_called_once_with(
        hash_api_key("invalid-api-key")
    )


@pytest.mark.asyncio
async def test_disabled_api_key_raises_authentication_error(
    context,
    key_config,
):
    """A disabled virtual key must return HTTP 401."""

    repository = Mock()
    disabled_key = key_config.model_copy(update={"status": "disabled"})
    repository.get_by_hash.return_value = disabled_key

    with pytest.raises(AuthenticationError) as exc_info:
        await authenticate_request(
            create_request(RAW_API_KEY),
            context,
            repository,
        )

    assert exc_info.value.status_code == 401
    assert context.decision_trace == ["auth failed"]


@pytest.mark.asyncio
async def test_valid_api_key_populates_request_context(
    context,
    key_config,
):
    """A valid API key must attach its configuration to the context."""

    repository = Mock()
    repository.get_by_hash.return_value = key_config

    result = await authenticate_request(
        create_request(RAW_API_KEY),
        context,
        repository,
    )

    assert result is context
    assert context.key_config == key_config
    assert context.key_config.tenant_id == "tenant-demo"
    assert context.decision_trace == ["auth ok"]


@pytest.mark.asyncio
async def test_empty_api_key_raises_authentication_error(context):
    """An empty API key must return HTTP 401."""

    repository = Mock()

    with pytest.raises(AuthenticationError) as exc_info:
        await authenticate_request(
            create_request("   "),
            context,
            repository,
        )

    assert exc_info.value.status_code == 401
    assert context.decision_trace == ["auth failed"]
    repository.get_by_hash.assert_not_called()


@pytest.mark.asyncio
async def test_hash_comparison_uses_constant_time_function(
    context,
    key_config,
    monkeypatch,
):
    """Authentication must use hmac.compare_digest."""

    import prism.services.stages.auth as auth_module

    repository = Mock()
    repository.get_by_hash.return_value = key_config

    comparison_calls = []
    original_compare_digest = auth_module.hmac.compare_digest

    def tracked_compare_digest(first, second):
        comparison_calls.append((first, second))
        return original_compare_digest(first, second)

    monkeypatch.setattr(
        auth_module.hmac,
        "compare_digest",
        tracked_compare_digest,
    )

    await authenticate_request(
        create_request(RAW_API_KEY),
        context,
        repository,
    )

    assert len(comparison_calls) == 1
    assert comparison_calls[0] == (
        hash_api_key(RAW_API_KEY),
        key_config.key_hash,
    )
