"""Structured JSON logging for Prism."""

import json
import logging
import os
import sys
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any


_request_id: ContextVar[str] = ContextVar(
    "prism_request_id",
    default="-",
)

_SAFE_EXTRA_FIELDS = {
    "method",
    "path",
    "status_code",
    "model",
    "duration_ms",
    "error_type",
}


def _configured_level() -> int:
    """Read the configured log level, defaulting to INFO."""

    level_name = os.getenv("PRISM_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    return level if isinstance(level, int) else logging.INFO


class RequestIdFilter(logging.Filter):
    """Attach the current request ID to each log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = _request_id.get()
        return True


class JsonFormatter(logging.Formatter):
    """Format each log record as one JSON object per line."""

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "timestamp": (
                datetime.fromtimestamp(record.created, timezone.utc)
                .isoformat()
                .replace("+00:00", "Z")
            ),
            "level": record.levelname,
            "request_id": getattr(record, "request_id", "-"),
            "message": record.getMessage(),
        }

        for field in _SAFE_EXTRA_FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                entry[field] = value

        # Include the exception type, but not its potentially sensitive text.
        if record.exc_info and record.exc_info[0]:
            entry["error_type"] = record.exc_info[0].__name__

        return json.dumps(entry, ensure_ascii=False)


def configure_logging() -> None:
    """Configure JSON logging to stdout."""

    level = _configured_level()
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    for handler in root_logger.handlers:
        if getattr(handler, "_prism_json_handler", False):
            handler.setLevel(level)
            return

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(RequestIdFilter())
    handler.setLevel(level)
    handler._prism_json_handler = True  # type: ignore[attr-defined]
    root_logger.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    """Return a logger configured for Prism's JSON logging."""

    configure_logging()
    return logging.getLogger(name)


def set_request_id(request_id: str):
    """Set the request ID for the current asynchronous context."""

    return _request_id.set(request_id)


def reset_request_id(token: Any) -> None:
    """Restore the previous request ID context."""

    _request_id.reset(token)


def get_uvicorn_logging_config() -> dict[str, Any]:
    """Configure Uvicorn's logs to use the JSON formatter."""

    level = _configured_level()

    return {
        "version": 1,
        "disable_existing_loggers": False,
        "filters": {
            "request_id": {
                "()": "prism.config.logging.RequestIdFilter",
            },
        },
        "formatters": {
            "json": {
                "()": "prism.config.logging.JsonFormatter",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",
                "formatter": "json",
                "filters": ["request_id"],
                "level": level,
            },
        },
        "root": {
            "handlers": ["console"],
            "level": level,
        },
        "loggers": {
            "uvicorn": {
                "handlers": ["console"],
                "level": level,
                "propagate": False,
            },
            "uvicorn.error": {
                "handlers": ["console"],
                "level": level,
                "propagate": False,
            },
            "uvicorn.access": {
                "handlers": ["console"],
                "level": level,
                "propagate": False,
            },
        },
    }
