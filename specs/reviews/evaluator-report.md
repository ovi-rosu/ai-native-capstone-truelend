# Evaluator Report — /gate group A

**Evaluator instance:** 1 of 3 (canonical outputs)
**Verdict: FAIL** · `failure_layer: ["api", "security"]`
**Branch:** `feat/harness-scaffold-and-planning` · **Range:** `14e9487..d0b5c94` + uncommitted working tree
**Contract:** `sprint-contracts/A.json` (read-only, not modified)
**Timestamp:** 2026-09-14T06:47:00Z

**One-line reason:** `QA-VM-003` / `E15-S1-AC3` fails — only 50% of the log lines emitted while
serving the request parse as JSON — and `E15-S1-AC2` fails in the running server, where a value
explicitly marked sensitive was written to the log sink verbatim. The security gate also reports
`pass: false` (VULN-001, high) — see §15.

---

## 1. Runtime target

`project-manifest.json#verification.mode` is `local`. Docker is not used.

| Fact | Value |
|---|---|
| Official target | `uvicorn` PID 60768, `http://127.0.0.1:8000` — **already running, verified up, not restarted** |
| Health probe | `curl -s -i http://127.0.0.1:8000/health` → `HTTP/1.1 200 OK`, `x-request-id: 523250dba563455ab4949c9622e2e549`, body `{"status":"ok"}` |
| Official log | `.claude/state/uvicorn.log` |
| Isolation instance | `http://127.0.0.1:8010`, same command, log `.claude/state/evaluator1-uvicorn.log` (created by this evaluation; shut down afterwards) |

### Why an isolation instance was needed (evidence-integrity note)

`.claude/state/uvicorn.log` is **not a clean evidence source** and I did not rely on it for the
log-window checks:

1. It contains 16,514 NUL bytes (`tr -dc '\000' | wc -c`) — `grep` reports it as a binary file.
   Two processes redirected into it concurrently on Windows. All quotes below are after
   `tr -d '\000'`.
2. Line 4 is `ERROR:    [Errno 10048] error while attempting to bind on address
   ('127.0.0.1', 8000)` — a **second, failed** start. Lines 1-6 belong to that aborted process,
   lines 7+ to the live PID 60768.
3. The official server is being driven concurrently by evaluator instances 2 and 3. Their probes
   are interleaved in the same file — e.g. line 31 carries a 150+ char `AAAA…` request id and
   line 33 carries `"request_id": "abc%0d%0aX-Injected: yes"`. Neither request was mine.

A "log lines emitted while serving **this** request" criterion cannot be measured in a file with
three concurrent writers. I therefore measured byte-offset log windows against a dedicated
instance on port 8010 started with the identical command, and **separately confirmed the same
defect reproduces on the official 8000 target** (§4).

---

## 2. Verdict summary

### api_checks (`sprint-contracts/A.json`)

| id | matrix | check | verdict |
|---|---|---|---|
| QA-VM-003 | VM-003 | `GET /health` → 200, 100% of log lines parse as JSON and carry `request_id == req-abc` | **FAIL** |
| QA-VM-004 | VM-004 | `GET /health` → 200, generated `request_id` on every request-scoped line + echoed | **PASS** |
| QA-VM-005 | VM-005 | `GET /health` → 200, JSON body, response time < 1s | **PASS** |

### Acceptance criteria

| feature | AC | verdict |
|---|---|---|
| F001 | E15-S1-AC1 — 0 occurrences of PAN / Aadhaar / salary content in captured buffer | PASS (caveat) |
| F002 | E15-S1-AC2 — redaction filter installed on 100% of configured loggers | **FAIL** |
| F003 | E15-S1-AC3 — 100% of lines parse as JSON, each `request_id == req-abc` | **FAIL** |
| F004 | E15-S1-AC4 — same generated non-empty `request_id`, response echoes it | PASS |
| F005 | E15-S1-AC5 — 200, JSON body, < 1s | PASS |
| F009 | E9-S1-AC1 — every money field a `Decimal` quantized to exactly 2dp | PASS (caveat) |
| F010 | E9-S1-AC2 — static check reports 0 float arithmetic ops in backend money paths | PASS |
| F011 | E9-S1-AC3 — frontend money held as decimal, never float; 0 float ops | PASS |
| F070 | E11-S1-AC1 — 35 days past due → `DPD-30` | PASS |
| F071 | E11-S1-AC2 — exactly one of five buckets for 0..400, no gap/overlap | PASS |
| F072 | E11-S1-AC3 — nothing past due → `CURRENT` | PASS |
| F073 | E11-S1-AC4 — bucket only, no fee / penal interest / charge | PASS |

**Story roll-up:** E15-S1 **FAIL** (2 of 5 ACs) · E9-S1 **PASS** (3 of 3) · E11-S1 **PASS** (4 of 4)

### Deterministic suites (re-run by me, not taken from the pack)

| Command | Observed | Matches pack |
|---|---|---|
| `cd backend && uv run pytest -q` | exit 0 — `42 passed, 2 warnings in 0.12s` | yes |
| `cd backend && uv run mypy src/` | exit 0 — `Success: no issues found in 12 source files` | yes |
| `cd backend && uv run ruff check .` | exit 0 — `All checks passed!` | yes |
| `cd frontend && npm test` | exit 0 — `Test Files 1 passed (1) / Tests 11 passed (11)` | yes |
| `cd frontend && npm run lint` | exit 0 — clean (additional) | — |
| `cd frontend && npm run typecheck` | exit 0 — `tsc --noEmit` clean (additional) | — |

All four suites pass exactly as the pack reports. **The green suite does not cover the two
defects below** — see §7 for why the AC2 unit test passes while the deployed server leaks.

---

## 3. QA-VM-003 — FAIL (the hard judgement)

**Criterion (verbatim):** "`GET /health` → 200 — sent with header `X-Request-ID: req-abc`;
100% of the log lines emitted while serving parse as JSON and each carries `request_id` equal to
`req-abc`"

### Method

Recorded `stat -c %s` on the isolated instance's log, issued two `GET /health` requests with
`X-Request-ID: req-abc`, slept 2s for flush, read only the byte-delta.

`offset_before=441` → `offset_after=869`.

### Response (passes)

```
HTTP/1.1 200 OK
content-type: application/json
x-request-id: req-abc

{"status":"ok"}
```
`status=200 time_total=0.016817`

### The log window — all 4 lines, verbatim

```
{"timestamp": "2026-09-14T06:41:16.045631+00:00", "level": "INFO", "logger": "truelend.access", "message": "GET /health -> 200", "request_id": "req-abc"}
INFO:     127.0.0.1:51975 - "GET /health HTTP/1.1" 200 OK
{"timestamp": "2026-09-14T06:41:16.132085+00:00", "level": "INFO", "logger": "truelend.access", "message": "GET /health -> 200", "request_id": "req-abc"}
INFO:     127.0.0.1:51976 - "GET /health HTTP/1.1" 200 OK
```

**2 of 4 lines (50%) parse as JSON.** The two `uvicorn.access` lines are plain text and carry no
`request_id` field at all. Required: 100%. **FAIL.**

### Does the startup-vs-request distinction rescue it? No.

I take the distinction seriously and applied it. The instance's four startup lines
(`INFO:     Started server process [76416]`, `Waiting for application startup.`,
`Application startup complete.`, `Uvicorn running on http://127.0.0.1:8010`) are genuinely
emitted before any request exists, and I excluded all of them — they are outside the byte-offset
window by construction.

The line that fails the criterion is **not** a startup line:

```
INFO:     127.0.0.1:51975 - "GET /health HTTP/1.1" 200 OK
```

It is emitted once per request, inside the window, and its content *is* the request being served.
Under the contract's literal wording — "log lines emitted **while serving**" — it is squarely
in scope. No reading that excludes it survives contact with the text: it is the most
request-specific line in the file. Excluding startup lines changes the ratio from 2/8 to 2/4; it
does not reach 100%.

### Root cause, proven at runtime (not inferred from source)

Two independent defects, both verified by probing the running server:

**(a) uvicorn's loggers never reach the JSON formatter.** Enumerating the logger tree inside a
live server:

```
uvicorn          propagate=False  handlers=[('StreamHandler', 'DefaultFormatter', ...)]
uvicorn.access   propagate=False  handlers=[('StreamHandler', 'AccessFormatter',  ...)]
<root>           propagate=True   handlers=[('StreamHandler', 'JSONLogFormatter', ...)]
```

`configure_logging()` clears and replaces **root's** handlers only. `uvicorn` and `uvicorn.access`
have `propagate=False` plus their own `StreamHandler`, so their records never reach root's
`JSONLogFormatter`.

**(b) Even with the formatter fixed, the id would still be wrong.** I attached a probe handler to
`uvicorn.access` *after* server startup and read the contextvar at emit time:

```
logger=uvicorn.access  request_id_var=''  msg=127.0.0.1:62884 - "GET /health HTTP/1.1" 200
logger=truelend.access request_id_var='req-abc'  msg=GET /health -> 200
```

`CorrelationIdMiddleware.dispatch` resets the contextvar in its `finally:` block before uvicorn
writes its access line. So merely attaching `JSONLogFormatter` to `uvicorn.access` would yield
`"request_id": ""` — still not `req-abc`. **A complete fix needs both the formatter wiring and a
correlation scope that outlives the middleware.** A reviewer who fixes only the formatter will
still fail this AC.

### Verdict: FAIL, not "partially met"

Both clauses of the criterion are violated (JSON parse rate, and `request_id` presence), by a
request-scoped line, on the designated runtime target. It is fully fixable in
`backend/src/config/logging.py` + `backend/src/api/middleware.py` — this is an implementation gap,
not an untestable criterion, so there is no ground for accepting it as-is.

---

## 4. Same defect on the official 8000 target

Not only the isolation instance. From `.claude/state/uvicorn.log` (PID 60768, after NUL-stripping),
lines 15-16 — an `X-Request-ID: req-abc` request served by the official target:

```
{"timestamp": "2026-09-14T06:39:11.439688+00:00", "level": "INFO", "logger": "truelend.access", "message": "GET /health -> 200", "request_id": "req-abc"}
INFO:     127.0.0.1:52936 - "GET /health HTTP/1.1" 200 OK
```

Identical interleaving: one JSON line, one plain-text line with no `request_id`. The defect is in
the product, not in my harness.

---

## 5. QA-VM-004 — PASS

**Criterion:** "sent with no `X-Request-ID` header; every request-scoped log line carries the same
generated non-empty `request_id` and the response echoes that id"

Response:
```
HTTP/1.1 200 OK
x-request-id: 16e5582b50174c5aa81472015c6a2509
{"status":"ok"}
```

Log window (2 lines):
```
{"timestamp": "2026-09-14T06:41:39.355531+00:00", "level": "INFO", "logger": "truelend.access", "message": "GET /health -> 200", "request_id": "16e5582b50174c5aa81472015c6a2509"}
INFO:     127.0.0.1:61432 - "GET /health HTTP/1.1" 200 OK
```

- generated id is non-empty, 32-hex (`uuid4().hex`) — **yes**
- the request-scoped log line carries it — **yes**, byte-identical to the header
- the response echoes that id — **yes**, `x-request-id: 16e5582b50174c5aa81472015c6a2509`

**Why this is a PASS while QA-VM-003 is a FAIL — the wording differs and the difference is
load-bearing.** VM-004 scopes to "**request-scoped** log line"; VM-003 scopes to lines "emitted
**while serving**". I tested which reading the implementation's own correlation scope supports and
found `request_id_var == ''` at `uvicorn.access` emit time (§3b) — the uvicorn access line is
emitted *after* the request scope is torn down, so it is not request-scoped in the sense this
substrate defines. VM-004 also imposes no JSON-format requirement, which is VM-003's other
independent failure. I am recording this asymmetry explicitly because it is the only thing
separating the two verdicts; if a reviewer rejects it, VM-004 fails for the same root cause as
VM-003 and the remediation is unchanged.

---

## 6. QA-VM-005 — PASS

10 consecutive samples, isolated instance:

```
status=200 content_type=application/json time_total=0.021423s body={"status":"ok"}
status=200 content_type=application/json time_total=0.003563s body={"status":"ok"}
status=200 content_type=application/json time_total=0.003239s body={"status":"ok"}
status=200 content_type=application/json time_total=0.019928s body={"status":"ok"}
status=200 content_type=application/json time_total=0.003367s body={"status":"ok"}
status=200 content_type=application/json time_total=0.003400s body={"status":"ok"}
status=200 content_type=application/json time_total=0.003392s body={"status":"ok"}
status=200 content_type=application/json time_total=0.003212s body={"status":"ok"}
status=200 content_type=application/json time_total=0.024824s body={"status":"ok"}
status=200 content_type=application/json time_total=0.025953s body={"status":"ok"}
```

10/10 status 200 · `content-type: application/json` · body parsed: `JSON OK: {"status":"ok"}` ·
max 25.95 ms, well under the 1 s budget and under the `p95_ms: 500` runtime SLO.

**Performance ratchet:** no baseline artifact exists (no `perf-baseline` state file; group A is the
first landed group, `features.json` has zero prior `passes: true`). Per the ratchet rule a missing
baseline is a **WARN, not a FAIL**. No regression can be computed. Recorded, not blocking.

---

## 7. E15-S1-AC2 — FAIL (found independently; not in the context pack)

**Criterion:** "Given the application's logging configuration, when every configured logger is
enumerated, then the redaction filter is installed on 100% of them and a logger registered without
it fails the assertion."

This is the most consequential finding in the evaluation, and the green `pytest` run hides it.

### The logger tree inside a genuinely running uvicorn server

```
  <root>                   propagate=True  logger_redaction=True  handlers=[('StreamHandler', 'JSONLogFormatter', True)]
  httpx                    propagate=True  logger_redaction=True  handlers=[]
  truelend.access          propagate=True  logger_redaction=True  handlers=[]
  uvicorn                  propagate=False logger_redaction=False handlers=[('StreamHandler', 'DefaultFormatter', False)]
  uvicorn.access           propagate=False logger_redaction=False handlers=[('StreamHandler', 'AccessFormatter', False)]
  uvicorn.error            propagate=True  logger_redaction=True  handlers=[]
  ...
total loggers=17  loggers with own handlers lacking redaction coverage=2 -> ['uvicorn', 'uvicorn.access']
```

`uvicorn` and `uvicorn.access` carry **no `RedactionFilter` on the logger and none on their
handler**, and `propagate=False` means their records never reach root's filtered handler. Coverage
is 15/17, not 100%.

### Demonstrated PII leak

With the PAN explicitly marked sensitive via `redact_values(PAN)`, I issued
`GET /health?pan=ABCDE1234F`. Observed on stderr, verbatim:

```
INFO:     127.0.0.1:55076 - "GET /health?pan=ABCDE1234F HTTP/1.1" 200 OK
{"timestamp": "...", "level": "INFO", "logger": "httpx", "message": "HTTP Request: GET http://127.0.0.1:8023/health?pan=[REDACTED] ...", "request_id": ""}
```

The `httpx` logger — which propagates to root — correctly rendered `pan=[REDACTED]`. The
`uvicorn.access` logger wrote the PAN **verbatim to the log sink**. Redaction is bypassed on
precisely the two loggers that record request URLs and query strings.

### Why the unit test passes anyway — a test-validity defect

Startup order matters and the test harness uses the wrong one. Under `uv run uvicorn`, uvicorn
applies its own `LOGGING_CONFIG` via `dictConfig` around app import, which **replaces the handlers
and filters** on `uvicorn*` loggers that `_install_redaction_filter_everywhere()` had already
attached. I confirmed both orders:

- order used by `pytest` (no uvicorn `dictConfig` at all) → `uvicorn.access` redaction `True`,
  11/11 loggers covered, `missing: []` — **the test's view**
- order used by the real server → `uvicorn.access` redaction `False`, 2/17 uncovered — **production**

`backend/tests/unit/test_log_redaction.py` asserts against a logger tree that never exists in the
deployed process. The AC2 test is green and the AC2 invariant is false simultaneously.

### The obvious fix triggers a second, latent defect

`RedactionFilter.filter` sets `record.msg = message; record.args = ()`. uvicorn's `AccessFormatter`
unpacks `recordcopy.args` into five values. Installing the filter on `uvicorn.access` therefore
crashes formatting. Reproduced:

```
--- Logging error ---
  File ".../uvicorn/logging.py", line 99, in formatMessage
    ) = recordcopy.args  # type: ignore[misc]
ValueError: not enough values to unpack (expected 5, got 0)
Message: '127.0.0.1:1234 - "GET /x?pan=[REDACTED] HTTP/1.1" 200'
Arguments: ()
```

The access line was **silently dropped** (empty output) and replaced by a logging-error traceback
on stderr. So the two states are: filter absent → PII leak (today); filter present → access log
destroyed. Both are broken, and a naive remediation of the leak lands on the crash. The fix must
make `RedactionFilter` preserve `record.args` (redact each arg in place) rather than clear it.

Impact today is bounded — only `/health` exists and it takes no parameters — but E15-S1 *is* the
story that owns this substrate, and every later story inherits it. This is a BLOCK.

---

## 8. E15-S1-AC1, AC5 — PASS (with caveat on AC1)

**AC1** — marked values redacted through the root/JSON path. Emitted line:

```
{"timestamp": "2026-09-14T06:43:21.976705+00:00", "level": "INFO", "logger": "truelend.access", "message": "applicant pan=[REDACTED] aadhaar=[REDACTED] doc=[REDACTED]", "request_id": "req-abc"}
```
occurrences in captured buffer — PAN `0`, Aadhaar `0`, salary-document `0`. Line parses as JSON.
**PASS** for the criterion as written.

Caveats recorded, deliberately not escalated to a FAIL on AC1:
- AC1 says "*when the request is served*". No endpoint accepts a payload in group A (`/health`
  only, and the story's `scope_out` forbids adding one), so the end-to-end form is unverifiable
  here. I verified the substrate directly instead, and say so rather than implying otherwise.
- Redaction is **opt-in**: values are only scrubbed inside a `redact_values(...)` scope. Outside
  it, PII is logged verbatim — confirmed: `"message": "applicant pan=ABCDE1234F
  aadhaar=123456789012 doc=payslip-Sept-2026-net-84500.pdf"`, PAN occurrences `1`. The module
  docstring discloses this as a deliberate design choice, so it is not a defect against AC1 — but
  it moves the whole burden onto every future story remembering to call `redact_values`. Flagging
  for E4/E5 (application intake), where the PAN/Aadhaar payloads actually arrive.
- The leak in §7 is via URL/query on `uvicorn.access`, which does not log request bodies — so a
  *payload*-borne PAN does not leak by that path. This is why §7 is charged to AC2, not AC1.

**AC5** — covered by QA-VM-005, §6. **PASS.**

---

## 9. E9-S1 — PASS (3/3)

Verified independently, not by re-reading the story's own tests.

**AC1 (F009)** — my own generator, seed `999777` (the story's test uses `20240913`), 2,000
principal/rate/tenure triples → 8,000 money fields through `multiply` / `subtract` / `add`
chains:

```
triples=2000 money_fields=8000 non-2dp-or-non-Decimal: 0 []
amount type is Decimal, never float: Decimal 1.01
float rejected on construct: yes
float rejected on multiply: yes
```
Every field is a `Decimal` with `as_tuple().exponent == -2`. **PASS.**

Caveat: AC1 says "*when a schedule is computed*". No schedule generator exists in group A (it lands
in E9-S2/E4). I verified the invariant on the `Money` type that every future schedule field will
hold — the strongest statement available in this group. The AC text was written against a
downstream artifact; noting the wording/scope mismatch as a MINOR finding, not a failure.

**AC2 (F010)** — I ran my own AST scan, **broader than the shipped check**: `float(...)` calls,
float literals, *and* true-division `/` (which the shipped check omits and which is the usual way a
float sneaks into Python money code).

```
src/types/money.py:        []
src/api/serializers.py:    []
```
0 hits on all three categories. **PASS** — and the result holds under the stricter scan, so the
shipped check's narrowness does not mask anything today. Recording the gap as MINOR: the shipped
`_count_float_usages` would not catch `a / b`, so it will weaken as money paths grow.

**AC3 (F011)** — `frontend/src/types/money.ts` holds `private readonly amount: Decimal`
(`decimal.js`); arithmetic is `plus` / `minus` / `times` / `toDecimalPlaces`; `format()` is pure
string manipulation (`toFixed(2)`, `split`, regex). The static check **does exist** —
`money.test.ts:70-88`, asserting against `parseFloat`, `parseInt`, `Number(`, `: number`,
`as number` — and passes. I independently confirmed zero matches in `money.ts` *and* in
`MoneyText.tsx` (which the shipped check does not cover). `npm run typecheck` clean, no `any` in
`frontend/src`. **PASS.** MINOR: the check is a regex scan over one file, not an AST scan over the
money paths.

**D-G spot check** — `backend/src/api/serializers.py` is the single money wire serializer;
`_serialize_money` returns `str(value.amount)` with `return_schema=core_schema.str_schema()`, so a
money amount renders as a quoted 2dp string and never a JSON number. Consistent with D-G/D-J.

---

## 10. E11-S1 — PASS (4/4)

**AC1 (F070)** — `classify_by_days_past_due(35)` → `DPD-30`. **PASS.**

**AC2 (F071)** — exhaustive, not sampled: all 401 values 0..400 against an independently written
expected-bucket function.
```
values=401 mismatches: 0 []
distinct buckets returned: ['CURRENT', 'DPD-30', 'DPD-60', 'DPD-90', 'NPA']
boundary spot-checks: [(0,'CURRENT'),(29,'CURRENT'),(30,'DPD-30'),(59,'DPD-30'),(60,'DPD-60'),
                       (89,'DPD-60'),(90,'DPD-90'),(179,'DPD-90'),(180,'NPA'),(400,'NPA')]
negative dpd raises: yes (days_past_due must be zero or positive, got -1)
```
Exactly one of five buckets for every value, every floor exact, no gap, no overlap. **PASS.**

**AC3 (F072)** — `classify(due, as_of)` with nothing past due: due today → `CURRENT`, due in 1 day
→ `CURRENT`, due in 10 days → `CURRENT`. **PASS.**

**AC4 (F073)** — result is `DelinquencyBucket.NPA`, a `StrEnum` whose only members are the five
bucket names. Attribute scan for `fee` / `penal` / `charge` / `interest` / `amount`: `[]`. Carries a
bucket and nothing else. **PASS.**

---

## 11. Additional findings (not AC failures)

**MAJOR — untrusted `X-Request-ID` reflected without limit.** `middleware.py:32` takes the caller's
header verbatim. Observed: a 4,000-character id echoed in full (response header 4,015 bytes) and
written to the log; a tab control character echoed as-is (`x-request-id: a<TAB>b`). No length cap,
no charset allow-list. Log-bloat / header-bloat amplification vector. Owned by the
`security-reviewer`; no group A AC covers it.

**Positive finding — JSON log-injection is not possible.** I tested whether a hostile id can break
out of the JSON line. It cannot — `json.dumps` escapes correctly:
```
PARSES OK  request_id="x\",\"injected\":\"yes"
PARSES OK  request_id="a\tb"
PARSES OK  request_id="AAAA...(len 4000)
```
No field injection, no line splitting. The `abc%0d%0aX-Injected: yes` value seen in the shared log
(another instance's probe) is literal percent-encoded text, not a CRLF. Worth recording as
verified-safe so the header-length finding is not over-read.

**MINOR — loggers registered after startup get no redaction filter.**
`_install_redaction_filter_everywhere()` walks loggers existing at configure time only. Confirmed:
`logging.getLogger("truelend.laterstory")` → `has RedactionFilter: False`. Independent of §7 and
will bite any story that creates its logger lazily.

**Note — `typing.Any` in `serializers.py:43`.** `_source_type: Any` is required by Pydantic v2's
`__get_pydantic_core_schema__` hook signature; `mypy` and `ruff` both pass. Not a violation of the
zero-`any` rule (which targets TypeScript). No action.

---

## 12. Scope conflicts — reported, not acted on

I did not modify `sprint-contracts/**`, `project-manifest.json`, or anything under
`specs/design/`. Conflicts I am obliged to report rather than fix:

1. **`project-manifest.json` is modified in the working tree** (`verification.mode` docker→local
   plus a `mode_note` key) while this pack lists it as frozen and it sits outside the task
   envelope's `allowed_paths`. I independently confirmed the pack's "duplicate `mode` key" worry is
   **unfounded** — the file parses and `verification.mode` appears exactly once inside
   `verification`. The change is defensible on the merits; it lacks an envelope amendment.
2. **`.claude/state/task-envelope.json` was rotated, not amended** — `previous_envelope_hash` is
   still `null` and `amendments` still `[]` despite two files under `task-envelope-history/`. The
   chain is unauditable. Outside my remit; flagged for `/gate`.
3. **`plan-seal.js check` exits 1** — sealed artifacts changed (`specs/design/reasons-canvas.md`,
   `specs/bundles/E{9,11,15}-S1.json`). `contract-freeze.js --check` passes, so the sprint contract
   I evaluated against is intact. I treated `sprint-contracts/A.json` as read-only throughout.
4. **`regression-suite-full` BLOCK is a misapplied check, confirmed independently.** `features.json`
   has **zero** stories with `passes: true` in any group (I verified: `any passes=true anywhere: 0`),
   so group A is the first landed group and the prior-contract regression set is empty. Its
   findings are 404s on groups B..M endpoints that do not exist. Not a product regression.
5. **`ownership-check`** — `backend/src/__init__.py` unowned in `specs/design/component-map.md`.
   The fix is a `specs/design/` edit, which is frozen to me. Reported.
6. I created `.claude/state/evaluator1-uvicorn.log` (inside `allowed_paths`) for the isolation
   instance, and shut that instance down after the run. The official server on 8000 was **not**
   restarted — it was up throughout.

---

## 13. Gate inputs

- `evidence-integrity`: contract A declares `api_checks` only and **no `playwright_checks`**, so
  `classifyEvidence` returns `applicable: false` / `pass: true`. I still wrote an entry for all
  three contracted checks in `specs/reviews/evaluator-evidence.json`, honestly labelled
  `layer: "api"`. I did **not** label them `playwright`: no browser was driven, and a `playwright`
  entry with no interaction would be a false claim (and would correctly trip `no-interaction-pass`).
- Browser layer: not contracted for group A (no `playwright_checks`, no `design_checks`, no
  `accessibility_checks`). Not executed, nothing claimed.
- SLO sensor: `observability.enabled` — no 5xx observed in any probe; p95 ≈ 26 ms against
  `p95_ms: 500`. No SLO failure.

## 14. Required to clear

1. `backend/src/config/logging.py` — bring `uvicorn` / `uvicorn.access` / `uvicorn.error` under
   `JSONLogFormatter` **and** the `RedactionFilter`, in a way that survives uvicorn's own
   `dictConfig` (pass a `log_config` to uvicorn, or re-assert after startup).
2. `backend/src/config/logging.py` — make `RedactionFilter` redact `record.args` element-wise
   instead of clearing it, or the fix to (1) destroys the access log (§7).
3. `backend/src/api/middleware.py` — keep the correlation id readable for the duration of
   uvicorn's access logging, so the line can carry `request_id == req-abc` (§3b).
4. `backend/tests/unit/test_log_redaction.py` — assert AC2 against the real uvicorn startup order,
   otherwise the test stays green while the invariant is false.
5. Re-run `/evaluate` for group A. E9-S1 and E11-S1 need no rework.

**Failure JSON:** `specs/reviews/eval-failures-001.json`

---

## 15. Security gate — folded in (FAIL)

`specs/reviews/security-verdict.json` reports **`pass: false`** — 1 BLOCK, 7 warn, 6 info. Per the
evaluator's security gate this makes the overall verdict FAIL independently of the functional
results. My verdict was already FAIL; this is a second, independent reason.

| id | sev | file | summary |
|---|---|---|---|
| VULN-001 | high (BLOCK) | `backend/src/api/middleware.py:32` | Caller-supplied `X-Request-ID` accepted with no length cap, echoed verbatim into the response header and into every structured log line. An 8 MB header value returns 200 with full echo; 20 × 1 MB requests to the unauthenticated, unrate-limited `GET /health` wrote 20.98 MB to the log in 1.28 s (~15.6 MB/s, ~1.3 GB/min from one client). Remote unauthenticated disk and bandwidth exhaustion. CWE-770. matrix_ids VM-003, VM-004. |

**Independently corroborated.** I flagged the same reflection as a MAJOR additional finding in §11
from my own probes (4,000-char id echoed in full, 4,015-byte response header, tab control character
echoed). The security reviewer proved a materially stronger impact than my probe reached and owns
the finding; I am not restating its remediation.

It also retro-explains §1: the abnormal size and NUL padding of `.claude/state/uvicorn.log` is
consistent with those megabyte-scale probes landing in the shared log while I was measuring. That
concurrency is exactly why I measured log windows against an isolated instance rather than trusting
the shared file — the two findings reinforce each other.

**Revised overall:** FAIL · `failure_layer: ["api", "security"]`.
