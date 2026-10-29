"""Application composition root for the Prism LLM Gateway."""

import os

import uvicorn
from fastapi import FastAPI

from prism.adapters.openai_compatible import OpenAICompatibleProvider
from prism.adapters.system_clock import SystemClock
from prism.api.error_handler import prism_error_handler
from prism.api.routes import router
from prism.config.loader import load_configuration
from prism.config.settings import Settings
from prism.domain.errors import PrismError


def create_app() -> FastAPI:
    """Load configuration and wire application dependencies."""

    # 1. Load environment variables and application settings.
    settings = Settings.from_env()

    # 2. Load and validate the configuration files.
    config = load_configuration(settings.config_dir)

    # 3. Create the clock dependency.
    clock = SystemClock()

    # 4. Create the alpha provider adapter.
    alpha_provider_url = os.getenv(
        "ALPHA_PROVIDER_URL",
        "http://localhost:9001",
    )
    alpha_api_key = os.getenv(
        "ALPHA_PROVIDER_API_KEY",
        "mock-key",
    )

    provider_timeout = (
        settings.provider_timeout_seconds
        or config.gateway_config.provider_timeout_seconds
    )

    provider_adapter = OpenAICompatibleProvider(
        base_url=alpha_provider_url,
        api_key=alpha_api_key,
        timeout=provider_timeout,
    )

    # 5. Create the FastAPI application.
    application = FastAPI(title="Prism LLM Gateway")

    # Store dependencies and loaded configuration in the app.
    application.state.clock = clock
    application.state.provider_adapter = provider_adapter
    application.state.config = config

    # 6. Register routes and the global error handler.
    application.include_router(router)
    application.add_exception_handler(
        PrismError,
        prism_error_handler,
    )

    # Health endpoint for checking whether the gateway is running.
    @application.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return application


app = create_app()


def main() -> None:
    """Start the Prism HTTP server."""

    port = int(os.getenv("PORT", "3000"))

    uvicorn.run(
        "prism.main:app",
        host="0.0.0.0",
        port=port,
        reload=False,
    )


if __name__ == "__main__":
    main()
