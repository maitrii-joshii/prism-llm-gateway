"""Unit tests for UsageRecordingService."""

from datetime import datetime, timezone

import pytest

from prism.domain.errors import UpstreamError
from prism.domain.models import (
    ProviderResponse,
    RequestContext,
    VirtualKeyConfig,
)
from prism.services.observability.usage_recording import (
    UsageRecordingService,
)


class FakeUsageRepository:
    def __init__(self):
        self.records = []

    def record_usage(self, **kwargs):
        self.records.append(kwargs)


@pytest.fixture
def service():
    return UsageRecordingService()


@pytest.fixture
def context():
    return RequestContext(
        request_id="req_usage_test",
        model_requested="fast",
        start_time=datetime.now(timezone.utc),
        provider_response=ProviderResponse(
            content="Hello",
            model="gpt-4o-mini",
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
            finish_reason="stop",
            raw_response={},
        ),
        key_config=VirtualKeyConfig(
            key_hash="test_hash",
            tenant_id="test_tenant",
            budget_usd=100.0,
            rate_limit_rpm=60,
            model_allowlist=["gpt-4o-mini"],
            cache_enabled=True,
            cache_threshold=0.9,
            status="active",
        ),
        cost_usd=0.002,
    )


def test_records_completion_usage(service, context):
    repository = FakeUsageRepository()

    service.record(context, repository)

    assert len(repository.records) == 1
    record = repository.records[0]

    assert record["key_hash"] == "test_hash"
    assert record["month"] == context.start_time.strftime("%Y-%m")
    assert record["cost"] == 0.002
    assert record["tokens"] == 15
    assert record["is_cache_hit"] is False
    assert "usage recorded: 15 tokens" in context.decision_trace


def test_records_cache_hit(service, context):
    repository = FakeUsageRepository()
    context.cache_status = "hit"

    service.record(context, repository)

    assert repository.records[0]["is_cache_hit"] is True


def test_skips_when_provider_response_is_missing(service, context):
    repository = FakeUsageRepository()
    context.provider_response = None

    service.record(context, repository)

    assert repository.records == []


def test_raises_when_key_configuration_is_missing(service, context):
    repository = FakeUsageRepository()
    context.key_config = None

    with pytest.raises(
        UpstreamError,
        match="Authenticated key configuration is missing",
    ):
        service.record(context, repository)

    assert repository.records == []
