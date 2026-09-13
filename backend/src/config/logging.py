"""Structured JSON logging, correlation id propagation and PII redaction.

Per specs/design/architecture.md's cross-cutting section: a `RedactionFilter`
installed on every configured logger drops PAN, Aadhaar and salary-document
content before a record is formatted, and `JSONLogFormatter` renders every
record as one JSON line carrying the Correlation Id (`request_id`) bound for
the current request scope.

Business code (a future story's origination endpoint) marks the values that
must never reach a log sink by wrapping the request-handling code in
`redact_values(*values)`. This module does not know PAN/Aadhaar formats in
advance -- it redacts whatever values the caller marks as sensitive, which is
the only sound approach given those are per-applicant, per-request data.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime

from src.config.settings import Settings

request_id_var: ContextVar[str] = ContextVar("request_id", default="")
_sensitive_values: ContextVar[frozenset[str]] = ContextVar("sensitive_values", default=frozenset())


@contextmanager
def redact_values(*values: str) -> Iterator[None]:
    """Mark `values` as sensitive for every log line emitted in this scope."""
    non_empty = frozenset(value for value in values if value)
    token = _sensitive_values.set(_sensitive_values.get() | non_empty)
    try:
        yield
    finally:
        _sensitive_values.reset(token)


class RedactionFilter(logging.Filter):
    """Scrubs every currently-registered sensitive value from a log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        sensitive_values = _sensitive_values.get()
        if not sensitive_values:
            return True
        message = record.getMessage()
        for value in sensitive_values:
            message = message.replace(value, "[REDACTED]")
        record.msg = message
        record.args = ()
        return True


class JSONLogFormatter(logging.Formatter):
    """Renders one log record as a single JSON line carrying the request id."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_var.get(),
        }
        return json.dumps(payload)


def configure_logging(settings: Settings) -> None:
    """Install JSON formatting and redaction on every configured logger."""
    handler = logging.StreamHandler()
    handler.setFormatter(JSONLogFormatter())
    handler.addFilter(RedactionFilter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(settings.log_level)

    _install_redaction_filter_everywhere()


def _install_redaction_filter_everywhere() -> None:
    """Attach a `RedactionFilter` to root and to every already-registered logger."""
    loggers: list[logging.Logger] = [logging.getLogger()]
    for logger_obj in logging.root.manager.loggerDict.values():
        if isinstance(logger_obj, logging.Logger):
            loggers.append(logger_obj)

    for logger_obj in loggers:
        already_installed = any(isinstance(f, RedactionFilter) for f in logger_obj.filters)
        if not already_installed:
            logger_obj.addFilter(RedactionFilter())
