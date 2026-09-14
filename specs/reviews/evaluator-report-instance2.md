# Evaluator Report — Group A — INSTANCE 2 of 3

| Field | Value |
|---|---|
| Instance | 2 (independent; no contact with instances 1 or 3) |
| HEAD evaluated | `f4abd41` — evaluated from scratch, no stored verdict read |
| Branch | `feat/harness-scaffold-and-planning` |
| Contract | `sprint-contracts/A.json` (frozen, read-only) |
| Stories | E15-S1, E9-S1, E11-S1 |
| verification.mode | `local` (Docker not installed; no `docker compose` attempted) |
| Runtime | `uv run uvicorn src.api.app:app --port 8001`, backgrounded, stdout+stderr captured to `.claude/state/eval2-uvicorn.log`; process killed (PID 49452) and port 8001 confirmed released |
| Browser layer | **Not applicable** — no contract declares `playwright_checks`/`design_checks`, `e2e/` is empty. No browser evidence produced; none claimed. |

## VERDICT: PASS (functional)

All three frozen `api_checks` pass. All 12 acceptance criteria across the three
stories pass. Two sub-assertions from the context pack's fix table were **not
runtime-reachable** and are recorded `untested`, not `pass` — neither is an
acceptance criterion nor a contract check, so neither gates this verdict.

This is the **functional** verdict only. Per the evaluator KEY RULES the overall
`/gate` verdict is FAIL if the security reviewer reports `pass: false`,
regardless of this PASS. Findings O1–O3 below are handed to that reviewer.

## Per-check result

| Check | Matrix | Verdict | Evidence |
|---|---|---|---|
| QA-VM-003 | VM-003 | **PASS** | 200; `x-request-id: req-abc` echoed; 1 log line emitted during the request, parsed as JSON, `request_id == "req-abc"`. Whole run: **71/71 log lines parsed as JSON, 0 failures.** |
| QA-VM-004 | VM-004 | **PASS** | 200; generated `09c68604047745c6b7a2822e6b2ddd7d` — non-empty, echoed in `x-request-id`, identical on the request-scoped log line. 23 distinct generated ids over the run, 0 empty. |
| QA-VM-005 | VM-005 | **PASS** | 200; `content-type: application/json`; body `{"status":"ok"}`. 20 samples: min 201.8ms, p50 208.5ms, **p95 218.7ms**, max 223.9ms. 0 non-200, 0 over 1s. |

### The CR-004 claim, verified rather than trusted

The pack claims f4abd41 routes uvicorn's own loggers through the root JSON
formatter. I verified this directly and it holds, with one correction to the
prose (see O4):

- 4 `uvicorn.error` **startup** lines — all valid JSON, `request_id: ""`.
- 3 `uvicorn.error` **in-flight WARNING** lines (`"Invalid HTTP request
  received."`, produced by my malformed-header probes) — all valid JSON. This is
  the stronger test: it proves the routing survives outside the startup path.
- `uvicorn.access` emits nothing at all — it is `disabled`, not reformatted.

Across the entire evaluation: **71 non-blank log lines, 0 JSON parse failures**,
including lines whose `request_id` carried embedded double quotes, a TAB, 4000
characters, and raw UTF-8 multibyte. `json.dumps` escaped every one, so
attacker-controlled input cannot break the log structure. QA-VM-003's
"100% parse as JSON" is robust, not merely true for the benign input.

## Acceptance criteria

| AC | Verdict | How verified |
|---|---|---|
| E15-S1-AC1 | PASS | 0 occurrences of PAN/Aadhaar/salary-doc in the captured buffer — including lowercase, space-separated and hyphen-separated variants, values inside a nested dict payload, an exception traceback, and a `uvicorn.error` line. |
| E15-S1-AC2 | PASS | 9 configured loggers enumerated, **0** without a `RedactionFilter`. Handler-level filter also present, and a logger created *after* `configure_logging` was still redacted. |
| E15-S1-AC3 | PASS | = QA-VM-003 |
| E15-S1-AC4 | PASS | = QA-VM-004 |
| E15-S1-AC5 | PASS | = QA-VM-005 |
| E9-S1-AC1 | PASS | 2000 random principal/rate/tenure triples × 4 money values = 8000 checks; **0** quantization failures; every value a `Decimal` with exponent exactly −2. D-G wire form confirmed: `{"principal":"1234.50","emi":"99.01"}`; a float on the wire is rejected with `ValidationError`. |
| E9-S1-AC2 | PASS | Architecture check: 36 passed, 0 float ops in the real money modules — and its 4 negative controls (`float-call`, `float-literal`, `float-exponent`, `math-import-from`) prove the guard actually detects a leak, so the zero is not vacuous. |
| E9-S1-AC3 | PASS | 18 vitest tests pass; eslint and `tsc --noEmit` clean. My independent grep of `money.ts` found one hit, `this.amount.toFixed(2)` — decimal.js's method on a `Decimal` receiver returning a string, not `Number.prototype.toFixed` and not arithmetic. |
| E11-S1-AC1 | PASS | 35 dpd → `DPD_30` via both the int and the date-based entry point. |
| E11-S1-AC2 | PASS | Exhaustive 0..400 sweep: 401 values, all in the 5-member enum, every band contiguous (0-29 / 30-59 / 60-89 / 90-179 / 180-400), union equals `range(401)` exactly once — no gap, no overlap. All 8 boundary pairs correct. |
| E11-S1-AC3 | PASS | Due-tomorrow, due-today and dpd 0 all → `CURRENT`. Negative dpd rejected with `ValueError`. |
| E11-S1-AC4 | PASS | Result is a `StrEnum` member; zero `fee`/`charge`/`penal`/`interest` attributes anywhere on the enum. |

### CR-001 and CR-002, verified closed

- **CR-001** (`Money` accepted NaN): `Money` now rejects `float('nan')`,
  `float('inf')`, `float('-inf')`, plain floats, `bool`, `Decimal('NaN')`,
  `Decimal('±Infinity')`, `'abc'`, `'NaN'`, `'Infinity'`. `multiply` rejects a
  float scalar and a `Decimal('NaN')` scalar.
- **CR-002** (float guard ignored arithmetic): the guard's negative controls
  fire, and `test_float_guard_allows_explicitly_marked_decimal_division` shows
  the per-line exemption mechanism works.

## Deterministic gates — reproduced independently at HEAD

| Command | Result |
|---|---|
| `uv run pytest -q` | exit 0 — 73 passed, 2 warnings |
| `uv run ruff check .` | exit 0 — all checks passed |
| `uv run mypy src/` | exit 0 — no issues in 12 source files |
| `npm test` | exit 0 — 18 passed (1 file) |
| `npm run lint` | exit 0 — clean |
| `npm run typecheck` | exit 0 — clean |

These match the pack's reported counts; I re-ran them rather than accepting them.

## Could not execute (recorded `untested`, not `pass`)

1. **CR-003 — correlation id surviving the 500 path.** Only `GET /health` is
   registered, it takes no input, and it cannot fail. No HTTP surface in group A
   can raise an unhandled exception, so a 500 is unreachable black-box. The claim
   that `CorrelationIdMiddleware` installed outside `ServerErrorMiddleware`
   stamps a 500 is **not independently runtime-verified by me**. It is not an AC
   and not a contract check, so it does not gate the verdict — but the pack
   should not be read as though a runtime evaluator confirmed it.

2. **The `{error, detail, context}` envelope.** The only error reachable over
   HTTP is Starlette's default 404, which returned `{"detail":"Not Found"}` —
   *not* the `{error, detail, context}` shape from `api-contracts.md`, because it
   bypasses the `AppError` mapping. No `AppError`-raising route exists yet, so
   the envelope is unverifiable at runtime. The 404 path *does* correctly echo
   `X-Request-ID` and emit a JSON log line carrying it.

3. **Playwright / accessibility layers.** Not applicable, not untested — no
   contract declares them and `e2e/` is empty.

## Observations (non-blocking; O1–O3 for the security reviewer)

- **O1 — `X-Request-ID` is unbounded.** A 4000-character id was accepted,
  reflected in full in the response header, and written in full to the log
  stream. No length cap. Log-volume amplification and an unbounded
  attacker-controlled field in every log line. JSON integrity is unaffected.
- **O2 — the id is reflected with no character sanitization.** `ev"il","injected":"yes`,
  a TAB, and raw UTF-8 multibyte bytes are all echoed verbatim into the response
  header. Response splitting is *not* achievable: bare CR and bare LF are
  rejected `400` at the parser, and a genuine CRLF is truncated at the CR by h11.
  But the app itself validates nothing — it relies entirely on h11. Raw UTF-8 in
  a response header is non-conformant (header values are latin-1).
- **O3 — `extra=` fields bypass redaction by construction.** `JSONLogFormatter`
  drops `extra` entirely, and `RedactionFilter` scrubs only `message` and
  `exc_text`. My `extra={"pan_extra": PAN}` probe leaked nothing *because the
  extras never reached the output at all*. If a later story adds `extra` to the
  formatter payload, PII in extras will bypass redaction and silently break
  E15-S1-AC1. Forward risk.
- **O4 — the pack overstates the CR-004 fix.** `uvicorn`/`uvicorn.error`/
  `gunicorn.error` are routed through the root JSON formatter, but
  `uvicorn.access` is **silenced** (`disabled = True`) and replaced by a
  middleware-emitted `truelend.access` line. The module docstring explains this
  and the reasoning is sound, but the consequence is that if the middleware ever
  fails before it logs, a request produces **no access line at all**.
- **O5 — QA-VM-003's "100%" is 1/1.** Exactly one line is emitted per request.
  The criterion is met, but the substrate is thinly exercised — there is no
  handler-level application log line yet to correlate against. The whole-stream
  71/71 result is the evidence worth relying on.
- **O6 — build-contract deviation.** E15-S1's Operation 2 places
  `classify(days_past_due: int)` in `backend/src/types/delinquency.py`; the
  implementation puts `classify_by_days_past_due(int)` and `classify(date, date)`
  in `backend/src/config/delinquency.py`. The rationale (Types may not import
  Config) is architecturally correct and no AC constrains location, but it
  diverges from the frozen story's Operations list.
- **O7 — `Money` has no `divide`.** Fine for group A, but E9-S1-AC1's literal
  "schedule is computed" is not satisfiable until EMI arrives. Whoever adds
  division must keep it Decimal-only; the float guard already walks `Div`/
  `FloorDiv` and has a working per-line exemption.
- **O8 — server-level lines carry `request_id: ""`.** The 7 `uvicorn.error`
  lines (4 startup, 3 in-flight) have an empty `request_id`. Correct per the ACs'
  "request-scoped" wording, but it means a per-request log segment cannot be
  isolated by timestamp alone once traffic is concurrent.

## Ratchets

| Gate | Status | Detail |
|---|---|---|
| Performance ratchet | **WARN** (not FAIL) | No baseline exists — group A is the first group in a greenfield build, so there is nothing to regress against. p95 218.7ms, inside the 500ms SLO. |
| SLO error-rate | n/a | `observability.enabled` not configured, no `/metrics` in group A. Zero 5xx observed. The only non-2xx were a deliberate 404 and three deliberate 400s from malformed-header probes — all 4xx, outside the error-rate SLO. |
| Accessibility | n/a | No `accessibility_checks` in the contract; no frontend route served. |
| Security gate | not owned by this instance | Functional PASS does not clear it. The stored `security-verdict.json` predates HEAD and was deliberately not read. |

## Method notes

- No stored verdict under `specs/reviews/` was read except the context pack.
  Every result above comes from an execution I performed at HEAD `f4abd41`.
- No production source, no file under `sprint-contracts/`, and no file under
  `specs/design/` was modified. Source was read only to discover *what to drive*
  (route surface, public API names) — never to decide whether behaviour was
  correct.
- Files written by this instance: this report and
  `specs/reviews/evaluator-evidence-instance2.json`. `features.json`,
  `evaluator-report.md` and `evaluator-evidence.json` were left untouched
  (instance 1 owns them).
- Raw captures retained at `.claude/state/eval2-*.log` (gitignored via
  `.claude/state/*.log`).
