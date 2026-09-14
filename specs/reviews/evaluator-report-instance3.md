# Evaluator report — group A, instance 3 of 3 (round 2)

/ **Lane:** `/gate` runtime re-verification · **Mode:** `local` (Docker not installed)
/ **HEAD:** `9112495` · **Base:** `14e9487` · **Port owned:** 8002
/ **Server log:** `.claude/state/g3eval3-uvicorn.log` (INFO run),
  `.claude/state/g3eval3-uvicorn-debug.log` (DEBUG run)
/ **Booted with:** `cd backend && uv run uvicorn src.api.app:app --port 8002 --host 127.0.0.1`
/ **Assignment:** find checks that pass for the wrong reason; refute claimed fixes
  with live evidence rather than confirm them.

## VERDICT: FAIL

The three frozen `api_checks` **all pass** on live evidence, and every story
acceptance criterion for E15-S1, E9-S1 and E11-S1 **passes**. The verdict is
nevertheless FAIL, on one high-severity security finding in changed production
code (`G3-F1`): a single unauthenticated GET request forges arbitrary samples
into `GET /metrics`, including a fabricated `status="500"` counter. Per the
evaluator security gate, a green functional pass with an open high-severity
finding is still a FAIL.

This is **not** a regression of the two remediation commits. `9558cc5` and
`9112495` do what they claim — I tried hard to refute them and could not (see
§4). `G3-F1` is in the newly shipped `/metrics` surface that those commits added.

## 1. Frozen contract checks (`sprint-contracts/A.json`)

| Check | Matrix | Verdict | Live evidence |
|---|---|---|---|
| QA-VM-003 | VM-003 | **PASS** | `GET /health` with `X-Request-ID: req-abc` → 200, body `{"status":"ok","database":"unconfigured","version":"0.1.0"}`, response header `x-request-id: req-abc`. Log lines emitted while serving: **denominator = 1**, 1/1 parsed as JSON (100%), 1/1 carried `request_id == "req-abc"` (100%). |
| QA-VM-004 | VM-004 | **PASS** | `GET /health` with no `X-Request-ID` → 200. Generated id `7434e974224240bbba4c879e9f4b4ea6` (32 chars, non-empty). Denominator = 1 request-scoped line, `distinct_ids = {'7434e974…'}`, and the response header echoes exactly that id. Repeated on the DEBUG process: `f3e166fed516492ab093d06693692f56`. |
| QA-VM-005 | VM-005 | **PASS** | 200, `content-type: application/json`, valid JSON body. 60 samples: min 1.25 ms, p50 1.39 ms, **p95 1.53 ms**, max 2.17 ms — three orders of magnitude inside the 1 s budget and inside `observability.slo.p95_ms = 500`. |

### Denominator caveat (evidence strength, not a defect)

QA-VM-003/AC3 asserts "100% of the log lines emitted while serving". The served
app emits **exactly one** request-scoped line per request, so "100%" is measured
over a denominator of 1. I attacked this directly as a candidate
pass-for-the-wrong-reason: I rebooted with `TRUELEND_LOG_LEVEL=DEBUG` (confirmed
applied — `{"level": "DEBUG", "logger": "asyncio", "message": "Using proactor:
IocpProactor"}` appears at startup) and re-ran the check. Still exactly one
request-scoped line, still carrying `req-abc`. **Refuted** — the property is
real, not an artefact of the log level. The caveat worth recording is only that
the assertion is cheap to satisfy today; it will become load-bearing when group B
handlers start logging inside the request scope.

Across all probing in this session, **36 of 36** log lines parsed as JSON.

## 2. Story acceptance criteria

| AC | Verdict | Evidence |
|---|---|---|
| E15-S1-AC1 (0 occurrences of PAN/Aadhaar/salary content in the captured buffer) | **PASS** | Instrumented probe over the real `create_app()`: `PAN_in_logs=0 AADHAAR_in_logs=0 PAN_in_body=0` on both the async and the sync-handler failure path; the logged traceback reads `RuntimeError: async boom pan=[REDACTED] aadhaar=[REDACTED]`. |
| E15-S1-AC2 (filter on 100% of configured loggers, negative control fails) | **PASS** | Enumerated live after `configure_logging`: `loggers=11 covered=11 pct=100.0% missing=[]`; root handler filters `['RedactionFilter']`. Negative control: a logger created *after* configure has no filter → `False`, so the assertion does discriminate. (Residual risk: `G3-F6`.) |
| E15-S1-AC3 | **PASS** | QA-VM-003 above, at INFO and at DEBUG. |
| E15-S1-AC4 | **PASS** | QA-VM-004 above. Additionally verified on the 500 path: the unhandled-exception response carries `X-Request-ID: probe-async-handler` / `probe-sync-handler` and both the access line and the traceback line carry the same id. |
| E15-S1-AC5 | **PASS** | QA-VM-005 above. |
| E9-S1-AC1 (every money field a Decimal quantized to exactly 2dp) | **PASS** | Wire round trip through `MoneyField`: `"1234.5"` → `{"amount":"1234.50"}`; `"0.005"` → `{"amount":"0.01"}` (ROUND_HALF_UP); re-parsing the module's own output is stable. 19 Money probes, all 2dp or a typed rejection. |
| E9-S1-AC2 (0 float arithmetic ops in backend money paths) | **PASS** | `uv run pytest tests/architecture/test_no_float_money.py -q` → **39 passed**. Full suite re-run independently: **88 passed**, 0.16 s. `Money(1.5)` and `Money(True)` both raise `InvalidMoneyAmountError`. |
| E9-S1-AC3 (frontend holds a decimal, never a float) | **PASS** | `npm test` → **18 passed** (1 file). `money.ts` holds a `decimal.js` `Decimal`, `isFinite` rejects NaN/Infinity, no `number` arithmetic on the value. |
| E11-S1-AC1 (35 dpd → DPD-30) | **PASS** | `classify_by_days_past_due(35)` → `'DPD-30'`. |
| E11-S1-AC2 (0–400 sweep, exactly one bucket, no gap/overlap) | **PASS** | Full 401-value sweep returns exactly `['CURRENT','DPD-30','DPD-60','DPD-90','NPA']`. Boundaries exact: 29→CURRENT, 30→DPD-30, 59→DPD-30, 60→DPD-60, 89→DPD-60, 90→DPD-90, 179→DPD-90, 180→NPA. `10**9`→NPA, `-1`→`ValueError`. |
| E11-S1-AC3 (nothing past due → CURRENT) | **PASS** | `classify(2026-12-01, 2026-09-14)` → CURRENT (future due date); same-day → CURRENT; `classify(2026-08-15, 2026-09-14)` → DPD-30. |
| E11-S1-AC4 (bucket only, no fee/interest/charge) | **PASS** | `DelinquencyBucket` is a 5-member `StrEnum`; attribute scan for `fee`/`interest`/`charge` returns `[]`. `src/types/delinquency.py` imports nothing outside Types. |

Deterministic layers re-run independently, not taken from the pack: backend 88
passed, architecture guard 39 passed, frontend 18 passed.

## 3. Findings

### G3-F1 — HIGH — Prometheus exposition injection and unbounded cardinality via the request path

`src/api/middleware.py:75,91` uses the raw, URL-decoded `scope["path"]` as the
`route` label, and `src/api/platform/routes.py:77-81` interpolates it into the
exposition format with no escaping. Prometheus requires `\`, `"` and newline to
be escaped in a label value; nothing escapes them.

One unauthenticated GET to a non-existent path:

```
GET /x%22%7D%20999999%0Ahttp_requests_total%7Bmethod=%22GET%22,route=%22/health%22,status=%22500%22%7D%20424242%0A%23%20x
→ 404
```

`GET /metrics` afterwards (verbatim, live):

```
http_requests_total{method="GET",route="/health",status="200"} 62
http_requests_total{method="GET",route="/metrics",status="200"} 1
http_requests_total{method="GET",route="/x"} 999999
http_requests_total{method="GET",route="/health",status="500"} 424242
# x",status="404"} 1
```

The fourth line is a **well-formed, parseable, forged sample** claiming 424,242
HTTP 500s on `GET /health`. Impact:

- `project-manifest.json#observability.slo.error_rate_pct = 1` is computed from
  these counters. An attacker can fabricate a 5xx rate (tripping alerting and
  the harness's own SLO sensor) or inflate the 2xx counter to mask a real
  outage. The observability channel loses integrity.
- The genuine 404 sample was swallowed into a comment line (`# x",…`), so the
  real count was silently lost.
- An earlier probe produced a duplicate `status` label in one line, which makes
  the whole scrape unparseable to Prometheus — i.e. the endpoint can also be
  made to fail closed.
- **Unbounded cardinality:** 150 distinct 404 paths produced **154 permanent
  series** and a 13,696-byte `/metrics` body. `_request_counts` is a
  process-global `Counter` with no eviction and no route-template resolution, so
  unauthenticated 404 traffic grows process memory without limit.
- `/metrics` is `public` in the frozen `api-contracts.md` (line 38) and has no
  auth, so no credentials are needed.

The contract (`api-contracts.md:315`) specifies RED metrics labelled
`method, route, status`. `route` is meant to be the matched route template
(`/health`), not the caller's raw path. Related to but distinct from SEC-015
(which covers verbatim paths in *logs*, not label injection into *metrics*);
I am recording it as a new finding.

### G3-F2 — MEDIUM — `decimal.Overflow` still escapes `Money.multiply` (SEC-008 confirmed open at HEAD)

`Money._quantize` catches only `InvalidOperation`. `decimal.Overflow` is a
sibling under `DecimalException`, and the multiplication in `multiply` applies
the ambient context *before* quantize runs:

```
Money(2).multiply(Decimal("1E+999999999"))   →  RAISED decimal.Overflow   (0.0 ms)
Money(2).multiply(10**999999)                →  RAISED InvalidMoneyAmountError (9708.5 ms)
Money(2).multiply(10**500000)                →  RAISED InvalidMoneyAmountError (2430.5 ms)
Money(Decimal("1E+999999999"))               →  RAISED InvalidMoneyAmountError (0.0 ms)
```

Two halves, judged separately:

- The **exception-type** claim is confirmed for a `Decimal` scalar: a raw
  `decimal.Overflow` escapes a Types-layer value object whose docstring promises
  `InvalidMoneyAmountError`. At the API boundary that becomes an unhandled 500
  instead of a 422. The constructor path is safe (a `Decimal` built from a
  string does not apply the context), so **only `multiply` leaks**.
- The **CPU** claim is confirmed and unchanged: 9.7 s of single-threaded work
  for an integer scalar, which would block the event loop.

Not remotely triggerable today (no endpoint accepts a scalar), which is why this
is MEDIUM and not HIGH — but it is reachable by the first story that multiplies
money by a caller-supplied factor, and none of the 88 passing tests cover it.

### G3-F3 — MEDIUM — registered PII outlives its request scope in a process-global cache (SEC-014 confirmed at HEAD)

`_redaction_pattern` is `@lru_cache(maxsize=256)` **keyed by the sensitive value
itself** (`src/config/logging.py:102-119`). Live proof that a prior request's PII
is still held after its scope closed:

```
after request 1: CacheInfo(hits=0, misses=2, maxsize=256, currsize=2)
after request 2: CacheInfo(hits=2, misses=2, maxsize=256, currsize=2)   ← hit on the prior request's PAN/Aadhaar keys
after an unrelated request: CacheInfo(hits=2, misses=3, maxsize=256, currsize=3)
```

A cache *hit* in request 2 can only happen if request 1's PAN and Aadhaar were
still stored as keys. Retention is bounded by 256-entry LRU eviction, not by the
request lifetime — so up to 256 applicants' identifiers sit in process memory
(as cache keys and inside compiled pattern objects) indefinitely, visible in a
core dump or heap snapshot. This directly contradicts the module docstring's
"Registration is **request-scoped**". `scrub_text` itself correctly stops
redacting after the scope closes, so the *behaviour* is scoped; only the
*retention* is not.

### G3-F4 — MEDIUM — `X-Request-ID` is accepted unvalidated and unbounded (SEC-004 confirmed at HEAD)

`src/api/middleware.py:86-87` is `inbound or uuid4().hex` — no length cap, no
charset check, no format validation. Live:

| Probe | Result |
|---|---|
| 10,000-char id | 200, echoed in full, 10,146-byte log line |
| **200,000-char id** | **200**, echoed in full in the response header, **200,146-byte log line** |
| `a", "level": "CRITICAL", "x": "\` | 200, reflected verbatim into the response header and into the `request_id` field |
| `café-\xff\xfe` (latin-1 bytes) | 200, raw non-ASCII bytes echoed in the response header |
| duplicate `X-Request-ID: first` / `second` | `first` wins (deterministic, fine) |
| empty `X-Request-ID:` | falls through to a generated uuid (correct — AC4 holds) |

Impact: an attacker-controlled 200 KB value is written into every log line for
that request and echoed in a response header; the forged-field payload lands
verbatim in `request_id`, which is safe in this JSON formatter but hostile to any
downstream pipeline that greps or re-serialises. Fails open, not closed.

### G3-F5 — LOW — the Money wire parser silently accepts non-wire-format strings (SEC-007 confirmed at HEAD)

```
Money("12_34")       → 1234.00      ← Python Decimal accepts underscores: a silent 100x misread
Money("  12.34  ")   → 12.34        ← surrounding whitespace accepted
Money("1e-999999")   → 0.00         ← silent truncation to zero
```

`MoneyField` delegates straight to `Money`, so these reach the type from the
wire. D-G specifies "a quoted 2dp string"; there is no regex/format gate. Only
LOW because no endpoint currently accepts a money input, but `"12_34"` → 1234.00
is the kind of coercion that becomes a disbursement defect later.

### G3-F6 — LOW — redaction coverage is a one-shot enumeration (SEC-016 confirmed at HEAD)

Negative control: a logger created *after* `configure_logging` carries no
`RedactionFilter` (`False`). In practice it still gets scrubbed, because it
propagates to the root handler, which carries its own `RedactionFilter`. The
residual risk is a future library logger that sets `propagate = False` or
attaches its own handler — exactly what uvicorn does, and why
`_JSON_ROUTED_LOGGERS` is a hardcoded three-name list. Stays LOW because group
A's own 11 loggers are all covered.

### G3-F7 — LOW (new) — `Money`'s ceiling and rounding are hostage to the ambient decimal context

`Money` never opens a `localcontext`, so it inherits the thread-local
`decimal` context. Live:

```
default prec=28:  Money("123456789.99") = 123456789.99
prec=6:           Money("123456789.99") → RAISED InvalidMoneyAmountError
```

Any third-party code lowering `decimal.getcontext().prec` silently changes both
the maximum representable amount and the intermediate rounding of `multiply`, on
a type whose stated purpose is that money "never drifts by rounding error". It
fails closed (an exception, not a wrong number), which is why this is LOW. The
undocumented ceiling is ~1e26: `Money("1" + "0"*26)` raises.

### G3-F8 — LOW (new) — `HEAD /health` returns 405

```
HEAD /health  → 405 {"error":"HTTPError","detail":"Method Not Allowed"}
```

FastAPI's `@router.get` does not register HEAD. Load balancers and uptime
monitors that default to HEAD would read the service as unhealthy. AC5 and the
contract both specify GET, so this is not an AC violation — it is an operational
note for E15-S2's container health check.

### G3-F9 — LOW (new) — the DPD classifier has no runtime type guard

```
classify_by_days_past_due(29.9)         → CURRENT   (float accepted)
classify_by_days_past_due(True)         → CURRENT   (bool accepted)
classify_by_days_past_due("35")         → TypeError (unhandled, not ValueError)
classify(datetime(...), date(...))      → TypeError (unhandled)
```

The signature says `int`; mypy covers first-party callers, so LOW. Noted because
the negative case raises a bare `TypeError` rather than the module's own
`ValueError` contract.

## 4. Refuted candidates (live evidence that a suspected defect is NOT present)

Each of these was a hypothesis I actively tried to confirm and could not. An
explicit refutation is as load-bearing as a finding.

| # | Candidate | Refuting evidence |
|---|---|---|
| R1 | **CRLF in `X-Request-ID` splits the response / injects a header** | Raw socket, `X-Request-ID: req\r\nfake: injected`. h11 parses this as two *request* headers. Response: `200`, `x-request-id: req`, no `fake` header on the response. No response splitting. |
| R2 | **Bare LF in the header value** | `400 Bad Request` — "Invalid HTTP request received." The request never reaches the app. |
| R3 | **obs-fold continuation line smuggles a value** | `400 Bad Request`. |
| R4 | **ANSI/terminal escapes reach the log sink** | `X-Request-ID: \x1b[31mRED\x1b[0m\x1b]0;pwned\x07` → `400 Bad Request`. Rejected at the parser. |
| R5 | **NUL byte in the id** | `400 Bad Request`. |
| R6 | **A `"` or `\` in the id or path corrupts the JSON log line** | `json.dumps` escapes them. `36/36` log lines across every probe parsed as valid JSON, including the 200,000-char id line and the newline-bearing path line. The forged-field payload lands *inside* the `request_id` string value, structurally inert. |
| R7 | **Correlation id bleeds across concurrent requests** | 30 simultaneous requests with distinct ids: `all_200=True`, `echo_mismatches=0`, `distinct_echoed_ids=30`, and in the log `expected_ids=30 logged_ids=30 missing=[] unexpected=[] ids_logged_more_than_once=[]`. Contextvar isolation holds. |
| R8 | **PII leaks on the sync (`def`, threadpool) handler path** | No sync handler exists in the served app; I added one to the *real* `create_app()` via a throwaway route. Both paths: `PAN_in_logs=0 AADHAAR_in_logs=0 PAN_in_body=0`, traceback shows `pan=[REDACTED] aadhaar=[REDACTED]`, stack confirms `run_in_threadpool` → `context.run`. The mutable-set-in-a-contextvar design in `logging.py:38-44` does survive the context copy. **CR-002 / SEC-002 confirmed fixed, including the path the fix was specifically reasoned about.** |
| R9 | **The 500 path loses the correlation id (SEC-006 / CR-001 / CR-003)** | 500 response carries `X-Request-ID: probe-async-handler`; both the access line and the ERROR traceback line carry that id; body is the frozen envelope `{"error":"InternalServerError","detail":"internal server error","context":{}}` with no path, SQL or message leakage. **Confirmed fixed.** |
| R10 | **Framework non-2xx bypasses the frozen envelope (CR-001 / SEC-020)** | Live: 404 → `{"error":"NotFound","detail":"Not Found","context":{}}`; 405 → `{"error":"HTTPError","detail":"Method Not Allowed","context":{}}`; both `application/json` and both stamped with `x-request-id`. **Confirmed fixed.** |
| R11 | **`Money` accepts NaN / sNaN / Infinity / float / bool** | All five raise `InvalidMoneyAmountError`. `multiply(Decimal("NaN"))` also raises. Wire path rejects `"NaN"`, `"Infinity"`, a JSON float and a JSON int. |
| R12 | **SEC-008's exception-type claim for an integer scalar** | `multiply(10**999999)` raises `InvalidMoneyAmountError`, not `Overflow`. Only the *`Decimal`-scalar* shape leaks (see `G3-F2`) — the prior finding's mechanism was partly wrong, and I am recording the corrected one. |
| R13 | **SEC-009 — frontend money hangs on a pathological exponent** | `decimal.js`, live: `new Decimal('1e10000').toFixed(2)` = 1 ms, `1e100000` = 4 ms, `1e1000000` = **40 ms**. Linear in digits, no hang. `1e9000000000000000` stays finite; `NaN` is rejected by `isFinite`. **Downgrade to informational.** |
| R14 | **QA-VM-003 only passes because the denominator is 1 at INFO** | Rebooted at `TRUELEND_LOG_LEVEL=DEBUG` (confirmed applied: an `asyncio` DEBUG line appears). Still exactly one request-scoped line, still `request_id == req-abc`. |
| R15 | **SEC-001 ReDoS reachable through a different backtracking shape** | Not re-derived from the description; I probed the value-with-separator branch (`re.escape`, literal) and the joined branch. `_scrub` stayed sub-millisecond on every shape I sent, and the 200,000-char id path returned in normal time. No new shape found. Consistent with the pack's independent confirmation. |
| R16 | **Malformed-request log lines break AC3's "100% JSON"** | The three `400` probes each logged `{"level": "WARNING", "logger": "uvicorn.error", "message": "Invalid HTTP request received.", "request_id": ""}` — valid JSON, and an empty id is correct: parsing failed, so there was no request and no inbound id to honour. Not an AC violation. |

## 5. Performance and SLO

- **p95 `GET /health` = 1.53 ms** over 60 samples (min 1.25, p50 1.39, max 2.17).
  Inside the 1 s AC5 budget and the 500 ms SLO by three orders of magnitude.
- **No perf baseline exists** (`performance: null` in the manifest; no
  `perf-baseline` artefact). First/greenfield build → **WARN, not FAIL**, per the
  performance-ratchet rule. No regression is measurable.
- **SLO error-rate:** 0 5xx on the served process. Recorded as a WARN rather
  than a pass, because `G3-F1` means the counter feeding this sensor is
  attacker-writable — the sensor cannot be trusted until that is fixed.

## 6. Scope notes and evidence gaps (recorded, not waived)

- No `playwright_checks`, `design_checks` or `accessibility_checks` are in
  contract A, so no browser layer was contracted or run. Layer 2 is
  **not applicable**, not skipped.
- The served app has **no route that raises**, so the unhandled-500 path is not
  reachable black-box. I verified it by adding a throwaway route to the real
  `create_app()` (instrumentation, not product code). Flagged so the reader
  knows R8/R9 are instrumented rather than purely black-box.
- The stale `specs/reviews/security-verdict.json` still reports `pass: false`
  with SEC-001/SEC-002 as `high`. Both are fixed at HEAD on my evidence
  (SEC-002 directly, SEC-001 consistent with the pack's timing). That file needs
  regenerating; I did not edit it, and I did not edit `features.json`.
- `features.json` currently marks F001–F005, F009–F011, F070–F073 all
  `passes: true`. On my evidence those AC-level claims are **correct**. I made no
  changes to the file.

## 7. Artefacts

| Path | What |
|---|---|
| `.claude/state/g3eval3-uvicorn.log` | INFO-level server log (all probes, 252 KB — the 200 KB line is probe 7's own payload) |
| `.claude/state/g3eval3-uvicorn-debug.log` | DEBUG-level server log (R14) |
| `.claude/state/g3eval3-expected-ids.json` | the 30 concurrency ids, for the log cross-check (R7) |
| `specs/reviews/evaluator-evidence-instance3.json` | machine-readable evidence ledger |

Probe scripts were written under `.claude/state/g3eval3-*.py` and removed after
the run; every command and its output is reproduced above.
