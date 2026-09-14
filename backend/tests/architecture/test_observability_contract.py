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

    # This assertion was inverted, not merely weak: it accepted `+Inf` — which
    # means p95 landed in the *overflow* bucket, slower than the largest bound
    # — while rejecting a finite value over budget. A forced p95 of 11 s, 22x
    # the budget, passed. `+Inf` is the worst outcome, so it must fail first.
    assert p95_bound != "+Inf", (
        "p95 landed in the overflow bucket: slower than the largest bound"
    )
    # A no-I/O health probe must land far under the 500 ms budget.
    assert float(p95_bound) <= 0.5, f"p95 bound {p95_bound}s exceeds the 500 ms budget"


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


def test_escape_label_neutralises_exposition_metacharacters() -> None:
    """The escaping needs a direct test, not only an end-to-end one.

    Mutation-tested: replacing `_escape_label` with the identity function left
    all 104 tests green. The cause was my own pair of fixes interfering — once
    the counters keyed on the matched route template, a crafted path resolved
    to `<unmatched>` and the raw attacker string never reached a label, so the
    integration test passed for the wrong reason and the escaping was
    unprotected. A refactor could have silently reopened the injection.
    """
    from src.api.platform.routes import _escape_label

    # Each metacharacter becomes its escaped two-character form.
    assert _escape_label('a"b') == 'a\\"b'
    assert _escape_label("a\\b") == "a\\\\b"
    assert _escape_label("a\nb") == "a\\nb"

    # The real payload: no bare quote or newline survives, so the crafted text
    # cannot terminate the label and start a new series.
    escaped = _escape_label('x" 1\nhttp_requests_total{route="/forged"} 9')
    assert "\n" not in escaped, "a raw newline could start a forged series"
    assert not re.search(r'(?<!\\)"', escaped), "an unescaped quote could close the label"
    assert escaped.count('\\"') == 3, "all three quotes must be escaped"
    # Unchanged for the ordinary case, so the escaping cannot be "passing" by
    # mangling every label.
    assert _escape_label("/products/{product_code}") == "/products/{product_code}"


def test_metric_label_cardinality_is_bounded_on_the_method_dimension() -> None:
    """CR-301: the route dimension was bounded, the method dimension was not.

    `method` flowed straight from the request into the keys of
    `_request_counts`, `_duration_counts` and `_duration_totals` — all
    process-global, never evicted, behind an unauthenticated /metrics. The
    reviewers measured 3,000 distinct methods producing ~6,000 series and
    22,003 producing 25.3 MB retained. It only looked safe because
    `uvicorn[standard]`'s httptools rejects unknown methods at 400 below the
    ASGI layer — an optional C extension that nothing documents, tests or
    pins, under a middleware that is deliberately server-agnostic.
    """
    from src.api.middleware import (
        duration_snapshot,
        record_request,
        request_counter_snapshot,
        reset_request_counters,
    )

    reset_request_counters()
    for index in range(200):
        record_request(f"BOGUS{index}", "/health", 200, 0.001)

    methods = {method for method, _, _ in request_counter_snapshot()}
    duration_methods = {method for method, _ in duration_snapshot()}

    assert len(methods) == 1, f"unbounded method labels on the counters: {methods}"
    assert len(duration_methods) == 1, (
        f"unbounded method labels on the histogram: {duration_methods}"
    )
    assert methods == {"<other>"}


def test_known_methods_keep_their_own_label() -> None:
    """Bounding must not collapse the methods anyone actually reports on."""
    from src.api.middleware import record_request, request_counter_snapshot, reset_request_counters

    reset_request_counters()
    for method in ("GET", "POST", "PUT", "PATCH", "DELETE"):
        record_request(method, "/health", 200, 0.001)

    methods = {method for method, _, _ in request_counter_snapshot()}
    assert methods == {"GET", "POST", "PUT", "PATCH", "DELETE"}


def test_metrics_scrapes_do_not_count_toward_the_error_rate_denominator() -> None:
    """SEC3-003, partially: a scraper must not dilute its own signal.

    `errorRate` in the harness's prom-parse sums every `http_requests_total`
    series globally, so every request to any route inflates the denominator.
    A frequent scraper therefore dilutes the business error rate purely by
    observing: the reviewers showed a real 50% outage reading 0.0100% and
    passing the 1% budget.

    Excluding the observability endpoint from its own counters removes the
    self-observation component. It does NOT close the finding — any public
    route still contributes, and the real fix is per-route aggregation in
    `.claude/hooks/lib/prom-parse.js`, which is harness machinery.
    """
    from src.api.middleware import request_counter_snapshot

    body = _scrape(["/health", "/health"])

    routes = {route for _, route, _ in request_counter_snapshot()}
    assert "/metrics" not in routes, "the scrape counted itself into the denominator"
    assert "/health" in routes, "real traffic must still be counted"
    assert 'route="/metrics"' not in body


def test_metrics_scrapes_are_excluded_from_the_histogram_too() -> None:
    """GATE-B2: excluding the counter but not the histogram fixed one half.

    The SLO sensor reads errorRate from `http_requests_total` and p95 from
    `http_request_duration_seconds`. Excluding the scrape from only the former
    left a fast scrape dragging p95 down while no longer leaving even a trace
    in the counters: measured p95 of 5 ms against a real business p95 of
    4,875 ms on a 500 ms budget, under-reporting a breach by ~1000x on the one
    metric this story exists to make measurable.
    """
    from src.api.middleware import duration_snapshot

    body = _scrape(["/health", "/health"])

    duration_routes = {route for _, route in duration_snapshot()}
    assert "/metrics" not in duration_routes, "the scrape diluted its own p95"
    assert "/health" in duration_routes, "real traffic must still be timed"
    assert 'route="/metrics"' not in body


def test_p95_guard_rejects_a_breach_instead_of_accepting_the_worst_case() -> None:
    """GATE-B1 regression: the guard must fail on a real breach.

    The original assertion accepted `+Inf` -- the overflow bucket, slower than
    every bound -- while rejecting finite values over budget, so a forced p95 of
    11 s passed. This drives the same computation over a synthetic breach and
    asserts the guard bites.
    """
    from src.api.middleware import (
        duration_snapshot,
        latency_bucket_bounds,
        observe_duration,
        reset_request_counters,
    )

    reset_request_counters()
    for _ in range(20):
        observe_duration("GET", "/slow", 11.0)

    counts, observations, _ = duration_snapshot()[("GET", "/slow")]
    bounds = (*latency_bucket_bounds(), float("inf"))
    threshold = 0.95 * observations

    running = 0
    p95_bound = None
    for bound, count in zip(bounds, counts, strict=True):
        running += count
        if not running < threshold:
            p95_bound = bound
            break

    assert p95_bound == float("inf"), "an 11 s request must land in the overflow bucket"
    # The corrected guard's shape, applied to a breach: it must reject.
    accepted = p95_bound != float("inf") and p95_bound < 0.51
    assert not accepted, "the guard accepted a p95 22x over budget"
