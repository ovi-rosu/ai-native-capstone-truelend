# Evaluator Report — `/gate --group A` (round 2), instance 1 of 3

| Field | Value |
|---|---|
| Instance | 1 of 3 (worked alone; no contact with instances 2/3) |
| Mode | runtime, `verification.mode: local` (Docker not installed; no `docker compose` attempted) |
| Port owned | 8000 |
| HEAD evaluated | `9112495` |
| Branch | `feat/harness-scaffold-and-planning` |
| Contract | `sprint-contracts/A.json` (read-only; not modified) |
| Stories | E15-S1, E9-S1, E11-S1 |
| Served | `src.api.app:app` (i.e. `create_app()` — correlation middleware present). `build_fastapi_app()` never served. |
| Timestamp | 2026-09-14T11:52:00Z |

## VERDICT: **FAIL**

**Failure layer: `security`.**

Every frozen contract check and every story acceptance criterion in scope
**passes**, proven by live interaction. The evaluation nevertheless fails the
security gate on one **HIGH** finding, newly discovered at HEAD, in group A's
own new code (`/metrics` + `CorrelationIdMiddleware`): an unauthenticated
attacker can inject arbitrary, well-formed Prometheus series through the
request path. Per the evaluator rule *"a green functional pass with an open
critical/high vulnerability is still a FAIL."*

All five prior BLOCK findings (CR-001, CR-002, CR-003, SEC-001, SEC-002) are
**independently confirmed fixed**. SEC-003 is **partially** fixed.

---

## 1. Frozen contract checks — 3/3 PASS

App reachability was established with the manifest health-check retry loop
before any check ran (`http://127.0.0.1:8000/health` → 200 on attempt 1).

Method for the log assertions: the server's stdout+stderr were captured to a
file; the line count was read immediately **before** each request and again
**after**, so the newly appended lines are exactly the lines emitted while
serving that request. That difference is the reported denominator. Parsing and
`request_id` comparison were done programmatically by
`.claude/state/eval-i1/logcheck.js`, not by eye.

### QA-VM-003 — PASS (matrix VM-003, E15-S1-AC3)

```
curl -s -D - -o body -H "X-Request-ID: req-abc" http://127.0.0.1:8000/health
```

| Assertion | Observed | Result |
|---|---|---|
| status 200 | `HTTP/1.1 200 OK` | pass |
| JSON body | `{"status":"ok","database":"unconfigured","version":"0.1.0"}` | pass |
| response echoes id | `x-request-id: req-abc` | pass |
| **denominator** (lines emitted while serving) | **1** (non-vacuous; not 0) | pass |
| 100% parse as JSON | 1/1 = 100.0%, 0 non-JSON | pass |
| each carries `request_id == "req-abc"` | 1/1; distinct ids observed: `{req-abc: 1}`; 0 lines not carrying it | pass |

Raw evidence (`.claude/state/eval-i1/f003.lines`):

```
{"timestamp": "2026-09-14T11:48:36.972470+00:00", "level": "INFO", "logger": "truelend.access", "message": "GET /health -> 200", "request_id": "req-abc"}
```

**Denominator hardening.** One line is a thin denominator, so the check was
repeated with 5 sequential requests carrying the same id on the first server
run: denominator **5**, 5/5 parsed as JSON, 5/5 `request_id == req-abc`, all 5
responses echoed `req-abc`
(`.claude/state/eval-i1/vm003.lines`). Additionally, across **all three**
server runs in this evaluation — 107 non-empty log lines total, including
startup lines, 404/405/409/422 errors, three unhandled 500s with full
tracebacks, and deliberate log-injection payloads — **107/107 (100.0%) parsed
as JSON and 0 lines lacked a `request_id` key.** No plain-text uvicorn access
line appeared at any point.

### QA-VM-004 — PASS (matrix VM-004, E15-S1-AC4)

```
curl -s -D - -o body http://127.0.0.1:8000/health      # no X-Request-ID sent
```

| Assertion | Observed | Result |
|---|---|---|
| status 200 | `HTTP/1.1 200 OK` | pass |
| id generated and non-empty | `892eff5f34ef4b0ba399bd49897cce74` (32 hex) | pass |
| response header echoes it | `x-request-id: 892eff5f34ef4b0ba399bd49897cce74` | pass |
| denominator | **1** | pass |
| every request-scoped line shares that id | 1/1; distinct ids: `{892eff5f…: 1}` | pass |

Raw evidence (`.claude/state/eval-i1/f004.lines`):

```
{"timestamp": "2026-09-14T11:48:39.164207+00:00", "level": "INFO", "logger": "truelend.access", "message": "GET /health -> 200", "request_id": "892eff5f34ef4b0ba399bd49897cce74"}
```

**Multi-line hardening.** The one-line denominator was strengthened on the
unhandled-500 path, which emits 3 request-scoped lines. With no inbound id the
response carried `x-request-id: b1e5fc9c7c5f4b4cb1df30492f7f1a62` and **all 3**
log lines (`truelend.access` INFO, `truelend.access` ERROR with traceback, and
`uvicorn.error` ERROR with traceback) carried that same generated id. This is
the CR-003/AC4 case the middleware docstring claims to fix, and it holds.

An empty or valueless `X-Request-ID` header correctly falls through to a
generated id rather than an empty string (2 probes, both generated a fresh
32-hex id).

### QA-VM-005 — PASS (matrix VM-005, E15-S1-AC5)

30 timed samples against a freshly booted server
(`.claude/state/eval-i1/f005.timings`):

| Metric | Value | Budget | Result |
|---|---|---|---|
| non-200 responses | 0 / 30 | 0 | pass |
| JSON body | `{"status":"ok","database":"unconfigured","version":"0.1.0"}` | JSON | pass |
| mean wall-clock | 0.0019 s | — | — |
| sample p95 | 0.0016 s | < 1 s | pass |
| max wall-clock | 0.0206 s | < 1 s | pass |

Margin to the 1 s criterion is ~48x on the worst sample.

---

## 2. Story acceptance criteria — 12/12 PASS

### E15-S1

| AC | Feature | Verdict | How proven |
|---|---|---|---|
| AC1 | F001 | pass (with caveat, see MED-1) | **Live.** `/eval/pii-boom` registers a synthetic PAN, Aadhaar and salary-doc string then raises an exception carrying all three. Window of 3 log lines: **0** occurrences of `ABCDE1234F`, **0** of `1234 5678 9012`, **0** of `payslip-secret-content`, **6** `[REDACTED]` markers. Repeated on a **sync (threadpool) handler** — the contextvar-copy path — same result: 0/0/0, 6 markers. |
| AC2 | F002 | pass | **Live + unit.** Live: the `uvicorn.error` traceback line — emitted by uvicorn's own logger *after* the middleware re-raised — came out scrubbed and correlated, proving the filter reaches loggers outside the app's own. Unit: `test_redaction_filter_installed_on_every_configured_logger`, `test_redaction_filter_covers_every_logger_under_the_real_server_config`, `test_pii_redaction_control_is_not_vacuous` — all pass. |
| AC3 | F003 | pass | **Live.** QA-VM-003 above; plus 107/107 log lines JSON across all runs. |
| AC4 | F004 | pass | **Live.** QA-VM-004 above; plus the 3-line unhandled-500 window sharing one generated id, and the 500 response carrying `X-Request-ID`. |
| AC5 | F005 | pass | **Live.** QA-VM-005 above. |

### E9-S1

| AC | Feature | Verdict | How proven |
|---|---|---|---|
| AC1 | F009 | pass | `test_random_principal_rate_tenure_triples_always_quantize_to_two_places` plus add/subtract/multiply quantization tests. 39 passed in `tests/architecture/test_no_float_money.py`. |
| AC2 | F010 | pass | **Mutation-proven non-vacuous** (see below). |
| AC3 | F011 | pass | `cd frontend && npm test` → 18/18 passed (`tests/unit/money.test.ts`); `npm run lint` clean; `npm run typecheck` clean. |

**Mutation test for AC2 — the static guard is not vacuous.** I appended a real
float operation to the *production* module and re-ran the guard:

```python
# appended to backend/src/types/money.py
def _evaluator_mutation_probe(x: object) -> object:
    return float(x) * 1.5
```

Result: `2 failed, 37 passed` —
`test_money_type_has_zero_float_operations` and
`test_float_guard_still_reports_zero_for_the_real_money_modules` both fired.
Restored with `git checkout -- backend/src/types/money.py`; `git status
--porcelain` confirms the file is clean and no tracked product file was left
modified by this evaluation. So the AC2 "reports 0 float arithmetic
operations" result is a real measurement over
`src/types/money.py` and `src/api/serializers.py`, not a guard that scans
nothing.

### E11-S1

| AC | Feature | Verdict | How proven |
|---|---|---|---|
| AC1 | F070 | pass | 35-DPD case → `DPD-30`. 18/18 passed in `tests/unit/test_bucket_ladder.py`. |
| AC2 | F071 | pass | Verified the sweep is genuinely exhaustive, not sampled: `test_bucket_ladder.py:41` is `for days_past_due in range(0, 401)`. Boundary params at 30/59/60/89/90/179/180 all pass; `test_exactly_five_buckets_exist` pins the ladder at five. |
| AC3 | F072 | pass | `test_no_installment_overdue_is_current_when_due_date_is_as_of_date`, `…_in_the_future`, `test_zero_days_past_due_is_current`. |
| AC4 | F073 | pass | `test_result_carries_bucket_only_no_fee_or_charge_attribute`. |

E9-S1 and E11-S1 are Types-layer stories exposing no HTTP surface, so the
deterministic layer is the only evidence available for them. Recorded as
`unit`, not as live interaction — see the evidence ledger.

---

## 3. Prior BLOCK findings — re-verified independently

Commit messages were not accepted as evidence; each was re-tested at HEAD.

### CR-001 — **FIXED** (proven live, all statuses)

The frozen envelope `{error, detail, context}` is returned for framework
errors, not only `AppError`. A throwaway harness registered raising routes
against the *inner* app and wrapped it with the published `create_app()`, so
the middleware under test is the production one.

| Probe | Status | Body | `X-Request-ID` |
|---|---|---|---|
| `GET /eval/401` | 401 | `{"error":"Unauthorized","detail":"no or invalid token","context":{}}` | `rid-401` |
| `GET /eval/403` | 403 | `{"error":"Forbidden","detail":"wrong role","context":{}}` | `rid-403` |
| `GET /eval/409` | 409 | `{"error":"Conflict","detail":"illegal transition","context":{}}` | `rid-409` |
| `GET /eval/does-not-exist` | 404 | `{"error":"NotFound","detail":"Not Found","context":{}}` | `rid-404` |
| `GET /nonexistent` (real app, no harness) | 404 | `{"error":"NotFound","detail":"Not Found","context":{}}` | `rid-404` |
| `POST /health` (real app) | 405 | `{"error":"HTTPError","detail":"Method Not Allowed","context":{}}` | `rid-405` |
| `POST /eval/422` bad type | 422 | `{"error":"ValidationError","detail":"request validation failed","context":{"field":"body.amount"}}` | `rid-422` |
| `GET /eval/apperror` | 400 | `{"error":"AppError","detail":"typed failure","context":{"threshold_kind":"dti","configured_value":42}}` | `rid-app` |
| `GET /eval/boom` (unhandled `ValueError`) | 500 | `{"error":"InternalServerError","detail":"internal server error","context":{}}` | `rid-500` |

All nine carry the three envelope keys and nothing else. The 422 reports
`field` only and never echoes the rejected value. The 500 leaks neither the
`ValueError` message, nor the `SELECT * FROM loans` string, nor the filesystem
paths that were in it.

### CR-002 / SEC-002 — **FIXED** (proven live, both async and sync paths)

PII registered inside a handler, then carried out on an escaping exception, is
scrubbed **and** correlated. See E15-S1-AC1 above: 0 occurrences of all three
synthetic values across the 3-line window, on both the async handler and the
sync/threadpool handler, and on the `uvicorn.error` line emitted after
re-raise. `request_id` on those lines was `rid-pii-async` / `rid-pii-sync` —
never the empty string the prior finding reported.

### CR-003 — **FIXED**

`tests/architecture/test_no_float_money.py` carries
`test_division_exemption_does_not_silence_other_float_categories` with three
parameters (`float-call-on-marked-line`, `float-literal-on-marked-line`,
`math-import-on-marked-line`), all passing — i.e. the per-line exemption is
now scoped to division only. Plus the mutation test above proves the guard
still fires on the real module.

### SEC-001 — **CONFIRMED FIXED** (accepted from the pack's measurement; no new shape found)

The pack's direct timing of `_scrub` at HEAD is flat/linear (0.025–0.044 ms
across value lengths 13→61, against 199,326 ms at length 41 pre-fix). I did
not re-derive it and did not find a different backtracking shape. The unit
suite's `test_redaction_pattern_is_not_exponential_on_separator_bearing_values`
covers three shapes and passes. Note the documented behaviour narrowing: a gap
of 5+ separators between characters no longer matches (`[ \t\-]{0,4}`).

### SEC-003 — **PARTIALLY FIXED** (see MED-2)

`GET /eval/pii-context` returned:

```json
{"error":"AppError","detail":"rejected for pan [REDACTED]",
 "context":{"pan":"[REDACTED]","aadhaar":"[REDACTED]","doc":"[REDACTED]",
            "abs_path":"C:/Users/rosuo/WORK/ai-native-capstone-truelend/backend/src"}}
```

Closed: registered PII is redacted in both `detail` and `context`; the
credential DSN (`postgresql://admin:…@db.internal:5432/truelend`) was dropped;
the nested mapping `{"internal":"state"}` was dropped. Still open: the
**absolute filesystem path egressed to the client**. `sanitise_context` filters
only credential URIs and strings over 200 chars, so absolute paths and raw SQL
under 200 chars still cross the boundary — two of the four leak classes the
`errors.py` docstring claims to have closed.

---

## 4. Findings

### HIGH-1 — Unauthenticated Prometheus metric forgery via the request path (`/metrics`) — **BLOCK**

**Axis:** security. **New at HEAD.** Not in the prior BLOCK list.

`CorrelationIdMiddleware._stamping_send` keys the RED counter on the **raw**
`scope["path"]` rather than the matched route template, and
`platform/routes.py::get_metrics` interpolates that value into a Prometheus
label with **no escaping**:

```python
f'http_requests_total{{method="{method}",route="{route}",status="{status}"}} {count}'
```

`scope["path"]` is URL-decoded, so `%0A`, `%22` and `%23` in the request path
become real newlines, quote characters and comment markers inside the
exposition.

**Proof — a single unauthenticated GET against a freshly booted server.**
Sensor reading before the attack:

```
{"verdict":"pass","error_rate_pct":0,...,"breaches":[]}
```

Attack (one request, returns an innocuous 404):

```
curl 'http://127.0.0.1:8000/x%22%2Cstatus%3D%22200%22%7D%201%0Ahttp_requests_total%7Bmethod%3D%22GET%22%2Croute%3D%22%2Fhealth%22%2Cstatus%3D%22500%22%7D%2099999%0A%23'
→ status=404
```

Resulting `/metrics` (`.claude/state/eval-i1/metrics-forged.txt`):

```
# HELP http_requests_total Total HTTP requests served.
# TYPE http_requests_total counter
http_requests_total{method="GET",route="/health",status="200"} 1
http_requests_total{method="GET",route="/metrics",status="200"} 1
http_requests_total{method="GET",route="/x",status="200"} 1
http_requests_total{method="GET",route="/health",status="500"} 99999
#",status="404"} 1
```

Line 4 is a **fully fabricated series** the server never recorded. The trailing
fragment is swallowed by the injected `#` comment marker, so the exposition is
**well-formed** — my exposition checker reports `non-comment data lines: 4,
malformed lines: 0`. A real Prometheus scraper ingests it without complaint.

Sensor reading after that one request:

```
{"verdict":"fail","error_rate_pct":99.995000199992,...,"breaches":["error_rate"],"exit":1}
```

**Impact.** An unauthenticated remote party can write arbitrary values into the
platform's metrics, and therefore into dashboards, alerting, and this
project's own runtime-SLO gate (`observability.slo.error_rate_pct: 1`). Both
directions matter: fabricate a 99.995% error rate to trigger false SLO
breaches and drown on-call, or inflate the `status="200"` counter to **mask a
real** error-rate breach. State is a module-level `Counter`, so the poison
persists until the process restarts.

A cruder variant also **breaks** the exposition outright: three GETs with `"`,
`\` and a bare `%0A` in the path produced 3 malformed lines out of 12
(`.claude/state/eval-i1/metrics-poisoned.txt`), which makes a real Prometheus
scrape fail wholesale — denial of observability.

**Secondary defect, same root cause: unbounded label cardinality.** Because
`route` is the raw path, every distinct 404 path mints a new time series. Three
requests to `/random-aaa|bbb|ccc` produced three new series; the counter grew
from 4 to 7 entries. The `Counter` is unbounded and never evicted, so an
attacker can drive it to memory exhaustion and simultaneously destroy the
Prometheus TSDB's cardinality budget.

**Files:** `backend/src/api/middleware.py:78-86`
(`_stamping_send`, the `_request_counts[method, path, status]` key and the
`scope.get("path")` argument), `backend/src/api/platform/routes.py:82-91`
(`get_metrics` label interpolation).

Direction of fix (not implemented — evaluator does not generate code): key the
counter on the **matched route template** with a single fixed bucket for
unmatched paths, and escape label values per the Prometheus exposition spec.
Both changes are needed; escaping alone leaves the cardinality bomb, and
route-templating alone leaves any future label value unescaped.

### MED-1 — Attacker-controlled `X-Request-ID` and the raw path are written to the log sink verbatim

**Axis:** security / PII. E15-S1 scope says "must not write applicant PAN,
Aadhaar or salary-document content to **any log sink**."

Redaction is by design **registration-based** (`register_sensitive`) — it
scrubs only values a handler has explicitly marked. Nothing sanitises the two
inbound channels this story itself reads:

- `X-Request-ID` is taken verbatim, bound to `request_id`, written to **every**
  log line for the request, and reflected in the response header.
- the raw request path is embedded in the access-log `message`.

Proof: a request with `X-Request-ID: ABCDE1234F` (canonical Indian PAN format)
and a request to `/nonexistent-ABCDE1234F` put **2 occurrences** of that
PAN-shaped value into the log file, unredacted.

Strictly, E15-S1-AC1's *Given* is "an application **payload**", so the AC as
written is satisfied and F001 is recorded as passing. But the story's business
value — "keeps synthetic PAN, Aadhaar and salary content out of operational
logs" — is not met for the header and path channels, and no AC covers them.
Flagging as an **AC-coverage gap** rather than an AC failure, because
correcting it is a spec decision, not just a code one.

Also unbounded: a 4,000-character `X-Request-ID` was accepted, reflected in the
response header, and written into the log line, producing a **4,147-byte**
single log record from a request whose own response body is 59 bytes — roughly
70x log amplification per request, with no length cap.

Log **integrity** does hold: `X-Request-ID: a", "level": "CRITICAL", "message": "FORGED`
was correctly escaped by `json.dumps` into one well-formed JSON line with no
forged fields. So the JSON formatter is not injectable — only the metrics
formatter is (HIGH-1).

**Files:** `backend/src/api/middleware.py:89-91` (`inbound or uuid4().hex`),
`backend/src/api/middleware.py:84` (access-log message).

### MED-2 — `sanitise_context` still egresses absolute paths (SEC-003 residual)

See section 3. `abs_path` crossed to the client in a 400 response body. Raw SQL
under 200 characters would cross too. Only the credential-URI pattern and the
200-char length cap are enforced, yet the `errors.py` docstring claims the
absolute-path and SQL classes are closed. Either the allow-list needs to be a
real allow-list of keys, or the docstring overstates the fix.

**File:** `backend/src/api/errors.py:75-88`.

### MED-3 — `/metrics` exposes no duration metric, so half the declared SLO is unmeasurable

`observability.slo` declares `p95_ms: 500`, but `/metrics` exposes only
`http_requests_total`. Every SLO sensor run in this evaluation reported
`"p95_ms": null`. The RED acronym is Rate, Errors, **Duration**; Duration is
absent, so the p95 half of the project's own SLO can never be evaluated from
the metrics surface. `routes.py` notes `/metrics` "is covered by no acceptance
criterion" — that is exactly why this gap survived.

### MED-4 — `frontend/package-lock.json` is gitignored (SEC-011 still open)

`git check-ignore -v` → `.gitignore:49:package-lock.json`. The lockfile exists
on disk but is deliberately excluded from version control, so installs are not
reproducible and no dependency set is pinned for review. `npm audit
--omit=dev` reports **0 vulnerabilities**, so SEC-010 (advisories) is clear —
but that result is not reproducible without a committed lockfile.

### LOW-1 — Unhandled-exception tracebacks log absolute paths and raw exception text

The 500 traceback log lines contain full filesystem paths and the raw
exception message (including the probe's `SELECT * FROM loans` string). This is
intentional per the `handle_unexpected` docstring and does not cross to the
client. Noting it only because these logs are structured for shipping off-host,
at which point the log sink inherits that exposure.

### INFO-1 — Evaluation-hygiene: untracked probe debris in `backend/` breaks `ruff check .`

`cd backend && uv run ruff check .` reports **92 errors**, contradicting the
context pack's "All checks passed". Every error is in an untracked
`backend/_probe_*.py` file (14 of them: `_probe_labelinj.py`,
`_probe_metrics.py`, `_probe_redact.py`, `_probe_mem.py`, …) with mtimes inside
the last 9 minutes and still being written during my run — i.e. a **concurrent
evaluator instance's** working-tree debris, not product code. `git ls-files
backend | grep _probe` returns only `tests/unit/test_health_probe.py`.

Scoped to tracked source, `uv run ruff check src/ tests/` → **All checks
passed!**. Not a product defect, but the gate's lint result is not trustworthy
until `backend/` is cleaned, and these files must not be committed.

---

## 5. Deterministic layer (re-run independently at HEAD)

| Check | Command | Result |
|---|---|---|
| Backend tests | `cd backend && uv run pytest -q` | **88 passed**, 2 warnings, 0.15 s |
| Float-money guard | `uv run pytest tests/architecture/test_no_float_money.py -q` | 39 passed |
| Bucket ladder | `uv run pytest tests/unit/test_bucket_ladder.py -q` | 18 passed |
| E15-S1 units | `uv run pytest tests/unit/test_{log_redaction,correlation_id,error_envelope,health_probe}.py -q` | 31 passed |
| Backend lint (tracked) | `uv run ruff check src/ tests/` | All checks passed |
| Backend lint (whole dir) | `uv run ruff check .` | 92 errors — **all in another instance's untracked `_probe_*.py`**, see INFO-1 |
| Backend types | `uv run mypy src/` | Success: no issues in 12 source files |
| Frontend tests | `cd frontend && npm test` | **18 passed** (1 file) |
| Frontend lint | `npm run lint` | clean |
| Frontend types | `npm run typecheck` | clean |
| npm audit (prod) | `npm audit --omit=dev` | 0 vulnerabilities |

The pack's 88/18 counts reproduce exactly.

## 6. Operational endpoints

| Endpoint | Observed | Verdict |
|---|---|---|
| `GET /health` | 200, `{"status":"ok","database":"unconfigured","version":"0.1.0"}` — all three contract keys present | pass |
| `GET /metrics` | 200, `content-type: text/plain; charset=utf-8`, valid Prometheus exposition on a clean server (0 malformed lines), RED labels `method`/`route`/`status` all present | pass on shape; **see HIGH-1 and MED-3** |

`database: "unconfigured"` is the documented port default — group A owns no
database. Worth restating for group B: `/health` returns
`status: "ok"` while the database is unconfigured, so E15-S2-AC1's "all three
report healthy" will be vacuous until E1-S1 registers a real probe.

## 7. Performance ratchet — WARN (no regression)

| Item | Value |
|---|---|
| Baseline | **none** — `specs/brownfield/perf-baseline.json` does not exist |
| `perf-baseline.js --compare` | `no baseline … capture one first` |
| `perf-baseline.js --measure` | `/health p50=0.68ms p95=1.26ms p99=1.68ms (30 samples)` |
| Absolute budget | `slo.p95_ms: 500` → 1.26 ms is 0.25% of budget |

First/greenfield build with no recorded baseline, so this is a **WARN, not a
FAIL**, per the ratchet rule. No regression is possible or reported. I did not
write a baseline: a concurrent evaluator instance was generating load on the
same machine throughout, so any figure recorded now would bake in contaminated
measurements. Baseline capture should be a separate, quiet run.

## 8. SLO sensor — pass on a clean server, but forgeable

| Run | Verdict | `error_rate_pct` | `p95_ms` |
|---|---|---|---|
| Clean, freshly booted | `pass` | 0 | `null` (MED-3) |
| After one crafted GET | `fail` | 99.995 | `null` |

Error-rate counts only 5xx, so the deliberate 404/405/409/422 negative tests
did not trip it — correct behaviour. The clean reading passes. The forged
reading is HIGH-1's proof, not a real breach.

## 9. Layers not applicable

- **Layer 2 (Playwright / browser):** `sprint-contracts/A.json` contains
  `api_checks` only — no `playwright_checks`, no `design_checks`. No browser
  interaction was contracted, so none was performed and none is reported as
  passed. The frontend for group A is two unmounted modules (`money.ts`,
  `MoneyText.tsx`) with no served page; `evaluation.ui_base_url`
  (`:3000`) has no server. Recorded `not_applicable`, not `pass`.
- **Accessibility:** the contract declares no `accessibility_checks`, so no
  axe-core audit was required or run.
- **Schema layer:** no response-shape contract entries beyond the three
  `api_checks`; `/health` and the error envelope shapes were asserted inline
  above.

## 10. Reproduction artifacts

| Artifact | Contents |
|---|---|
| `.claude/state/eval-i1-final.log` | production app log for the final clean contract run (37 lines, 100% JSON) |
| `.claude/state/eval-i1-uvicorn.log` | first production run: 5x VM-003, injection/bloat probes, metrics cardinality probes (46 lines, 100% JSON) |
| `.claude/state/eval-i1/harness.log` | error-path harness: 401/403/404/409/422/500, PII probes (24 lines, 100% JSON) |
| `.claude/state/eval-i1/harness.py` | throwaway raising routes; wraps the inner app with the published `create_app()`. **Evaluator-only, outside `backend/`, not product code.** |
| `.claude/state/eval-i1/logcheck.js` | JSON-parse + `request_id` assertion tool (produces the denominators quoted above) |
| `.claude/state/eval-i1/promcheck.js` | Prometheus exposition well-formedness checker |
| `.claude/state/eval-i1/f003.lines`, `f004.lines`, `f005.timings` | raw per-check evidence windows |
| `.claude/state/eval-i1/metrics-forged.txt` | the well-formed forged exposition (HIGH-1) |
| `.claude/state/eval-i1/metrics-poisoned.txt` | the malformed exposition (HIGH-1 secondary) |
| `specs/reviews/evaluator-evidence.json` | machine-readable ledger, one entry per check |

Server was killed at the end of the run (port 8000 confirmed closed).
`git status --porcelain backend/ frontend/` shows no tracked product file
modified by this evaluation; `backend/src/types/money.py` was restored after
the mutation test.

---

## Summary for the orchestrator

The remediation work is real and it holds. CR-001, CR-002, CR-003 and SEC-002
are fixed in substance, not just in the commit message, and I verified them by
interaction rather than by reading the diff. The three frozen contract checks
pass with non-vacuous denominators, and all twelve group-A acceptance criteria
are met — the float-money guard is provably non-vacuous and the bucket sweep is
provably exhaustive.

The gate still fails, on one HIGH finding that the prior review did not reach
because `/metrics` did not exist then: the endpoint added by this very
remediation commit lets any unauthenticated caller write arbitrary Prometheus
series through the request path, and I demonstrated it flipping this project's
own SLO sensor from `pass` to `fail` with a single request. That is squarely
inside group A's new attack surface, which the context pack itself flagged as a
risk trigger.

Recommend: **FAIL / return to generator for HIGH-1**, with MED-2 folded into
the same fix pass since both are outbound-channel sanitisation in group A's own
files. MED-1 and MED-3 need a spec decision (an AC for log-input sanitisation,
and an AC or an explicit waiver for `/metrics`) before group B builds on this
substrate.
