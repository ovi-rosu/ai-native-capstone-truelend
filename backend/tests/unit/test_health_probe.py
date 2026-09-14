"""E15-S1: the health probe (AC5)."""

from __future__ import annotations

import time

from fastapi.testclient import TestClient


def test_health_endpoint_returns_ok_json_under_one_second(client: TestClient) -> None:
    """E15-S1-AC5: GET /health is 200 with a JSON body, under 1 second."""
    start = time.monotonic()
    response = client.get("/health")
    elapsed = time.monotonic() - start

    assert response.status_code == 200
    # AC5 asks for 200, a JSON body and sub-second timing -- not one exact
    # shape. Pinning the whole body here made this test fail when the probe
    # grew the `database` and `version` fields the frozen contract requires;
    # `test_health_reports_the_contract_shape` owns the shape assertion.
    assert isinstance(response.json(), dict)
    assert response.json()["status"] == "ok"
    assert elapsed < 1.0


def test_health_reports_the_contract_shape() -> None:
    """The frozen contract specifies `{status, database, version}`.

    The landed probe returned `{"status": "ok"}` only. E15-S1-AC5 is satisfied
    by 200-plus-JSON either way, but a probe that never touches its database
    reports healthy with Postgres down -- which also hollows out E15-S2-AC1's
    "all three report healthy". api-contracts.md is frozen, so the code is the
    stale side.
    """
    from src.api.app import create_app

    with TestClient(create_app()) as test_client:
        response = test_client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"status", "database", "version"}
    assert body["status"] == "ok"
    assert body["version"]


def test_health_reports_the_database_probe_result() -> None:
    """`database` reflects a registered probe, not a hardcoded "ok".

    E15-S1 owns no database access -- the engine arrives with E1-S1 in group B
    -- so the probe is a port here. Until one is registered the field reads
    `unconfigured` rather than claiming health this story cannot observe.
    """
    from src.api.app import create_app
    from src.api.platform.routes import register_database_probe, reset_database_probe

    with TestClient(create_app()) as test_client:
        reset_database_probe()
        assert test_client.get("/health").json()["database"] == "unconfigured"

        register_database_probe(lambda: True)
        assert test_client.get("/health").json()["database"] == "ok"

        register_database_probe(lambda: False)
        down = test_client.get("/health")
        assert down.json()["database"] == "down"
        assert down.json()["status"] == "degraded"
        reset_database_probe()


def test_metrics_endpoint_exposes_red_counters() -> None:
    """`GET /metrics` is in the frozen contract but returned 404.

    It is assigned to E15-S1 and no acceptance criterion covers it, so nothing
    forced it to exist and the runtime-SLO sensor was permanently
    unmeasurable. RED counters labelled method, route and status.
    """
    from src.api.app import create_app

    with TestClient(create_app()) as test_client:
        test_client.get("/health")
        response = test_client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    body = response.text
    assert "http_requests_total" in body
    assert 'method="GET"' in body
    assert 'route="/health"' in body
    assert 'status="200"' in body


def test_metrics_labels_cannot_be_injected_from_a_request_path() -> None:
    """A crafted path must not forge a counter line.

    The route label was rendered from `scope["path"]` verbatim, so one
    percent-encoded GET closed the label quote and appended a fully-formed
    series. Running this project's own SLO sensor against the poisoned
    endpoint reported a 99.90% error rate against a 1% budget -- and the same
    trick masks a real outage. Prometheus label values must be escaped.
    """
    from src.api.app import create_app
    from src.api.middleware import reset_request_counters

    reset_request_counters()
    forged = (
        "/x%22%201%0Ahttp_requests_total%7Bmethod%3D%22GET%22%2C"
        "route%3D%22/forged%22%2Cstatus%3D%22500%22%7D%20999999"
    )
    with TestClient(create_app()) as test_client:
        test_client.get(forged)
        body = test_client.get("/metrics").text

    assert 'route="/forged"' not in body, "a forged series was injected"
    assert "999999" not in body, "an attacker-supplied counter value was rendered"
    for line in body.splitlines():
        if line.startswith("http_requests_total"):
            assert line.count("{") == 1 and line.count("}") == 1


def test_metrics_cardinality_is_bounded_by_route_not_path() -> None:
    """Unmatched paths must collapse to one series.

    Keying on the raw path let 60,000 requests from a single keep-alive
    connection retain 28.2 MB permanently. The matched route template is the
    bounded key; anything unrouted shares one bucket.
    """
    from src.api.app import create_app
    from src.api.middleware import request_counter_snapshot, reset_request_counters

    reset_request_counters()
    with TestClient(create_app()) as test_client:
        for index in range(25):
            test_client.get(f"/no-such-route-{index}")

    routes = {route for _, route, _ in request_counter_snapshot()}
    assert len(routes) == 1, f"unmatched paths created {len(routes)} series: {routes}"


def test_metrics_uses_the_route_template_for_matched_requests() -> None:
    """A matched request is labelled with its route template."""
    from src.api.app import create_app
    from src.api.middleware import request_counter_snapshot, reset_request_counters

    reset_request_counters()
    with TestClient(create_app()) as test_client:
        test_client.get("/health")

    assert any(route == "/health" for _, route, _ in request_counter_snapshot())
