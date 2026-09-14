"""E15-S1: Correlation Id propagation (AC3, AC4).

Split out of test_log_redaction.py: that file had grown past the 500-line
cap with six responsibilities in it. component-map.md now lists this path
for E15-S1.
"""

from __future__ import annotations

import json
import logging

from fastapi.testclient import TestClient
from src.config.logging import JSONLogFormatter
from tests.conftest import ListLogHandler


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
def test_uvicorn_loggers_do_not_bypass_json_formatting() -> None:
    """E15-S1-AC3: no request-scoped line escapes as plain text.

    `uvicorn` installs its own `dictConfig` with `propagate=False` and its
    own formatters on `uvicorn`, `uvicorn.error` and `uvicorn.access`.
    `configure_logging()` rebuilds only the *root* handler, so under a real
    `uvicorn` run roughly half of the lines for a request were plain text
    with no `request_id` — while the unit suite saw none of it, because
    pytest never applies uvicorn's `dictConfig`. This test applies it first,
    exactly as a real run does.
    """
    import logging.config

    from src.config.logging import configure_logging
    from src.config.settings import Settings
    from uvicorn.config import LOGGING_CONFIG

    logging.config.dictConfig(LOGGING_CONFIG)
    configure_logging(Settings(_env_file=None))

    for name in ("uvicorn", "uvicorn.error"):
        logger_obj = logging.getLogger(name)
        assert logger_obj.handlers == [], f"{name} keeps its own plain-text handler"
        assert logger_obj.propagate is True, f"{name} does not reach the JSON root handler"

    access = logging.getLogger("uvicorn.access")
    assert access.disabled is True, (
        "uvicorn.access must be silenced: its AccessFormatter emits plain text and "
        "the request_id contextvar is already reset by the time it logs, so our own "
        "truelend.access JSON line is the single source of access logging"
    )
def test_unhandled_exception_response_still_carries_the_correlation_id() -> None:
    """CR-003 / E15-S1-AC4 on the path that matters most.

    The correlation middleware wrote the header and emitted the access line
    only after `await call_next(request)` returned, with just the contextvar
    reset in `finally`. An unhandled exception ran neither, so a 500 came
    back with no `X-Request-ID` and left no access-log record — the one case
    an operator needs to correlate.

    A `BaseHTTPMiddleware` cannot fix this: Starlette's
    `ServerErrorMiddleware` builds the 500 *outside* user middleware, and an
    `app.exception_handler(Exception)` is bound to it, by which point the
    contextvar is already reset. The correlation middleware is therefore a
    pure-ASGI wrapper mounted outside `ServerErrorMiddleware`, stamping the
    header on `http.response.start` whoever produced it.
    """
    from src.api.app import build_fastapi_app, create_app

    inner = build_fastapi_app()

    @inner.get("/_test-only-explodes")
    def _explode() -> None:
        raise RuntimeError("unhandled")

    with TestClient(create_app(inner), raise_server_exceptions=False) as test_client:
        response = test_client.get(
            "/_test-only-explodes", headers={"X-Request-ID": "req-500"}
        )

    assert response.status_code == 500
    assert response.headers.get("X-Request-ID") == "req-500", (
        "a 500 response must still echo the correlation id"
    )
def test_unhandled_exception_still_emits_an_access_log_line() -> None:
    """The 500 must leave an access-log record carrying the correlation id."""
    from src.api.app import build_fastapi_app, create_app

    inner = build_fastapi_app()

    @inner.get("/_test-only-explodes-logged")
    def _explode() -> None:
        raise RuntimeError("unhandled")

    handler = ListLogHandler()
    handler.setFormatter(JSONLogFormatter())
    root = logging.getLogger()
    root.addHandler(handler)
    try:
        with TestClient(create_app(inner), raise_server_exceptions=False) as test_client:
            test_client.get(
                "/_test-only-explodes-logged", headers={"X-Request-ID": "req-501"}
            )
    finally:
        root.removeHandler(handler)

    access_lines = [
        json.loads(line)
        for line in handler.lines
        if json.loads(line).get("logger") == "truelend.access"
    ]
    assert access_lines, "no access-log line was emitted for the failing request"
    assert any(
        entry["request_id"] == "req-501" and "500" in entry["message"]
        for entry in access_lines
    ), f"access lines did not record the 500 with its correlation id: {access_lines}"
