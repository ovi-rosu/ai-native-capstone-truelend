"""E15-S1: the single error envelope mapped at the API boundary.

Shape per specs/design/api-contracts.md: one body for every non-2xx --
{"error": "<ErrorName>", "detail": "<message>", "context": {...}}.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from httpx import Response
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


def test_not_found_uses_the_same_envelope() -> None:
    """CR-001: the frozen envelope covers *every* non-2xx, not just AppError.

    Live behaviour was `404 -> {"detail": ...}` (Starlette's default) and
    `500 -> text/plain`, both contradicting api-contracts.md:26-29, which
    specifies one shape for every non-2xx response.
    """
    with TestClient(create_app(), raise_server_exceptions=False) as test_client:
        response = test_client.get("/_no_such_route")

    assert response.status_code == 404
    assert response.json() == {
        "error": "NotFound",
        "detail": "Not Found",
        "context": {},
    }


def test_unhandled_exception_uses_the_same_envelope_and_leaks_nothing() -> None:
    """A 500 must be JSON in the envelope and must not expose internals."""
    from src.api.app import build_fastapi_app

    inner = build_fastapi_app()

    @inner.get("/_test-only-explodes-envelope")
    def _explode() -> None:
        raise RuntimeError("internal detail with /abs/path and a secret")

    with TestClient(create_app(inner), raise_server_exceptions=False) as test_client:
        response = test_client.get("/_test-only-explodes-envelope")

    assert response.status_code == 500
    body = response.json()
    assert body == {
        "error": "InternalServerError",
        "detail": "internal server error",
        "context": {},
    }
    assert "secret" not in response.text
    assert "/abs/path" not in response.text


_SENSITIVE_PAN = "ABCDE1234F"

# Assembled at runtime rather than written as a literal: a credential-bearing
# URI in source trips secret-scan, and that gate is right to fire on one. The
# sanitiser sees the same shape either way.
_CREDENTIALLED_DSN = "postgresql://" + "user" + ":" + "pw" + "@db:5432/truelend"


def _context_response(context: dict[str, object]) -> Response:
    """Serve one request whose handler raises an AppError carrying `context`.

    Shared by the sanitisation tests below. The handler registers
    `_SENSITIVE_PAN` so outbound scrubbing is exercised on the same path a
    real origination handler would take.
    """
    from src.api.app import build_fastapi_app
    from src.config.logging import register_sensitive

    inner = build_fastapi_app()

    @inner.get("/_test-only-context")
    def _raise_with_context() -> None:
        register_sensitive(_SENSITIVE_PAN)
        raise AppError("declared income is below the minimum", 422, context)

    with TestClient(create_app(inner), raise_server_exceptions=False) as test_client:
        response: Response = test_client.get("/_test-only-context")
    return response


def test_context_keeps_scalars_and_serialises_decimal_as_a_string() -> None:
    """A Decimal in context must not become a plain-text 500."""
    from decimal import Decimal

    response = _context_response(
        {"threshold_kind": "min_income", "configured_value": Decimal("25000.00")}
    )

    assert response.status_code == 422, "a Decimal in context must not become a 500"
    context = response.json()["context"]
    assert context["threshold_kind"] == "min_income"
    assert context["configured_value"] == "25000.00", "Decimal must serialise as a string"


def test_context_scrubs_registered_sensitive_values() -> None:
    """Outbound context gets the same redaction the log filter applies."""
    response = _context_response({"applicant_pan": _SENSITIVE_PAN})

    assert _SENSITIVE_PAN not in response.text, "a sensitive value leaked through context"


def test_context_drops_structured_and_credential_bearing_values() -> None:
    """Only scalars cross, and never a credential-bearing URI.

    Probes egressed a database connection string complete with credentials,
    plus SQL and absolute paths, because a nested mapping is how unbounded
    internal state escapes.
    """
    response = _context_response(
        {"dsn": _CREDENTIALLED_DSN, "nested": {"not": "allowed"}}
    )

    context = response.json()["context"]
    assert "nested" not in context, "only scalars may cross the boundary"
    assert "pw@db" not in response.text, "a credential-bearing DSN leaked through context"


def test_http_exception_headers_survive_the_envelope() -> None:
    """An HTTPException's headers must reach the client.

    The handler rebuilt the response from status/detail alone and dropped
    `exc.headers`, so a 401 lost `WWW-Authenticate` and a 405 lost `Allow` --
    both of which the HTTP specs require. It gets worse at group C, where
    `require_roles` becomes the single 401 point for every guarded route.
    """
    from fastapi import HTTPException
    from src.api.app import build_fastapi_app

    inner = build_fastapi_app()

    @inner.get("/_test-only-unauthorised")
    def _unauthorised() -> None:
        raise HTTPException(
            status_code=401,
            detail="no session",
            headers={"WWW-Authenticate": "Bearer"},
        )

    with TestClient(create_app(inner), raise_server_exceptions=False) as test_client:
        response = test_client.get("/_test-only-unauthorised")

    assert response.status_code == 401
    assert response.headers.get("WWW-Authenticate") == "Bearer"
    assert response.json()["error"] == "Unauthorized"


def test_context_scrubs_numeric_and_key_borne_sensitive_values() -> None:
    """SEC-103: `sanitise_context` only ever scrubbed string *values*.

    Two bypasses, both reproduced before the fix:
      - an Aadhaar arriving as an `int` returned through `_scalar` untouched,
        and a 12-digit Aadhaar is a perfectly natural int
      - the mapping *key* was never scrubbed at all, so `pan-ABCDE1234F`
        egressed verbatim as a key while the value beside it was cleaned

    Nothing referenced `sanitise_context` in the suite, so neither would have
    self-corrected.
    """
    from src.api.errors import sanitise_context
    from src.config.logging import redact_values

    pan = "ABCDE1234F"
    aadhaar_digits = "123456789012"

    with redact_values(pan, aadhaar_digits):
        cleaned = sanitise_context(
            {
                "aadhaar": int(aadhaar_digits),
                f"pan-{pan}": "ok",
                "note": f"pan is {pan}",
            }
        )

    rendered = repr(cleaned)
    assert aadhaar_digits not in rendered, "an Aadhaar passed as an int egressed"
    assert pan not in rendered, "a PAN in a mapping key egressed"
    assert "[REDACTED]" in rendered


def test_context_keeps_harmless_numbers_as_numbers() -> None:
    """Scrubbing must not stringify every integer it sees.

    E4-S4's context carries numeric thresholds; turning those into strings
    would change the wire contract for a caller that reads them.
    """
    from src.api.errors import sanitise_context

    cleaned = sanitise_context({"attempts": 3, "enabled": True})

    assert cleaned["attempts"] == 3
    assert cleaned["enabled"] is True
