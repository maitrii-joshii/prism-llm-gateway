"""Model allowlist enforcement stage for the Prism request pipeline."""

from prism.domain.errors import AuthenticationError, ModelNotAllowedError
from prism.domain.models import RequestContext


async def enforce_model_allowlist(
    context: RequestContext,
) -> RequestContext:
    """Ensure the authenticated key can access requested and resolved models."""

    if context.key_config is None:
        raise AuthenticationError(
            "Request must be authenticated before model allowlist checking."
        )

    allowed_models = context.key_config.model_allowlist

    # Wildcard means the key can access every model and alias.
    if "*" in allowed_models:
        context.decision_trace.append("model allowlist ok (wildcard)")
        return context

    requested_model = context.model_requested.strip()

    # Explicitly require permission to use automatic routing.
    if requested_model == "auto" and requested_model not in allowed_models:
        context.decision_trace.append("model not allowed")
        raise ModelNotAllowedError(
            "Model 'auto' is not allowed for this API key."
        )

    # For auto routing, check the classifier-selected tier.
    if requested_model == "auto":
        selected_tier = next(
            (
                tier
                for tier in ("fast", "smart")
                if any(
                    f"auto→{tier} " in trace
                    for trace in context.decision_trace
                )
            ),
            None,
        )

        if selected_tier is None:
            context.decision_trace.append("model not allowed")
            raise ModelNotAllowedError(
                "Automatic routing decision is missing."
            )

        if selected_tier not in allowed_models:
            context.decision_trace.append("model not allowed")
            raise ModelNotAllowedError(
                f"Model tier '{selected_tier}' is not allowed "
                "for this API key."
            )

    # Validate every resolved primary and fallback model.
    requested_models = (
        context.model_candidates
        if context.model_candidates
        else [requested_model]
    )

    for model in requested_models:
        if model not in allowed_models:
            context.decision_trace.append("model not allowed")
            raise ModelNotAllowedError(
                f"Model '{model}' is not allowed for this API key."
            )

    context.decision_trace.append(
        f"model allowlist ok ({', '.join(requested_models)})"
    )

    return context


__all__ = ["enforce_model_allowlist"]
