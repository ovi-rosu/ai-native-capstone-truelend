"""Correlation Id middleware.

Honours an inbound `X-Request-ID` header or generates one, binds it to the
`request_id` contextvar for the request scope (so `JSONLogFormatter` can read
it), emits one access-log line while it is still bound, and echoes it back on
the response header. See specs/design/CONTEXT.md: "Correlation Id -- the
request-scoped identifier carried by every structured log line emitted while
handling one request."
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from uuid import uuid4

from src.config.logging import request_id_var
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

_REQUEST_ID_HEADER = "X-Request-ID"
_access_logger = logging.getLogger("truelend.access")


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Binds and echoes the Correlation Id for every request."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get(_REQUEST_ID_HEADER) or uuid4().hex
        token = request_id_var.set(request_id)
        try:
            response = await call_next(request)
            response.headers[_REQUEST_ID_HEADER] = request_id
            _access_logger.info(
                "%s %s -> %s", request.method, request.url.path, response.status_code
            )
            return response
        finally:
            request_id_var.reset(token)
