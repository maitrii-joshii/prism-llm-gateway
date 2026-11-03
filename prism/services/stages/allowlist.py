"""Model allowlist enforcement stage for the Prism request pipeline."""

from prism.domain.errors import AuthenticationError, ModelNotAllowedError
from prism.domain.models import RequestContext


async def enforce_model_allowlist(
    context: RequestContext,
) -> RequestContext:
    """Ensure all candidate models are allowed for the authenticated key."""

    if context.key_config is None:
        raise AuthenticationError(
            "Request must be authenticated before model allowlist checking."
        )

    allowed_models = context.key_config.model_allowlist

    # Wildcard means the key can access every model.
    if "*" in allowed_models:
        context.decision_trace.append("model allowlist ok (wildcard)")
        return context

    # Use candidate models when available.
    # Otherwise, preserve the original single-model behavior.
    requested_models = (
        context.model_candidates
        if context.model_candidates
        else [context.model_requested]
    )

    # Reject the request if any candidate model is not allowed.
    for model in requested_models:
        if model not in allowed_models:
            # Keep the original decision trace for backward compatibility.
            context.decision_trace.append("model not allowed")
            raise ModelNotAllowedError(
                f"Model '{model}' is not allowed for this API key."
            )

    context.decision_trace.append(
        f"model allowlist ok ({', '.join(requested_models)})"
    )

    return context
