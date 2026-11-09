"""OpenAI-compatible mock provider for Prism integration testing."""

import argparse
import asyncio
import json
import time
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse


def create_app(provider_name: str) -> FastAPI:
    app = FastAPI(title=f"Prism {provider_name} Mock Provider")

    @app.get("/health")
    async def health():
        return {
            "status": "ok",
            "provider": provider_name,
        }

    @app.post("/v1/chat/completions")
    async def chat_completions(request: Request):
        authorization = request.headers.get("Authorization", "")

        if not authorization.startswith("Bearer "):
            return JSONResponse(
                status_code=401,
                content={
                    "error": {
                        "message": "Missing bearer token"
                    }
                },
            )

        body: dict[str, Any] = await request.json()

        messages = body.get("messages", [])
        model = body.get("model", f"{provider_name}-mock-model")
        stream = body.get("stream", False)

        prompt_text = " ".join(
            str(message.get("content", ""))
            for message in messages
        )

        content = (
            f"Mock response from {provider_name}: "
            "Received your message successfully."
        )

        prompt_tokens = max(1, len(prompt_text.split()))
        completion_tokens = max(1, len(content.split()))
        total_tokens = prompt_tokens + completion_tokens

        if not stream:
            return {
                "id": f"chatcmpl-{provider_name}-mock",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": model,
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": content,
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": total_tokens,
                },
            }

        async def generate_events():
            response_words = content.split()

            for word in response_words:
                chunk = {
                    "id": f"chatcmpl-{provider_name}-mock",
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": model,
                    "choices": [
                        {
                            "index": 0,
                            "delta": {
                                "content": word + " "
                            },
                            "finish_reason": None,
                        }
                    ],
                }

                yield f"data: {json.dumps(chunk)}\n\n"
                await asyncio.sleep(0.05)

            usage_event = {
                "id": f"chatcmpl-{provider_name}-mock",
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": model,
                "choices": [
                    {
                        "index": 0,
                        "delta": {},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": total_tokens,
                },
            }

            yield f"data: {json.dumps(usage_event)}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(
            generate_events(),
            media_type="text/event-stream",
        )

    return app


def main():
    parser = argparse.ArgumentParser(
        description="Run an OpenAI-compatible mock provider."
    )

    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--name", type=str, required=True)

    args = parser.parse_args()

    import uvicorn

    uvicorn.run(
        create_app(args.name),
        host="0.0.0.0",
        port=args.port,
    )


if __name__ == "__main__":
    main()
