"""Streaming proxy service for the Prism LLM Gateway."""

import asyncio
import json
import os
from collections.abc import AsyncIterator
from typing import Any

from prism.config.logging import get_logger
from prism.domain.cost import CostCalculator
from prism.domain.errors import UpstreamError
from prism.domain.models import GatewayConfig, RequestContext
from prism.ports.repositories import UsageRepository

logger = get_logger(__name__)

DEFAULT_STREAM_IDLE_TIMEOUT = 10.0


def get_stream_idle_timeout() -> float:
    """Read the stream idle timeout from the environment."""

    value = os.getenv(
        "PRISM_STREAM_IDLE_TIMEOUT",
        str(DEFAULT_STREAM_IDLE_TIMEOUT),
    )

    try:
        timeout = float(value)

        if timeout <= 0:
            raise ValueError

        return timeout

    except ValueError:
        logger.warning(
            "Invalid PRISM_STREAM_IDLE_TIMEOUT; using default",
            extra={"configured_value": value},
        )

        return DEFAULT_STREAM_IDLE_TIMEOUT


def format_sse_chunk(chunk: dict[str, Any]) -> str:
    """Format a provider event as an SSE data message."""

    return f"data: {json.dumps(chunk)}\n\n"


def format_sse_error(
    message: str = "Provider disconnected",
) -> str:
    """Format an upstream failure as an SSE error event."""

    return (
        "event: error\n"
        f"data: {json.dumps({
            'error': {
                'message': message,
                'type': 'upstream_error',
            }
        })}\n\n"
    )


async def close_provider_stream(
    provider_stream: AsyncIterator[dict[str, Any]],
    context: RequestContext,
) -> None:
    """Close the upstream provider iterator when possible."""

    close_method = getattr(provider_stream, "aclose", None)

    if close_method is None:
        return

    try:
        await close_method()

    except Exception:
        logger.warning(
            "Could not close provider stream cleanly",
            extra={"request_id": context.request_id},
            exc_info=True,
        )


def update_stream_usage(
    usage: dict[str, int],
    context: RequestContext,
) -> None:
    """
    Update token usage in the request context.

    This makes observed usage available to request logging even
    when the stream terminates before normal completion.
    """

    prompt_tokens = usage.get("prompt_tokens", 0)
    completion_tokens = usage.get("completion_tokens", 0)

    context.stream_prompt_tokens = prompt_tokens
    context.stream_completion_tokens = completion_tokens


async def record_stream_usage(
    usage: dict[str, int] | None,
    context: RequestContext,
    usage_repository: UsageRepository,
    loaded_config: GatewayConfig,
    adapter: Any,
    completed: bool,
) -> None:
    """Calculate and persist observed usage, including partial usage."""

    # Use adapter usage as a fallback if no event contained usage.
    adapter_usage = getattr(adapter, "last_stream_usage", None)

    if usage is None and isinstance(adapter_usage, dict):
        usage = adapter_usage

        # Also preserve fallback usage in the request context.
        update_stream_usage(usage, context)

    if usage is None:
        logger.warning(
            "Streaming ended without provider usage information",
            extra={
                "request_id": context.request_id,
                "completed": completed,
            },
        )
        return

    if context.key_config is None:
        raise UpstreamError(
            "Authenticated key configuration is missing."
        )

    model = context.model_resolved or context.model_requested

    pricing = loaded_config.model_pricing.get(model)

    if pricing is None:
        raise UpstreamError(
            f"No pricing configured for model '{model}'."
        )

    prompt_tokens = usage.get("prompt_tokens", 0)
    completion_tokens = usage.get("completion_tokens", 0)

    total_tokens = usage.get(
        "total_tokens",
        prompt_tokens + completion_tokens,
    )

    cost = CostCalculator.calculate(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        model_pricing=pricing,
    )

    context.cost_usd = cost

    month = context.start_time.strftime("%Y-%m")

    usage_repository.record_usage(
        key_hash=context.key_config.key_hash,
        month=month,
        cost=cost,
        tokens=total_tokens,
        is_cache_hit=context.cache_status == "hit",
    )

    context.decision_trace.append(
        f"stream usage recorded: {total_tokens} tokens"
    )

    context.decision_trace.append(
        f"cost: ${cost:.6f}"
    )


async def stream_response(
    provider_stream: AsyncIterator[dict[str, Any]],
    context: RequestContext,
    usage_repository: UsageRepository,
    loaded_config: GatewayConfig,
    adapter: Any,
) -> AsyncIterator[str]:
    """
    Forward provider events immediately while observing usage.

    Provider failures produce an SSE error event and terminate the
    stream. The gateway never switches providers after streaming
    has started.

    Usage observed before a failure or client disconnect is persisted.
    The upstream iterator is closed when the downstream stream ends.
    """

    usage: dict[str, int] | None = None
    completed = False
    error_message: str | None = None
    client_disconnected = False

    idle_timeout = get_stream_idle_timeout()

    try:
        while True:
            try:
                chunk = await asyncio.wait_for(
                    anext(provider_stream),
                    timeout=idle_timeout,
                )

            except StopAsyncIteration:
                break

            except TimeoutError:
                error_message = (
                    f"Provider stream idle timeout after "
                    f"{idle_timeout:g} seconds."
                )

                context.decision_trace.append(
                    "upstream_error: stream idle timeout"
                )

                logger.error(
                    "upstream_error",
                    extra={
                        "request_id": context.request_id,
                        "error_type": "upstream_error",
                        "idle_timeout_seconds": idle_timeout,
                    },
                )

                yield format_sse_error(error_message)
                break

            # Inspect usage before forwarding the event. This ensures
            # usage is captured even if the client disconnects after
            # receiving this event.
            chunk_usage = chunk.get("usage")

            if isinstance(chunk_usage, dict):
                prompt_tokens = chunk_usage.get(
                    "prompt_tokens",
                    0,
                )

                completion_tokens = chunk_usage.get(
                    "completion_tokens",
                    0,
                )

                usage = {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": chunk_usage.get(
                        "total_tokens",
                        prompt_tokens + completion_tokens,
                    ),
                }

                # Persist observed token counts in RequestContext
                # immediately, not only during final usage recording.
                update_stream_usage(usage, context)

            if chunk.get("done") is True:
                completed = True

            # Forward the event immediately.
            yield format_sse_chunk(chunk)

    except asyncio.CancelledError:
        # A downstream cancellation commonly means the client
        # disconnected while the stream was active.
        client_disconnected = True

        context.decision_trace.append(
            "stream cancelled: client disconnected or request cancelled"
        )

        logger.info(
            "Streaming cancelled",
            extra={
                "request_id": context.request_id,
                "usage_observed": usage is not None,
            },
        )

        raise

    except GeneratorExit:
        # The downstream consumer explicitly closed this generator.
        client_disconnected = True

        context.decision_trace.append(
            "stream closed by downstream consumer"
        )

        logger.info(
            "Streaming consumer disconnected",
            extra={
                "request_id": context.request_id,
                "usage_observed": usage is not None,
            },
        )

        raise

    except Exception:
        # Do not expose internal provider exception details to clients.
        error_message = "Provider disconnected"

        context.decision_trace.append(
            "upstream_error: provider disconnected"
        )

        logger.exception(
            "upstream_error",
            extra={
                "request_id": context.request_id,
                "error_type": "upstream_error",
            },
        )

        # Send an SSE error event instead of raising the provider
        # exception after response headers have already been sent.
        yield format_sse_error("Provider disconnected")

    finally:
        # Always stop reading from the provider when the downstream
        # stream finishes, fails, or is cancelled.
        await close_provider_stream(
            provider_stream,
            context,
        )

        try:
            await record_stream_usage(
                usage=usage,
                context=context,
                usage_repository=usage_repository,
                loaded_config=loaded_config,
                adapter=adapter,
                completed=completed,
            )

        except Exception:
            logger.exception(
                "Could not record streaming usage",
                extra={"request_id": context.request_id},
            )

        finally:
            logger.info(
                "Streaming request finished",
                extra={
                    "request_id": context.request_id,
                    "model": (
                        context.model_resolved
                        or context.model_requested
                    ),
                    "cost_usd": context.cost_usd,
                    "prompt_tokens": context.stream_prompt_tokens,
                    "completion_tokens": context.stream_completion_tokens,
                    "completed": completed,
                    "client_disconnected": client_disconnected,
                    "error_type": (
                        "upstream_error"
                        if error_message is not None
                        else None
                    ),
                },
            )
