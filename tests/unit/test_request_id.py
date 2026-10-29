"""Tests for request ID generation, response headers, and JSON logging."""

import json
import logging
import re

from fastapi import FastAPI
from fastapi.testclient import TestClient

from prism.api.middleware import request_id_middleware
from prism.config.logging import JsonFormatter


def create_test_client() -> TestClient:
    """Create a minimal app using Prism's request ID middleware."""

    app = FastAPI()
    app.middleware("http")(request_id_middleware)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return TestClient(app)


def test_request_id_has_expected_format():
    """Every response should contain a correctly formatted request ID."""

    with create_test_client() as client:
        response = client.get("/health")

    assert response.status_code == 200

    request_id = response.headers["x-prism-request-id"]
    assert re.fullmatch(r"req_[0-9a-f]{12}", request_id)


def test_each_request_gets_a_unique_request_id():
    """Two separate requests should receive different request IDs."""

    with create_test_client() as client:
        first_response = client.get("/health")
        second_response = client.get("/health")

    first_id = first_response.headers["x-prism-request-id"]
    second_id = second_response.headers["x-prism-request-id"]

    assert first_id != second_id


def test_request_id_header_is_present():
    """The middleware should add the request ID header to the response."""

    with create_test_client() as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert "x-prism-request-id" in response.headers
    assert response.headers["x-prism-request-id"].startswith("req_")


def test_json_log_format_contains_required_fields():
    """Each formatted log line should be valid JSON with required fields."""

    record = logging.LogRecord(
        name="prism.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="Request received",
        args=(),
        exc_info=None,
    )
    record.request_id = "req_abc123def456"

    formatted = JsonFormatter().format(record)
    entry = json.loads(formatted)

    assert entry["timestamp"]
    assert entry["level"] == "INFO"
    assert entry["request_id"] == "req_abc123def456"
    assert entry["message"] == "Request received"
