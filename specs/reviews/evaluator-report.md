# Evaluator Report — story group A (instance 1 of 3, independent)

| Field | Value |
|---|---|
| Verdict | **PASS** (functional scope: 3 api_checks + 12 acceptance criteria) |
| Commit evaluated | `f4abd41` on `feat/harness-scaffold-and-planning` |
| Sprint contract | `sprint-contracts/A.json` (frozen) — 3 api_checks |
| Stories | E15-S1, E9-S1, E11-S1 |
| Verification mode | `local` (Docker not installed; no compose file until E15-S2) |
| App under test | `uv run uvicorn src.api.app:app --port 8000`, stdout+stderr captured to `.claude/state/ev1-uvicorn.log` |
| Health check | `GET /health` → 200 on retry attempt 1 |
| Evaluated at | 2026-09-14T10:43:47Z |
| Evidence ledger | `specs/reviews/evaluator-evidence.json` |
| Browser layer | not contracted — 0 playwright/design/accessibility checks in any contract, no `e2e/`. No browser evidence produced or claimed. |
| Prior verdicts | not read as evidence; every stored verdict under `specs/reviews/` predates this commit |

## Contract checks

| Check | Matrix | Criterion | Result |
|---|---|---|---|
| QA-VM-003 | VM-003 | `GET /health` with `X-Request-ID: req-abc` → 200; 100% of log lines parse as JSON; each carries `request_id == "req-abc"` | **PASS** |
| QA-VM-004 | VM-004 | `GET /health` with no header → 200; every request-scoped line carries the same generated non-empty `request_id`; response echoes it | **PASS** |
| QA-VM-005 | VM-005 | `GET /health` → 200, JSON body, under 1 s | **PASS** |

### QA-VM-003 — PASS

```
$ curl -s -D - -H 'X-Request-ID: req-abc' http://localhost:8000/health
HTTP/1.1 200 OK
content-type: application/json
x-request-id: req-abc

{"status":"ok"}
```

Log line emitted while serving:

```json
{"timestamp": "2026-09-14T10:35:39.325023+00:00", "level": "INFO", "logger": "truelend.access", "message": "GET /health -> 200", "request_id": "req-abc"}
```

Whole-stream integrity, re-parsed with `json.loads` line by line at the end of the
run: **93 of 93 lines parsed as JSON, 0 failures**, with one uniform key shape
(`timestamp, level, logger, message, request_id`). That total includes uvicorn's own
startup lines, which commit `f4abd41` claims to route through the root JSON
formatter — verified rather than trusted:

```json
{"timestamp": "...", "level": "INFO", "logger": "uvicorn.error", "message": "Application startup complete.", "request_id": ""}
```

The mechanism is not quite what the commit message says, and the distinction
matters: `uvicorn.error` really is formatted by the root JSON handler, while
`uvicorn.access` has `propagate=False` and **zero handlers**, so its records are
discarded rather than reformatted. No plain-text access line is emitted because
none is emitted at all; the app's own `truelend.access` line carries the
correlation id instead. Either way the AC3 invariant holds, and the previous
round's plain-text `uvicorn.access` line is gone. The trade-off is recorded as
EV1-F7.

Robustness of the JSON invariant against a hostile id (the header is
caller-supplied): ids containing `"`, `\`, a tab, an ANSI escape, and the payload
`req-", "level": "CRITICAL", "x": "` each produced a single still-parseable line
with no forged field.

### QA-VM-004 — PASS

```
$ curl -s -D - http://localhost:8000/health
HTTP/1.1 200 OK
x-request-id: 908ff398335f46f397b99e8b31377836
```

```json
{"timestamp": "2026-09-14T10:35:48.775172+00:00", "level": "INFO", "logger": "truelend.access", "message": "GET /health -> 200", "request_id": "908ff398335f46f397b99e8b31377836"}
```

The echoed id and the logged id are identical, 32 hex chars, non-empty. Across the
run, 22 requests without the header produced 22 distinct ids — generation is
per-request, not per-process. Caveat on the strength of the evidence, not on the
verdict: the app emits exactly **one** log line per request, so "every
request-scoped log line" is satisfied over a single line by construction.

### QA-VM-005 — PASS

20 consecutive samples: 20/20 `200`, 20/20 `content-type: application/json`, body
`{"status":"ok"}` parses as a JSON object.

| min | median | p95 | max | mean |
|---|---|---|---|---|
| 0.2024 s | 0.2096 s | 0.2238 s | 0.2253 s | 0.2110 s |

Contract budget 1.000 s — met with margin. Manifest SLO `p95_ms: 500` — met
(223.8 ms). See "Performance and SLO" below for why this is a WARN-free but
baseline-free measurement.

## Acceptance criteria

| AC | Feature | Result | Evidence |
|---|---|---|---|
| E15-S1-AC1 | F001 | **PASS** (one clause untested) | PII in query string + header served live: 0 occurrences of the PAN, Aadhaar and salary token in the 93-line stream; registered values render `[REDACTED]` in messages, `%`-args and exception tracebacks |
| E15-S1-AC2 | F002 | **PASS** | root + all 10 explicitly configured loggers carry `RedactionFilter`; single root handler also carries it; 9-namespace leak probe: 8 lines, 0 leaks, 0 non-JSON |
| E15-S1-AC3 | F003 | **PASS** | QA-VM-003 above |
| E15-S1-AC4 | F004 | **PASS** | QA-VM-004 above |
| E15-S1-AC5 | F005 | **PASS** | QA-VM-005 above |
| E9-S1-AC1 | F009 | **PASS** (schedule clause untested) | every constructed and derived `Money` has `Decimal` exponent `-2`; ROUND_HALF_UP verified; float/NaN/Inf rejected |
| E9-S1-AC2 | F010 | **PASS** | my own AST scan of both money paths: 0 float literals, 0 `float()` calls, 0 `math.*`, 0 `Div/FloorDiv/Pow`; no exemption markers present |
| E9-S1-AC3 | F011 | **PASS** | value held as `decimal.js` Decimal; 0 `Number(`/`parseFloat`/numeric-operator uses; 18 vitest cases, lint and `tsc --noEmit` clean |
| E11-S1-AC1 | F070 | **PASS** | `classify_by_days_past_due(35)` → `DPD-30`; `classify(2026-01-01, 2026-02-05)` → `DPD-30` |
| E11-S1-AC2 | F071 | **PASS** | 0–400 sweep: 401/401 classified, ranges 0-29 / 30-59 / 60-89 / 90-179 / 180+, transitions exactly at the floors, 5 distinct buckets, no gap, no overlap |
| E11-S1-AC3 | F072 | **PASS** | `as_of == due` → `CURRENT`; due in future → `CURRENT`; dpd 0 and 29 → `CURRENT` |
| E11-S1-AC4 | F073 | **PASS** | result is a bare `DelinquencyBucket` StrEnum member; attributes beyond enum/str machinery: `name`, `value`; 0 fee/penal/charge/interest attributes |

### The two previously failing features

`features.json` carried `F002` and `F003` as `passes: false` from the
2026-09-14T06:47Z round with very specific evidence — a plain-text
`uvicorn.access` line carrying no `request_id`, and a PAN logged verbatim from
`GET /health?pan=...` while it was registered as sensitive. Both vectors were
re-driven at HEAD and both are closed:

- there is no `uvicorn.access` output at all now, so there is no unformatted
  request-scoped line (93/93 JSON);
- the live query-string PII probe logged `GET /health -> 200` with no query
  string, and the 93-line stream contains 0 occurrences of the PAN, the Aadhaar
  number or the salary token;
- `uvicorn` and `uvicorn.access` both carry `RedactionFilter` now, and no
  configured logger lacks it.

Four names in `loggerDict` have no filter of their own — `concurrent`, `dotenv`,
`truelend`, `gunicorn`. These are auto-created parent namespace nodes, not
loggers the app configures, they never emit, and anything routed through them is
filtered at the single root handler. That was proven empirically rather than
argued: a registered secret logged through nine namespaces (including a logger
created *after* `configure_logging`) produced 0 leaking lines.

## Untested — recorded honestly, not as passes

| Check | Why it could not be executed |
|---|---|
| Observability SLO sensor (`/metrics` scrape) | `GET /metrics` → **404** at HEAD. `project-manifest.json` sets `observability.enabled: true` with `metrics_path: /metrics`, and the frozen `api-contracts.md` (lines 38, 315) assigns `GET /metrics` to **E15-S1** — but no E15-S1 acceptance criterion covers it and the story's own Scope/Out forbids endpoints beyond `/health`. The error-rate sensor therefore had nothing to scrape. This is a planning contradiction for a human, not a code defect I can fail an AC on. |
| Performance ratchet (p95 regression) | No recorded baseline exists — group A is the first group. Absolute latency measured instead (p95 223.8 ms vs 1 s contract and 500 ms SLO). Per the no-baseline rule: WARN, not FAIL. |
| E9-S1-AC1 "schedule computed from each triple" | No schedule computation exists at HEAD (later epic). Only the quantization invariant it depends on could be driven. |
| E15-S1-AC1 "when the request is served" with an application payload | No endpoint accepts an application payload at HEAD. Nearest executable equivalents were driven live (query string, request header) plus in-process message/`%`-arg/nested-`extra`/traceback paths. |
| Browser and accessibility layers | Not contracted anywhere in this repo, and `e2e/` does not exist. Nothing executed, nothing claimed. |

## Findings that do not fail a contract check

Full detail and repro commands in `specs/reviews/evaluator-evidence.json`.

| id | Sev | Where | Finding |
|---|---|---|---|
| EV1-F1 | major | `routes.py` vs `api-contracts.md:314` | `/health` returns `{"status":"ok"}`; the frozen contract documents `{status, database, version}` and cites E15-S1-AC5. Two of three fields absent. The AC text is met; the frozen shape is not. Needs a human call — the contract file is frozen, and omitting `database` (no DB until group B) and `version` (disclosure) both look like the *handler* being right and the contract line being stale. |
| EV1-F2 | major | `serializers.py` | `MoneyField` has no JSON-schema hook, so `model_json_schema()` raises `PydanticInvalidForJsonSchema`. `/openapi.json` and `/docs` are 200 today only because no route carries money; the first money-bearing contract breaks both. |
| EV1-F3 | major | `config/logging.py` | Redaction is opt-in by exact value registration — no pattern or key-name matching. An unregistered PAN is logged verbatim (demonstrated). AC1 holds today only because the one route logs no payload. A structural guard test exists for future call sites. |
| EV1-F4 | minor | `config/delinquency.py` | `classify` / `classify_by_days_past_due` live in Config; E11-S1 operation 2 places the pure classifier in `types/delinquency.py`, which holds only the enum. No layer rule broken; the bundle's owned-file contract drifted. |
| EV1-F5 | major | `api/errors.py`, `types/errors.py` | `AppError.context` is serialized to the client verbatim — no allowlist, no redaction, no size limit — and `error` is the class name. A probe put `internal_path: /etc/passwd` and a PAN in `context` and both came back to the client. 0 subclasses exist yet, so this is a forward-looking unguarded outbound channel. Security-reviewer remit; repro in the ledger. |
| EV1-F6 | minor | `api/middleware.py` | A 5000-char `X-Request-ID` is echoed and logged in full — no cap, no allowlist. JSON escaping does block line forgery and header splitting was not reproducible, so the impact is bloat, not injection. Security-reviewer remit. |
| EV1-F7 | minor | `config/logging.py` | `uvicorn.access` is silenced rather than reformatted, discarding client address/bytes/protocol and making `--access-log` a no-op. Separately, the formatter drops `extra=` fields entirely, so structured context cannot be attached to a log record. |

Supplementary probes that came back clean: the 500 path echoes `X-Request-ID:
req-500` and its access line carries `request_id` with 0 non-JSON lines (the
CR-003 middleware-ordering claim holds — `create_app()` returns the pure-ASGI
`CorrelationIdMiddleware` wrapping the FastAPI app); `AppError` maps to
`application/json {error, detail, context}`; 404/405 echo the correlation id.
Note that the 500 body itself is Starlette's plain-text `Internal Server Error`,
and no app-emitted ERROR record with a traceback appeared on that path.

## Scope note

This verdict covers the three frozen `api_checks` and the twelve acceptance
criteria of E15-S1, E9-S1 and E11-S1. It is not a security verdict (a separate
reviewer owns that gate) and it is not a merge decision: EV1-F1 and the missing
`/metrics` endpoint are contract-level conflicts with frozen artefacts that only
a human can resolve, and EV1-F5 is an unguarded outbound channel the security
reviewer should rule on.

Process killed before finishing: `uv run uvicorn ... --port 8000` (port 8000
released).
