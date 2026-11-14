"""Model alias and automatic difficulty-based resolution stage."""

from typing import Any

from prism.domain.errors import ModelNotFoundError
from prism.domain.models import RequestContext
from prism.services.router import HeuristicClassifier


def get_gateway_config(loaded_config: Any) -> Any:
    """Support both LoadedConfig and GatewayConfig objects."""
    return getattr(
        loaded_config,
        "gateway_config",
        loaded_config,
    )


def get_model_pricing(loaded_config: Any) -> dict[str, Any]:
    """Retrieve model pricing from the loaded configuration."""
    gateway_config = get_gateway_config(loaded_config)

    return getattr(
        loaded_config,
        "model_pricing",
        getattr(gateway_config, "model_pricing", {}),
    )


def extract_prompt(context: RequestContext) -> str:
    """Extract textual message content for difficulty classification."""

    prompt_parts = []

    for message in context.messages:
        content = message.get("content", "")

        if isinstance(content, str):
            prompt_parts.append(content)

        elif isinstance(content, list):
            for item in content:
                if isinstance(item, dict):
                    text = item.get("text")

                    if isinstance(text, str):
                        prompt_parts.append(text)

    return "\n".join(prompt_parts)


def resolve_model_candidates(
    context: RequestContext,
    loaded_config: Any,
) -> RequestContext:
    """
    Resolve a requested model into primary and fallback candidates.

    Supported behavior:
    - auto: classify the prompt and resolve the selected tier.
    - Configured aliases: resolve to primary and fallback models.
    - Configured direct model names: pass through unchanged.
    - Unknown aliases or models: raise ModelNotFoundError.
    """

    gateway_config = get_gateway_config(loaded_config)
    aliases = gateway_config.aliases
    pricing = get_model_pricing(loaded_config)

    requested_model = context.model_requested.strip()

    if not requested_model:
        raise ModelNotFoundError(
            "A model name or alias must be provided."
        )

    # Automatically select the fast or smart alias.
    if requested_model == "auto":
        prompt = extract_prompt(context)

        classifier = HeuristicClassifier()
        classification = classifier.classify(prompt)

        selected_tier = classification["tier"]
        score = classification["score"]
        reason = classification["reason"]

        # Config may map tiers to other aliases (route_by_difficulty).
        auto_routes = getattr(gateway_config, "auto_routes", None) or {}
        target_alias = auto_routes.get(selected_tier, selected_tier)

        context.decision_trace.append(
            f"auto→{selected_tier} "
            f"(score {score:.2f}, {reason})"
        )

        alias_config = aliases.get(target_alias)

        if alias_config is None:
            raise ModelNotFoundError(
                f"Automatic routing selected '{target_alias}', "
                "but that alias is not configured."
            )

    else:
        alias_config = aliases.get(requested_model)

    if alias_config is not None:
        candidates = [
            alias_config.primary_model,
            *alias_config.fallback_chain,
        ]

        context.decision_trace.append(
            f"alias '{alias_config.alias_name}' resolved"
        )

    else:
        if requested_model not in pricing:
            raise ModelNotFoundError(
                f"Model '{requested_model}' is not configured."
            )

        candidates = [requested_model]

    # Remove duplicates while preserving configured order.
    context.model_candidates = list(dict.fromkeys(candidates))

    if not context.model_candidates:
        raise ModelNotFoundError(
            f"No models configured for '{requested_model}'."
        )

    # The first candidate is always the initial model.
    context.model_resolved = context.model_candidates[0]

    context.decision_trace.append(
        "model candidates: "
        + ", ".join(context.model_candidates)
    )

    return context


__all__ = [
    "get_gateway_config",
    "get_model_pricing",
    "extract_prompt",
    "resolve_model_candidates",
]
