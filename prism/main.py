"""Application entry point for Prism LLM Gateway."""

import os
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from prism.adapters.openai_compatible import OpenAICompatibleProvider
from prism.adapters.sqlite_repos import (
    SQLiteKeyRepository,
    SQLiteLogRepository,
    SQLiteUsageRepository,
    init_database,
)
from prism.adapters.system_clock import SystemClock
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
from prism.config.settings import PROJECT_ROOT, Settings
from prism.config.loader import load_configuration
from prism.domain.errors import PrismError
from prism.domain.limiter import TokenBucketRateLimiter
from prism.services.pipeline import Pipeline


logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load application settings and gateway configuration.
    settings = Settings.from_env()
    loaded_config = load_configuration()

    # Initialize database.
    database_path = os.getenv(
        "PRISM_DB_PATH",
        str(PROJECT_ROOT / "data" / "prism.db"),
    )

    init_database(database_path)

    key_repository = SQLiteKeyRepository(database_path)
    key_repository.seed_keys(loaded_config.seed_keys)

    usage_repository = SQLiteUsageRepository(database_path)
    log_repository = SQLiteLogRepository(database_path)

    # Initialize shared services.
    clock = SystemClock()
    rate_limiter = TokenBucketRateLimiter(clock)

    # Validate provider credentials.
    if not settings.openai_api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is missing. Add it to your .env file."
        )

    if not settings.groq_api_key:
        raise RuntimeError(
            "GROQ_API_KEY is missing. Add it to your .env file."
        )

    # Initialize OpenAI provider.
    openai_provider = OpenAICompatibleProvider(
        base_url=settings.openai_base_url,
        api_key=settings.openai_api_key,
        connect_timeout=settings.connect_timeout_seconds,
        request_timeout=settings.provider_timeout_seconds,
    )

    # Initialize Groq provider.
    groq_provider = OpenAICompatibleProvider(
        base_url=settings.groq_base_url,
        api_key=settings.groq_api_key,
        connect_timeout=settings.connect_timeout_seconds,
        request_timeout=settings.provider_timeout_seconds,
    )

    # Map model names to their respective provider adapters.
    provider_adapters = {
        "gpt-4o-mini": openai_provider,
        "llama-3.3-70b-versatile": groq_provider,
    }

    # Store application dependencies.
    app.state.loaded_config = loaded_config
    app.state.settings = settings

    app.state.key_repository = key_repository
    app.state.usage_repository = usage_repository
    app.state.log_repository = log_repository
    app.state.database_path = database_path

    app.state.pipeline = Pipeline()
    app.state.clock = clock
    app.state.rate_limiter = rate_limiter

    # New multi-provider configuration.
    app.state.provider_adapters = provider_adapters

    # Keep the old single-provider reference for existing tests
    # and backward compatibility.
    app.state.provider_adapter = openai_provider

    logger.info(
        "Prism initialized successfully",
        extra={
            "database_path": database_path,
            "providers": ["openai", "groq"],
            "max_retries": settings.max_retries,
            "connect_timeout": settings.connect_timeout_seconds,
            "request_timeout": settings.provider_timeout_seconds,
        },
    )

    yield

    logger.info("Prism application shutting down")


app = FastAPI(
    title="Prism LLM Gateway",
    lifespan=lifespan,
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


if __name__ == "__main__":
    configure_logging()

    uvicorn.run(
        "prism.main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "3000")),
        log_config=get_uvicorn_logging_config(),
        reload=True,
    )
