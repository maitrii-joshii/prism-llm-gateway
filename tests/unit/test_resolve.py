"""Unit tests for model alias and automatic resolution."""

from datetime import datetime, timezone

import pytest

from prism.domain.errors import ModelNotFoundError
from prism.domain.models import (
    AliasConfig,
    GatewayConfig,
    ModelPricing,
    RequestContext,
)
from prism.services.stages.resolve import resolve_model_candidates


FAST_MODEL = "gpt-4o-mini"
SMART_MODEL = "llama-3.3-70b-versatile"


@pytest.fixture
def gateway_config():
    """Provide a gateway configuration with fast and smart aliases."""

    pricing = {
        FAST_MODEL: ModelPricing(
            model_name=FAST_MODEL,
            input_price_per_million=0.15,
            output_price_per_million=0.60,
        ),
        SMART_MODEL: ModelPricing(
            model_name=SMART_MODEL,
            input_price_per_million=0.59,
            output_price_per_million=0.79,
        ),
    }

    return GatewayConfig(
        aliases={
            "fast": AliasConfig(
                alias_name="fast",
                primary_model=FAST_MODEL,
                fallback_chain=[SMART_MODEL],
            ),
            "smart": AliasConfig(
                alias_name="smart",
                primary_model=SMART_MODEL,
                fallback_chain=[FAST_MODEL],
            ),
        },
        model_pricing=pricing,
    )


@pytest.fixture
def request_context():
    """Create a request context for resolver tests."""

    return RequestContext(
        request_id="test-request-123",
        model_requested="",
        start_time=datetime.now(timezone.utc),
    )


def test_fast_alias_resolves_to_primary_and_fallback(
    request_context,
    gateway_config,
):
    request_context.model_requested = "fast"

    result = resolve_model_candidates(
        request_context,
        gateway_config,
    )

    assert result.model_resolved == FAST_MODEL
    assert result.model_candidates == [
        FAST_MODEL,
        SMART_MODEL,
    ]


def test_smart_alias_resolves_to_primary_and_fallback(
    request_context,
    gateway_config,
):
    request_context.model_requested = "smart"

    result = resolve_model_candidates(
        request_context,
        gateway_config,
    )

    assert result.model_resolved == SMART_MODEL
    assert result.model_candidates == [
        SMART_MODEL,
        FAST_MODEL,
    ]


def test_direct_model_name_passes_through_unchanged(
    request_context,
    gateway_config,
):
    request_context.model_requested = FAST_MODEL

    result = resolve_model_candidates(
        request_context,
        gateway_config,
    )

    assert result.model_resolved == FAST_MODEL
    assert result.model_candidates == [FAST_MODEL]


def test_unknown_model_raises_model_not_found(
    request_context,
    gateway_config,
):
    request_context.model_requested = "nonexistent"

    with pytest.raises(ModelNotFoundError) as exc_info:
        resolve_model_candidates(
            request_context,
            gateway_config,
        )

    assert exc_info.value.status_code == 404


def test_duplicate_fallback_models_are_removed(
    request_context,
    gateway_config,
):
    gateway_config.aliases["fast"].fallback_chain = [
        SMART_MODEL,
        SMART_MODEL,
    ]

    request_context.model_requested = "fast"

    result = resolve_model_candidates(
        request_context,
        gateway_config,
    )

    assert result.model_candidates == [
        FAST_MODEL,
        SMART_MODEL,
    ]


def test_auto_routes_easy_prompt_to_fast(
    request_context,
    gateway_config,
):
    request_context.model_requested = "auto"
    request_context.messages = [
        {
            "role": "user",
            "content": "List five popular Python frameworks.",
        }
    ]

    result = resolve_model_candidates(
        request_context,
        gateway_config,
    )

    assert result.model_resolved == FAST_MODEL
    assert result.model_candidates == [
        FAST_MODEL,
        SMART_MODEL,
    ]

    assert any(
        "auto→fast" in trace
        for trace in result.decision_trace
    )


def test_auto_routes_hard_prompt_to_smart(
    request_context,
    gateway_config,
):
    request_context.model_requested = "auto"
    request_context.messages = [
        {
            "role": "user",
            "content": "Prove that the square root of 2 is irrational.",
        }
    ]

    result = resolve_model_candidates(
        request_context,
        gateway_config,
    )

    assert result.model_resolved == SMART_MODEL
    assert result.model_candidates == [
        SMART_MODEL,
        FAST_MODEL,
    ]

    assert any(
        "auto→smart" in trace
        for trace in result.decision_trace
    )


def test_auto_routing_trace_contains_score_and_reason(
    request_context,
    gateway_config,
):
    request_context.model_requested = "auto"
    request_context.messages = [
        {
            "role": "user",
            "content": "Prove that the square root of 2 is irrational.",
        }
    ]

    result = resolve_model_candidates(
        request_context,
        gateway_config,
    )

    routing_trace = next(
        trace
        for trace in result.decision_trace
        if trace.startswith("auto→")
    )

    assert "smart" in routing_trace
    assert "score" in routing_trace
    assert "prove" in routing_trace
    assert "judged complex" in routing_trace


def test_auto_raises_error_when_selected_alias_is_missing(
    request_context,
    gateway_config,
):
    del gateway_config.aliases["smart"]

    request_context.model_requested = "auto"
    request_context.messages = [
        {
            "role": "user",
            "content": "Prove that 2 is irrational.",
        }
    ]

    with pytest.raises(ModelNotFoundError):
        resolve_model_candidates(
            request_context,
            gateway_config,
        )
