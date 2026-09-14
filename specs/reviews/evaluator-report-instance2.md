# Evaluator report — instance 2 of 3 (independent)

**Verdict: FAIL** · `failure_layer: api` · group A · contract `sprint-contracts/A.json` (read-only)
Runtime mode, `verification.mode: local`, target `http://127.0.0.1:8000`.
Evidence ledger: `specs/reviews/evaluator-evidence-instance2.json`.

This is one vote of three. I reached it without reference to the other instances, and
deliberately against the context pack's framing where the evidence disagreed with it.

## Health check

`GET http://127.0.0.1:8000/health` -> `200 {"status":"ok"}`, `x-request-id` echoed.
App confirmed up before any check; no restart needed.

## Per-api_check results

| id | matrix | expected | measured | verdict |
|---|---|---|---|---|
| QA-VM-003 | VM-003 | 200 + **100%** of log lines emitted while serving parse as JSON with `request_id == req-abc` | 200; **1 of 2 lines (50.0%)**; deterministic on 3/3 trials | **FAIL** |
| QA-VM-004 | VM-004 | 200 + every request-scoped log line carries the same generated non-empty `request_id`, echoed in the response | 200; one distinct id `bf591e69...`, non-empty, matches the echoed header | PASS |
| QA-VM-005 | VM-005 | 200 + JSON body + response time under 1 s | 200, `application/json`, body parses; 5 samples, max 66 ms, p95 ~3 ms | PASS |

## The contested item: my independent ruling on QA-VM-003 — **FAILED**

Not "partially met". Failed.

I drove real traffic and read the log files with an exact before/after line-offset window,
so the captured set is precisely the lines emitted while serving that request:

```
{"timestamp": "2026-09-14T06:39:11.439688+00:00", "level": "INFO", "logger": "truelend.access",
 "message": "GET /health -> 200", "request_id": "req-abc"}
INFO:     127.0.0.1:52936 - "GET /health HTTP/1.1" 200 OK
```

Two lines. One parses as JSON and carries `request_id == req-abc`. One does not parse as JSON
and carries no `request_id` at all. That is 50.0%, reproduced identically on 3 of 3 trials with
a 2 s flush wait. The contract's wording is `100% of the log lines emitted while serving`. 50 is
not 100.

**Why I did not accept the "uvicorn is third-party, not our log lines" reading.** Three reasons,
in increasing order of weight.

1. *The contract admits no carve-out.* It says "100% of the log lines emitted while serving",
   not "100% of the application's log lines". Compare QA-VM-004, which the same author scoped
   narrowly and explicitly to "every **request-scoped** log line" — and which I therefore passed
   on exactly that narrower reading. The drafter demonstrably knew how to write the narrow form
   and chose the broad form here. Reading the narrow form into VM-003 rewrites a frozen contract.

2. *The implementation's own position contradicts the carve-out.* E15-S1-AC2 requires the
   redaction filter on "every configured logger", and `_install_redaction_filter_everywhere()`
   installs it on `uvicorn`, `uvicorn.error` and `uvicorn.access` — I confirmed this by runtime
   introspection. So the implementation treats uvicorn's loggers as configured loggers when that
   earns an AC pass. It cannot also treat them as out-of-scope third-party noise when they cost
   one. Pick one.

3. *The gap is load-bearing, not cosmetic — and I proved it.* See B2-02 below. The same
   propagation gap that makes the access line non-JSON also makes it bypass the app's formatter
   entirely, and I got applicant PII into the log sink in cleartext through it. A contract clause
   whose violation leaks PAN and Aadhaar is not a technicality.

**Root cause, located precisely.** Reproducing the real CLI startup path in-process
(`uvicorn.Config` applies `LOGGING_CONFIG` via `dictConfig`) gives:

```
{"name": "",               "propagate": true,  "handlers": [["StreamHandler", "JSONLogFormatter", ["RedactionFilter"]]]}
{"name": "uvicorn.access", "propagate": false, "handlers": [["StreamHandler", "AccessFormatter",  []]]}
```

`configure_logging()` clears and replaces only the **root** handler. `uvicorn.access` keeps
`propagate=False` and its own `AccessFormatter`, so its records never reach `JSONLogFormatter`.
The fix is narrow and in-scope for E15-S1: clear the uvicorn loggers' handlers and let them
propagate to root (or bind `JSONLogFormatter` to them) inside `configure_logging()`.

## Group A acceptance criteria

| AC | Verdict | Basis |
|---|---|---|
| E15-S1-AC1 | pass *(with block-level finding)* | unit layer is the designated evidence per `test-plan.md`; test passes. See B2-02. |
| E15-S1-AC2 | pass | runtime introspection: 12 named loggers, **0** uncovered by a `RedactionFilter`. |
| E15-S1-AC3 | **FAIL** | same defect as QA-VM-003. |
| E15-S1-AC4 | pass | verified live. |
| E15-S1-AC5 | pass | verified live, 66 ms worst of 5. |
| E9-S1-AC1 | pass | every constructor and operator yields `Decimal` exponent `-2`; `Money(1.5)` raises `InvalidMoneyAmountError`. |
| E9-S1-AC2 | pass | 18/18 architecture tests, incl. float-scalar rejection and a randomized triple sweep. |
| E9-S1-AC3 | pass | `decimal.js` throughout; 0 JS `number` arithmetic, 0 `parseFloat`, 0 `Number()`, 0 `Math.*`, 0 `any`. |
| E11-S1-AC1 | pass | `classify_by_days_past_due(35)` -> `DPD-30`. |
| E11-S1-AC2 | pass | independent 0..400 sweep: 401/401 classified, exactly 5 buckets, every range contiguous, no gap/overlap. |
| E11-S1-AC3 | pass | due-today and future-due both `CURRENT`; `dpd=0` `CURRENT`. |
| E11-S1-AC4 | pass | bare `StrEnum` member; no fee/penal/charge attribute. |

Ladder measured independently: `CURRENT 0-29 · DPD-30 30-59 · DPD-60 60-89 · DPD-90 90-179 · NPA 180+`.
Matches D3 exactly. Negative input raises `ValueError` rather than silently bucketing.

## Deterministic suites — re-run by me, not self-reported

| Command | Exit | Result |
|---|---|---|
| `cd backend && uv run pytest -q` | 0 | 42 passed |
| `cd backend && uv run mypy src/` | 0 | no issues, 12 source files |
| `cd backend && uv run ruff check .` | 0 | all checks passed |
| `cd frontend && npm test` | 0 | 11 passed |
| `cd frontend && npm run typecheck` | 0 | clean |
| `cd frontend && npm run lint` | 0 | clean |

All six reproduce the context pack's claims. No discrepancy.

## BLOCK findings

### B2-01 — QA-VM-003 / E15-S1-AC3 not met (api)

As above. 50% against a literal 100% requirement, deterministic.
Fix in `backend/src/config/logging.py`.

### B2-02 — PII reaches the log sink in cleartext; redaction is opt-in with zero production opt-ins (security)

This is my most consequential finding and I do not believe it is in the context pack.

```
GET /health?pan=ABCDE1234F&aadhaar=123456789012&salary=95000
-> INFO:  127.0.0.1:62890 - "GET /health?pan=ABCDE1234F&aadhaar=123456789012&salary=95000 HTTP/1.1" 200 OK
```

PAN, Aadhaar and a salary figure, verbatim, in the log sink. The app's own `truelend.access`
JSON line correctly omits the query string; uvicorn's access line does not, and it bypasses the
formatter for the reason established above.

The deeper issue is the redaction design. `RedactionFilter.filter()` is:

```python
sensitive_values = _sensitive_values.get()
if not sensitive_values:
    return True          # <-- no-op
```

It redacts **only** values explicitly registered in the current context via the
`redact_values(...)` context manager. It knows no PAN or Aadhaar pattern. And
`grep -rn redact_values backend/src/` returns **zero callers** — only the definition and a
docstring. I demonstrated both halves: the identical log call leaks PAN/Aadhaar/salary without
the context manager and redacts with it.

So E15-S1-AC2's "filter installed on 100% of loggers" is literally true and confers no default
protection. And AC1's pass is achieved by a test that itself wraps the emission in
`redact_values(pan, aadhaar, salary_doc_content)` — registering the very values it then asserts
absent. I am not calling AC1 failed, because `test-plan.md` designates unit as its evidence layer
and no endpoint accepts a payload until E4-S1. But I record that the AC as currently proven does
not establish the property the story claims, and that the live surface already violates E15-S1's
unqualified `scope_out`: *"must not write applicant PAN, Aadhaar or salary-document content to
any log sink."*

Severity high: PAN and Aadhaar are regulated identifiers, the leak is unauthenticated and
remote, and every future endpoint inherits the default-off behaviour.

## Non-blocking findings

- **B2-03 (major, security)** — `X-Request-ID` has no length cap, allow-list or truncation. A
  **60,000-character** id returned 200 with all 60,000 chars in the `x-request-id` response
  header *and* all 60,000 in the JSON log field; 4 000 / 8 000 / 16 000 / 60 000 all accepted
  verbatim. Roughly 2000x log amplification per unauthenticated request. Confirming the pack's
  item 2, I also found the injection half **mitigated**: raw control characters are rejected by
  h11 with 400, percent-encoded CRLF is not decoded, and `JSONLogFormatter` correctly escapes a
  `"}{evil":"1` payload — so there is no CRLF header injection and no JSON log injection. The
  residual risk is volume and header bloat, not injection.
- **B2-04 (minor, design)** — `classify()` and `classify_by_days_past_due()` are exported from
  `backend/src/config/delinquency.py`; `backend/src/types/delinquency.py` holds only the enum.
  E11-S1 bundle operation 2 and the story's `Layer: Types` both place the classifier in Types.
  Import direction is legal (Config may depend on Types) so this is **not** a layering violation,
  but the delivered structure diverges from the frozen bundle.
- **B2-05 (minor, security)** — `/docs` and `/openapi.json` served unauthenticated; currently
  disclose only `/health` plus title/version. `/docs` pulls swagger-ui from `cdn.jsdelivr.net`.
- **B2-06 (minor, infrastructure)** — two uvicorn processes wrote to one log file (line 4 is
  `[Errno 10048]` bind failure); line 7 carries ~1000 leading spaces before a valid JSON record.
  Harness/operational, not group A product code, but a naive parser sees a padded line.
- **B2-07 (minor, design)** — `request_id` is `""` on non-request-scoped lines rather than null
  or omitted.

## Architecture spot-checks (all clean)

Layering verified by import inspection: `types/*` import nothing from other layers;
`config/delinquency.py` -> `src.types.delinquency`; `api/*` -> `src.config.*` / `src.types.*`.
One-way only, no violations, no UI->backend import. All 13 changed source files are well inside
the 300-line file cap (largest: `money.py` at 105).
D-G verified end to end at runtime: `MoneyField` emits a **quoted 2dp string** on the wire
(`{"amount":"1234.50"}`), the serializer lives in exactly one module, and float is rejected on
both sides.

## Performance ratchet

No recorded baseline exists (group A is the first landed group), so per the ratchet rule a
missing baseline is **WARN, not FAIL**. `GET /health`: max 66 ms, p95 ~3 ms, against the
manifest's 500 ms budget. No regression measurable. Not a contributor to this verdict.

## Scope discipline

I did not edit `sprint-contracts/**`, `project-manifest.json`, or `specs/design/**`. I did not
write `specs/reviews/evaluator-report.md`, `specs/reviews/evaluator-evidence.json`, or
`features.json` — instance 1 owns those. I did not approve or merge. The contract declares no
`playwright_checks`, `design_checks` or `accessibility_checks`, so there were zero contracted
browser checks; I used no browser tool and report no browser or accessibility layer as passed.

One brief second uvicorn bound to port 8011 in-process to introspect logger state under the real
`LOGGING_CONFIG`; it was shut down and never served external traffic.
