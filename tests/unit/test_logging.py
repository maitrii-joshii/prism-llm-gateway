import json
import logging

from prism.config.logging import (
    JsonFormatter,
    RequestIdFilter,
    reset_request_id,
    set_request_id,
)


def test_log_line_is_valid_json():
    record = logging.LogRecord(
        name="prism.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="Request received",
        args=(),
        exc_info=None,
    )
    record.request_id = "req_abc123"

    output = JsonFormatter().format(record)
    parsed = json.loads(output)

    assert parsed["level"] == "INFO"
    assert parsed["request_id"] == "req_abc123"
    assert parsed["message"] == "Request received"
    assert "timestamp" in parsed


def test_request_id_filter_adds_context_request_id():
    token = set_request_id("req_test123")

    try:
        record = logging.LogRecord(
            name="prism.test",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="Request received",
            args=(),
            exc_info=None,
        )

        assert RequestIdFilter().filter(record) is True
        assert record.request_id == "req_test123"
    finally:
        reset_request_id(token)


def test_formatter_excludes_unapproved_fields():
    record = logging.LogRecord(
        name="prism.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="Request received",
        args=(),
        exc_info=None,
    )
    record.request_id = "req_abc123"
    record.authorization = "Bearer secret-token"

    output = JsonFormatter().format(record)
    parsed = json.loads(output)

    assert "authorization" not in parsed
    assert "secret-token" not in output
