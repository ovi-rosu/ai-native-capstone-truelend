# Evaluator Report — group A, instance 2 of 3

**Lane:** `/gate --group A` (re-run, round 2) · **HEAD:** `9112495` · **Base:** `14e9487`
**Verification mode:** `local` (Docker not installed) · **Port owned:** 8001
**Boot:** `cd backend && uv run uvicorn src.api.app:app --port 8001`
**Date:** 2026-09-14 · **Instance:** 2 (worked alone; no contact with instances 1 or 3)

## VERDICT: PASS (functional) — with one blocking process item not in my gift to clear

All three frozen `api_checks` (QA-VM-003 / 004 / 005) pass live against a booted
app, on **non-vacuous denominators**. All acceptance criteria for E15-S1, E9-S1
and E11-S1 are satisfied. Both prior high-severity BLOCKs I could re-test
(SEC-001, SEC-002) are independently confirmed fixed against HEAD, as is CR-001
and CR-003.

I did **not** clear the security gate. `specs/reviews/security-verdict.json`
self-reports commit `f4abd41` — two commits behind HEAD — and reports
`pass: false`. It is a snapshot of a superseded tree (see F-2I). My PASS is a
**functional** verdict only; the overall `/gate` verdict still needs a security
verdict regenerated against `9112495`.

---

## 1. Frozen contract results (`sprint-contracts/A.json`, never edited)

| Check | Matrix | Status | Denominator | Result |
|---|---|---|---|---|
| QA-VM-003 | VM-003 | **PASS** | 1 line / 1 JSON / 1 correct id | 200; `X-Request-ID: req-abc` echoed; 1/1 log lines parsed as JSON, `request_id == "req-abc"` |
| QA-VM-004 | VM-004 | **PASS** | 1 line / 1 JSON / 1 correct id | 200; generated id `85daf79199cf475faee136cb7965f0d7`; log line and response header carry the **same** non-empty id |
| QA-VM-005 | VM-005 | **PASS** | 60 samples | 200; `content-type: application/json`; body `{status,database,version}` parses; max **1.89 ms**, p95 **1.57 ms** (budget 1 s) |

### QA-VM-003 — the denominator question, answered directly

The task asks me to report the exact denominator and to refuse a vacuous pass.
`GET /health` emits **exactly one** log line, so the literal denominator for
QA-VM-003 is **1**. One line is thin evidence on its own, so I did not accept it
on its own. I corroborated with three independent, larger denominators:

| Probe | Lines | JSON | Carried the right `request_id` |
|---|---|---|---|
| `GET /health`, `X-Request-ID: req-abc` | 1 | 1/1 | 1/1 (`req-abc`) |
| `GET /probe/chatty` — handler emits 2 extra lines | **3** | 3/3 | 3/3 (`req-abc`) |
| `GET /probe/boom` — unhandled 500 | **3** | 3/3 | 3/3 (`err-500`), incl. uvicorn's own `Exception in ASGI application` |
| 12 concurrent requests, distinct ids | **12** | 12/12 | 12/12, zero cross-contamination |
| Whole server lifetime | **180** | **180/180** | 176 request-scoped all non-empty; the only 4 empty-id lines are the pre-request `uvicorn.error` startup lines |

The correlation is **genuine**, not an artefact of a denominator of 1: when a
handler emits three lines, all three carry the id; when the request fails, the
server's *own* error line carries it too. The denominator for `/health` is 1
because `/health` genuinely causes one line, not because lines were hidden.

---

## 2. The `uvicorn.access` question — judged explicitly

The task asks whether disabling `uvicorn.access`
(`src/config/logging.py:224`, `_SILENCED_LOGGERS`) makes "100% of log lines are
JSON" easier to satisfy than E15-S1-AC3 intends — correlation, or silencing.

I ran the counterfactual rather than reasoning about it. A probe harness wrapping
the **real** production factory re-enabled `uvicorn.access` in two modes:

| Mode | Emitted line | Parses as JSON? | `request_id` |
|---|---|---|---|
| `silenced` (production) | *nothing* | n/a | n/a |
| `native` (uvicorn's own `AccessFormatter`) | `INFO:     127.0.0.1:53135 - "GET /health HTTP/1.1" 200` | **NO — plain text** | none |
| `routed` (propagated through the JSON root handler, the exact treatment `uvicorn.error` already gets) | `{"...","logger": "uvicorn.access", "message": "127.0.0.1:63273 - \"GET /health HTTP/1.1\" 200", "request_id": "req-abc"}` | **YES** | **`req-abc` — correct** |

**Findings from the counterfactual:**

1. The hazard is real. Left native, `uvicorn.access` emits a plain-text line that
   *would* break AC3's "100% parse as JSON". Something had to be done.
2. **Both stated reasons for disabling are factually false.**
   - Claim: *"`request_id_var` is already reset by the time it emits (it logs
     after the response completes, outside the middleware scope)."* False. The
     routed run printed `request_id: "req-abc"`. Confirmed in uvicorn's source:
     `.venv/Lib/site-packages/uvicorn/protocols/http/httptools_impl.py:484-492`
     emits `self.access_logger.info(...)` inside `RequestResponseCycle.send()`
     at `http.response.start` — i.e. synchronously inside the `await send(message)`
     that `CorrelationIdMiddleware._stamping_send` makes, while the contextvar is
     still bound.
   - Claim: *"its `AccessFormatter` reads `record.args`, which `RedactionFilter`
     clears, raising `ValueError` and dropping the line entirely."* Moot under the
     routed treatment (`AccessFormatter` is never invoked), and not reproducible
     even in `native` mode with redaction actively firing — the line printed fine,
     because `RedactionFilter` only clears `args` when the scrub *changes* the
     message, and an access record contains no PII.
3. **Routing would have satisfied AC3 *and* preserved the data.** `disabled = True`
   is broader than the problem: it permanently drops client address, HTTP version
   and the query string from the operational record, and suppresses any future
   `uvicorn.access` WARNING/ERROR.

**My judgement: honest compliance in substance, dishonest in its stated reason.**
It is not gaming the denominator — I proved the denominator non-trivially three
separate ways, and the middleware's replacement line genuinely covers every
request including 4xx and 5xx. But the justification in the code comment is
wrong, a strictly better option exists and was rejected on a false premise, and
the next maintainer reading that comment will be misled. Recorded as **F-2A
(MAJOR)** — a defect against maintainability and operational completeness, **not**
a failure of QA-VM-003/004 or of E15-S1-AC3/AC4, which pass on their own terms.

---

## 3. Story acceptance criteria

### E15-S1 — logging, correlation, redaction, health

| AC | Status | Live evidence |
|---|---|---|
| AC1 — 0 occurrences of PAN/Aadhaar/salary content in the captured buffer | **PASS** | `GET /probe/pii` → `"applicant pan=[REDACTED] aadhaar=[REDACTED] lower=[REDACTED]"`. Spaced and lowercase forms both caught. `GET /probe/piiboom` (PII inside an **escaping** exception) → `grep -c ABCDE1234F` = **0**, `grep -c 123456789012` = **0** across all 3 lines |
| AC2 — redaction filter on 100% of configured loggers | **PASS (with caveat F-2E)** | 9 loggers enumerated at `configure_logging` time, **0** without a `RedactionFilter` |
| AC3 — 100% JSON, `request_id == req-abc` | **PASS** | see §1; 180/180 JSON over the server's lifetime |
| AC4 — generated id shared by every request-scoped line and echoed | **PASS** | §1; `x-request-id: 85daf791...` matched the log line exactly |
| AC5 — 200, JSON body, < 1 s | **PASS** | 60 samples, max 1.89 ms |

### E9-S1 — Money value type

| AC | Status | Evidence |
|---|---|---|
| AC1 — every money field a Decimal quantized to exactly 2 dp | **PASS (by proxy, F-2G)** | 200 random principal/rate/tenure triples; every result has `as_tuple().exponent == -2`. No schedule exists in group A; the test file discloses the substitution |
| AC2 — static check reports 0 float ops in money paths | **PASS** | 39 tests in `tests/architecture/test_no_float_money.py`; guard reports 0 for `money.py` and `serializers.py`; catches true/floor division, `math` import/attr, `float()`, float literals, `** 0.5` |
| AC3 — frontend value held as decimal, never float | **PASS** | `npm test` 18/18; `npm run lint` clean; `npm run typecheck` clean |

### E11-S1 — delinquency bucket ladder

Verified by execution against an oracle I wrote myself, not by reading the tests.

| AC | Status | Evidence |
|---|---|---|
| AC1 — dpd 35 → DPD-30 | **PASS** | `classify_by_days_past_due(35)` → `DPD-30` |
| AC2 — 0..400, exactly one bucket, no gap/overlap | **PASS** | 401 values, **0 mismatches** vs an independent oracle; all 5 buckets observed; boundaries exact at 0/29/30/59/60/89/90/179/180/400; negative dpd rejected with `ValueError` |
| AC3 — nothing past due → CURRENT | **PASS** | due 2026-09-20 as-of 2026-09-14 → CURRENT; due == as-of → CURRENT |
| AC4 — bucket only, no fee/interest/charge | **PASS** | `StrEnum` with 5 members; 0 public attributes matching fee/interest/charge/penal/amount/money |

---

## 4. Prior BLOCK findings re-tested against HEAD

| ID | Claim | Re-test | Verdict |
|---|---|---|---|
| CR-001 | envelope applied only to `AppError`; framework 404/422 and unhandled 500 bypass it | live 404 → `{"error":"NotFound","detail":"Not Found","context":{}}`; 405 → `{"error":"HTTPError",...}`; 422 → `{"error":"ValidationError","detail":"request validation failed","context":{"field":"body.amount"}}`; unhandled 500 → `{"error":"InternalServerError","detail":"internal server error","context":{}}`. All four carried `x-request-id` | **FIXED** |
| CR-002 / SEC-002 | PII in an escaping exception logged unredacted with an empty `request_id` | `GET /probe/piiboom` with PAN+Aadhaar in the `RuntimeError` message → 3 log lines, **0** PAN occurrences, **0** Aadhaar occurrences, all 3 carrying `request_id: "pii-2"`, including uvicorn's own traceback line | **FIXED** |
| CR-003 | per-line money-guard exemption silenced every float category | `test_division_exemption_does_not_silence_other_float_categories` present with 3 cases; guard source exempts only `is_division`; 39/39 pass | **FIXED** |
| SEC-001 | catastrophic regex backtracking (ReDoS), 199,326 ms at length 40 | Re-attacked with **four shapes of my own construction**, not the recorded probe: (A) long no-separator value vs a 4-separator-packed near-miss haystack, lengths 10→60: 0.111→0.404 ms; (B) repeated-char value vs separator-dense haystack, 10→40: 0.084→0.287 ms; (C) repeated-prefix ×3 + 500-char tail: ≤0.213 ms; (D) 4998-char pure-separator haystack: ≤0.383 ms. Growth linear. Structural reason: the separator class and the literal characters are disjoint (a value *containing* a separator takes the `re.escape` literal branch), so the run length at each position is forced by the input — no ambiguity to backtrack through | **FIXED** |
| SEC-003 | `context` an unfiltered outbound channel | 422 returns only `{"field":"body.amount"}` — never the rejected value; 500 returns `context: {}`; `sanitise_context` drops non-scalars, credential URIs and >200-char values, and scrubs registered PII | **FIXED** |

Additionally verified not exploitable:
- **Log forging** via `X-Request-ID: x","level":"CRITICAL","message":"forged` — `json.dumps` escaped it correctly; the forged `CRITICAL` line did **not** appear (`forged CRITICAL line present: false`).
- **CRLF response splitting** via a raw socket with an embedded `\r\nX-Injected: yes` — blocked at the protocol layer; the app saw `X-Request-ID: a`.

---

## 5. Findings

| ID | Severity | Finding |
|---|---|---|
| F-2A | **MAJOR** | `uvicorn.access` is disabled (`src/config/logging.py:217-238`) on **two factually false premises**, when routing it through the JSON root handler — the treatment `uvicorn.error` already gets — demonstrably yields a valid JSON line carrying the correct `request_id`. `disabled = True` permanently drops client address, HTTP version and query string from the operational record and suppresses any future `uvicorn.access` WARNING/ERROR. See §2. Fix: move `"uvicorn.access"` from `_SILENCED_LOGGERS` to `_JSON_ROUTED_LOGGERS` and correct the comment. |
| F-2B | **MEDIUM** | `/metrics` labels the RED counter with the **raw request path**, not the matched route template (`middleware.py:75`, `scope.get("path")`), and `_request_counts` is a module-level `Counter` that never evicts. Measured: 150 unauthenticated requests to distinct nonexistent paths → **154 series**, a **10,302-byte** `/metrics` response. Unbounded attacker-driven memory growth and metric-cardinality explosion on an unauthenticated endpoint that the runtime-SLO sensor scrapes. Fix: label with the matched route (`scope["route"].path`) or bucket unmatched paths to a single `__unmatched__` label. |
| F-2C | **MEDIUM** | Inbound `X-Request-ID` is accepted with **no length or charset validation** (`middleware.py:86-87`). Measured: an 8,000-character value was reflected verbatim into the response header **and** written at full length into every log line for that request; `<script>alert(1)</script>` was reflected verbatim. Not injection — log forging and CRLF splitting both verified blocked — but unbounded attacker-controlled data written to the log sink E15-S1 exists to protect. Fix: accept the inbound id only if it matches an opaque-token shape (e.g. `^[A-Za-z0-9._-]{1,128}$`), else generate one. |
| F-2D | **MINOR** | `register_sensitive` **silently** ignores any value shorter than `_MIN_REDACTABLE_LENGTH` (6). Measured: `_scrub('secret=AB123 here', ['AB123'])` returns the string unchanged. A silent no-op in a PII control — a caller registering a short identifier gets no signal that it is unprotected. Fix: log a warning, or raise, when a registered value is below the threshold. |
| F-2E | **MINOR** | E15-S1-AC2's oracle is a snapshot that decays. Measured: **9/9** loggers carry a `RedactionFilter` at `configure_logging` time, but two loggers created **afterwards** (`truelend.service.underwriting`, `truelend.repository.loan` — the shape every later story will use) carry **0**. Redaction still holds because the root *handler* carries the filter (verified: `pan=[REDACTED]`), so AC1 is safe today. The forward risk: a later story adding `propagate = False` plus its own handler — exactly what uvicorn does — bypasses the only filter that is actually load-bearing. Fix: install the filter in a `logging.setLoggerClass` hook or assert the invariant at request time, not once at boot. |
| F-2F | **MINOR** | `_scrub` is O(registered values × text length) per log line. Measured: **200** registered values against a 4,000-char line costs **23.7 ms** of CPU for one line. No group-A caller registers anything, but the project SLO is `p95_ms: 500`, so a later story registering per-applicant values at volume has a real budget to watch. |
| F-2G | **MINOR** | E9-S1-AC1's literal subject — *"when a schedule is computed from each triple"* — does not exist in group A. It is verified by proxy on `Money` arithmetic over 200 random triples. The test file discloses this explicitly, and it parallels the contract retargeting recorded in the context pack §3, so it is a defensible narrowing — but AC1 is not closed as worded until the schedule generator lands. |
| F-2H | **INFO** | Working-tree pollution breaks a documented gate command. `backend/` contains 7 untracked `_probe_*.py` files (from a sibling instance or an earlier session), so `cd backend && uv run ruff check .` now returns **41 errors** and does not reproduce the context pack §5 claim "All checks passed". `uv run ruff check src/ tests/` is clean — no product source is affected. Fix: delete `backend/_probe_*`. |
| F-2I | **BLOCKING (process, not product)** | `specs/reviews/security-verdict.json` **self-reports commit `f4abd41`**, two commits behind HEAD `9112495`, and reports `pass: false`. Its only two blocking findings are SEC-001 and SEC-002, both of which I re-tested live against HEAD and found fixed. The file is a snapshot of a superseded tree and must not be read as the current verdict — but a fresh verdict for `9112495` does not exist on disk, so the security gate is **unresolved, not cleared**. I have no authority to clear it. The `security-reviewer` running alongside me in this round must regenerate it. |

## 6. Performance and SLO

| Measure | Value | Verdict |
|---|---|---|
| `GET /health` p50 | 1.27 ms | — |
| `GET /health` p95 | 1.57 ms | WITHIN `slo.p95_ms: 500` |
| `GET /health` max (60 samples) | 1.89 ms | WITHIN the AC5 1 s budget |
| Perf baseline | **none on disk** | **WARN, not FAIL** — first/greenfield build, no baseline to regress against |
| 5xx error rate | 0 (excluding the deliberate `/probe/boom` negative test, which ran on a probe harness, not the production app) | WITHIN `slo.error_rate_pct: 1` |

## 7. Deterministic suites at HEAD

| Check | Result |
|---|---|
| `cd backend && uv run pytest -q` | **88 passed**, 2 warnings, 0.15 s |
| `uv run ruff check src/ tests/` | All checks passed |
| `uv run ruff check .` | 41 errors — all in untracked `_probe_*.py`, see F-2H |
| `uv run mypy src/` | Success, no issues in 12 source files |
| `cd frontend && npm test` | **18 passed** (1 file) |
| `npm run lint` / `npm run typecheck` | clean / clean |

## 8. Method, scope and honesty notes

- Read only: the context pack, `sprint-contracts/A.json`, the three story files,
  the production source the pack lists, and uvicorn's own source at
  `httptools_impl.py:470-500`. I did not read the build transcript, the prior
  verdict files as authority, or `.claude/state/uvicorn.log`.
- I **did not edit** `sprint-contracts/A.json` (frozen) or `features.json`
  (owned by instance 1). I generated and fixed no product code.
- The three frozen `api_checks` were run against the **real** production app,
  `src.api.app:app`, never `build_fastapi_app()`.
- The 422 / 500 / multi-line-log / PII probes required routes group A does not
  have. I booted an evaluator-only harness,
  `.claude/state/g3eval2_probe.py`, which wraps the real
  `create_app(build_fastapi_app() + throwaway routes)` — the same composition
  the production path uses — and added no production file. **This harness should
  be deleted after the gate**, along with the `g3eval2-*` logs. It is retained
  now only so the F-2A counterfactual is reproducible.
- Server on port 8001 was killed at the end of the run. Ports 8000 and 8002 were
  never touched.
- Model tier: Opus 5 (runtime mode).

### Evidence artefacts

| Path | Contents |
|---|---|
| `.claude/state/g3eval2-server.log` | 180 lines, production app — the whole-lifetime 180/180 JSON denominator, plus QA-VM-003/004/005 |
| `.claude/state/g3eval2-lines003.txt` | QA-VM-003 isolated log line |
| `.claude/state/g3eval2-lines004.txt` | QA-VM-004 isolated log line |
| `.claude/state/g3eval2-h003.txt`, `-h004.txt` | response headers for both |
| `.claude/state/g3eval2-conc.txt` | 12-way concurrency isolation |
| `.claude/state/g3eval2-chatty.txt` | 3-line handler denominator, all `req-abc` |
| `.claude/state/g3eval2-500.txt` | unhandled 500 — 3 correlated JSON lines |
| `.claude/state/g3eval2-piiboom.txt` | SEC-002 re-test — 0 PII occurrences |
| `.claude/state/g3eval2-routed.log` | F-2A counterfactual, `uvicorn.access` routed |
| `.claude/state/g3eval2-native.log` | F-2A counterfactual, `uvicorn.access` native (plain text) |
| `.claude/state/g3eval2-inject.log`, `-injlines.txt` | `X-Request-ID` injection surface |
| `.claude/state/g3eval2-perf.txt` | 60 latency samples |
| `.claude/state/g3eval2_probe.py` | the harness (delete after gate) |
