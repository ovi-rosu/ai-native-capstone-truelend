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
    assert response.json() == {"status": "ok"}
    assert elapsed < 1.0
