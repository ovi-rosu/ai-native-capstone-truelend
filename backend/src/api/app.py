"""Application factory.

Wires structured logging, Correlation Id propagation, the global error
mapping and the platform router. `app` is importable and runnable directly
via `uv run uvicorn src.api.app:app` -- no Docker required.

Two factories, because the Correlation Id middleware has to sit *outside*
Starlette's `ServerErrorMiddleware` to stamp a 500 it did not build
(CR-003, see `src.api.middleware`):

- `build_fastapi_app()` returns the `FastAPI` instance. Every story adding a
  router adds its `include_router` call here -- this is the app factory
  router registry `specs/design/component-map.md` names.
- `create_app()` is the published factory and what should always be served:
  it wraps that instance in `CorrelationIdMiddleware`, so the returned object
  is an ASGI callable rather than a `FastAPI`. Tests that need to register a
  throwaway route build the inner app and pass it in.
"""

from __future__ import annotations

from fastapi import FastAPI
from src.api.errors import register_exception_handlers
from src.api.middleware import CorrelationIdMiddleware
from src.api.platform.routes import router as platform_router
from src.config.logging import configure_logging
from src.config.settings import Settings
from starlette.types import ASGIApp


def build_fastapi_app() -> FastAPI:
    """Build the inner FastAPI application: routers and error mapping."""
    settings = Settings()
    configure_logging(settings)

    fastapi_app = FastAPI(title=settings.service_name)
    register_exception_handlers(fastapi_app)
    fastapi_app.include_router(platform_router)
    return fastapi_app


def create_app(fastapi_app: FastAPI | None = None) -> ASGIApp:
    """Wrap the FastAPI app so correlation survives an unhandled exception.

    Always use this to serve the application. Reaching for
    `build_fastapi_app()` directly yields an app with no Correlation Id
    middleware, so a request would carry no `request_id` on any log line.
    """
    return CorrelationIdMiddleware(fastapi_app or build_fastapi_app())


app = create_app()
