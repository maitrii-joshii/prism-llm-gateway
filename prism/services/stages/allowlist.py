"""Model allowlist enforcement stage for the Prism request pipeline."""

from prism.domain.errors import AuthenticationError, ModelNotAllowedError
from prism.domain.models import RequestContext


async def enforce_model_allowlist(
    context: RequestContext,
) -> RequestContext:
    """Ensure the requested model is allowed for the authenticated key."""

    if context.key_config is None:
        raise AuthenticationError(
            "Request must be authenticated before model allowlist checking."
        )

    requested_model = context.model_requested
    allowed_models = context.key_config.model_allowlist

    # Wildcard means the key can access every model.
    if "*" in allowed_models:
        context.decision_trace.append("model allowlist ok (wildcard)")
        return context

    # Check whether the requested model is explicitly allowed.
    if requested_model not in allowed_models:
        context.decision_trace.append("model not allowed")
        raise ModelNotAllowedError(
            f"Model '{requested_model}' is not allowed for this API key."
        )

    context.decision_trace.append(
        f"model allowlist ok ({requested_model})"
    )

    return context