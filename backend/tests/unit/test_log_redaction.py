"""E15-S1: structured JSON logging, Correlation Id propagation, PII
redaction and the health probe -- one test per acceptance criterion.
"""

from __future__ import annotations

import json
import logging
import time

import pytest
from fastapi.testclient import TestClient
from src.api.app import create_app
from src.config.logging import redact_values
from src.types.errors import AppError
from tests.conftest import ListLogHandler


def test_sensitive_application_values_never_appear_in_any_log_line(
    client: TestClient, log_capture: ListLogHandler
) -> None:
    """E15-S1-AC1: PAN, Aadhaar and salary-doc content are redacted from
    every emitted log line, however they reach the logger."""
    pan = "ABCDE1234F"
    aadhaar = "234123412346"
    salary_doc_content = "SALARY-DOC-BASE64-CONTENT-XYZ"

    with redact_values(pan, aadhaar, salary_doc_content):
        logging.getLogger("app.origination").info(
            "processing application pan=%s aadhaar=%s salary_doc=%s",
            pan,
            aadhaar,
            salary_doc_content,
        )
        response = client.get("/health")

    assert response.status_code == 200
    assert log_capture.lines
    joined = "\n".join(log_capture.lines)
    assert pan not in joined
    assert aadhaar not in joined
    assert salary_doc_content not in joined


def test_redaction_filter_installed_on_every_configured_logger() -> None:
    """E15-S1-AC2: enumerating every configured logger shows the redaction
    filter on 100% of them; a logger registered without it fails the same
    assertion, proving the check is not vacuous."""
    create_app()  # runs configure_logging()

    def _has_redaction_filter(logger_obj: logging.Logger) -> bool:
        from src.config.logging import RedactionFilter

        return any(isinstance(f, RedactionFilter) for f in logger_obj.filters)

    configured_loggers: list[logging.Logger] = [logging.getLogger()]
    for logger_obj in logging.root.manager.loggerDict.values():
        if isinstance(logger_obj, logging.Logger):
            configured_loggers.append(logger_obj)

    assert configured_loggers
    for logger_obj in configured_loggers:
        assert _has_redaction_filter(logger_obj), f"logger {logger_obj.name!r} missing filter"

    unfiltered_logger = logging.Logger("unregistered-probe-logger")
    with pytest.raises(AssertionError):
        assert _has_redaction_filter(unfiltered_logger)


def test_supplied_request_id_header_propagates_to_every_log_line(
    client: TestClient, log_capture: ListLogHandler
) -> None:
    """E15-S1-AC3: every log line emitted while serving a request carrying
    X-Request-ID parses as JSON and carries that same request_id."""
    response = client.get("/health", headers={"X-Request-ID": "req-abc"})

    assert response.status_code == 200
    assert log_capture.lines
    for line in log_capture.lines:
        parsed = json.loads(line)
        assert parsed["request_id"] == "req-abc"


def test_missing_request_id_header_generates_and_echoes_one(
    client: TestClient, log_capture: ListLogHandler
) -> None:
    """E15-S1-AC4: without an inbound X-Request-ID, every request-scoped log
    line carries the same generated non-empty id, and the response echoes
    that same id on the X-Request-ID response header."""
    response = client.get("/health")

    assert response.status_code == 200
    echoed_id = response.headers.get("X-Request-ID")
    assert echoed_id
    assert log_capture.lines
    for line in log_capture.lines:
        parsed = json.loads(line)
        assert parsed["request_id"] == echoed_id


def test_health_endpoint_returns_ok_json_under_one_second(client: TestClient) -> None:
    """E15-S1-AC5: GET /health is 200 with a JSON body, under 1 second."""
    start = time.monotonic()
    response = client.get("/health")
    elapsed = time.monotonic() - start

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert elapsed < 1.0


def test_app_error_is_mapped_to_a_typed_json_response() -> None:
    """Coverage for api/errors.py: AppError is mapped once at the API
    boundary to a JSON body carrying its message, at its status code."""
    app = create_app()

    @app.get("/_test-only-raises")
    def _raise_app_error() -> None:
        raise AppError("boom", status_code=418)

    with TestClient(app, raise_server_exceptions=False) as test_client:
        response = test_client.get("/_test-only-raises")

    assert response.status_code == 418
    assert response.json() == {"error": "boom"}
