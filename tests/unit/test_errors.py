
import pytest

from prism.domain.errors import (
    AuthenticationError,
    BudgetExceededError,
    InvalidRequestError,
    ModelNotAllowedError,
    ModelNotFoundError,
    PrismError,
    RateLimitError,
    UpstreamError,
)


@pytest.mark.parametrize(
    ("error_class", "status_code", "error_type"),
    [
        (PrismError, 500, "internal_error"),
        (AuthenticationError, 401, "authentication_error"),
        (InvalidRequestError, 400, "invalid_request"),
        (ModelNotAllowedError, 403, "model_not_allowed"),
        (ModelNotFoundError, 404, "not_found_error"),
        (RateLimitError, 429, "rate_limit_exceeded"),
        (BudgetExceededError, 429, "budget_exceeded"),
        (UpstreamError, 502, "upstream_error"),
    ],
)
def test_error_attributes(error_class, status_code, error_type):
    error = error_class("Test error")

    assert error.status_code == status_code
    assert error.error_type == error_type
    assert error.message == "Test error"


def test_custom_errors_inherit_from_prism_error():
    error = AuthenticationError("Invalid API key")

    assert isinstance(error, PrismError)


def test_error_can_be_raised_and_caught_by_type():
    with pytest.raises(RateLimitError, match="Too many requests"):
        raise RateLimitError("Too many requests")