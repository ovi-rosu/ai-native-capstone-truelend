"""E15-S1: the single error envelope mapped at the API boundary.

Shape per specs/design/api-contracts.md: one body for every non-2xx --
{"error": "<ErrorName>", "detail": "<message>", "context": {...}}.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from src.api.app import create_app
from src.types.errors import AppError


def test_app_error_is_mapped_to_a_typed_json_response() -> None:
    """Coverage for api/errors.py: AppError is mapped once at the API
    boundary to a JSON body carrying its message, at its status code."""
    from src.api.app import build_fastapi_app

    inner = build_fastapi_app()

    @inner.get("/_test-only-raises")
    def _raise_app_error() -> None:
        raise AppError("boom", status_code=418)

    with TestClient(create_app(inner), raise_server_exceptions=False) as test_client:
        response = test_client.get("/_test-only-raises")

    assert response.status_code == 418
    # Envelope per api-contracts.md, not the old {"error": <message>} shape.
    assert response.json() == {"error": "AppError", "detail": "boom", "context": {}}
def test_error_response_matches_the_frozen_contract_envelope() -> None:
    """Defect 1: the landed envelope contradicts the frozen contract.

    `specs/design/api-contracts.md:27` mandates one shape for every non-2xx
    response — `{"error": "<ErrorName>", "detail": "<message>",
    "context": {...}}` — but the handler emitted `{"error": exc.message}`,
    putting the *message* where the error *name* belongs and omitting both
    other fields. The contract is frozen, so the code is what is wrong.
    E4-S4-AC2 needs `threshold_kind` and `configured_value` in `context`.
    """
    from src.api.app import build_fastapi_app, create_app

    inner = build_fastapi_app()

    @inner.get("/_test-only-app-error")
    def _raise_app_error() -> None:
        raise AppError(
            "declared income is below the minimum",
            status_code=422,
            context={"threshold_kind": "min_income", "configured_value": "25000.00"},
        )

    with TestClient(create_app(inner), raise_server_exceptions=False) as test_client:
        response = test_client.get("/_test-only-app-error")

    assert response.status_code == 422
    assert response.json() == {
        "error": "AppError",
        "detail": "declared income is below the minimum",
        "context": {"threshold_kind": "min_income", "configured_value": "25000.00"},
    }
def test_error_envelope_context_defaults_to_empty() -> None:
    """An error raised without context still ships all three keys."""
    from src.api.app import build_fastapi_app, create_app

    inner = build_fastapi_app()

    @inner.get("/_test-only-bare-error")
    def _raise_bare() -> None:
        raise AppError("boom", status_code=418)

    with TestClient(create_app(inner), raise_server_exceptions=False) as test_client:
        response = test_client.get("/_test-only-bare-error")

    assert response.status_code == 418
    assert response.json() == {"error": "AppError", "detail": "boom", "context": {}}
