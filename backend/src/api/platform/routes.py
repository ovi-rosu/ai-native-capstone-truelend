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
from src.api.middleware import request_counter_snapshot
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


@router.get("/metrics", response_class=PlainTextResponse)
async def get_metrics() -> PlainTextResponse:
    """RED request counters in Prometheus text exposition format."""
    lines = [
        "# HELP http_requests_total Total HTTP requests served.",
        "# TYPE http_requests_total counter",
    ]
    for (method, route, status), count in sorted(request_counter_snapshot().items()):
        lines.append(
            f'http_requests_total{{method="{_escape_label(method)}",'
            f'route="{_escape_label(route)}",status="{status:d}"}} {count:d}'
        )
    return PlainTextResponse("\n".join(lines) + "\n")
