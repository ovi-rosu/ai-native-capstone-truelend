"""Shared fixtures: a TestClient bound to the real app factory, and a
log-capture fixture that records every JSON-formatted line emitted by the
root logger for the duration of a test.
"""

from __future__ import annotations

import logging
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from src.api.app import create_app
from src.config.logging import JSONLogFormatter, RedactionFilter


class ListLogHandler(logging.Handler):
    """Collects every formatted log line emitted while it is attached."""

    def __init__(self) -> None:
        super().__init__()
        self.lines: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(self.format(record))


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    """A TestClient bound to a freshly-built app (real `configure_logging` runs)."""
    with TestClient(create_app()) as test_client:
        yield test_client


@pytest.fixture
def log_capture(client: TestClient) -> Generator[ListLogHandler, None, None]:
    """Captures every log line emitted after the app (and its logging config)
    is already in place -- depends on `client` so `configure_logging`'s
    handler reset has already happened before this fixture attaches.

    Silences the `httpx` logger for the duration: `TestClient` makes its
    request through a real `httpx` client on the test's own thread, and that
    client-side instrumentation line is not part of the *server's*
    request-scoped log output the acceptance criteria describe.
    """
    handler = ListLogHandler()
    handler.setFormatter(JSONLogFormatter())
    handler.addFilter(RedactionFilter())
    root = logging.getLogger()
    root.addHandler(handler)
    httpx_logger = logging.getLogger("httpx")
    previous_httpx_level = httpx_logger.level
    httpx_logger.setLevel(logging.WARNING)
    try:
        yield handler
    finally:
        httpx_logger.setLevel(previous_httpx_level)
        root.removeHandler(handler)
