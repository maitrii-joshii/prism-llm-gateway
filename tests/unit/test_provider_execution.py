"""Unit tests for ProviderExecutionService."""

from datetime import datetime, timezone

import pytest

from prism.domain.errors import UpstreamError
from prism.domain.models import (
    GatewayConfig,
    ProviderResponse,
    RequestContext,
)
from prism.services.executor import ExecutionResult
from prism.services.providers.execution import (
    ProviderExecutionService,
)
from tests.helpers.fake_adapter import FakeProviderAdapter


PRIMARY_MODEL = "gpt-4o-mini"
BACKUP_MODEL = "llama-3.3-70b-versatile"


def create_context(
    model_candidates: list[str] | None = None,
) -> RequestContext:
    """Create a request context for provider execution."""

    return RequestContext(
        request_id="req_test123",
        model_requested="fast",
        messages=[
            {
                "role": "user",
                "content": "Hello Prism",
            }
        ],
        request_payload={
            "model": "fast",
            "messages": [
                {
                    "role": "user",
                    "content": "Hello Prism",
                }
            ],
        },
        start_time=datetime.now(timezone.utc),
        model_candidates=model_candidates or [PRIMARY_MODEL],
    )


def create_response(
    model: str = PRIMARY_MODEL,
) -> ProviderResponse:
    """Create a successful fake provider response."""

    return ProviderResponse(
        content="Test response",
        model=model,
        prompt_tokens=10,
        completion_tokens=5,
        total_tokens=15,
        finish_reason="stop",
        raw_response={"test": True},
    )


@pytest.fixture
def service() -> ProviderExecutionService:
    """Create a provider execution service."""

    return ProviderExecutionService()


@pytest.mark.asyncio
async def test_legacy_single_provider_execution(service):
    """Legacy configuration executes through the default adapter."""

    adapter = FakeProviderAdapter(
        response=create_response()
    )
    context = create_context()

    result = await service.execute(
        context=context,
        loaded_config=None,
        settings=None,
        provider_adapters=None,
        default_provider=adapter,
    )

    assert isinstance(result, ExecutionResult)
    assert result.response.model == PRIMARY_MODEL
    assert result.provider_name == "alpha"
    assert result.retries == 0
    assert result.fallback_used is False
    assert adapter.call_count == 1


@pytest.mark.asyncio
async def test_multi_provider_successful_execution(service):
    """The primary configured provider handles the request."""

    primary_adapter = FakeProviderAdapter(
        response=create_response()
    )
    backup_adapter = FakeProviderAdapter(
        response=create_response(BACKUP_MODEL)
    )

    primary_adapter.name = "openai"
    backup_adapter.name = "groq"

    context = create_context(
        [PRIMARY_MODEL, BACKUP_MODEL]
    )

    config = GatewayConfig(
        max_retries=0,
        provider_timeout_seconds=10.0,
    )

    result = await service.execute(
        context=context,
        loaded_config=config,
        settings=None,
        provider_adapters={
            PRIMARY_MODEL: primary_adapter,
            BACKUP_MODEL: backup_adapter,
        },
        default_provider=None,
        provider_names={
            PRIMARY_MODEL: "openai",
            BACKUP_MODEL: "groq",
        },
    )

    assert result.response.model == PRIMARY_MODEL
    assert result.provider_name == "openai"
    assert result.fallback_used is False
    assert primary_adapter.call_count == 1
    assert backup_adapter.call_count == 0
    assert primary_adapter.last_request["model"] == PRIMARY_MODEL


@pytest.mark.asyncio
async def test_multi_provider_failover(service):
    """The backup provider handles the request if primary fails."""

    primary_adapter = FakeProviderAdapter(
        error=UpstreamError("Primary provider unavailable")
    )
    backup_adapter = FakeProviderAdapter(
        response=create_response(BACKUP_MODEL)
    )

    primary_adapter.name = "openai"
    backup_adapter.name = "groq"

    context = create_context(
        [PRIMARY_MODEL, BACKUP_MODEL]
    )

    config = GatewayConfig(
        max_retries=0,
        provider_timeout_seconds=10.0,
    )

    result = await service.execute(
        context=context,
        loaded_config=config,
        settings=None,
        provider_adapters={
            PRIMARY_MODEL: primary_adapter,
            BACKUP_MODEL: backup_adapter,
        },
        default_provider=None,
        provider_names={
            PRIMARY_MODEL: "openai",
            BACKUP_MODEL: "groq",
        },
    )

    assert result.response.model == BACKUP_MODEL
    assert result.provider_name == "groq"
    assert result.fallback_used is True
    assert primary_adapter.call_count == 1
    assert backup_adapter.call_count == 1


@pytest.mark.asyncio
async def test_missing_legacy_provider_raises_error(service):
    """Execution fails when no legacy provider is configured."""

    context = create_context()

    with pytest.raises(
        UpstreamError,
        match="Provider adapter is not configured",
    ):
        await service.execute(
            context=context,
            loaded_config=None,
            settings=None,
            provider_adapters=None,
            default_provider=None,
        )


@pytest.mark.asyncio
async def test_missing_model_adapter_raises_error(service):
    """An unresolved provider mapping raises an upstream error."""

    context = create_context(
        [PRIMARY_MODEL, BACKUP_MODEL]
    )

    config = GatewayConfig(
        max_retries=0,
    )

    with pytest.raises(
        UpstreamError,
        match="No provider configured",
    ):
        await service.execute(
            context=context,
            loaded_config=config,
            settings=None,
            provider_adapters={
                PRIMARY_MODEL: FakeProviderAdapter()
            },
            default_provider=None,
        )
