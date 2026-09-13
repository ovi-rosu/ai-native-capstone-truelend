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
        return JSONResponse(status_code=exc.status_code, content={"error": exc.message})
