"""Application entry point for Prism LLM Gateway."""

import os
from contextlib import asynccontextmanager
from typing import Any

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from prism.adapters.bow_embedder import BowEmbedder
from prism.adapters.openai_compatible import OpenAICompatibleProvider
from prism.adapters.sqlite_repos import (
    CacheRepository,
    SQLiteKeyRepository,
    SQLiteLogRepository,
    SQLiteUsageRepository,
    init_database,
)
from prism.adapters.system_clock import SystemClock
from prism.api.admin import router as admin_router
from prism.api.error_handler import (
    prism_error_handler,
    unexpected_error_handler,
)
from prism.api.middleware import request_id_middleware
from prism.api.routes import router
from prism.config.loader import load_configuration, provider_for_model
from prism.config.logging import (
    configure_logging,
    get_logger,
    get_uvicorn_logging_config,
)
from prism.config.settings import Settings
from prism.domain.errors import PrismError
from prism.domain.limiter import TokenBucketRateLimiter
from prism.services.cache import CacheService
from prism.services.pipeline import Pipeline

logger = get_logger(__name__)


def _build_provider(
    settings: Settings,
    base_url: str,
    api_key: str,
) -> OpenAICompatibleProvider:
    """Create an OpenAI-compatible provider adapter."""

    return OpenAICompatibleProvider(
        base_url=base_url,
        api_key=api_key,
        connect_timeout=settings.connect_timeout_seconds,
        request_timeout=settings.provider_timeout_seconds,
    )


async def _close_provider_adapters(
    adapters: list[OpenAICompatibleProvider],
) -> None:
    """Close every unique provider adapter exactly once."""

    unique_adapters = {
        id(adapter): adapter
        for adapter in adapters
    }

    for adapter in unique_adapters.values():
        close = getattr(adapter, "aclose", None)

        if close is None:
            continue

        try:
            await close()
        except Exception:
            logger.exception(
                "Failed to close provider adapter",
                extra={
                    "provider": getattr(
                        adapter,
                        "name",
                        adapter.__class__.__name__,
                    )
                },
            )


async def _initialize_providers(
    settings: Settings,
    loaded_config: Any,
) -> tuple[
    dict[str, OpenAICompatibleProvider],
    dict[str, str],
    OpenAICompatibleProvider,
    list[str],
    list[OpenAICompatibleProvider],
]:
    """Initialize configured providers and map them to available models."""

    gateway_config = loaded_config.gateway_config
    provider_names: dict[str, str] = {}
    initialized_adapters: list[OpenAICompatibleProvider] = []

    try:
        # Configuration-driven provider initialization.
        if gateway_config.providers:
            registry = {}

            for provider in gateway_config.providers:
                adapter = _build_provider(
                    settings,
                    provider.base_url,
                    provider.api_key,
                )

                registry[provider.name] = adapter
                initialized_adapters.append(adapter)

            provider_adapters = {}

            for model_name in loaded_config.model_pricing:
                provider = provider_for_model(
                    model_name,
                    gateway_config.providers,
                )

                if provider is not None:
                    provider_adapters[model_name] = registry[
                        provider.name
                    ]
                    provider_names[model_name] = provider.name

            default_provider = next(iter(registry.values()))

            return (
                provider_adapters,
                provider_names,
                default_provider,
                list(registry),
                initialized_adapters,
            )

        # Legacy environment-based provider initialization.
        if not settings.openai_api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is missing. Add it to your .env file."
            )

        if not settings.groq_api_key:
            raise RuntimeError(
                "GROQ_API_KEY is missing. Add it to your .env file."
            )

        openai_provider = _build_provider(
            settings,
            settings.openai_base_url,
            settings.openai_api_key,
        )
        initialized_adapters.append(openai_provider)

        groq_provider = _build_provider(
            settings,
            settings.groq_base_url,
            settings.groq_api_key,
        )
        initialized_adapters.append(groq_provider)

        provider_adapters = {
            "gpt-4o-mini": openai_provider,
            "llama-3.3-70b-versatile": groq_provider,
        }

        provider_names = {
            "gpt-4o-mini": "openai",
            "llama-3.3-70b-versatile": "groq",
        }

        return (
            provider_adapters,
            provider_names,
            openai_provider,
            ["openai", "groq"],
            initialized_adapters,
        )

    except Exception:
        # Close adapters created before initialization failed.
        await _close_provider_adapters(initialized_adapters)
        raise


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize application dependencies and clean up on shutdown."""

    provider_adapters_for_cleanup: list[
        OpenAICompatibleProvider
    ] = []

    try:
        settings = Settings.from_env()
        loaded_config = load_configuration()

        # Initialize database and repositories.
        database_path = settings.db_path
        init_database(database_path)

        key_repository = SQLiteKeyRepository(database_path)
        key_repository.seed_keys(loaded_config.seed_keys)

        usage_repository = SQLiteUsageRepository(database_path)
        log_repository = SQLiteLogRepository(database_path)

        # Initialize semantic cache.
        cache_repository = CacheRepository(database_path)
        cache_embedder = BowEmbedder()

        cache_service = CacheService(
            embedder=cache_embedder,
            repository=cache_repository,
        )

        # Initialize shared infrastructure services.
        clock = SystemClock()
        rate_limiter = TokenBucketRateLimiter(clock)

        # Initialize provider adapters.
        (
            provider_adapters,
            provider_names,
            default_provider,
            provider_labels,
            provider_adapters_for_cleanup,
        ) = await _initialize_providers(settings, loaded_config)

        # Register application dependencies.
        app.state.loaded_config = loaded_config
        app.state.settings = settings

        app.state.key_repository = key_repository
        app.state.usage_repository = usage_repository
        app.state.log_repository = log_repository
        app.state.database_path = database_path

        app.state.cache_repository = cache_repository
        app.state.cache_embedder = cache_embedder
        app.state.cache_service = cache_service

        app.state.pipeline = Pipeline()
        app.state.clock = clock
        app.state.rate_limiter = rate_limiter

        app.state.provider_adapters = provider_adapters
        app.state.provider_names = provider_names

        # Backward compatibility for existing tests.
        app.state.provider_adapter = default_provider

        app.state.admin_token = settings.admin_token

        if not settings.admin_token:
            logger.warning(
                "PRISM_ADMIN_TOKEN is not set; admin endpoints will reject all requests."
            )

        logger.info(
            "Prism initialized successfully",
            extra={
                "database_path": database_path,
                "providers": provider_labels,
                "max_retries": settings.max_retries,
                "connect_timeout": settings.connect_timeout_seconds,
                "request_timeout": settings.provider_timeout_seconds,
                "semantic_cache_enabled": True,
            },
        )

        yield

    finally:
        logger.info("Prism application shutting down")

        await _close_provider_adapters(
            provider_adapters_for_cleanup
        )


def create_app() -> FastAPI:
    """Create and configure the Prism FastAPI application."""

    application = FastAPI(
        title="Prism LLM Gateway",
        lifespan=lifespan,
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=[
            "x-prism-provider",
            "x-prism-cache",
            "x-prism-fallback",
            "x-prism-cost-usd",
            "x-prism-request-id",
        ],
    )

    application.middleware("http")(request_id_middleware)

    application.add_exception_handler(
        PrismError,
        prism_error_handler,
    )

    application.add_exception_handler(
        Exception,
        unexpected_error_handler,
    )

    application.include_router(router)
    application.include_router(admin_router)

    return application


app = create_app()


if __name__ == "__main__":
    configure_logging()

    port = int(os.getenv("PORT", os.getenv("PRISM_PORT", "8000")))

    uvicorn.run(
        "prism.main:app",
        host="0.0.0.0",
        port=port,
        log_config=get_uvicorn_logging_config(),
        reload=False,
    )
