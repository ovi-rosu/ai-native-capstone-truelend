"""Platform-level routes: the health probe and the RED metrics endpoint.

Both are specified in the frozen `specs/design/api-contracts.md` "Operational
endpoints" section and both are attributed to E15-S1.

`/health` returns the contract's `{status, database, version}`. It previously
returned `{"status": "ok"}` alone, which satisfied `E15-S1-AC5` (200 plus a
JSON body) while telling an operator nothing: a probe that never touches its
database reports healthy with Postgres down, which also hollows out
`E15-S2-AC1`'s "all three report healthy".

E15-S1 owns no database access -- the engine arrives with E1-S1 in group B --
so the database check is a **port** here. Until a probe is registered the field
reads `unconfigured`, rather than hardcoding an "ok" this story cannot observe.
E1-S1 registers the real probe when it builds the session factory.

`/metrics` is covered by no acceptance criterion, so nothing forced it to
exist and it returned 404 while `observability.enabled` was true -- leaving the
runtime-SLO sensor permanently unmeasurable. It ships here as contract
compliance rather than AC coverage.
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse
from src.api.middleware import (
    duration_snapshot,
    latency_bucket_bounds,
    request_counter_snapshot,
)
from src.config.settings import Settings

router = APIRouter()

_DatabaseProbe = Callable[[], bool]
_database_probe: _DatabaseProbe | None = None


def register_database_probe(probe: _DatabaseProbe) -> None:
    """Register the database liveness check `/health` should report."""
    global _database_probe
    _database_probe = probe


def reset_database_probe() -> None:
    """Forget any registered probe, restoring the `unconfigured` reading."""
    global _database_probe
    _database_probe = None


def _database_status() -> str:
    if _database_probe is None:
        return "unconfigured"
    try:
        return "ok" if _database_probe() else "down"
    except Exception:  # noqa: BLE001 - a probe must never break the probe
        return "down"


@router.get("/health")
async def get_health() -> dict[str, str]:
    """Liveness probe. No I/O of its own beyond the registered database check."""
    database = _database_status()
    return {
        "status": "ok" if database in {"ok", "unconfigured"} else "degraded",
        "database": database,
        "version": Settings().version,
    }


# Prometheus label values escape backslash, double quote and newline. Without
# this a crafted request path closed the label quote and appended a complete
# forged series: one unauthenticated GET made the SLO sensor report a 99.90%
# error rate against a 1% budget, and the same trick masks a real outage.
_LABEL_ESCAPES = str.maketrans({"\\": r"\\", '"': r"\"", "\n": r"\n"})


def _escape_label(value: str) -> str:
    """Escape a label value per the Prometheus exposition format."""
    return value.translate(_LABEL_ESCAPES)


def _counter_lines() -> list[str]:
    """The RED request counters."""
    lines = [
        "# HELP http_requests_total Total HTTP requests served.",
        "# TYPE http_requests_total counter",
    ]
    for (method, route, status), count in sorted(request_counter_snapshot().items()):
        lines.append(
            f'http_requests_total{{method="{_escape_label(method)}",'
            f'route="{_escape_label(route)}",status="{status:d}"}} {count:d}'
        )
    return lines


def _histogram_lines() -> list[str]:
    """The request-duration histogram, cumulative as the format requires.

    Buckets have to be cumulative for a scraper to compute a quantile: p95 is
    the first bound whose running count reaches 95% of `_count`. Without this
    the declared 500 ms SLO stays unmeasurable -- `slo.p95_ms` was always null.
    """
    bounds = (*latency_bucket_bounds(), float("inf"))
    lines = [
        "# HELP http_request_duration_seconds Request duration in seconds.",
        "# TYPE http_request_duration_seconds histogram",
    ]
    for (method, route), (counts, observations, total) in sorted(duration_snapshot().items()):
        labels = f'method="{_escape_label(method)}",route="{_escape_label(route)}"'
        running = 0
        for bound, count in zip(bounds, counts, strict=True):
            running += count
            le = "+Inf" if bound == float("inf") else f"{bound:g}"
            lines.append(
                f'http_request_duration_seconds_bucket{{{labels},le="{le}"}} {running:d}'
            )
        lines.append(f"http_request_duration_seconds_count{{{labels}}} {observations:d}")
        lines.append(f"http_request_duration_seconds_sum{{{labels}}} {total:.6f}")
    return lines


@router.get("/metrics", response_class=PlainTextResponse)
async def get_metrics() -> PlainTextResponse:
    """RED counters and the request-duration histogram, Prometheus text format."""
    return PlainTextResponse("\n".join(_counter_lines() + _histogram_lines()) + "\n")
