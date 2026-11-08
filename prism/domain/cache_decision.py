"""Pure domain decisions for semantic caching."""

from prism.domain.models import RequestContext


TIME_SENSITIVE_KEYWORDS = (
    "now",
    "today",
    "latest",
    "current",
    "right now",
    "this moment",
)


def is_cacheable(request_context: RequestContext) -> bool:
    """
    Determine whether a request is eligible for semantic caching.

    A request is not cacheable when:
    - No virtual key is associated with the request.
    - Caching is disabled for the virtual key.
    - The prompt contains time-sensitive keywords.
    - The provider response represents an error.
    """

    key_config = request_context.key_config

    if key_config is None or not key_config.cache_enabled:
        return False

    # Combine message content to inspect the complete prompt.
    prompt_parts = []

    for message in request_context.messages:
        content = message.get("content", "")

        if isinstance(content, str):
            prompt_parts.append(content)

        elif isinstance(content, list):
            for item in content:
                if isinstance(item, dict):
                    text = item.get("text")

                    if isinstance(text, str):
                        prompt_parts.append(text)

    prompt = " ".join(prompt_parts).lower()

    if any(
        keyword in prompt
        for keyword in TIME_SENSITIVE_KEYWORDS
    ):
        return False

    # Do not cache unsuccessful provider responses.
    if request_context.provider_response is None:
        return False

    if request_context.provider_response.finish_reason == "error":
        return False

    return True


def is_hit(similarity_score: float, threshold: float) -> bool:
    """
    Determine whether a similarity score qualifies as a cache hit.

    A score equal to or greater than the threshold is a hit.
    """

    if not 0.0 <= similarity_score <= 1.0:
        raise ValueError("Similarity score must be between 0 and 1.")

    if not 0.0 <= threshold <= 1.0:
        raise ValueError("Threshold must be between 0 and 1.")

    return similarity_score >= threshold


__all__ = [
    "TIME_SENSITIVE_KEYWORDS",
    "is_cacheable",
    "is_hit",
]
