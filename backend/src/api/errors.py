"""Global exception handling.

Maps every non-2xx response to the one envelope `specs/design/api-contracts.md`
specifies -- `{"error": "<ErrorName>", "detail": "<message>", "context": {...}}`
-- at the API boundary, per specs/design/architecture.md: "Errors -- typed
errors in Types, mapped once at the API boundary."

Four handlers, because the contract says *every* non-2xx: `AppError` for typed
application errors, `HTTPException` for the framework's own 401/403/404/409,
`RequestValidationError` for 422s, and a catch-all so an unhandled exception
returns the envelope instead of Starlette's `text/plain` 500.

`context` is sanitised on the way out. It was an unfiltered outbound channel:
probes egressed PAN, Aadhaar, a database connection string complete with
credentials, SQL and absolute paths, and a `Decimal` in it turned a 422 into a
plain-text 500.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from decimal import Decimal

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from src.config.logging import scrub_text
from src.types.errors import AppError
from starlette.exceptions import HTTPException as StarletteHTTPException

# The contract's own vocabulary: 401 no or invalid token, 403 wrong role,
# 404 unknown id, 409 illegal transition, 422 validation.
_STATUS_ERROR_NAMES = {
    400: "BadRequest",
    401: "Unauthorized",
    403: "Forbidden",
    404: "NotFound",
    409: "Conflict",
    422: "ValidationError",
}

# A URI carrying inline credentials before the host, which is how a database
# connection string leaks a password.
_CREDENTIAL_URI = re.compile(r"[a-z][a-z0-9+.\-]*://[^/\s:@]+:[^/\s@]+@", re.IGNORECASE)

_MAX_CONTEXT_VALUE_CHARS = 200


def _scalar(value: object) -> str | int | bool | None:
    """Coerce a context value to a wire-safe scalar, or `None` to drop it.

    `Decimal` becomes a string so money never crosses as a float and never
    trips the JSON encoder into a 500. Anything structured is dropped: a
    nested mapping is how unbounded internal state escapes.
    """
    if isinstance(value, bool | int):
        return value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, str):
        return value
    return None


def sanitise_context(context: Mapping[str, object]) -> dict[str, str | int | bool]:
    """Allow-list a `context` mapping for the wire."""
    clean: dict[str, str | int | bool] = {}
    for key, raw in context.items():
        value = _scalar(raw)
        if value is None:
            continue
        if isinstance(value, str):
            if _CREDENTIAL_URI.search(value) or len(value) > _MAX_CONTEXT_VALUE_CHARS:
                continue
            value = scrub_text(value)
        clean[str(key)] = value
    return clean


def _envelope(
    status_code: int,
    error: str,
    detail: str,
    context: Mapping[str, object] | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": error,
            "detail": scrub_text(detail),
            "context": sanitise_context(context or {}),
        },
        # Rebuilding the response from status and detail alone dropped these,
        # so a 401 lost `WWW-Authenticate` and a 405 lost `Allow` -- both
        # required by the HTTP specs, and the 401 case becomes the single
        # enforcement point for every guarded route at group C.
        headers=dict(headers) if headers else None,
    )


async def handle_app_error(request: Request, exc: Exception) -> JSONResponse:
    """A typed application error keeps its own name, message and context."""
    assert isinstance(exc, AppError)
    return _envelope(exc.status_code, exc.error, exc.message, exc.context)


async def handle_http_error(request: Request, exc: Exception) -> JSONResponse:
    """The framework's own 401/403/404/409 take the same shape."""
    assert isinstance(exc, StarletteHTTPException)
    name = _STATUS_ERROR_NAMES.get(exc.status_code, "HTTPError")
    return _envelope(exc.status_code, name, str(exc.detail), headers=exc.headers)


async def handle_validation_error(request: Request, exc: Exception) -> JSONResponse:
    """A 422 reports *where* validation failed, never the rejected value.

    Echoing the offending input back would put a submitted PAN or Aadhaar
    straight into the response body.
    """
    assert isinstance(exc, RequestValidationError)
    errors = exc.errors()
    field = ".".join(str(part) for part in (errors[0].get("loc") or ())) if errors else ""
    return _envelope(422, "ValidationError", "request validation failed", {"field": field})


async def handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
    """Nothing from an unhandled exception crosses the boundary.

    Its message can carry paths, SQL or secrets. The traceback is logged by
    the correlation middleware instead -- scrubbed, and carrying the request id.
    """
    return _envelope(500, "InternalServerError", "internal server error")


def register_exception_handlers(app: FastAPI) -> None:
    """Register the one-envelope mapping for every non-2xx response."""
    app.add_exception_handler(AppError, handle_app_error)
    app.add_exception_handler(StarletteHTTPException, handle_http_error)
    app.add_exception_handler(RequestValidationError, handle_validation_error)
    app.add_exception_handler(Exception, handle_unexpected)
