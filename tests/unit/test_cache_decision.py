"""Unit tests for semantic cache decision logic."""

from datetime import datetime, timezone

import pytest

from prism.domain.cache_decision import is_cacheable, is_hit
from prism.domain.models import (
    ProviderResponse,
    RequestContext,
    VirtualKeyConfig,
)


@pytest.fixture
def key_config():
    return VirtualKeyConfig(
        key_hash="test-hash",
        tenant_id="tenant-1",
        budget_usd=10.0,
        rate_limit_rpm=60,
        model_allowlist=["*"],
        cache_enabled=True,
        cache_threshold=0.85,
        status="active",
    )


@pytest.fixture
def successful_context(key_config):
    return RequestContext(
        request_id="test-request",
        key_config=key_config,
        messages=[
            {
                "role": "user",
                "content": "Reset my password",
            }
        ],
        provider_response=ProviderResponse(
            content="Follow the password reset instructions.",
            model="gpt-4o-mini",
            prompt_tokens=10,
            completion_tokens=20,
            total_tokens=30,
            finish_reason="stop",
            raw_response={},
        ),
        start_time=datetime.now(timezone.utc),
    )


def test_cache_disabled_key_is_not_cacheable(successful_context):
    successful_context.key_config.cache_enabled = False

    assert is_cacheable(successful_context) is False


def test_missing_key_config_is_not_cacheable(successful_context):
    successful_context.key_config = None

    assert is_cacheable(successful_context) is False


@pytest.mark.parametrize(
    "prompt",
    [
        "What's the weather now?",
        "What happened today?",
        "Give me the latest news",
        "What is the current price?",
        "What is happening right now?",
        "What is happening at this moment?",
    ],
)
def test_time_sensitive_prompt_is_not_cacheable(
    successful_context,
    prompt,
):
    successful_context.messages = [
        {"role": "user", "content": prompt}
    ]

    assert is_cacheable(successful_context) is False


def test_successful_non_time_sensitive_request_is_cacheable(
    successful_context,
):
    assert is_cacheable(successful_context) is True


def test_missing_provider_response_is_not_cacheable(
    successful_context,
):
    successful_context.provider_response = None

    assert is_cacheable(successful_context) is False


def test_error_response_is_not_cacheable(successful_context):
    successful_context.provider_response.finish_reason = "error"

    assert is_cacheable(successful_context) is False


def test_similarity_above_threshold_is_hit():
    assert is_hit(0.90, 0.85) is True


def test_similarity_equal_to_threshold_is_hit():
    assert is_hit(0.85, 0.85) is True


def test_similarity_below_threshold_is_miss():
    assert is_hit(0.70, 0.85) is False


@pytest.mark.parametrize(
    "score,threshold",
    [
        (-0.1, 0.85),
        (1.1, 0.85),
        (0.9, -0.1),
        (0.9, 1.1),
    ],
)
def test_invalid_similarity_values_raise_error(score, threshold):
    with pytest.raises(ValueError):
        is_hit(score, threshold)
