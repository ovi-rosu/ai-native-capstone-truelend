"""Evaluator-only probe harness (instance 2). NOT production code.

Wraps the *real* production factory -- src.api.app.build_fastapi_app() then
src.api.app.create_app(inner) -- and adds throwaway routes so the frozen
error envelope can be exercised live for a framework 422, an unhandled 500,
and a handler that emits more than one log line.

G3EVAL2_ACCESS controls the counterfactual for the `uvicorn.access`
silencing in src.config.logging._SILENCED_LOGGERS:

  unset / "silenced" -- production behaviour, logger disabled.
  "routed"           -- re-enabled and propagated through the JSON root
                        handler, exactly the treatment `uvicorn.error` gets.
                        Tests the comment's claim that request_id_var is
                        already reset when uvicorn.access emits.
  "native"           -- re-enabled with uvicorn's own AccessFormatter, as
                        uvicorn's default dictConfig would leave it. Tests
                        the comment's claim that RedactionFilter clearing
                        record.args breaks AccessFormatter.
"""

from __future__ import annotations

import logging
import os

from fastapi import FastAPI
from pydantic import BaseModel
from src.api.app import build_fastapi_app, create_app
from src.config.logging import RedactionFilter, register_sensitive
from starlette.types import ASGIApp

_PAN = "ABCDE1234F"
_AADHAAR = "123456789012"
_probe_log = logging.getLogger("truelend.probe")


class _Payload(BaseModel):
    amount: int


def _add_error_routes(fastapi_app: FastAPI) -> None:
    @fastapi_app.get("/probe/boom")
    async def boom() -> dict[str, str]:
        raise RuntimeError("probe-boom: unhandled exception on purpose")

    @fastapi_app.post("/probe/validate")
    async def validate(payload: _Payload) -> dict[str, int]:
        return {"amount": payload.amount}


def _add_log_routes(fastapi_app: FastAPI) -> None:
    @fastapi_app.get("/probe/chatty")
    async def chatty() -> dict[str, str]:
        _probe_log.info("handler line one")
        _probe_log.warning("handler line two")
        return {"ok": "yes"}

    @fastapi_app.get("/probe/pii")
    async def pii() -> dict[str, str]:
        register_sensitive(_PAN, _AADHAAR)
        _probe_log.info(
            "applicant pan=ABCDE1234F aadhaar=1234 5678 9012 lower=abcde1234f"
        )
        return {"ok": "yes"}

    @fastapi_app.get("/probe/piiboom")
    async def piiboom() -> dict[str, str]:
        register_sensitive(_PAN, _AADHAAR)
        raise RuntimeError("leak pan ABCDE1234F and aadhaar 123456789012")


def _inner() -> FastAPI:
    fastapi_app = build_fastapi_app()
    _add_error_routes(fastapi_app)
    _add_log_routes(fastapi_app)
    return fastapi_app


def _configure_access_logger() -> None:
    mode = os.environ.get("G3EVAL2_ACCESS", "silenced")
    if mode == "silenced":
        return
    access = logging.getLogger("uvicorn.access")
    access.disabled = False
    access.handlers.clear()
    access.setLevel(logging.INFO)
    if mode == "routed":
        access.propagate = True
        return
    from uvicorn.logging import AccessFormatter

    handler = logging.StreamHandler()
    handler.setFormatter(AccessFormatter("%(levelprefix)s %(message)s"))
    handler.addFilter(RedactionFilter())
    access.addHandler(handler)
    access.propagate = False


def build() -> ASGIApp:
    app_obj = create_app(_inner())
    _configure_access_logger()
    return app_obj


app = build()
