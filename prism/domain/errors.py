
"""Custom exceptions for the Prism LLM Gateway."""


class PrismError(Exception):
    """Base class for Prism errors."""

    status_code = 500
    error_type = "internal_error"

    def __init__(
        self,
        message: str = "An unexpected internal error occurred.",
    ) -> None:
        self.message = message
        super().__init__(message)


class AuthenticationError(PrismError):
    status_code = 401
    error_type = "authentication_error"


class InvalidRequestError(PrismError):
    status_code = 400
    error_type = "invalid_request"


class ModelNotAllowedError(PrismError):
    status_code = 403
    error_type = "model_not_allowed"


class ModelNotFoundError(PrismError):
    status_code = 404
    error_type = "not_found_error"


class RateLimitError(PrismError):
    status_code = 429
    error_type = "rate_limit_exceeded"


class BudgetExceededError(PrismError):
    status_code = 429
    error_type = "budget_exceeded"


class UpstreamError(PrismError):
    status_code = 502
    error_type = "upstream_error"
