"""Application entry point for Prism LLM Gateway."""

import os
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse

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
from prism.config.logging import (
    configure_logging,
    get_logger,
    get_uvicorn_logging_config,
)
from prism.config.settings import Settings
from prism.config.loader import load_configuration, provider_for_model
from prism.domain.errors import PrismError
from prism.domain.limiter import TokenBucketRateLimiter
from prism.services.cache import CacheService
from prism.services.pipeline import Pipeline


logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load application settings and gateway configuration.
    settings = Settings.from_env()
    loaded_config = load_configuration()

    # Initialize database using the path from typed Settings.
    database_path = settings.db_path

    init_database(database_path)

    key_repository = SQLiteKeyRepository(database_path)
    key_repository.seed_keys(loaded_config.seed_keys)

    usage_repository = SQLiteUsageRepository(database_path)
    log_repository = SQLiteLogRepository(database_path)

    # Initialize semantic cache components.
    cache_repository = CacheRepository(database_path)
    cache_embedder = BowEmbedder()

    cache_service = CacheService(
        embedder=cache_embedder,
        repository=cache_repository,
    )

    # Initialize shared services.
    clock = SystemClock()
    rate_limiter = TokenBucketRateLimiter(clock)

    gateway_config = loaded_config.gateway_config

    def build_provider(base_url: str, api_key: str) -> OpenAICompatibleProvider:
        return OpenAICompatibleProvider(
            base_url=base_url,
            api_key=api_key,
            connect_timeout=settings.connect_timeout_seconds,
            request_timeout=settings.provider_timeout_seconds,
        )

    provider_names: dict[str, str] = {}

    if gateway_config.providers:
        # Config-driven provider registry (e.g. starter mocks alpha/beta).
        registry = {
            provider.name: build_provider(provider.base_url, provider.api_key)
            for provider in gateway_config.providers
        }

        provider_adapters = {}
        for model_name in loaded_config.model_pricing:
            provider = provider_for_model(
                model_name, gateway_config.providers
            )
            if provider is not None:
                provider_adapters[model_name] = registry[provider.name]
                provider_names[model_name] = provider.name

        default_provider = next(iter(registry.values()))
        provider_labels = list(registry)

    else:
        # Legacy setup: real OpenAI + Groq credentials from the environment.
        if not settings.openai_api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is missing. Add it to your .env file."
            )

        if not settings.groq_api_key:
            raise RuntimeError(
                "GROQ_API_KEY is missing. Add it to your .env file."
            )

        openai_provider = build_provider(
            settings.openai_base_url, settings.openai_api_key
        )
        groq_provider = build_provider(
            settings.groq_base_url, settings.groq_api_key
        )

        # Map model names to their respective provider adapters.
        provider_adapters = {
            "gpt-4o-mini": openai_provider,
            "llama-3.3-70b-versatile": groq_provider,
        }
        default_provider = openai_provider
        provider_labels = ["openai", "groq"]

    # Store application dependencies.
    app.state.loaded_config = loaded_config
    app.state.settings = settings

    app.state.key_repository = key_repository
    app.state.usage_repository = usage_repository
    app.state.log_repository = log_repository
    app.state.database_path = database_path

    # Semantic cache dependencies.
    app.state.cache_repository = cache_repository
    app.state.cache_embedder = cache_embedder
    app.state.cache_service = cache_service

    app.state.pipeline = Pipeline()
    app.state.clock = clock
    app.state.rate_limiter = rate_limiter

    # Multi-provider configuration.
    app.state.provider_adapters = provider_adapters
    app.state.provider_names = provider_names

    # Backward compatibility for existing tests.
    app.state.provider_adapter = default_provider

    # Admin API token — read from Settings so it is validated at startup.
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

    logger.info("Prism application shutting down")
    for adapter in provider_adapters.values():
        if hasattr(adapter, "aclose"):
            await adapter.aclose()


app = FastAPI(
    title="Prism LLM Gateway",
    lifespan=lifespan,
)


# Health check endpoint for Docker and monitoring.
@app.get("/health", tags=["Health"])
async def health_check():
    """Return application health status."""
    return {"status": "ok"}


# Register CORS middleware for console UI and external callers.
app.add_middleware(
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
        "x-request-id",
    ],
)

# Register request ID middleware.
app.middleware("http")(request_id_middleware)

# Register centralized exception handlers.
app.add_exception_handler(
    PrismError,
    prism_error_handler,
)

app.add_exception_handler(
    Exception,
    unexpected_error_handler,
)

# Register API routes.
app.include_router(router)
app.include_router(admin_router)

# Serve the ops console as a static file at /console and root /.
_CONSOLE_DIR = Path(__file__).resolve().parent.parent / "console"
_CONSOLE_HTML = _CONSOLE_DIR / "index.html"


@app.get("/", include_in_schema=False)
@app.get("/console", tags=["Console"], include_in_schema=False)
@app.get("/console/", include_in_schema=False)
async def ops_console():
    """Serve the static ops console HTML page."""
    if _CONSOLE_HTML.is_file():
        return HTMLResponse(content=_CONSOLE_HTML.read_text(encoding="utf-8"))
    return HTMLResponse(
        content="<h1>console/index.html not found on disk</h1>",
        status_code=404,
    )


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
