# Evaluator report — story group A — INSTANCE 3 of 3

| Field | Value |
|---|---|
| Verdict (functional) | **PASS** |
| Tree evaluated | `f4abd41` "fix: close CR-003 and align the error envelope with the frozen contract" |
| Branch | `feat/harness-scaffold-and-planning` |
| Contract | `sprint-contracts/A.json` (frozen) — 3 `api_checks`, 0 `playwright_checks`, 0 `design_checks`, no `accessibility_checks` |
| Stories | E15-S1, E9-S1, E11-S1 |
| Verification mode | `local` (Docker not installed; no `docker compose` attempted) |
| Runtime | `uv run uvicorn src.api.app:app --port 8002`, base url `http://localhost:8002`, stdout+stderr captured to a file for the whole session |
| Evaluated at | 2026-09-14T10:35–10:40Z |
| Instance isolation | Own uvicorn on port 8002 only. No stored verdict under `specs/reviews/` was read for its verdict; all evidence below was produced in this session. |

The uvicorn process was killed at the end of the run and the temporary capture
directory (`backend/.eval-i3/`) removed, so the verbatim log lines are quoted
inline below rather than cited as a path.

## Layer 1 — API checks (frozen contract)

Health-check retry: `GET /health` returned 200 on the first attempt after boot.

### QA-VM-003 / VM-003 — PASS

`GET /health` with `X-Request-ID: req-abc`.

```
status=200   content-type: application/json   x-request-id: req-abc
body: {"status":"ok"}
log lines emitted while serving (1):
{"timestamp": "2026-09-14T10:39:49.002202+00:00", "level": "INFO", "logger": "truelend.access", "message": "GET /health -> 200", "request_id": "req-abc"}
```

- Status 200 — yes.
- 100% of the lines emitted while serving parse as JSON — yes (1 of 1).
- Each carries `request_id == "req-abc"` — yes.
- Whole-session log purity, independently checked with `json.loads` over every
  non-empty line of the captured stream: **53 lines, 0 non-JSON**.

The commit's claim that uvicorn's *own* loggers are routed through the root JSON
formatter was verified rather than trusted. The four startup lines are JSON with
`logger: "uvicorn.error"`:

```
{"timestamp": "...", "level": "INFO", "logger": "uvicorn.error", "message": "Started server process [28276]", "request_id": ""}
{"timestamp": "...", "level": "INFO", "logger": "uvicorn.error", "message": "Waiting for application startup.", "request_id": ""}
{"timestamp": "...", "level": "INFO", "logger": "uvicorn.error", "message": "Application startup complete.", "request_id": ""}
{"timestamp": "...", "level": "INFO", "logger": "uvicorn.error", "message": "Uvicorn running on http://127.0.0.1:8002 (Press CTRL+C to quit)", "request_id": ""}
```

A protocol-level rejection (raw socket sending control characters in the header)
also stayed JSON, which is the path most likely to have escaped the formatter:

```
{"timestamp": "...", "level": "WARNING", "logger": "uvicorn.error", "message": "Invalid HTTP request received.", "request_id": ""}
```

`uvicorn.access` emitted no separate plaintext line at any point in the session;
the correlated access line comes from the application's own `truelend.access`
logger. No plaintext uvicorn access line leaked into the stream.

**Adversarial probe of the same criterion.** `request_id` is caller-supplied, so
a JSON-breaking value is the obvious way to falsify "100% parse as JSON". Sent
`X-Request-ID: inj-a", "level": "FAKE` and got:

```
{"timestamp": "...", "level": "INFO", "logger": "truelend.access", "message": "GET /health -> 200", "request_id": "inj-a\", \"level\": \"FAKE"}
```

Properly escaped — the line still parses and the injected `level` does not become
a field. The criterion survives the attack. (See WARN-2 for what this probe did
surface.)

### QA-VM-004 / VM-004 — PASS

`GET /health` with no `X-Request-ID`.

```
status=200   content-type: application/json   x-request-id: fc43305076c6454785e6f4f70214addb
body: {"status":"ok"}
log line:
{"timestamp": "2026-09-14T10:39:50.343804+00:00", "level": "INFO", "logger": "truelend.access", "message": "GET /health -> 200", "request_id": "fc43305076c6454785e6f4f70214addb"}
```

- Status 200 — yes.
- A `request_id` was generated and is non-empty (32 hex chars) — yes.
- The request-scoped log line carries that id — yes.
- The response echoes the same id in `x-request-id` — yes, byte-identical to the
  log field.
- Distinct per request — three independent no-header requests produced
  `a261c5878dff490fa431d87e09843bba`, `810da1a88d0140c88945d6cfc04e5c16` and
  `fc43305076c6454785e6f4f70214addb`.

See WARN-1 on the strength of the "every request-scoped log line" quantifier.

### QA-VM-005 / VM-005 — PASS

`GET /health` to 200, JSON body, response time under 1 second.

- `content-type: application/json`, body `{"status":"ok"}` — parses as JSON.
- 20 single-shot samples: all `200`, `time_total` 0.2035–0.2252 s (dominated by
  per-process curl/connect overhead on Windows) — all under 1 s.
- 10 requests over one reused connection: 0.212722 s for the first (connect),
  then 0.000221–0.000381 s. Server-side service time is about **0.3 ms**, p95
  about 0.4 ms.
- Against `observability.slo.p95_ms = 500`: far under budget. No perf baseline
  exists (group A is the first group), so the perf ratchet has nothing to
  regress against — WARN-only by rule, and nothing to report.

## Layer 2 — Browser

**Not applicable and not claimed.** `sprint-contracts/A.json` declares no
`playwright_checks` and no `design_checks`; no contract in the repo declares any;
`e2e/` is empty. No browser evidence was produced and none is claimed. The
evidence ledger contains zero `playwright` and zero `accessibility` entries,
which matches the contract.

## Layer 3 — Acceptance criteria

Deterministic instruments, re-run at HEAD in this session:

| Command | Result |
|---|---|
| `cd backend && uv run pytest -q` | exit 0 — 73 passed, 2 warnings, 0.10 s |
| `cd backend && uv run ruff check .` | exit 0 — all checks passed |
| `cd backend && uv run mypy src/` | exit 0 — no issues in 12 source files |
| `cd frontend && npm test` | exit 0 — 18 passed (1 file) |

### E15-S1

| AC | Verdict | Evidence |
|---|---|---|
| AC1 — 0 occurrences of PAN/Aadhaar/salary-doc in the captured buffer | PASS | `test_sensitive_application_values_never_appear_in_any_log_line` PASSED, and the control it depends on is proven non-vacuous by `test_pii_redaction_control_is_not_vacuous` PASSED. Live corroboration: PII sent in the query string (`?pan=ABCDE1234F&aadhaar=123412341234&salary_document=payslip-secret.pdf`) and in a POST body; a grep for those four values over the whole captured stream returned **0** occurrences. See WARN-4 on the opt-in shape of the mechanism. |
| AC2 — redaction filter on 100% of configured loggers, and a logger without it fails the assertion | PASS | `test_redaction_filter_installed_on_every_configured_logger` PASSED — it enumerates the root logger plus every entry in `logging.root.manager.loggerDict` and carries the required negative control (`pytest.raises(AssertionError)` on an unregistered logger). `test_redaction_filter_covers_every_logger_under_the_real_server_config` PASSED — the stronger variant that applies uvicorn's own `dictConfig` first, which is what makes the claim hold for the process I actually booted. |
| AC3 — supplied `req-abc` on 100% of lines, all JSON | PASS | QA-VM-003 above, live. |
| AC4 — generated non-empty id on every request-scoped line, echoed in the response | PASS | QA-VM-004 above, live. |
| AC5 — 200, JSON body, under 1 s | PASS | QA-VM-005 above, live. The body is `{"status":"ok"}` only — no config, version or secret disclosure on this unauthenticated endpoint. |

### E9-S1

| AC | Verdict | Evidence |
|---|---|---|
| AC1 — every money field a Decimal quantized to exactly 2 places | PASS (with note) | `test_random_principal_rate_tenure_triples_always_quantize_to_two_places` PASSED — 200 seeded random principal/rate/tenure triples, asserting `isinstance(..., Decimal)` and exact 2-place quantization on four derived values each. `test_construction_quantizes_to_two_decimal_places` (6 cases) and the add/subtract/multiply quantization tests PASSED. See WARN-5: the AC says "a schedule is computed" and no schedule exists in group A. |
| AC2 — static check reports 0 float arithmetic in backend money paths | PASS | `test_money_type_has_zero_float_operations` and `test_serializers_module_has_zero_float_operations` PASSED. Non-vacuity is proven by `test_float_guard_detects_realistic_leaks` across 7 leak shapes (true-division, floor-division, `math.*`, `float()` call, float literal, float exponent, `from math import`), plus `test_float_guard_allows_explicitly_marked_decimal_division` and `test_float_guard_still_reports_zero_for_the_real_money_modules`. Construction rejects `float`, `bool`, invalid strings and 9 non-finite forms (NaN/Infinity variants). |
| AC3 — frontend value held as decimal, never float; static check reports 0 float ops | PASS | 18 vitest cases PASSED, including the static-check group "zero float-arithmetic operations in src/types/money.ts": the shipped module reports no float risk, and the checker is proven non-vacuous by 7 negative controls (`toNumber`, `Math`, float literal, unary plus, `parseFloat`, `Number()`, `number` type). Round-trip through the quoted 2dp wire string and Decimal add/subtract/multiply/compare all pass. |

### E11-S1

| AC | Verdict | Evidence |
|---|---|---|
| AC1 — 35 days past due to DPD-30 | PASS | `test_35_days_past_due_is_dpd_30` and `test_installment_due_35_days_before_as_of_date_is_dpd_30` PASSED. |
| AC2 — 0 through 400, exactly one bucket, no gap, no overlap | PASS | `test_full_sweep_has_no_gap_or_overlap` PASSED — exhaustive `range(0, 401)` checked against an independent expected-bucket oracle, asserting the five buckets are exactly the set observed. Plus 9 explicit boundary cases at 0/29/30/59/60/89/90/179/180 and `test_exactly_five_buckets_exist`. |
| AC3 — nothing past due as of the date to CURRENT | PASS | `test_no_installment_overdue_is_current_when_due_date_is_as_of_date`, `test_no_installment_overdue_is_current_when_due_date_is_in_the_future` and `test_zero_days_past_due_is_current` PASSED. |
| AC4 — result carries a bucket only, no fee/penal interest/charge | PASS | `test_result_carries_bucket_only_no_fee_or_charge_attribute` PASSED. |

## Warnings (recorded, not blocking)

**WARN-1 — the "every log line" quantifier in VM-003/VM-004 is verified over n=1
at runtime.** `GET /health` emits exactly one request-scoped line, so "100% of
the lines" and "every request-scoped log line carries the same id" are satisfied
trivially by one line. The multi-line-per-request case is covered only at test
level (`test_unhandled_exception_response_still_carries_the_correlation_id` and
`test_unhandled_exception_still_emits_an_access_log_line`, both PASSED). Group A
ships no endpoint that emits two lines for one request, so no stronger runtime
proof was available. When a multi-line endpoint lands, this criterion deserves
re-driving live.

**WARN-2 — `X-Request-ID` is reflected unbounded and unvalidated.** A
5000-character caller-supplied id was accepted, written verbatim into the log
line and echoed verbatim into the `x-request-id` response header (header value
measured at 5015 bytes). JSON-breaking characters are correctly escaped, so the
contract criterion holds, and h11 rejects bare control characters at the protocol
layer with a 400. But there is no length cap and no charset allow-list on a value
that reaches both the log sink and a response header. This is a security-surface
observation on the exact file the context pack flags
(`backend/src/api/middleware.py`); it is **not** a functional failure of any
group-A contract check or AC. It belongs to the security reviewer's verdict, and
my functional PASS does not pre-empt it.

**WARN-3 — the SLO error-rate sensor could not be executed: recorded
`untested`.** `project-manifest.json` sets `observability.enabled: true` with
`metrics_path: "/metrics"`, but `GET /metrics` on the running app returns **404**,
and no group-A story, AC or feature (F001–F005, F009–F011, F070–F073) owns a
metrics endpoint — no story file in the repo mentions `metrics` at all. So this is
a manifest/roadmap gap for the orchestrator, not a group-A code defect, and I did
not fail the evaluation on it. It is recorded `untested` in the evidence ledger
rather than passed. Observed error rate from my own traffic was 0% 5xx: the only
non-2xx responses were a deliberate 404 probe, a 405 probe and a 400
malformed-request probe, all 4xx, none counted as a server error.

**WARN-4 — PII redaction is opt-in, not ambient.** AC1 and AC2 are both
satisfied, but the mechanism verified is an explicit `redact_values(...)` scope
plus an architecture test
(`test_modules_handling_applicant_pii_enter_a_redaction_scope`, PASSED) that
forces modules handling PII into that scope. A future logger that writes PAN
outside the scope leaks unless that architecture test catches the module. The
guard exists and is green today; the fragility is worth carrying forward into the
groups that actually handle applicant payloads.

**WARN-5 — E9-S1-AC1 says "a schedule is computed"; group A has no schedule.**
E9-S1's own Scope explicitly excludes interest/EMI rules from the type, so no
schedule could exist here. The AC was verified at the level group A can support:
Money arithmetic over 200 random principal/rate/tenure triples. The literal
"schedule" form of the AC becomes testable when the schedule story lands and
should be re-verified there rather than treated as closed.

**INFO — `features.json` is stale relative to this evidence.** F002 (AC2) and
F003 (AC3) still read `passes: false` from the superseded tree; my evidence
supports `true` for both. Instance 1 owns `features.json`; I did not write it.

**INFO — out-of-scope known items.** The `ownership-check` block on
`backend/src/__init__.py`, the `canvas-sync` block and the
`regression-suite-full` behaviour on contracts B..M are orchestrator-level items
listed in the context pack. They are not group-A runtime failures and I did not
re-litigate them.

## Verdict

**Functional verdict: PASS.**

All 3 `api_checks` in the frozen contract executed live against the tree at
`f4abd41` and passed. All 12 acceptance criteria across E15-S1, E9-S1 and E11-S1
are independently verified — the five E15-S1 criteria against a running uvicorn
and its captured log stream, the E9/E11 criteria against green deterministic
instruments whose non-vacuity I checked rather than assumed. `pytest` (73),
`ruff`, `mypy --strict` and `vitest` (18) are all clean.

Two scoped limits on that PASS, stated plainly: there is no browser layer to
evaluate (the contract declares none), and the SLO error-rate sensor is recorded
`untested` because the app exposes no `/metrics` yet (WARN-3). The overall
`/gate` verdict additionally depends on the security reviewer's judgement of
WARN-2, which I have not pre-empted.
