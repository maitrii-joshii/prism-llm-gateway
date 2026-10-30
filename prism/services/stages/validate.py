"""Request validation stage for Prism."""

from typing import Any

from prism.config.settings import Settings
from prism.domain.errors import InvalidRequestError


def validate_request(
    payload: dict[str, Any],
    settings: Settings | None = None,
) -> dict[str, Any]:
    """
    Validate a chat completion request.

    Validates model, messages, and max_tokens.
    Caps max_tokens to the configured maximum.

    Returns the validated payload.
    Raises InvalidRequestError when validation fails.
    """

    if not isinstance(payload, dict):
        raise InvalidRequestError(
            "Request body must be a JSON object."
        )

    # Load settings when they are not provided by the caller.
    if settings is None:
        settings = Settings.from_env()

    # Validate model.
    model = payload.get("model")

    if not isinstance(model, str) or not model.strip():
        raise InvalidRequestError(
            "'model' is required and must be a non-empty string."
        )

    # Validate messages.
    messages = payload.get("messages")

    if not isinstance(messages, list) or not messages:
        raise InvalidRequestError(
            "'messages' is required and must be a non-empty array."
        )

    for index, message in enumerate(messages):
        if not isinstance(message, dict):
            raise InvalidRequestError(
                f"Message at index {index} must be an object."
            )

        if "role" not in message:
            raise InvalidRequestError(
                f"Message at index {index} is missing 'role'."
            )

        if "content" not in message:
            raise InvalidRequestError(
                f"Message at index {index} is missing 'content'."
            )

        if not isinstance(message["role"], str) or not message["role"].strip():
            raise InvalidRequestError(
                f"Message at index {index} has an invalid 'role'."
            )

        if not isinstance(message["content"], (str, list)):
            raise InvalidRequestError(
                f"Message at index {index} has an invalid 'content'."
            )

    # Validate and cap max_tokens.
    if "max_tokens" in payload:
        max_tokens = payload["max_tokens"]

        # bool is a subclass of int in Python, so reject it explicitly.
        if isinstance(max_tokens, bool) or not isinstance(max_tokens, int):
            raise InvalidRequestError(
                "'max_tokens' must be a positive integer."
            )

        if max_tokens <= 0:
            raise InvalidRequestError(
                "'max_tokens' must be a positive integer."
            )

        # Cap the requested value instead of rejecting large values.
        payload["max_tokens"] = min(
            max_tokens,
            settings.max_tokens_cap,
        )

    return payload
