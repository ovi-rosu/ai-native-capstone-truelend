"""E15-S1: structured JSON logging, Correlation Id propagation, PII
redaction and the health probe -- one test per acceptance criterion.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from src.api.app import create_app
from src.config.logging import redact_values
from src.types.errors import AppError
from tests.conftest import ListLogHandler


def test_sensitive_application_values_never_appear_in_any_log_line(
    client: TestClient, log_capture: ListLogHandler
) -> None:
    """E15-S1-AC1: PAN, Aadhaar and salary-doc content are redacted from
    every emitted log line, however they reach the logger."""
    pan = "ABCDE1234F"
    aadhaar = "234123412346"
    salary_doc_content = "SALARY-DOC-BASE64-CONTENT-XYZ"

    with redact_values(pan, aadhaar, salary_doc_content):
        logging.getLogger("app.origination").info(
            "processing application pan=%s aadhaar=%s salary_doc=%s",
            pan,
            aadhaar,
            salary_doc_content,
        )
        response = client.get("/health")

    assert response.status_code == 200
    assert log_capture.lines
    joined = "\n".join(log_capture.lines)
    assert pan not in joined
    assert aadhaar not in joined
    assert salary_doc_content not in joined


def test_redaction_filter_installed_on_every_configured_logger() -> None:
    """E15-S1-AC2: enumerating every configured logger shows the redaction
    filter on 100% of them; a logger registered without it fails the same
    assertion, proving the check is not vacuous."""
    create_app()  # runs configure_logging()

    def _has_redaction_filter(logger_obj: logging.Logger) -> bool:
        from src.config.logging import RedactionFilter

        return any(isinstance(f, RedactionFilter) for f in logger_obj.filters)

    configured_loggers: list[logging.Logger] = [logging.getLogger()]
    for logger_obj in logging.root.manager.loggerDict.values():
        if isinstance(logger_obj, logging.Logger):
            configured_loggers.append(logger_obj)

    assert configured_loggers
    for logger_obj in configured_loggers:
        assert _has_redaction_filter(logger_obj), f"logger {logger_obj.name!r} missing filter"

    unfiltered_logger = logging.Logger("unregistered-probe-logger")
    with pytest.raises(AssertionError):
        assert _has_redaction_filter(unfiltered_logger)


def test_supplied_request_id_header_propagates_to_every_log_line(
    client: TestClient, log_capture: ListLogHandler
) -> None:
    """E15-S1-AC3: every log line emitted while serving a request carrying
    X-Request-ID parses as JSON and carries that same request_id."""
    response = client.get("/health", headers={"X-Request-ID": "req-abc"})

    assert response.status_code == 200
    assert log_capture.lines
    for line in log_capture.lines:
        parsed = json.loads(line)
        assert parsed["request_id"] == "req-abc"


def test_missing_request_id_header_generates_and_echoes_one(
    client: TestClient, log_capture: ListLogHandler
) -> None:
    """E15-S1-AC4: without an inbound X-Request-ID, every request-scoped log
    line carries the same generated non-empty id, and the response echoes
    that same id on the X-Request-ID response header."""
    response = client.get("/health")

    assert response.status_code == 200
    echoed_id = response.headers.get("X-Request-ID")
    assert echoed_id
    assert log_capture.lines
    for line in log_capture.lines:
        parsed = json.loads(line)
        assert parsed["request_id"] == echoed_id


def test_health_endpoint_returns_ok_json_under_one_second(client: TestClient) -> None:
    """E15-S1-AC5: GET /health is 200 with a JSON body, under 1 second."""
    start = time.monotonic()
    response = client.get("/health")
    elapsed = time.monotonic() - start

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert elapsed < 1.0


def test_app_error_is_mapped_to_a_typed_json_response() -> None:
    """Coverage for api/errors.py: AppError is mapped once at the API
    boundary to a JSON body carrying its message, at its status code."""
    app = create_app()

    @app.get("/_test-only-raises")
    def _raise_app_error() -> None:
        raise AppError("boom", status_code=418)

    with TestClient(app, raise_server_exceptions=False) as test_client:
        response = test_client.get("/_test-only-raises")

    assert response.status_code == 418
    assert response.json() == {"error": "boom"}


def test_uvicorn_loggers_do_not_bypass_json_formatting() -> None:
    """E15-S1-AC3: no request-scoped line escapes as plain text.

    `uvicorn` installs its own `dictConfig` with `propagate=False` and its
    own formatters on `uvicorn`, `uvicorn.error` and `uvicorn.access`.
    `configure_logging()` rebuilds only the *root* handler, so under a real
    `uvicorn` run roughly half of the lines for a request were plain text
    with no `request_id` — while the unit suite saw none of it, because
    pytest never applies uvicorn's `dictConfig`. This test applies it first,
    exactly as a real run does.
    """
    import logging.config

    from src.config.logging import configure_logging
    from src.config.settings import Settings
    from uvicorn.config import LOGGING_CONFIG

    logging.config.dictConfig(LOGGING_CONFIG)
    configure_logging(Settings(_env_file=None))

    for name in ("uvicorn", "uvicorn.error"):
        logger_obj = logging.getLogger(name)
        assert logger_obj.handlers == [], f"{name} keeps its own plain-text handler"
        assert logger_obj.propagate is True, f"{name} does not reach the JSON root handler"

    access = logging.getLogger("uvicorn.access")
    assert access.disabled is True, (
        "uvicorn.access must be silenced: its AccessFormatter emits plain text and "
        "the request_id contextvar is already reset by the time it logs, so our own "
        "truelend.access JSON line is the single source of access logging"
    )


def test_exception_tracebacks_are_redacted_and_rendered() -> None:
    """A sensitive value must not escape through the exception path.

    `RedactionFilter` scrubbed only `record.getMessage()`, so a PAN carried in
    an exception reached the sink untouched. The formatter also dropped
    `exc_info` entirely, losing every stack trace in production.
    """
    from src.config.logging import JSONLogFormatter, RedactionFilter

    pan = "ABCDE1234F"
    formatter = JSONLogFormatter()
    filt = RedactionFilter()

    with redact_values(pan):
        try:
            raise ValueError(f"rejected application for pan={pan}")
        except ValueError:
            record = logging.LogRecord(
                name="app.origination",
                level=logging.ERROR,
                pathname=__file__,
                lineno=1,
                msg="application failed",
                args=(),
                exc_info=__import__("sys").exc_info(),
            )
            assert filt.filter(record) is True
            rendered = formatter.format(record)

    assert pan not in rendered, "PAN leaked through the exception path"
    payload = json.loads(rendered)
    assert "ValueError" in payload.get("exception", ""), "stack trace was dropped"


@pytest.mark.parametrize(
    ("registered", "logged"),
    [
        pytest.param("ABCDE1234F", "abcde1234f", id="pan-lowercased"),
        pytest.param("ABCDE1234F", "AbCdE1234f", id="pan-mixed-case"),
        pytest.param("234123412346", "2341 2341 2346", id="aadhaar-spaced"),
        pytest.param("234123412346", "2341-2341-2346", id="aadhaar-dashed"),
    ],
)
def test_redaction_is_case_and_separator_insensitive(registered: str, logged: str) -> None:
    """Redaction matched byte-for-byte, so a reformatted value leaked.

    A PAN logged lowercase, or an Aadhaar rendered in the spaced form people
    actually type, sailed straight past the filter.
    """
    from src.config.logging import JSONLogFormatter, RedactionFilter

    formatter = JSONLogFormatter()
    filt = RedactionFilter()
    with redact_values(registered):
        record = logging.LogRecord(
            name="app.origination",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="applicant value=%s",
            args=(logged,),
            exc_info=None,
        )
        assert filt.filter(record) is True
        rendered = formatter.format(record)

    assert logged not in rendered, f"{logged!r} leaked despite {registered!r} being registered"


_PII_FIELD_NAMES = ("pan", "aadhaar", "salary_doc")


def _modules_referencing_pii() -> list[Path]:
    """Production modules that mention an applicant PII field by name."""
    src_root = Path(__file__).resolve().parents[2] / "src"
    hits: list[Path] = []
    for module in sorted(src_root.rglob("*.py")):
        lowered = module.read_text(encoding="utf-8").lower()
        # The redaction module itself names these fields in its own docstring.
        if module.name == "logging.py":
            continue
        if any(field in lowered for field in _PII_FIELD_NAMES):
            hits.append(module)
    return hits


def test_modules_handling_applicant_pii_enter_a_redaction_scope() -> None:
    """Redaction must not stay opt-in once a PII-accepting endpoint exists.

    `RedactionFilter` only scrubs values a caller registered through
    `redact_values(...)`, and in group A there are no production call sites at
    all: AC1 passes solely because its own test registers the values it then
    asserts absent. When E4-S1 writes `POST /applications`, a handler that
    forgets the scope will log raw PAN and Aadhaar with nothing objecting —
    and VM-001 is a unit-layer row, so no api check would catch it either.

    This test is the missing control. It is intentionally vacuous today (no
    production module names these fields yet) and becomes load-bearing the
    moment origination lands. `test_pii_redaction_control_is_not_vacuous`
    proves the check itself bites.
    """
    offenders = [
        module
        for module in _modules_referencing_pii()
        if "redact_values" not in module.read_text(encoding="utf-8")
    ]
    assert not offenders, (
        "these modules handle applicant PII without entering a redact_values scope: "
        + ", ".join(str(module) for module in offenders)
    )


def test_pii_redaction_control_is_not_vacuous(tmp_path: Path) -> None:
    """The control above must fail on a module that handles PII unredacted."""

    def offends(source: str) -> bool:
        return any(field in source.lower() for field in _PII_FIELD_NAMES) and (
            "redact_values" not in source
        )

    assert offends('def submit(pan: str) -> None:\n    logger.info("pan=%s", pan)\n')
    assert not offends(
        "from src.config.logging import redact_values\n"
        'def submit(pan: str) -> None:\n'
        "    with redact_values(pan):\n"
        '        logger.info("submitting")\n'
    )
    assert not offends("def unrelated(x: int) -> int:\n    return x\n")


def test_redaction_filter_covers_every_logger_under_the_real_server_config() -> None:
    """E15-S1-AC2 under uvicorn's own logging config, not pytest's.

    The existing AC2 test enumerates loggers in a bare pytest process, where
    uvicorn's `dictConfig` has never run — so it reported 100% while the
    running server had `uvicorn` and `uvicorn.access` with no redaction
    filter at all. Applying that config first is what makes the assertion
    mean something.
    """
    import logging.config

    from src.config.logging import RedactionFilter, configure_logging
    from src.config.settings import Settings
    from uvicorn.config import LOGGING_CONFIG

    logging.config.dictConfig(LOGGING_CONFIG)
    configure_logging(Settings(_env_file=None))

    loggers: list[logging.Logger] = [logging.getLogger()]
    loggers.extend(
        logger_obj
        for logger_obj in logging.root.manager.loggerDict.values()
        if isinstance(logger_obj, logging.Logger)
    )
    missing = [
        logger_obj.name
        for logger_obj in loggers
        if not any(isinstance(f, RedactionFilter) for f in logger_obj.filters)
    ]

    assert not missing, f"loggers without a RedactionFilter: {missing}"
