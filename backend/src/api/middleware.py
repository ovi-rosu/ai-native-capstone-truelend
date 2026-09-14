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
import time
from collections import Counter
from uuid import uuid4

from src.config.logging import begin_redaction_scope, end_redaction_scope, request_id_var
from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

_REQUEST_ID_HEADER = "X-Request-ID"
_access_logger = logging.getLogger("truelend.access")

# RED counters, keyed (method, route, status). Kept here because this
# middleware is the only writer; `GET /metrics` renders a snapshot.
_request_counts: Counter[tuple[str, str, int]] = Counter()


# Every unrouted request shares one series. Keying on the raw path let a
# single keep-alive connection mint 60,000 label values and retain 28.2 MB
# permanently -- unbounded cardinality is a denial-of-service on the metrics
# store, and the raw path is attacker-controlled besides.
_UNMATCHED_ROUTE = "<unmatched>"


def route_label(scope: Scope) -> str:
    """The matched route template, or one shared bucket when nothing matched."""
    template = getattr(scope.get("route"), "path", None)
    return template if isinstance(template, str) else _UNMATCHED_ROUTE


# Latency bucket upper bounds in seconds. Fixed rather than configurable: a
# histogram's buckets are part of its contract, and E15-S3 reads p95 off them
# against the 500 ms budget, so 0.5 has to be one of the boundaries.
_LATENCY_BUCKETS: tuple[float, ...] = (
    0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0,
)
_duration_counts: dict[tuple[str, str], list[int]] = {}
_duration_totals: dict[tuple[str, str], tuple[int, float]] = {}


# Bounded method label. `method` came straight from the request and flowed
# into the keys of three process-global dicts behind an unauthenticated
# /metrics, never evicted (CR-301): 3,000 distinct methods produced ~6,000
# series, 22,003 produced 25.3 MB retained. It only looked safe because
# `uvicorn[standard]`'s httptools rejects unknown methods at 400 below the ASGI
# layer -- an optional C extension that nothing here documents, tests or pins,
# under a middleware deliberately written to be server-agnostic.
_KNOWN_METHODS = frozenset(
    {"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "TRACE", "CONNECT"}
)
_OTHER_METHOD = "<other>"


def method_label(method: str) -> str:
    """The request method if it is a real one, else one shared bucket."""
    upper = method.upper()
    return upper if upper in _KNOWN_METHODS else _OTHER_METHOD


# The observability endpoint is excluded from BOTH of its own series. The SLO
# sensor aggregates globally with no per-route dimension
# (.claude/hooks/lib/prom-parse.js), reading errorRate from
# http_requests_total and p95 from http_request_duration_seconds, so a frequent
# scraper dilutes either one purely by observing (SEC3-003).
#
# The first attempt excluded the counter only and left the histogram, which
# fixed the wrong half: a fast scrape still dragged p95 down, and it no longer
# left even a trace in the counters. Measured p95 of 5 ms against a real
# business p95 of 4,875 ms on a 500 ms budget -- under-reporting a breach by
# ~1000x, on the one metric E15-S4 exists to make measurable.
#
# This still does not close SEC3-003: any public route contributes to both
# aggregates. The full fix is per-route aggregation, which lives in that
# harness file.
_SLI_EXCLUDED_ROUTES = frozenset({"/metrics"})


def record_request(method: str, route: str, status: int, seconds: float) -> None:
    """Record one served request: the RED counter and the duration observation.

    Single entry point so the method label is bounded once and the
    observability route is excluded once, for both series rather than one.
    """
    if route in _SLI_EXCLUDED_ROUTES:
        return
    label = method_label(method)
    _request_counts[label, route, status] += 1
    observe_duration(label, route, seconds)


def observe_duration(method: str, route: str, seconds: float) -> None:
    """Record one request duration against (method, route template)."""
    key = (method, route)
    counts = _duration_counts.setdefault(key, [0] * (len(_LATENCY_BUCKETS) + 1))
    index = next(
        (i for i, bound in enumerate(_LATENCY_BUCKETS) if seconds <= bound),
        len(_LATENCY_BUCKETS),
    )
    counts[index] += 1
    observations, total = _duration_totals.get(key, (0, 0.0))
    _duration_totals[key] = (observations + 1, total + seconds)


def duration_snapshot() -> dict[tuple[str, str], tuple[list[int], int, float]]:
    """Per (method, route): per-bucket counts, observation count, summed seconds."""
    snapshot = {}
    for key, counts in _duration_counts.items():
        observations, total = _duration_totals.get(key, (0, 0.0))
        snapshot[key] = (list(counts), observations, total)
    return snapshot


def latency_bucket_bounds() -> tuple[float, ...]:
    """The histogram's upper bounds, excluding the implicit +Inf bucket."""
    return _LATENCY_BUCKETS


def request_counter_snapshot() -> dict[tuple[str, str, int], int]:
    """A copy of the RED counters, for the metrics endpoint to render."""
    return dict(_request_counts)


def reset_request_counters() -> None:
    """Clear every counter. For tests that assert on exact counts."""
    _request_counts.clear()
    _duration_counts.clear()
    _duration_totals.clear()


class CorrelationIdMiddleware:
    """Binds, stamps and logs the Correlation Id for every HTTP request."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    @staticmethod
    def _stamping_send(
        send: Send, request_id: str, scope: Scope, seen: list[int]
    ) -> Send:
        """Wrap `send` so the response start carries the id and is logged."""
        method = str(scope.get("method", "-"))
        path = str(scope.get("path", "-"))

        async def send_with_correlation_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)[_REQUEST_ID_HEADER] = request_id
                status = int(message["status"])
                seen.append(status)
                _access_logger.info("%s %s -> %s", method, path, status)
            await send(message)

        return send_with_correlation_id

    @staticmethod
    def _observe(scope: Scope, started: float, seen: list[int]) -> None:
        """Record the request once, under the matched route template.

        Recorded here rather than at `http.response.start` because the duration
        is only known once the call returns; the status is carried over from the
        response-start message, defaulting to 500 when the app raised before
        sending one.
        """
        record_request(
            str(scope.get("method", "-")),
            route_label(scope),
            seen[0] if seen else 500,
            time.perf_counter() - started,
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started = time.perf_counter()
        inbound = Headers(scope=scope).get(_REQUEST_ID_HEADER.lower())
        request_id = inbound or uuid4().hex
        token = request_id_var.set(request_id)
        redaction_token = begin_redaction_scope()
        seen: list[int] = []
        wrapped_send = self._stamping_send(send, request_id, scope, seen)

        try:
            await self.app(scope, receive, wrapped_send)
            self._observe(scope, started, seen)
        except BaseException:
            self._observe(scope, started, seen)
            # Logged here, while the redaction set and the id are still bound,
            # so the traceback is scrubbed and correlated. Relying on the
            # server's own logger left it unscrubbed and with an empty id --
            # and under TestClient it was never recorded at all.
            _access_logger.exception("unhandled exception serving the request")
            raise  # both contextvars stay bound on purpose -- see module docstring
        else:
            end_redaction_scope(redaction_token)
            request_id_var.reset(token)
