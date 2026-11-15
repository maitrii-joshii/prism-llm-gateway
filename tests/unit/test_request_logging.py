"""Unit tests for RequestLoggingService."""

from datetime import datetime, timezone

import pytest

from prism.domain.models import ProviderResponse, RequestContext
from prism.domain.security import hash_api_key
from prism.services.observability.request_logging import (
    RequestLoggingService,
)
from prism.services.metrics import metrics_registry


class FakeLogRepository:
    """In-memory log repository for testing."""

    def __init__(self):
        self.logs = []

    def save_log(self, log_entry):
        self.logs.append(log_entry)


@pytest.fixture
def service():
    return RequestLoggingService()


@pytest.fixture
def context():
    return RequestContext(
        request_id="req_test123",
        model_requested="fast",
        model_resolved="gpt-4o-mini",
        provider_name="openai",
        start_time=datetime.now(timezone.utc),
        decision_trace=["request validation ok"],
        cost_usd=0.002,
        retry_count=1,
        fallback_used=False,
    )


@pytest.fixture
def mock_metrics(monkeypatch):
    """Capture Prometheus metric calls without changing global metrics."""

    increment_calls = []
    duration_calls = []

    def fake_increment_counter(name, value, labels=None):
        increment_calls.append((name, value, labels))

    def fake_observe_duration(name, value):
        duration_calls.append((name, value))

    monkeypatch.setattr(
        metrics_registry,
        "increment_counter",
        fake_increment_counter,
    )
    monkeypatch.setattr(
        metrics_registry,
        "observe_duration",
        fake_observe_duration,
    )

    return {
        "increment_calls": increment_calls,
        "duration_calls": duration_calls,
    }


def test_successful_request_logging(
    service,
    context,
    mock_metrics,
):
    """A successful request creates and saves a log entry."""

    repository = FakeLogRepository()

    context.provider_response = ProviderResponse(
        content="Hello",
        model="gpt-4o-mini",
        prompt_tokens=10,
        completion_tokens=5,
        total_tokens=15,
        finish_reason="stop",
        raw_response={"test": True},
    )

    service.save(
        context=context,
        log_repository=repository,
        status_code=200,
        request_started_at=0.0,
    )

    assert len(repository.logs) == 1

    log_entry = repository.logs[0]

    assert log_entry.request_id == "req_test123"
    assert log_entry.model_requested == "fast"
    assert log_entry.model_resolved == "gpt-4o-mini"
    assert log_entry.provider == "openai"
    assert log_entry.status_code == 200
    assert log_entry.prompt_tokens == 10
    assert log_entry.completion_tokens == 5
    assert log_entry.cost_usd == 0.002
    assert log_entry.retries == 1
    assert log_entry.fallback_used is False
    assert "request validation ok" in log_entry.decision_trace

    metric_names = [
        call[0]
        for call in mock_metrics["increment_calls"]
    ]

    assert "prism_requests_total" in metric_names
    assert "prism_tokens_total" in metric_names
    assert "prism_cost_usd_total" in metric_names

    assert len(mock_metrics["duration_calls"]) == 1


def test_api_key_is_hashed_before_logging(
    service,
    context,
    mock_metrics,
):
    """The raw API key is never stored in the request log."""

    repository = FakeLogRepository()
    raw_api_key = "prism_test_secret_key"

    service.save(
        context=context,
        log_repository=repository,
        status_code=200,
        request_started_at=0.0,
        raw_api_key=raw_api_key,
    )

    log_entry = repository.logs[0]

    assert log_entry.key_hash == hash_api_key(raw_api_key)
    assert log_entry.key_hash != raw_api_key


def test_streaming_token_counts_are_logged(
    service,
    context,
    mock_metrics,
):
    """Streaming token counts are used without a provider response."""

    repository = FakeLogRepository()

    context.stream_prompt_tokens = 20
    context.stream_completion_tokens = 15

    service.save(
        context=context,
        log_repository=repository,
        status_code=200,
        request_started_at=0.0,
    )

    log_entry = repository.logs[0]

    assert log_entry.prompt_tokens == 20
    assert log_entry.completion_tokens == 15


def test_missing_log_repository_does_not_raise(
    service,
    context,
    mock_metrics,
):
    """Missing repository is handled without raising an exception."""

    service.save(
        context=context,
        log_repository=None,
        status_code=200,
        request_started_at=0.0,
    )

    assert mock_metrics["increment_calls"] == []
    assert mock_metrics["duration_calls"] == []


def test_repository_failure_is_handled(
    service,
    context,
    mock_metrics,
):
    """A repository failure does not propagate to the caller."""

    class FailingLogRepository:
        def save_log(self, log_entry):
            raise RuntimeError("Database unavailable")

    service.save(
        context=context,
        log_repository=FailingLogRepository(),
        status_code=200,
        request_started_at=0.0,
    )

    # Metrics are not recorded if saving the log fails.
    assert mock_metrics["increment_calls"] == []
    assert mock_metrics["duration_calls"] == []
