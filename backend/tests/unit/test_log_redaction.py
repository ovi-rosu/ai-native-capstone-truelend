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
# Any module naming a PII field must reach redaction through one of these.
_REDACTION_ENTRYPOINTS = ("redact_values", "register_sensitive", "scrub_text")
def _modules_referencing_pii() -> list[Path]:
    """Production modules that mention an applicant PII field by name."""
    src_root = Path(__file__).resolve().parents[2] / "src"
    hits: list[Path] = []
    for module in sorted(src_root.rglob("*.py")):
        lowered = module.read_text(encoding="utf-8").lower()
        # The modules that *implement* redaction name these fields in their
        # own docstrings; they are the control, not a subject of it.
        if module.name in {"logging.py", "middleware.py"}:
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
        if not any(
            entrypoint in module.read_text(encoding="utf-8")
            for entrypoint in _REDACTION_ENTRYPOINTS
        )
    ]
    assert not offenders, (
        "these modules handle applicant PII without entering a redact_values scope: "
        + ", ".join(str(module) for module in offenders)
    )
def test_pii_redaction_control_is_not_vacuous(tmp_path: Path) -> None:
    """The control above must fail on a module that handles PII unredacted."""

    def offends(source: str) -> bool:
        return any(field in source.lower() for field in _PII_FIELD_NAMES) and not any(
            entrypoint in source for entrypoint in _REDACTION_ENTRYPOINTS
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
@pytest.mark.parametrize(
    "value",
    [
        pytest.param("A-A-A-A-A-A-A-A", id="dashes-in-value"),
        pytest.param("SALARY DOC CONTENT XYZ", id="spaces-in-value"),
        pytest.param("SALARY-DOC-BASE64-CONTENT-XYZ", id="real-salary-doc-shape"),
    ],
)
def test_redaction_pattern_is_not_exponential_on_separator_bearing_values(value: str) -> None:
    r"""SEC-001: the tolerant pattern must not backtrack catastrophically.

    `_redaction_pattern` joined every character with an unbounded `[\s\-]*`.
    When the registered value *itself* contains a separator — and the real
    salary-document fixture does — the quantifier and the literal overlap, so
    a separator-heavy haystack can be partitioned combinatorially. The gate
    measured 0.58 -> 314 ms for growing input and 199 s at length 40.

    Bounding the run, and matching separator-bearing values literally rather
    than tolerantly, removes the ambiguity outright.
    """

    from src.config.logging import _redaction_pattern

    pattern = _redaction_pattern(value)

    # Structural, not a stopwatch: an unbounded `[...]*` between two atoms is
    # what makes the partitioning combinatorial, so its absence IS the property.
    # A timing threshold alone passes or fails on machine speed.
    assert "]*" not in pattern.pattern, (
        f"unbounded separator quantifier still present: {pattern.pattern!r}"
    )

    # Behavioural backstop for the same property.
    haystack = ("- " * 40) + "x"
    started = time.perf_counter()
    pattern.search(haystack)
    elapsed_ms = (time.perf_counter() - started) * 1000
    assert elapsed_ms < 50, f"pattern took {elapsed_ms:.1f} ms, backtracking is not bounded"
def test_redaction_survives_an_exception_escaping_the_registration_scope() -> None:
    """PII must not leak once the exception leaves the handler's scope.

    Five reviewers found this independently and it was demonstrated live:
    `"exception": "...pan=ABCDE1234F..."` on `uvicorn.error` with an empty
    `request_id`. `redact_values` tore its registration down on `__exit__`,
    so by the time the traceback propagated out of the app and the server
    logged it, nothing was registered and nothing was scrubbed.

    Registration is now request-scoped: `register_sensitive` adds without
    tearing down, and the correlation middleware owns the lifetime.
    """
    from src.api.app import build_fastapi_app, create_app

    # Imported at test scope, not inside the handler: a missing symbol must
    # fail this test outright rather than becoming an ImportError traceback
    # that happens to contain no PAN and so passes vacuously.
    from src.config.logging import register_sensitive

    pan = "ABCDE1234F"
    inner = build_fastapi_app()

    @inner.get("/_test-only-leaks-on-raise")
    def _leak() -> None:
        register_sensitive(pan)
        raise ValueError(f"rejected application for pan={pan}")

    handler = ListLogHandler()
    from src.config.logging import JSONLogFormatter, RedactionFilter

    handler.setFormatter(JSONLogFormatter())
    handler.addFilter(RedactionFilter())
    root = logging.getLogger()
    root.addHandler(handler)
    try:
        with TestClient(create_app(inner), raise_server_exceptions=False) as test_client:
            test_client.get("/_test-only-leaks-on-raise", headers={"X-Request-ID": "req-leak"})
    finally:
        root.removeHandler(handler)

    joined = "\n".join(handler.lines)
    # Prove the intended exception really reached a sink, redacted, rather
    # than some other failure keeping the PAN out of the buffer by accident.
    assert "rejected application" in joined, "the handler exception never reached a sink"
    assert "[REDACTED]" in joined, "the registered value was not scrubbed"
    assert pan not in joined, "PAN leaked after the registration scope exited"
