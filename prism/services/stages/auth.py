"""Authentication stage for validating Prism virtual API keys."""

import hmac

from fastapi import Request

from prism.domain.errors import AuthenticationError
from prism.domain.models import RequestContext
from prism.domain.security import hash_api_key
from prism.ports.repositories import KeyRepository


async def authenticate_request(
    request: Request,
    context: RequestContext,
    key_repository: KeyRepository,
) -> RequestContext:
    """
    Authenticate an incoming request using its x-api-key header.

    On success, attach the VirtualKeyConfig to RequestContext.
    On failure, raise AuthenticationError with HTTP 401.
    """

    raw_key = request.headers.get("x-api-key")

    if not raw_key or not raw_key.strip():
        context.decision_trace.append("auth failed")
        raise AuthenticationError("Invalid or missing API key.")

    provided_hash = hash_api_key(raw_key)

    key_config = key_repository.get_by_hash(provided_hash)

    if key_config is None:
        context.decision_trace.append("auth failed")
        raise AuthenticationError("Invalid or missing API key.")

    # Compare the computed hash with the hash returned by the repository.
    if not hmac.compare_digest(provided_hash, key_config.key_hash):
        context.decision_trace.append("auth failed")
        raise AuthenticationError("Invalid or missing API key.")

    # Reject disabled or inactive virtual keys.
    if key_config.status.lower() != "active":
        context.decision_trace.append("auth failed")
        raise AuthenticationError("Invalid or missing API key.")

    context.key_config = key_config
    context.decision_trace.append("auth ok")

    return context
