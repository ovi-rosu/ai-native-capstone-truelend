"""Application factory.

Wires structured logging, Correlation Id propagation, the global error
mapping and the platform router. `app` is importable and runnable directly
via `uv run uvicorn src.api.app:app` -- no Docker required.
"""

from __future__ import annotations

from fastapi import FastAPI
from src.api.errors import register_exception_handlers
from src.api.middleware import CorrelationIdMiddleware
from src.api.platform.routes import router as platform_router
from src.config.logging import configure_logging
from src.config.settings import Settings


def create_app() -> FastAPI:
    """Build a fully-wired FastAPI application."""
    settings = Settings()
    configure_logging(settings)

    app = FastAPI(title=settings.service_name)
    app.add_middleware(CorrelationIdMiddleware)
    register_exception_handlers(app)
    app.include_router(platform_router)
    return app


app = create_app()
