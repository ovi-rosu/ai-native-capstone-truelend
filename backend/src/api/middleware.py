"""Correlation Id middleware.

Honours an inbound `X-Request-ID` header or generates one, binds it to the
`request_id` contextvar for the request scope (so `JSONLogFormatter` can read
it), stamps it on the outgoing response and emits one access-log line. See
specs/design/CONTEXT.md: "Correlation Id -- the request-scoped identifier
carried by every structured log line emitted while handling one request."

This is a **pure ASGI** middleware, deliberately not a
`BaseHTTPMiddleware`, and it is mounted *outside* Starlette's
`ServerErrorMiddleware` (see `src.api.app.create_app`). The earlier
`BaseHTTPMiddleware` version stamped the header and logged only after
`await call_next(request)` returned, so an unhandled exception produced a
500 with no `X-Request-ID` and no access-log line at all -- the one case an
operator needs to correlate (CR-003, `E15-S1-AC4`).

That could not be fixed from inside: `ServerErrorMiddleware` builds the 500
itself, outside any user middleware, and an `app.exception_handler(Exception)`
is bound to *it*, by which point the contextvar has already been reset.
Working at the ASGI level instead, this middleware sees the
`http.response.start` message whoever produced it -- a route, an exception
handler, or `ServerErrorMiddleware`'s own 500 -- and stamps the header and
logs the real status there.

It also owns the lifetime of the request's PII redaction set. On the failure
path it deliberately unwinds *neither* contextvar: the exception still has to
travel out through the server, which logs the traceback on its way, and that
line is exactly where PAN and Aadhaar leaked once the handler's registration
had been torn down -- with an empty `request_id` besides. Leaving both bound
keeps that line scrubbed and correlated, and the contextvars die with this
request's task context.
"""

from __future__ import annotations

import logging
from uuid import uuid4

from src.config.logging import begin_redaction_scope, end_redaction_scope, request_id_var
from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

_REQUEST_ID_HEADER = "X-Request-ID"
_access_logger = logging.getLogger("truelend.access")


class CorrelationIdMiddleware:
    """Binds, stamps and logs the Correlation Id for every HTTP request."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    @staticmethod
    def _stamping_send(send: Send, request_id: str, method: str, path: str) -> Send:
        """Wrap `send` so the response start carries the id and is logged."""

        async def send_with_correlation_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)[_REQUEST_ID_HEADER] = request_id
                _access_logger.info("%s %s -> %s", method, path, message["status"])
            await send(message)

        return send_with_correlation_id

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        inbound = Headers(scope=scope).get(_REQUEST_ID_HEADER.lower())
        request_id = inbound or uuid4().hex
        token = request_id_var.set(request_id)
        redaction_token = begin_redaction_scope()
        wrapped_send = self._stamping_send(
            send, request_id, scope.get("method", "-"), scope.get("path", "-")
        )

        try:
            await self.app(scope, receive, wrapped_send)
        except BaseException:
            # Logged here, while the redaction set and the id are still bound,
            # so the traceback is scrubbed and correlated. Relying on the
            # server's own logger left it unscrubbed and with an empty id --
            # and under TestClient it was never recorded at all.
            _access_logger.exception("unhandled exception serving the request")
            raise  # both contextvars stay bound on purpose -- see module docstring
        else:
            end_redaction_scope(redaction_token)
            request_id_var.reset(token)
