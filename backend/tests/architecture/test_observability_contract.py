"""E15-S4: the observability contract.

AC1 -- `GET /metrics` exposes a request-duration histogram labelled by method
and route template, so p95 is computable and the 500 ms runtime SLO declared in
`project-manifest.json` stops being unmeasurable (`slo.p95_ms` was always null).

AC2 -- hostile input reaching a log call or a metrics label renders as exactly
one line with no raw control character and no injected series. The `/gate`
review of group A reproduced a crafted path forging counter series, which drove
this project's own SLO sensor to report a 99.90% error rate against a 1% budget
and could equally mask a real outage.
"""

from __future__ import annotations

import json
import logging
import re

from fastapi.testclient import TestClient
from src.api.app import create_app
from src.api.middleware import reset_request_counters

_BUCKET_LINE = re.compile(
    r'^http_request_duration_seconds_bucket\{method="(?P<method>[^"]*)",'
    r'route="(?P<route>[^"]*)",le="(?P<le>[^"]*)"\} (?P<count>\d+)$'
)


def _scrape(paths: list[str]) -> str:
    """Serve `paths`, then return the exposition body."""
    reset_request_counters()
    with TestClient(create_app()) as client:
        for path in paths:
            client.get(path)
        return str(client.get("/metrics").text)


def test_metrics_exposes_a_duration_histogram_labelled_by_method_and_route() -> None:
    """AC1: the histogram exists with the same labels as the counters."""
    body = _scrape(["/health", "/health"])

    assert "# TYPE http_request_duration_seconds histogram" in body
    buckets = [_BUCKET_LINE.match(line) for line in body.splitlines()]
    health = [m for m in buckets if m and m["route"] == "/health"]
    assert health, f"no duration buckets for /health:\n{body}"
    assert all(m["method"] == "GET" for m in health)
    assert any(m["le"] == "+Inf" for m in health), "a histogram needs a +Inf bucket"


def test_histogram_buckets_are_cumulative_and_carry_count_and_sum() -> None:
    """AC1: p95 is only computable from cumulative buckets plus _count."""
    body = _scrape(["/health"])

    observed = [
        (m["le"], int(m["count"]))
        for line in body.splitlines()
        if (m := _BUCKET_LINE.match(line)) and m["route"] == "/health"
    ]
    counts = [count for _, count in observed]
    assert counts == sorted(counts), f"buckets are not cumulative: {observed}"
    assert counts[-1] == 1, "the +Inf bucket must hold every observation"
    assert 'http_request_duration_seconds_count{method="GET",route="/health"} 1' in body
    assert 'http_request_duration_seconds_sum{method="GET",route="/health"}' in body


def test_p95_is_computable_from_the_exposition() -> None:
    """AC1: the whole point -- slo.p95_ms must stop being null.

    Computed the way a scraper would: find the first cumulative bucket whose
    count reaches 95% of the total.
    """
    body = _scrape(["/health"] * 20)

    buckets = [
        (m["le"], int(m["count"]))
        for line in body.splitlines()
        if (m := _BUCKET_LINE.match(line)) and m["route"] == "/health"
    ]
    total = max(count for _, count in buckets)
    assert total == 20

    target = 0.95 * total
    p95_bound = next(le for le, count in buckets if count >= target)
    assert p95_bound, "no bucket satisfied the 95th percentile"
    # A no-I/O health probe must land far under the 500 ms budget.
    assert p95_bound == "+Inf" or float(p95_bound) <= 0.5


def test_histogram_labels_cannot_be_injected_from_a_request_path() -> None:
    """AC2: the histogram inherits the counters' escaping, not just the counters."""
    forged = (
        "/x%22%201%0Ahttp_request_duration_seconds_bucket%7Bmethod%3D%22GET%22%2C"
        "route%3D%22/forged%22%2Cle%3D%22+Inf%22%7D%20999999"
    )
    body = _scrape([forged])

    assert 'route="/forged"' not in body, "a forged histogram series was injected"
    assert "999999" not in body
    for line in body.splitlines():
        if line.startswith("http_request_duration_seconds"):
            assert line.count("{") == 1 and line.count("}") == 1


def test_histogram_cardinality_is_bounded_by_route_template() -> None:
    """AC2: unrouted paths must not mint a label value each."""
    body = _scrape([f"/no-such-{index}" for index in range(25)])

    routes = {
        m["route"]
        for line in body.splitlines()
        if (m := _BUCKET_LINE.match(line))
    }
    assert routes <= {"<unmatched>", "/metrics", "/health"}, f"unbounded labels: {routes}"


def test_hostile_log_input_renders_as_one_control_character_free_line() -> None:
    """AC2: the log-sink half of the same criterion."""
    from src.config.logging import JSONLogFormatter

    hostile = 'x"}\n{"level": "ERROR", "message": "forged"}\r\x00 tail'
    record = logging.LogRecord("app", logging.INFO, "t.py", 1, hostile, (), None)

    rendered = JSONLogFormatter().format(record)

    assert len(rendered.splitlines()) == 1
    assert not any(char in rendered for char in ("\n", "\r", "\x00"))
    assert json.loads(rendered)["logger"] == "app"
