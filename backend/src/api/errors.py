"""Global exception handling.

Maps `AppError` (Types layer) to a JSON error response once, at the API
boundary, per specs/design/architecture.md: "Errors -- typed errors in
Types, mapped once at the API boundary."
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from src.types.errors import AppError


def register_exception_handlers(app: FastAPI) -> None:
    """Register the `AppError` -> JSON response mapping on `app`."""

    @app.exception_handler(AppError)
    async def _handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        # One shape for every non-2xx response, per api-contracts.md:
        # {"error": "<ErrorName>", "detail": "<message>", "context": {...}}.
        # The earlier body put the *message* under "error" and omitted the
        # other two keys, which E4-S4 needs to read threshold_kind and
        # configured_value from.
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": exc.error,
                "detail": exc.message,
                "context": exc.context,
            },
        )
