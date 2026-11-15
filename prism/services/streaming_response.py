"""Application service for formatting and managing streaming responses."""

import asyncio
import json
import time
from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

from prism.config.logging import get_logger
from prism.domain.errors import UpstreamError
from prism.domain.models import ProviderResponse, RequestContext
from prism.services.observability.request_logging import RequestLoggingService
from prism.services.streaming import stream_response

logger = get_logger(__name__)


def _save_request_log(
    context: RequestContext,
    log_repository: Any,
    status_code: int,
    request_started_at: float,
    raw_api_key: str | None,
    request_logging_service: Any = None,
) -> None:
    """Save the completed streaming request log."""

    logging_service = (
        request_logging_service or RequestLoggingService()
    )

    logging_service.save(
        context=context,
        log_repository=log_repository,
        status_code=status_code,
        request_started_at=request_started_at,
        raw_api_key=raw_api_key,
    )


async def format_cached_streaming_body(
    context: RequestContext,
    log_repository: Any,
    request_started_at: float,
    raw_api_key: str | None = None,
    request_logging_service: Any = None,
) -> AsyncIterator[str]:
    """Replay a cached completion as one SSE content chunk."""

    status_code = 200

    try:
        result = context.provider_response

        if result is None:
            raise UpstreamError(
                "Cached streaming response is missing."
            )

        chunk = {
            "id": f"chatcmpl-{uuid4().hex}",
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": result.model,
            "choices": [
                {
                    "index": 0,
                    "delta": {
                        "role": "assistant",
                        "content": result.content,
                    },
                    "finish_reason": None,
                }
            ],
        }

        yield f"data: {json.dumps(chunk)}\n\n"
        yield "data: [DONE]\n\n"

    except (asyncio.CancelledError, GeneratorExit):
        status_code = 499

        context.decision_trace.append(
            "client disconnected during cached streaming"
        )

        raise

    except Exception:
        status_code = 502

        context.decision_trace.append(
            "cached streaming response failed"
        )

        raise

    finally:
        _save_request_log(
            context=context,
            log_repository=log_repository,
            status_code=status_code,
            request_started_at=request_started_at,
            raw_api_key=raw_api_key,
            request_logging_service=request_logging_service,
        )


async def format_streaming_body(
    provider_stream: AsyncIterator[dict[str, Any]],
    context: RequestContext,
    usage_repository: Any,
    loaded_config: Any,
    adapter: Any,
    log_repository: Any,
    request_started_at: float,
    cache_service: Any = None,
    raw_api_key: str | None = None,
    request_logging_service: Any = None,
) -> AsyncIterator[str]:
    """Forward SSE chunks, cache successful streams, and save request logs."""

    streaming_generator = stream_response(
        provider_stream=provider_stream,
        context=context,
        usage_repository=usage_repository,
        loaded_config=loaded_config,
        adapter=adapter,
    )

    status_code = 200
    client_disconnected = False
    response_parts: list[str] = []
    finish_reason: str | None = None
    stream_completed = False

    try:
        async for formatted_chunk in streaming_generator:
            is_done_event = False

            for line in formatted_chunk.splitlines():
                if not line.startswith("data:"):
                    continue

                data = line.removeprefix("data:").strip()

                try:
                    event = json.loads(data)
                except json.JSONDecodeError:
                    continue

                if not isinstance(event, dict):
                    continue

                error = event.get("error")

                if (
                    isinstance(error, dict)
                    and error.get("type") == "upstream_error"
                ):
                    status_code = 502

                choices = event.get("choices", [])

                if isinstance(choices, list):
                    for choice in choices:
                        if not isinstance(choice, dict):
                            continue

                        delta = choice.get("delta", {})

                        if isinstance(delta, dict):
                            content = delta.get("content")

                            if isinstance(content, str):
                                response_parts.append(content)

                        reason = choice.get("finish_reason")

                        if isinstance(reason, str):
                            finish_reason = reason

                if event.get("done") is True:
                    is_done_event = True
                    stream_completed = status_code == 200

            if is_done_event:
                yield "data: [DONE]\n\n"
                continue

            yield formatted_chunk

    except (asyncio.CancelledError, GeneratorExit):
        client_disconnected = True
        status_code = 499

        context.decision_trace.append(
            "client disconnected during streaming"
        )

        raise

    except Exception:
        status_code = 502

        context.decision_trace.append(
            "request failed: upstream_error"
        )

        logger.exception(
            "Streaming response failed",
            extra={"request_id": context.request_id},
        )

        raise

    finally:
        try:
            await streaming_generator.aclose()

        except Exception:
            logger.exception(
                "Failed to close streaming generator",
                extra={"request_id": context.request_id},
            )

            if status_code == 200:
                status_code = 502
                stream_completed = False

                context.decision_trace.append(
                    "stream cleanup failed"
                )

        finally:
            if client_disconnected:
                context.decision_trace.append(
                    "stream terminated by client disconnect"
                )

            if (
                stream_completed
                and cache_service is not None
                and context.key_config is not None
                and context.key_config.cache_enabled
                and context.stream_prompt_tokens >= 0
                and context.stream_completion_tokens >= 0
            ):
                try:
                    cached_response = ProviderResponse(
                        content="".join(response_parts),
                        model=context.model_resolved or "",
                        prompt_tokens=context.stream_prompt_tokens,
                        completion_tokens=context.stream_completion_tokens,
                        total_tokens=(
                            context.stream_prompt_tokens
                            + context.stream_completion_tokens
                        ),
                        finish_reason=finish_reason or "stop",
                        raw_response={"source": "stream"},
                    )

                    context.provider_response = cached_response
                    cache_service.store_response(context)

                except Exception:
                    logger.exception(
                        "Failed to store completed stream in semantic cache",
                        extra={"request_id": context.request_id},
                    )

            _save_request_log(
                context=context,
                log_repository=log_repository,
                status_code=status_code,
                request_started_at=request_started_at,
                raw_api_key=raw_api_key,
                request_logging_service=request_logging_service,
            )
