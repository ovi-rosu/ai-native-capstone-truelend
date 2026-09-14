# Evaluator Report — `/gate --group A`, round 3

**Instance:** 1 of 3 (canonical outputs) · **independent**, no coordination with siblings
**HEAD:** `ba457bf` · **Base:** `14e9487` · **Branch:** `feat/harness-scaffold-and-planning`
**Verification mode:** `local` (Docker absent) · **port 8031**
**Boot:** `cd backend && uv run uvicorn src.api.app:app --host 127.0.0.1 --port 8031`
**Served app:** `src.api.app:app` (i.e. `create_app()`, so `CorrelationIdMiddleware` is in the path)
**Model tier:** opus · **Evaluated:** 2026-09-14

---

## FUNCTIONAL VERDICT: **PASS**

`verdict_scope: functional`. All 3 frozen `api_checks` pass. All 14 group-A
acceptance criteria pass, including the two never-before-evaluated E15-S4
criteria. Two mutation tests confirm the passing tests are not vacuous.

**This is not a clearance of `/gate`.** Two things are outside the functional
verdict and outside an evaluator's gift:

1. **B-4 is STILL OPEN** and independently confirmed by measurement (below). It
   is a robustness/DoS defect, not an acceptance-criterion failure — no group-A
   AC asserts anything about `format()`'s time complexity — so it does not move
   the functional verdict. It must still be dispositioned before merge.
2. **The round-3 security verdict on disk contains no B-4 entry** (see
   §6). It reports `pass: true` with 0 BLOCK. It was formed without the finding
   I measured at 429 seconds. That needs reconciliation by the gate lead, not by
   me.

| Layer | Result |
|---|---|
| Layer 1 — API (3 frozen checks) | **PASS** 3/3 |
| Layer 2 — Playwright / design / accessibility | **not contracted** (see §5) |
| Layer 3 — schema / contract conformance | **PASS** with one documented deviation (§5) |
| Performance ratchet | **WARN — no baseline** (greenfield); measured p95 0.99 ms vs 500 ms budget |
| SLO error-rate sensor | **PASS** — `error_rate_pct: 0`, `p95_ms: 4.75` (no longer `null`) |
| Contract freeze | **verified** — `sprint-contracts/A.json` sha256 matches `contract-freeze.json` |

---

## 1. Health check and contract integrity

```
$ curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8031/health
health OK attempt 1

$ sha256sum sprint-contracts/A.json
a0625d4b737e36c76e628352fd2c130c8342187558f4e4dc4e5c30f1793e99a7 *sprint-contracts/A.json
# contract-freeze.json: "path":"sprint-contracts\\A.json",
#                       "sha256":"a0625d4b737e36c76e628352fd2c130c8342187558f4e4dc4e5c30f1793e99a7"
$ git status --short sprint-contracts/   ->  0 modified files
```

The contract was read, hashed and never written.

---

## 2. Layer 1 — the three frozen `api_checks`

### QA-VM-003 — PASS (`matrix_ids: VM-003`)

`GET /health` with `X-Request-ID: req-abc`; every log line emitted while serving
must parse as JSON and carry `request_id == req-abc`. Log lines were isolated by
byte-offset on the server's own stdout, not by grep, so "100% of the lines
emitted while serving" is exactly what was measured.

```
HTTP/1.1 200 OK
x-request-id: req-abc
{"status":"ok","database":"unconfigured","version":"0.1.0"}

--- log lines emitted while serving ---
{"timestamp": "2026-09-14T13:05:16.522437+00:00", "level": "INFO",
 "logger": "truelend.access", "message": "GET /health -> 200", "request_id": "req-abc"}

total lines: 1 | parsed+correct id: 1 | bad: []
QA-VM-003 LOG ASSERTION: PASS
```

### QA-VM-004 — PASS (`matrix_ids: VM-004`)

`GET /health` with no `X-Request-ID`; a generated non-empty id on every
request-scoped line, echoed on the response.

```
HTTP/1.1 200 OK
x-request-id: 20ebf37c2fff44668337862cb01e2d23
echoed id = [20ebf37c2fff44668337862cb01e2d23] len=32
{"timestamp": "...", "logger": "truelend.access", "message": "GET /health -> 200",
 "request_id": "20ebf37c2fff44668337862cb01e2d23"}
lines: 1 echoed: 20ebf37c2fff44668337862cb01e2d23 nonempty: true bad: []
QA-VM-004 LOG ASSERTION: PASS
```

### QA-VM-005 — PASS (`matrix_ids: VM-005`)

```
run1 status=200 total=0.001613s      content-type: application/json
run2 status=200 total=0.001528s      body parses: {"status":"ok","database":"unconfigured","version":"0.1.0"}
run3 status=200 total=0.001522s
run4 status=200 total=0.001754s
run5 status=200 total=0.001570s
```

Worst measured 1.75 ms against a 1 s budget.

---

## 3. Story acceptance criteria

| AC | Feature | Verdict | How it was verified |
|---|---|---|---|
| E15-S1-AC1 | F001 | PASS | Registered PAN / Aadhaar / salary-doc absent from the captured buffer; `test_sensitive_application_values_never_appear_in_any_log_line`. Unit-level only — group A ships no endpoint that accepts an application payload. |
| E15-S1-AC2 | F002 | PASS | Enumeration shows the filter on 11/11 configured loggers, and under `uvicorn`'s own `dictConfig` too. **Mutation-killed** (§4.1). See §6 W-1 for a residual test-quality defect. |
| E15-S1-AC3 | F003 | PASS | = QA-VM-003, live. |
| E15-S1-AC4 | F004 | PASS | = QA-VM-004, live. |
| E15-S1-AC5 | F005 | PASS | = QA-VM-005, live. |
| E9-S1-AC1 | F009 | PASS | 200 random principal/rate/tenure triples; every `Money` field a `Decimal` at exactly 2dp. See §6 W-4: the AC says "a schedule is computed" and no schedule type exists in group A, so the test uses direct arithmetic over the triple as a proxy. |
| E9-S1-AC2 | F010 | PASS | Static float guard reports 0 operations in `money.py` + `serializers.py`, and 7 seeded-leak control cases prove the guard is not vacuous (`test_float_guard_detects_realistic_leaks`). |
| E9-S1-AC3 | F011 | PASS | `frontend npm test` 18/18 in `money.test.ts`; static check reports 0 float risk in `src/types/money.ts` with its own negative controls; `npm run lint` and `npm run typecheck` clean. |
| E11-S1-AC1 | F070 | PASS | `test_35_days_past_due_is_dpd_30`. |
| E11-S1-AC2 | F071 | PASS | Full 0–400 sweep plus every floor boundary (0/29/30/59/60/89/90/179/180), no gap, no overlap. |
| E11-S1-AC3 | F072 | PASS | CURRENT for due-date-is-as-of-date and future-due-date. |
| E11-S1-AC4 | F073 | PASS | `test_result_carries_bucket_only_no_fee_or_charge_attribute`. |
| **E15-S4-AC1** | **F108** | **PASS** | New. p95 computed from the scraped cumulative buckets by hand (§3.1). |
| **E15-S4-AC2** | **F109** | **PASS** | New. Live hostile-input probes plus the log half (§3.2). |

### 3.1 E15-S4-AC1 — the histogram, and p95 actually computed

Not a grep for the metric name. 49 real requests were served, `/metrics` was
scraped, and p95 was computed from the cumulative buckets using the Prometheus
`histogram_quantile` interpolation.

```
$ curl -s http://127.0.0.1:8031/metrics
# TYPE http_request_duration_seconds histogram
http_request_duration_seconds_bucket{method="GET",route="/health",le="0.005"} 49
... (0.01 0.025 0.05 0.1 0.25 0.5 1 2.5 5 10) ...
http_request_duration_seconds_bucket{method="GET",route="/health",le="+Inf"} 49
http_request_duration_seconds_count{method="GET",route="/health"} 49
http_request_duration_seconds_sum{method="GET",route="/health"} 0.029746

$ node p95.js metrics1.txt
labels: {method="GET",route="/health"}
  count=49 sum=0.029746 mean=0.607ms
  cumulative/monotonic: true   +Inf==_count: true
  computed p95 = 4.750 ms  vs SLO 500 ms -> within budget
  -> COMPUTABLE
E15-S4-AC1 p95 COMPUTABLE: PASS
```

Three independent confirmations that this is real and not an artefact of a
degenerate single-bucket distribution:

1. **The buckets are genuinely cumulative.** Driving the production
   `observe_duration` with a known spread (90 × 2 ms, 6 × 300 ms, 4 × 800 ms)
   and re-parsing the rendered exposition:

   ```
   ..._bucket{...,le="0.25"} 90
   ..._bucket{...,le="0.5"}  96
   ..._bucket{...,le="1"}   100
   ..._count{...} 100     ..._sum{...} 5.180000

   true p95 of the samples  = 300.0 ms
   p95 from the exposition  = 458.3 ms
   monotonic non-decreasing = True
   +Inf == _count           = True
   VERDICT: p95 tracks the real distribution
   ```

   The 300 → 458 ms difference is the expected bucket-resolution error of a
   Prometheus histogram (the true value falls inside the `(0.25, 0.5]` bucket
   and is linearly interpolated). It is not an error in the exposition. `0.5` is
   one of the bounds, so the 500 ms SLO can also be evaluated exactly as a
   bucket fraction without interpolating at all.

2. **This project's own SLO sensor now reads it.** The business value E15-S4
   claims is that `slo.p95_ms` stops being `null`:

   ```
   $ node .claude/scripts/slo-check.js --url http://127.0.0.1:8031
   {"verdict":"pass","error_rate_pct":0,"p95_ms":4.75,
    "budgets":{"error_rate_pct":1,"p95_ms":500},"breaches":[],"exit":0}
   ```

   `4.75` matches my hand computation of `4.750` exactly, from two independent
   implementations.

3. **Mutation-killed** — §4.2.

### 3.2 E15-S4-AC2 — hostile input, one line, no forged series

**Metrics-label half.** Raw sockets, because `curl` will not emit a malformed
request line. Seven crafted percent-encoded paths carrying complete forged
exposition payloads (LF, CRLF, quote-close, backslash-quote, NUL/BEL/ESC, form
feed, NEL) and seven attacker-chosen methods:

```
A1 LF + forged series        -> HTTP/1.1 404 Not Found
A2 CRLF + forged series      -> HTTP/1.1 404 Not Found
A3 quote-close + payload     -> HTTP/1.1 404 Not Found
A4 backslash-quote           -> HTTP/1.1 404 Not Found
A5 NUL, BEL, ESC             -> HTTP/1.1 404 Not Found
A6 form feed 0x0C            -> HTTP/1.1 404 Not Found
A7 NEL 0x85                  -> HTTP/1.1 404 Not Found

B method=b'FOOBAR' / b'GETX' / b'GE"T' / b'GE\\T' / b'GE!T' / b'GE#T' / b'A'*40
                             -> HTTP/1.1 400 Bad Request   (all seven)

$ grep "forged|route=\"cr\"|route=\"ff\"|777|999999" metrics2.txt
NO forged series present

distinct route label values: 3 -> ['/health', '/metrics', '<unmatched>']
distinct method label values: 1 -> ['GET']
```

**Log half.** 20 log lines emitted during those probes, scanned bytewise:

```
lines: 20   with raw control chars: 0   unparseable: 0
```

A `X-Request-ID` containing a raw TAB (accepted by the parser) renders escaped,
not raw: `"request_id": "a\tb"`. The hardest case — a real multi-line traceback
carrying attacker text — also holds:

```
== A. hostile message ('x"}\n{"level":"ERROR",...}\r\x00\x07\x1b[31m\x0c\x0b\x7f tail') ==
   rendered lines: 1 OK     raw control chars: 0 OK     round-trips as one JSON: True
   hostile text survives as DATA inside message (not a new record): True
== B. real multi-line traceback carrying the same text ==
   rendered lines: 1 OK     raw control chars: 0 OK     round-trips as one JSON: True
E15-S4-AC2 (log half): PASS
```

---

## 4. Mutation tests

Two, both on ACs I am passing. Both restored and proven restored by blob hash.

### 4.1 E15-S1-AC2 — the redaction-filter install loop

Mutant: `_install_redaction_filter_everywhere()` installs on root only
(`loggers = [logging.getLogger()]`, `loggerDict` loop deleted).

```
>       assert not missing, f"loggers without a RedactionFilter: {missing}"
E       AssertionError: loggers without a RedactionFilter: ['concurrent.futures',
        'asyncio', 'fastapi', 'httpx', 'pydantic_settings', 'dotenv.main',
        'truelend.access', 'uvicorn', 'uvicorn.error', 'gunicorn.error',
        'uvicorn.access', 'watchfiles.watcher', 'watchfiles.main']
FAILED tests/unit/test_log_redaction.py::test_redaction_filter_installed_on_every_configured_logger
FAILED tests/unit/test_log_redaction.py::test_redaction_filter_covers_every_logger_under_the_real_server_config
2 failed, 13 deselected
```

**MUTANT KILLED by both AC2 tests.** This partially refutes the round-2 WARN:
the tests are *not* inert — they do detect a broken implementation. The residual
defect is narrower and is reported honestly as W-1 in §6 rather than as
"vacuous".

Restore:

```
$ git checkout -- backend/src/config/logging.py
restored blob: 01c23ad61062286376765e0ba337e6171f712bb4
HEAD blob    : 01c23ad61062286376765e0ba337e6171f712bb4
$ uv run pytest -k "every_logger or every_configured" -q   ->  2 passed
```

### 4.2 E15-S4-AC1 — cumulative buckets

Mutant: `running += count` → `running = count` in `_histogram_lines()` (buckets
no longer cumulative).

```
>       assert counts == sorted(counts), f"buckets are not cumulative: {observed}"
FAILED tests/architecture/test_observability_contract.py::test_histogram_buckets_are_cumulative_and_carry_count_and_sum
1 failed, 5 passed
```

**MUTANT KILLED.** But only by *one* of the three AC1 tests —
`test_p95_is_computable_from_the_exposition` survived it, because with 20
identical sub-5-ms observations a non-cumulative histogram still puts all 20 in
the first bucket and `count >= target` still holds. Recorded as W-5 in §6. My
own spread verification (§3.1 item 1) is what actually distinguishes the two.

Restore:

```
$ git checkout -- backend/src/api/platform/routes.py
restored: 355837f7ab08a7401a23ae9580da587f2e6dac27
HEAD    : 355837f7ab08a7401a23ae9580da587f2e6dac27
$ git diff --stat -- backend/src frontend/src   ->  (empty)
$ uv run pytest tests/architecture/test_observability_contract.py -q  ->  6 passed
```

### Deterministic suites at HEAD, against source proven pristine

```
$ git diff --stat -- backend/src frontend/src      (empty, pre-run)
$ cd backend && uv run pytest -q                   104 passed
$ git diff --stat -- backend/src frontend/src      (empty, post-run)

$ cd frontend && npm test        20 passed  (18 in money.test.ts + 2 in a sibling instance's probe file)
$ npm run lint                   clean
$ npm run typecheck              clean
```

---

## 5. Layers 2 and 3

**Layer 2 — not contracted.** `sprint-contracts/A.json` declares `api_checks`
only: no `playwright_checks`, no `design_checks`, no `accessibility_checks`.
`verification.e2e_targets` is `[]` and group A serves no frontend (the frontend
is a `Money` module and a presentational component, with no app shell and no
route). No browser tool was used and none was required; `classifyEvidence`
returns not-applicable for a contract with zero `playwright_checks`. No check is
recorded as passed that I could not execute.

**Layer 3 — contract conformance: PASS with one documented deviation.**

| Contract (`api-contracts.md` §Operational endpoints) | Observed |
|---|---|
| `GET /health` → `200 {status, database, version}` | `{"status":"ok","database":"unconfigured","version":"0.1.0"}` — all three keys, all strings |
| `GET /metrics` → `200 text/plain`, RED labelled `method`, `route`, `status` | `content-type: text/plain`, `http_requests_total{method=...,route=...,status=...}` |

Deviation: the contract's illustrative value for `database` is `"ok"`; the
implementation returns `"unconfigured"` because E15-S1 owns no database engine
(it arrives with E1-S1 in group B) and the field is a registered port. The
reasoning is documented in the module docstring and is sound — hardcoding `"ok"`
would be worse. Flagged for group B: `E15-S2-AC1` asserts "all three report
healthy", so E1-S1 must call `register_database_probe`. Not a group-A failure.

**Performance ratchet — WARN, not FAIL.** No baseline exists, which is the
greenfield case the rules class as WARN:

```
$ node .claude/scripts/perf-baseline.js --compare --base http://127.0.0.1:8031
perf-baseline: no baseline at specs/brownfield/perf-baseline.json — capture one first

$ node .claude/scripts/perf-baseline.js --measure --base http://127.0.0.1:8031 --samples 40
MEASURE: /health p50=0.66ms p95=0.99ms p99=1.79ms (40 samples)
```

No regression is possible against an absent baseline, and 0.99 ms is three
orders of magnitude inside the 500 ms budget. I did not write the baseline file —
that is not in the evaluator's output set.

---

## 6. Round-2 BLOCKs B-1 … B-4, re-tested by execution

### B-1 — `/metrics` exposition injection: **CLOSED**

Seven crafted paths carrying complete forged series, plus seven attacker-chosen
methods, produced zero forged series (§3.2). The mechanism is sound in two
independent ways: the `route` label is the *matched route template* or the single
`<unmatched>` bucket, so the percent-decoded path never reaches a label at all;
and `_escape_label` escapes `\`, `"` and `\n` on whatever does.

On the gate lead's two specific questions:

- **Is carriage return still unescaped?** Yes — `_LABEL_ESCAPES` covers `\\`,
  `"` and `\n`, not `\r`, and not `\x0c`/`\x0b`/`\x00`. **It is not reachable.**
  The only two label sources are `route` (template or `<unmatched>` — never
  attacker text) and `method`. Recorded as W-2: a latent hardening gap, not an
  exploitable one.
- **Is `scope["method"]` attacker-controlled?** **No.** All seven non-standard
  method tokens — including `GE"T` and `GE\T`, which are the only ones that
  could carry an escapable character — were rejected with `400 Bad Request` by
  the `httptools`/llhttp parser *before* ASGI, so no series is minted at all.
  The method label is confined to llhttp's fixed known-method table, which
  contains no quote, backslash or control character.

### B-2 — `/metrics` unbounded cardinality: **CLOSED, by measurement**

2,000 distinct attacker-chosen paths over one keep-alive connection:

```
server pid on 8031: 57340
RSS before      : 57844 KB          series before   : 45
sent            : 2000 distinct attacker paths on one connection
RSS after       : 59900 KB  (delta +2056 KB)
series after    : 45  (delta +0)
distinct route label values: 3 -> ['/health', '/metrics', '<unmatched>']
attacker-minted route labels: NONE
distinct method label values: 1 -> ['GET']
B-2 VERDICT: cardinality BOUNDED
```

Round 2 measured 60,000 label values and +28.2 MB permanently retained. Now: **0
new series**, and +2 MB of transient allocator noise with the series count
unchanged, so nothing is retained per path.

The gate lead's two follow-ups, both answered:

- **Do the new `_duration_counts` / `_duration_totals` inherit the bound?** Yes.
  Both are keyed `(method, route_label(scope))` through the same
  `route_label()`, and the exposition confirms it empirically — the histogram
  shows exactly the same three route values as the counters after the flood.
- **Does `method` re-open it?** No. See B-1: non-standard method tokens are
  rejected at 400 by the protocol layer and never reach the counter.

### B-3 — `HTTPException.headers` discarded: **CLOSED, by request**

Live:

```
$ curl -i -X POST http://127.0.0.1:8031/health
HTTP/1.1 405 Method Not Allowed
allow: GET
{"error":"HTTPError","detail":"Method Not Allowed","context":{}}
```

The 401 and 409 paths do not exist in group A, so they were exercised through
the *production* `create_app()` / `register_exception_handlers` with throwaway
routes (no production file edited):

```
GET    /probe-401   -> 401   www-authenticate: Bearer realm="truelend"
                             {"error":"Unauthorized","detail":"no token","context":{}}
GET    /probe-409   -> 409   x-custom: kept
                             {"error":"Conflict","detail":"illegal transition","context":{}}
GET    /probe-500   -> 500   {"error":"InternalServerError","detail":"internal server error","context":{}}
POST   /probe-422   -> 422   {"error":"ValidationError","detail":"request validation failed",
                              "context":{"field":"body.amount"}}
DELETE /probe-401   -> 405   allow: GET

401 keeps WWW-Authenticate: True
409 keeps custom header    : True
405 keeps Allow            : True
B-3 VERDICT: headers PRESERVED
```

The 500 and 422 paths were checked too, as asked: the 500 carried none of the
`C:\secrets\db.env password=hunter2` planted in the raised exception, and the
422 named the field without echoing the rejected value. Every path carried
`x-request-id` and the frozen envelope shape.

### B-4 — quadratic thousands-separator regex: **STILL OPEN**

`frontend/src/types/money.ts:78` is byte-identical at HEAD to its round-2 state.
Round 2 recorded one instance refuting this by timing `toFixed()`. Measuring the
**regex itself**, in isolation, on an all-digit string:

```
== 1. the regex ALONE (/\B(?=(\d{3})+(?!\d))/g) ==
  digits=  2000        1.4 ms   ratio vs half-size: -
  digits=  4000        5.6 ms   ratio vs half-size: 3.88
  digits=  8000       23.4 ms   ratio vs half-size: 4.16
  digits= 16000       99.6 ms   ratio vs half-size: 4.26
  digits= 32000      415.1 ms   ratio vs half-size: 4.17
```

A ratio of ~4.0 per doubling of input is the signature of Θ(n²). And the sink
round 2 timed instead:

```
== 2. toFixed(2) ALONE ==
  1e  2000  toFixed: 0.1 ms
  1e  8000  toFixed: 0.1 ms
  1e 32000  toFixed: 0.7 ms
  1e100000  toFixed: 2.1 ms
```

`toFixed()` is **cheap even at 100,001 digits (2.1 ms)**. Round 2's refutation
timed a linear operation and concluded the quadratic one was fine. The cost is
entirely in the regex.

**Reachability — the question the gate lead asked. No upstream bound exists.**

```
== 4. does any bound exist upstream of format()? ==
  fromWire(1e100000)     accepted=true  toWire() length=100004
  fromWire(1e1000000)    accepted=true  toWire() length=1000004
  fromWire(999999999...) accepted=true  toWire() length=50003
```

`toQuantizedDecimal()` checks only `isFinite()`. `decimal.js`'s default `maxE`
is 9e15, so `1e1000000` is finite and is accepted; `toDecimalPlaces(2)`
preserves the magnitude and `toWire()` returns a 1,000,004-character string
straight into `format()`. Neither the constructor, nor `fromWire`, nor `toWire`
bounds the digit count or the magnitude. End to end through the **public** API:

```
== 3. END TO END through the public Money API ==
  Money.fromWire("1234567.89") parse 0.2 ms  format   0.2 ms  (12 chars)
  Money.fromWire("1e4000")     parse 0.0 ms  format   5.7 ms  (5337 chars)
  Money.fromWire("1e16000")    parse 0.0 ms  format 101.7 ms  (21337 chars)
  Money.fromWire("1e40000")    parse 0.0 ms  format 647.7 ms  (53337 chars)
  fromWire("1e64000")  -> toWire() 64004 chars  -> format()  1659 ms
  fromWire("1e100000") -> toWire() 100004 chars -> format()  4088 ms
```

An **8-byte** input blocks the JavaScript main thread for **4.1 seconds**. My
quadratic model predicted 4.1 s from the 32,000-digit datapoint and measured
4.088 s, so the model is validated; it projects ~405 s for the 9-byte
`1e1000000`. A sibling instance's independent probe, run through the project's
own vitest, measured that case directly and agrees:

```
wire_bytes=8 fromWire_ms=0.1 toWire_ms=0.6 integer_digits=100001 format_ms=4074.9
wire_bytes=9 toWire_ms=29.9 format_ms=429463.7 finished=true
```

**429,464 ms — 7 minutes 9 seconds — from a 9-byte string.** Two instances
using different harnesses agree to within 0.4% on the 8-byte case. Round 2's
"did not finish in 100 s" is confirmed and now quantified.

`MoneyText`'s prop type is `Money | string` and it calls
`Money.fromWire(money).format()` on the string branch, so any untrusted string
routed to that component is a main-thread freeze.

**Severity and disposition.** No group-A AC asserts anything about `format()`'s
complexity, so this does not fail an acceptance criterion and does not move the
functional verdict. It is nonetheless a real defect with a measured 7-minute
worst case and no upstream bound. It is **not currently exploitable end to end**:
group A wires no fetch and no form into `MoneyText`, and the backend serializer
emits bounded 2dp strings. That makes it a latent defect whose severity rises
the moment the first real caller appears — which is group B. The fix is one
line either way: bound the digit count in `toQuantizedDecimal`, or group with a
linear loop instead of a lookahead.

---

## 7. Round-2 WARNs re-judged at HEAD

| ID | Finding | Status at HEAD |
|---|---|---|
| **SEC-103** | `sanitise_context` skipped `scrub_text` for int/bool values and for mapping KEYS | **CLOSED.** See below. |
| **W-1** | Both AC2 tests pass "by construction" | **PARTIALLY REFUTED, narrowed.** See below. |
| **W-2** | `_escape_label` does not escape `\r` or other control characters | **OPEN, unreachable.** Latent hardening gap (B-1). |
| **W-3** | Redaction bypass by formatting is far wider than the 5-dash case | **OPEN, harmless today.** See below. |
| **W-4** | E9-S1-AC1 says "a schedule is computed" but no schedule exists in group A | **OPEN, spec-side.** The test uses direct `Money` arithmetic over each random triple as a proxy. E9-S1's own Generation Contract lists no schedule operation, so the AC wording overreaches the story's scope. Minor; re-assert when E9-S3/E3-S1 land. |
| **W-5** | `test_p95_is_computable_from_the_exposition` survives a non-cumulative-bucket mutant | **NEW, found this round** (§4.2). Add a spread of durations, or assert monotonicity in that test too. |
| **W-6** | `HEAD /health` → 405 | **OPEN, reproduced.** RFC 9110 §9.3.2 expects HEAD wherever GET is supported; container and LB probes commonly use it. One-line fix. |
| **W-7** | `/metrics` has no authentication | **Deferral acceptable.** E15-S4 Scope Out states it explicitly, it needs an `api-contracts.md` amendment plus the auth layer arriving with E1-S1, and B-1/B-2 have removed the write-side leverage an unauthenticated scrape had. The residual exposure is read-only operational data. Must not survive group C. |
| **W-8** | `uvicorn.access` disabled on empirically false justifications | **OPEN, cosmetic.** AC3 passes on its merits (§2); the comment misstates the reason. Comment defect only. |

**SEC-103 — CLOSED.** `f5a5ace` holds:

```
'aadhaar_int'                -> '[REDACTED]'     (was: 12-digit Aadhaar egressed whole as an int)
'aadhaar_str'                -> '[REDACTED]'
'pan-[REDACTED]'             -> 'value-beside-it' (the KEY is scrubbed now)
'path'                       -> '[REDACTED]\\db.env'
'threshold'                  -> 42               (int preserved — wire contract kept)
'flag'                       -> True
leaks: NONE
```

Both halves of the finding are fixed, and the `_sanitise_value` design note is
borne out: a harmless numeric stays an `int`, so the fix did not silently change
the wire contract for a caller reading a threshold out of `context`.

**W-1 — partially refuted and narrowed.** The mutation test (§4.1) proves both
AC2 tests kill a broken install loop, so "vacuous" overstates it. The real
defect is twofold and both parts were executed:

```
loggers enumerated right after configure_logging : 11
  without a RedactionFilter                      : []

after a later logging.getLogger('app.origination.late_module'):
  registered in loggerDict : True
  has a RedactionFilter    : False
  re-enumeration reports missing: ['app.origination.late_module']

the test's negative control, logging.Logger('unregistered-probe-logger'):
  present in loggerDict (would be enumerated): False
```

1. The property holds only at the instant `configure_logging()` returns. Any
   logger created afterwards is registered in `loggerDict` with no filter.
2. The docstring's claim that the control case is "proving the check is not
   vacuous" is **empirically false**: `logging.Logger("unregistered-probe-logger")`
   is constructed directly and never enters `loggerDict`, so it is disjoint from
   the enumerated set and cannot demonstrate that the enumeration would catch a
   real omission.

Calibrating the impact honestly rather than overstating it: with **default**
propagation the root *handler* also carries a `RedactionFilter`, which catches
the record anyway —

```
late logger has its own RedactionFilter : False
late logger propagate                   : True
emitted through root handler            : {..., "message": "pan=[REDACTED]", ...}
PAN leaked with default propagation     : False
```

— so a real leak needs a logger with `propagate=False` or its own handler. AC2
as worded ("when every configured logger is enumerated, then the filter is
installed on 100% of them") is satisfied, so **F002 passes**. This is a
defence-in-depth gap plus a misleading docstring: WARN.

**W-3 — open, and harmless today for a verifiable reason.** Re-measured:

```
dash (covered)     -> redacted        dot                -> BYPASS
space (covered)    -> redacted        underscore         -> BYPASS
tab (covered)      -> redacted        slash              -> BYPASS
5 dashes           -> redacted        NBSP U+00A0        -> BYPASS
                                      soft hyphen U+00AD -> BYPASS
                                      zero width U+200B  -> BYPASS
                                      fullwidth digits   -> BYPASS
```

Round 2's specific 5-dash case is **no longer reproducible** (the `{0,4}`
separator run covers it). The broader class stands, and normalize-then-match is
the real fix. Severity stays WARN on a checked basis, not an assumed one:

```
$ grep -rn "register_sensitive" backend/src/
backend/src/config/logging.py:10:   (docstring)
backend/src/config/logging.py:60:   (docstring)
backend/src/config/logging.py:74:   def register_sensitive(...)
```

**Zero call sites in production code.** `ba457bf` put the call sites in the
*spec* Operations for E1-S1 and E4-S1 (`specs/bundles/E1-S1.json`,
`specs/bundles/E4-S1.json`) — future stories, not code. So the round-2
severity-rise trigger has **not** fired, and W-3 must be fixed before E1-S1 or
E4-S1 merges.

---

## 8. Disagreement with the round-3 security verdict — for the gate lead

`specs/reviews/security-verdict.json` is currently **uncommitted** (`M` in
`git status`) and reports:

```
gate: security   round: 3   head: ba457bf   pass: true
summary: {"block":0,"warn":6,"info":4}
unscanned: ["sast (semgrep absent)","secrets (gitleaks absent)","python-deps (pip-audit absent)"]
findings: B-1 low, B-2 low, SEC-003 low, SEC-201..206 medium, SEC-207..209 low
```

I agree with its B-1 and B-2 dispositions — I closed both independently. Two
things for the gate lead:

1. **It contains no B-4 entry.** The finding I measured at 4.1 s from 8 bytes
   and that a sibling measured at 429 s from 9 bytes appears nowhere in the
   round-3 security findings, under B-4 or any SEC-2xx id. Whether it is BLOCK
   or WARN is the security reviewer's call, not mine — but a `pass: true` formed
   without it is a verdict on an incomplete finding set.
2. **Three scanner tiers are unscanned, not passed** — semgrep, gitleaks and
   pip-audit are all absent. The verdict says so itself. `pass: true` with
   SAST and secrets unscanned is a narrower claim than it reads as.

I have not modified that file; it belongs to the concurrent security instance.

---

## 9. Housekeeping and honesty notes

- **Server killed.** `Stop-Process -Id 57340 -Force`; post-kill probe returns
  `000` and `Get-NetTCPConnection -LocalPort 8031` returns nothing.
- **Tree pristine after both mutations.** `git diff --stat -- backend/src
  frontend/src` is empty and both mutated files' blob hashes equal their HEAD
  blobs.
- **Concurrent-instance interference, disclosed.** Mid-run, sibling instances
  mutated `backend/src/api/platform/routes.py` (`running = count`) and
  `backend/src/api/middleware.py` (`route_label` returning the raw path) for
  their own mutation tests. I did not restore their mutations — doing so would
  have corrupted their measurements. Every backend measurement in this report
  was taken either **before** those mutations appeared or **after** the tree was
  re-verified pristine by `git diff --stat`, which is recorded inline at each
  test run. The `104 passed` figure was bracketed by an empty `git diff` on both
  sides.
- **Sibling scratch files present and left alone:** `backend/sec3_probe.py`,
  `backend/.eval-i3/`, `backend/.secrev3/`, `frontend/tests/unit/_eval_i2_b4.test.ts`,
  `.claude/state/tmp-review3/`, `.claude/state/tmp-sec3/`, `.qa003body.txt`.
  The frontend one is why `npm test` reports 20 tests rather than the pack's 18;
  the project's own `money.test.ts` contributes 18, unchanged.
- **My own scratch directory** is `.claude/state/tmp-eval1/`, removed at the end
  of the run.
- **Never edited:** `sprint-contracts/**` (0 modified, hash verified),
  `specs/design/architecture.md`, `api-contracts.md`, `data-models.md`.
