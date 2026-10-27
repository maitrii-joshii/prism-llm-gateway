from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from prism.domain.models import (
    AliasConfig,
    GatewayConfig,
    ModelPricing,
    ProviderResponse,
    RequestContext,
    UsageRecord,
    VirtualKeyConfig,
)


@pytest.fixture
def virtual_key():
    return VirtualKeyConfig(
        key_hash="abc123",
        tenant_id="tenant-1",
        budget_usd=100.0,
        rate_limit_rpm=60,
        model_allowlist=["gpt-4o-mini"],
        cache_enabled=True,
        cache_threshold=0.9,
        status="active",
    )


def test_virtual_key_config_accepts_valid_data(virtual_key):
    assert virtual_key.tenant_id == "tenant-1"
    assert virtual_key.rate_limit_rpm == 60


def test_virtual_key_config_rejects_missing_required_fields():
    with pytest.raises(ValidationError):
        VirtualKeyConfig()


def test_virtual_key_config_rejects_negative_rate_limit(virtual_key):
    with pytest.raises(ValidationError):
        VirtualKeyConfig(
            **{
                **virtual_key.model_dump(),
                "rate_limit_rpm": -1,
            }
        )


def test_request_context_has_independent_decision_traces(virtual_key):
    common = {
        "request_id": "req-1",
        "key_config": virtual_key,
        "model_requested": "gpt-4o-mini",
        "messages": [{"role": "user", "content": "Hello"}],
        "stream": False,
        "start_time": datetime.now(timezone.utc),
    }

    request1 = RequestContext(**common)
    request2 = RequestContext(**{**common, "request_id": "req-2"})

    request1.decision_trace.append("authentication passed")

    assert request1.decision_trace == ["authentication passed"]
    assert request2.decision_trace == []


def test_all_seven_domain_models_can_be_instantiated(virtual_key):
    RequestContext(
        request_id="req-1",
        key_config=virtual_key,
        model_requested="gpt-4o-mini",
        messages=[{"role": "user", "content": "Hello"}],
        stream=False,
        start_time=datetime.now(timezone.utc),
    )

    ProviderResponse(
        content="Hello!",
        model="gpt-4o-mini",
        prompt_tokens=5,
        completion_tokens=3,
        total_tokens=8,
        raw_response={},
    )

    ModelPricing(
        model_name="gpt-4o-mini",
        input_price_per_million=0.15,
        output_price_per_million=0.60,
    )

    AliasConfig(
        alias_name="fast",
        primary_model="gpt-4o-mini",
        fallback_chain=[],
    )

    GatewayConfig()

    UsageRecord(
        request_id="req-1",
        tenant_id="tenant-1",
        model="gpt-4o-mini",
        prompt_tokens=5,
        completion_tokens=3,
        total_tokens=8,
        cost_usd=0.000002,
        created_at=datetime.now(timezone.utc),
    )
