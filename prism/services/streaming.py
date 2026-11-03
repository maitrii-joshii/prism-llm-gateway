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


def format_sse_error(message: str) -> str:
    """Format an upstream error as an SSE error event."""

    return (
        "event: error\n"
        f"data: {json.dumps({
            'error': {
                'message': message,
                'type': 'upstream_error',
            }
        })}\n\n"
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

    Abort the stream when the provider does not send a new chunk
    within the configured idle timeout.

    Usage is inspected before forwarding each event so that a client
    disconnect immediately after receiving a usage event cannot prevent
    Prism from capturing that usage.
    """

    usage: dict[str, int] | None = None
    completed = False
    error_message: str | None = None
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
                        "error": error_message,
                        "idle_timeout_seconds": idle_timeout,
                    },
                )

                yield format_sse_error(error_message)
                break

            # Inspect usage BEFORE yielding to the client.
            chunk_usage = chunk.get("usage")

            if isinstance(chunk_usage, dict):
                prompt_tokens = chunk_usage.get("prompt_tokens", 0)
                completion_tokens = chunk_usage.get(
                    "completion_tokens", 0
                )

                usage = {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": chunk_usage.get(
                        "total_tokens",
                        prompt_tokens + completion_tokens,
                    ),
                }

            if chunk.get("done") is True:
                completed = True

            # Forward the event immediately.
            yield format_sse_chunk(chunk)

    except asyncio.CancelledError:
        raise

    except Exception as exc:
        error_message = str(exc)

        logger.exception(
            "Streaming request failed",
            extra={"request_id": context.request_id},
        )

        raise

    finally:
        # Use adapter usage as a fallback if no event contained usage.
        adapter_usage = getattr(adapter, "last_stream_usage", None)

        if usage is None and isinstance(adapter_usage, dict):
            usage = adapter_usage

        try:
            if usage is not None:
                if context.key_config is None:
                    raise UpstreamError(
                        "Authenticated key configuration is missing."
                    )

                model = (
                    context.model_resolved
                    or context.model_requested
                )

                pricing = loaded_config.model_pricing.get(model)

                if pricing is None:
                    raise UpstreamError(
                        f"No pricing configured for model '{model}'."
                    )

                prompt_tokens = usage["prompt_tokens"]
                completion_tokens = usage["completion_tokens"]
                total_tokens = usage["total_tokens"]

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
                    f"cost: ${cost:.6f}"
                )

            else:
                logger.warning(
                    "Streaming ended without provider usage information",
                    extra={
                        "request_id": context.request_id,
                        "completed": completed,
                    },
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
                    "completed": completed,
                    "error": error_message,
                },
            )
