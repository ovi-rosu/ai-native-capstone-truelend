"""Structured JSON logging, correlation id propagation and PII redaction.

Per specs/design/architecture.md's cross-cutting section: a `RedactionFilter`
installed on every configured logger drops PAN, Aadhaar and salary-document
content before a record is formatted, and `JSONLogFormatter` renders every
record as one JSON line carrying the Correlation Id (`request_id`) bound for
the current request scope.

Business code (a future story's origination endpoint) marks the values that
must never reach a log sink by calling `register_sensitive(*values)` as soon
as it has them. This module does not know PAN/Aadhaar formats in advance -- it
redacts whatever values the caller marks as sensitive, which is the only sound
approach given those are per-applicant, per-request data.

Registration is **request-scoped**, not block-scoped: `CorrelationIdMiddleware`
opens the scope and owns its lifetime. `redact_values` remains for narrow,
self-closing use, but a value withdrawn at the end of a `with` block is no
longer registered when the request's exception is logged on its way out --
which is how PAN and Aadhaar reached a traceback unscrubbed.
"""

from __future__ import annotations

import json
import logging
import re
import traceback
from collections.abc import Collection, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from functools import lru_cache

from src.config.settings import Settings

request_id_var: ContextVar[str] = ContextVar("request_id", default="")

# Holds a **mutable** set, and registration mutates it in place rather than
# rebinding the variable. FastAPI runs a `def` (non-async) handler in a
# threadpool, which runs on a *copy* of the context: a `ContextVar.set` there
# is invisible to the middleware that opened the scope, so rebinding silently
# lost every value a sync handler registered. Mutating the shared object is
# visible through the copy, which is the whole point of the request scope.
_sensitive_values: ContextVar[set[str] | None] = ContextVar("sensitive_values", default=None)


def _current_values() -> set[str]:
    """The set for the current scope, creating a scope-less one if needed."""
    current = _sensitive_values.get()
    if current is None:
        current = set()
        _sensitive_values.set(current)
    return current


@contextmanager
def redact_values(*values: str) -> Iterator[None]:
    """Mark `values` as sensitive for every log line emitted in this scope.

    Narrow and self-closing. Prefer `register_sensitive` inside a request
    handler: this one withdraws its own values on exit, so an exception
    escaping the `with` block is logged *after* they are gone -- which is how
    PAN and Aadhaar reached a traceback unscrubbed.
    """
    current = _current_values()
    added = {value for value in values if value} - current
    current.update(added)
    try:
        yield
    finally:
        current.difference_update(added)


def register_sensitive(*values: str) -> None:
    """Mark `values` as sensitive for the rest of the current request.

    Additive with no teardown: the correlation middleware owns the lifetime
    and deliberately does *not* unwind it when the request fails, so the
    traceback logged on the way out stays scrubbed and correlated.
    """
    _current_values().update(value for value in values if value)


def begin_redaction_scope() -> object:
    """Open a request-scoped redaction set; returns the token to close it."""
    return _sensitive_values.set(set())


def end_redaction_scope(token: object) -> None:
    """Close a scope opened by `begin_redaction_scope`."""
    _sensitive_values.reset(token)  # type: ignore[arg-type]


_MIN_REDACTABLE_LENGTH = 6
_SEPARATOR_CHARS = " \t-"
# Bounded on purpose. An unbounded `[...]*` between every character makes a
# separator-heavy haystack partitionable combinatorially -- catastrophic
# backtracking (SEC-001). Four is wider than any real PAN/Aadhaar grouping.
_SEPARATOR_RUN = r"[ \t\-]{0,4}"


@lru_cache(maxsize=256)
def _redaction_pattern(value: str) -> re.Pattern[str]:
    """A pattern matching `value` however it was cased or separated.

    Byte-for-byte matching let a reformatted value straight through: a PAN
    logged lowercase, or an Aadhaar written in the spaced form people
    actually type, never matched.

    A value that *itself* contains a separator is matched literally. Joining
    its characters with a tolerant run would make the run and the literal
    separator ambiguous, which is exactly the shape that backtracks -- and
    the real salary-document fixture is full of dashes.
    """
    if any(char in _SEPARATOR_CHARS for char in value):
        return re.compile(re.escape(value), re.IGNORECASE)
    return re.compile(
        _SEPARATOR_RUN.join(re.escape(char) for char in value), re.IGNORECASE
    )


def _scrub(text: str, sensitive_values: Collection[str]) -> str:
    for value in sensitive_values:
        if len(value) < _MIN_REDACTABLE_LENGTH:
            # Too short to match safely: a 2-3 character value with separators
            # allowed between each character matches far too much unrelated text.
            continue
        text = _redaction_pattern(value).sub("[REDACTED]", text)
    return text


class RedactionFilter(logging.Filter):
    """Scrubs every currently-registered sensitive value from a log record.

    Covers the formatted message *and* the exception traceback. The
    traceback is rendered here, redacted, and stashed on `exc_text` while
    `exc_info` is cleared, so no downstream handler can re-render the raw
    original.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        sensitive_values = _sensitive_values.get()
        if not sensitive_values:
            return True

        message = record.getMessage()
        scrubbed = _scrub(message, sensitive_values)
        if scrubbed != message:
            record.msg = scrubbed
            record.args = ()

        if record.exc_info and record.exc_info[0] is not None:
            rendered = "".join(traceback.format_exception(*record.exc_info))
            record.exc_text = _scrub(rendered, sensitive_values)
            record.exc_info = None
        elif record.exc_text:
            record.exc_text = _scrub(record.exc_text, sensitive_values)
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
        # Without this every stack trace was silently dropped: the payload was
        # built from the message alone and `exc_info` was never read.
        exception_text = record.exc_text
        if not exception_text and record.exc_info and record.exc_info[0] is not None:
            exception_text = "".join(traceback.format_exception(*record.exc_info))
        if exception_text:
            payload["exception"] = exception_text
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

    _route_server_loggers_through_root()
    _install_redaction_filter_everywhere()


# Loggers `uvicorn` installs via its own dictConfig. It sets propagate=False
# and attaches its own plain-text formatters, so rebuilding the root handler
# alone never reached them: under a real `uvicorn` run about half the lines for
# a request came out as plain text with no request_id, breaking E15-S1-AC3.
# pytest never applies that dictConfig, which is why the unit suite saw none of it.
_JSON_ROUTED_LOGGERS = ("uvicorn", "uvicorn.error", "gunicorn.error")

# `uvicorn.access` is silenced rather than reformatted, for two reasons:
# `request_id_var` is already reset by the time it emits (it logs after the
# response completes, outside the middleware scope), so it could only ever
# render request_id: ""; and its AccessFormatter reads record.args, which
# RedactionFilter clears, raising ValueError and dropping the line entirely.
# CorrelationIdMiddleware already emits an equivalent JSON line carrying
# method, path, status and the correlation id, so nothing is lost.
_SILENCED_LOGGERS = ("uvicorn.access",)


def _route_server_loggers_through_root() -> None:
    """Force the server's own loggers through the JSON root handler."""
    for name in _JSON_ROUTED_LOGGERS:
        logger_obj = logging.getLogger(name)
        logger_obj.handlers.clear()
        logger_obj.propagate = True

    for name in _SILENCED_LOGGERS:
        logger_obj = logging.getLogger(name)
        logger_obj.handlers.clear()
        logger_obj.propagate = False
        logger_obj.disabled = True


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
