"""Unit tests for the request validation stage."""

import pytest

from prism.config.settings import Settings
from prism.domain.errors import InvalidRequestError
from prism.services.stages.validate import validate_request


@pytest.fixture
def settings():
    return Settings(
        config_dir=None,
        max_tokens_cap=4096,
    )


@pytest.fixture
def valid_payload():
    return {
        "model": "gpt-4o-mini",
        "messages": [
            {
                "role": "user",
                "content": "Hello",
            }
        ],
    }


def test_valid_request_passes_validation(valid_payload, settings):
    result = validate_request(valid_payload, settings)

    assert result["model"] == "gpt-4o-mini"
    assert len(result["messages"]) == 1


def test_missing_model_raises_error(valid_payload, settings):
    valid_payload.pop("model")

    with pytest.raises(InvalidRequestError):
        validate_request(valid_payload, settings)


def test_empty_model_raises_error(valid_payload, settings):
    valid_payload["model"] = "   "

    with pytest.raises(InvalidRequestError):
        validate_request(valid_payload, settings)


def test_missing_messages_raises_error(valid_payload, settings):
    valid_payload.pop("messages")

    with pytest.raises(InvalidRequestError):
        validate_request(valid_payload, settings)


def test_empty_messages_raises_error(valid_payload, settings):
    valid_payload["messages"] = []

    with pytest.raises(InvalidRequestError):
        validate_request(valid_payload, settings)


def test_message_missing_role_raises_error(valid_payload, settings):
    valid_payload["messages"][0].pop("role")

    with pytest.raises(InvalidRequestError):
        validate_request(valid_payload, settings)


def test_message_missing_content_raises_error(valid_payload, settings):
    valid_payload["messages"][0].pop("content")

    with pytest.raises(InvalidRequestError):
        validate_request(valid_payload, settings)


def test_negative_max_tokens_raises_error(valid_payload, settings):
    valid_payload["max_tokens"] = -1

    with pytest.raises(InvalidRequestError):
        validate_request(valid_payload, settings)


def test_zero_max_tokens_raises_error(valid_payload, settings):
    valid_payload["max_tokens"] = 0

    with pytest.raises(InvalidRequestError):
        validate_request(valid_payload, settings)


def test_non_integer_max_tokens_raises_error(valid_payload, settings):
    valid_payload["max_tokens"] = 10.5

    with pytest.raises(InvalidRequestError):
        validate_request(valid_payload, settings)


def test_boolean_max_tokens_raises_error(valid_payload, settings):
    valid_payload["max_tokens"] = True

    with pytest.raises(InvalidRequestError):
        validate_request(valid_payload, settings)


def test_max_tokens_above_cap_is_capped(valid_payload, settings):
    valid_payload["max_tokens"] = 10000000

    result = validate_request(valid_payload, settings)

    assert result["max_tokens"] == 4096


def test_max_tokens_below_cap_is_unchanged(valid_payload, settings):
    valid_payload["max_tokens"] = 100

    result = validate_request(valid_payload, settings)

    assert result["max_tokens"] == 100


def test_missing_max_tokens_is_allowed(valid_payload, settings):
    result = validate_request(valid_payload, settings)

    assert "max_tokens" not in result
