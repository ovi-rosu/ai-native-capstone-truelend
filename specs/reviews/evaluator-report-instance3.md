# Evaluator Report — Instance 3 of 3 (independent)

**Group:** A · **Contract:** `sprint-contracts/A.json` (freeze re-verified: hashes match)
**Stories:** E15-S1, E9-S1, E11-S1 · **Mode:** `local` · **Target:** `http://127.0.0.1:8000`
**Evaluated:** 2026-09-14 · **Model tier:** opus (runtime mode)

## VERDICT: FAIL

**failure_layer:** `api`
**failure_reason:** QA-VM-003 / VM-003 / E15-S1-AC3 — the contract requires 100% of log lines
emitted while serving to parse as JSON and carry `request_id == req-abc`. Measured **50% (1 of 2)**.

Health check passed on the first attempt. All three api_checks returned the expected 200. The
failure is not the status code — it is the log-content assertion attached to QA-VM-003, which the
contract states as part of the check, not as a footnote.

---

## Per-api_check results

| id | matrix | check | status | content assertion | verdict |
|---|---|---|---|---|---|
| QA-VM-003 | VM-003 | `GET /health` + `X-Request-ID: req-abc` | 200 ✓ | **50% of lines parse as JSON (1/2)** — requires 100% | **FAIL** |
| QA-VM-004 | VM-004 | `GET /health`, no request-id header | 200 ✓ | generated id `e86d768…37b18`, echoed on response, carried by every correlated line | PASS (caveat) |
| QA-VM-005 | VM-005 | `GET /health` JSON body under 1s | 200 ✓ | `application/json`, body parses, p95 28.96 ms / max 34.29 ms vs 1000 ms | PASS |

Latency, 60 samples: min 1.85 · p50 15.45 · p95 28.96 · p99 34.29 · max 34.29 ms.

---

## Ruling on the contested item (QA-VM-003) — my own, not the pack's

**FAILED.** Not "partially met."

Definitive isolated run. I opened a raw socket so I could record my own client port and attribute
log lines to my exact request, then byte-diffed `.claude/state/uvicorn.log` around it:

```
log lines in window: 2   attributable to THIS request: 2
  [JSON ] request_id='req-abc' logger='truelend.access' msg='GET /health -> 200'
  [PLAIN] 'INFO:     127.0.0.1:56803 - "GET /health HTTP/1.1" 200 OK'   <-- not JSON, no request_id

lines emitted while serving = 2; parse as JSON = 1; json_pct = 50.0%  (contract demands 100%)
```

Reproduced identically on three separate requests (ports 52969, 56803, and the `base-ok` run).

The contract's wording is quantified and admits no rounding: *"100% of the log lines emitted while
serving parse as JSON and each carries request_id equal to req-abc."* Five reasons the plain line
cannot be excused:

1. **It is emitted while serving that request.** It is not a startup banner. It is written after the
   response is produced, within the handling of that specific request, and it is attributable to it —
   the client port in the line matches the socket I opened.
2. **It is the same sink.** Both lines land on the same process's stderr, in the same file the
   runtime target designates as the server log. There is no "different stream" carve-out available.
3. **Root cause is a wiring omission, deterministically confirmed.** I applied uvicorn's own
   `LOGGING_CONFIG` and then `configure_logging(Settings())` and enumerated the result:

   ```
   uvicorn.access   propagate=False  handlers=[('StreamHandler','AccessFormatter')]
   <root>           propagate=True   handlers=[('StreamHandler','JSONLogFormatter')]
   ```

   `configure_logging` clears and replaces **root's** handlers. `uvicorn.access` has
   `propagate=False` and its own handler bound to uvicorn's `AccessFormatter`, so its records never
   reach the JSON handler. `create_app()` also cannot fix this by ordering, because the uvicorn CLI
   applies its logging config before importing the app.
4. **The test plan anticipated exactly this and required api evidence to catch it.**
   `specs/test_artefacts/test-plan.md:291` states the api layer was added to VM-003/004/005 because
   *"proving them only at the log-capture fixture would leave the real request path unexercised."*
   `verification-matrix.json` lists `required_layers: ["unit","api"]` for VM-003. The api layer is
   the authoritative evidence for this row, and it fails.
5. **The passing unit test is structurally blind to the defect.** `conftest.py`'s `log_capture`
   fixture attaches a handler to the **root** logger. Since `uvicorn.access` does not propagate, the
   non-JSON line can never enter `log_capture.lines` — and under `TestClient` uvicorn is not running
   at all, so it is never emitted. `CHK-VM-003-unit` therefore passes vacuously with respect to the
   assertion it is supposed to prove. A green unit test here is not evidence of the AC.

The remedy is small and well-known (pass a `log_config` that routes uvicorn's loggers through
`JSONLogFormatter`, or disable uvicorn's access logger and keep the middleware line). That the fix is
cheap is what makes this an implementation gap rather than an unsatisfiable acceptance criterion.

**On QA-VM-004:** same root cause, different wording, so a different ruling. AC4 asks only that
*"every request-scoped log line carries the same generated non-empty request_id and the response
echoes that id."* It does not contain AC3's quantified "100% parse as JSON" clause. Every element
AC4 names explicitly is verified: the id is generated (32-hex uuid4), non-empty, identical across
the correlated lines, and echoed on the response header. I record it PASS with the caveat that the
uvicorn line emitted during the same request carries no `request_id`, so a strict reading of
"request-scoped" would fail it too. I am not stretching it into a second failure — one honest
failure with a clear fix is more useful than two contested ones with the same cause.

---

## Group A acceptance criteria

| AC | Verdict | Evidence |
|---|---|---|
| E15-S1-AC1 (0 PII occurrences) | PASS, caveat | pytest green; redaction is **opt-in** via `redact_values()` and does not scrub tracebacks (below) |
| E15-S1-AC2 (filter on 100% of loggers) | PASS, caveat | enumerated 10 loggers, 0 without a `RedactionFilter`; late-registered loggers get none |
| E15-S1-AC3 (100% JSON, `req-abc`) | **FAIL** | 1 of 2 lines, 50% — see ruling |
| E15-S1-AC4 (generated id, echoed) | PASS, caveat | id echoed and consistent across correlated lines |
| E15-S1-AC5 (200, JSON, <1s) | PASS | p95 28.96 ms, max 34.29 ms |
| E9-S1-AC1 (schedule money 2dp) | PASS **by proxy** | no schedule generator exists in group A; proven on `Money` arithmetic instead |
| E9-S1-AC2 (0 float ops, backend) | PASS, weak guard | guard misses true division / `math.*` / `round(a/b)` |
| E9-S1-AC3 (frontend decimal, 0 float ops) | PASS, weak guard | guard misses `.toNumber()`, `Math.*`, `0.1+0.2`, unary-plus |
| E11-S1-AC1 (35 dpd → DPD-30) | PASS | independent call returns `DPD-30` |
| E11-S1-AC2 (0–400, no gap/overlap) | PASS | 401/401 covered, 5 buckets, all ranges contiguous, no overlap |
| E11-S1-AC3 (nothing overdue → CURRENT) | PASS | due-today and due-future both `CURRENT` |
| E11-S1-AC4 (bucket only, no charge) | PASS | `StrEnum`; no fee/interest/charge/penal attribute |

E11-S1 is the cleanest story in the group: I re-derived the whole ladder independently and it matches
the specified floors exactly. `Money` is also genuinely robust — it rejects `float`, `bool`, and a
float scalar in `multiply` with `InvalidMoneyAmountError`. The weak guards below are about protecting
*future* stories, not about a current defect in these types.

---

## BLOCK findings

**BLOCK-1 — QA-VM-003 / E15-S1-AC3 fails at the api layer.** The contracted assertion. Fix the
uvicorn log wiring; do not weaken the AC, and do not accept the unit test as evidence for it.

**BLOCK-2 — `plan-seal.js check` exits BLOCKED; the group A bundles themselves changed after
sealing.** I re-ran it rather than trusting the pack:

```
plan-seal: BLOCKED — sealed artifacts changed: specs/design/reasons-canvas.md,
specs\bundles\E11-S1.json, specs\bundles\E15-S1.json, specs\bundles\E9-S1.json
```

All three group A bundles are in that list. These are the approved execution contracts the group was
built against, so their provenance for this group is currently unauditable. `contract-freeze.js
--check` passes (the sprint contract is intact), which is why I treat the contract text as
authoritative — but the bundles are not. Needs re-approval and `plan-seal.js write`, or a diff
showing the changes are immaterial.

**BLOCK-3 — `ownership-check` fails: `backend/src/__init__.py` has no owning story.** Independently
confirmed — `grep -c "backend/src/__init__.py" specs/design/component-map.md` returns `0` against 138
map entries. Small, real, and cheap to fix.

---

## MAJOR findings

**M1 — `RedactionFilter` does not scrub exception tracebacks.** Demonstrated: with a value marked
sensitive via `redact_values()`, the message was redacted but the rendered traceback leaked it
verbatim.

```
message containing [REDACTED]
handler failed
Traceback (most recent call last):
ValueError: boom for PAN ABCDE1234F        <-- secret occurrences in buffer: 1
```

`filter()` rewrites `record.msg` only; `record.exc_info` / `exc_text` are untouched. Not live today
(`JSONLogFormatter` omits `exc_info` entirely, and `uvicorn.error` propagates to the root JSON
handler), but it becomes a PII-to-log-sink leak the moment anything renders exceptions — which is
required for diagnosability. Directly contrary to E15-S1's `scope_out`: *"must not write applicant
PAN, Aadhaar or salary-document content to any log sink."* For a platform handling PAN and Aadhaar
this deserves fixing in group A, while the substrate is the only thing that exists.

**M2 — redaction is opt-in with no pattern fallback.** `RedactionFilter` scrubs only values a caller
explicitly wraps in `redact_values()`. Nothing in group A calls it. The NFR-03 guarantee therefore
rests on every future handler author remembering to. The module docstring concedes this. AC1's unit
test marks its own values, so the test cannot fail — it is self-fulfilling. Recommend a
pattern-based PAN/Aadhaar fallback as defence in depth.

**M3 — `JSONLogFormatter` silently drops `exc_info`.** No stack trace can ever reach the JSON log.
This is the flip side of M1 and an observability defect in its own right for a story whose purpose
is *"so that I can diagnose the origination flow."*

**M4 — caller-supplied `X-Request-ID` is unbounded.** An 8000-character header was accepted,
reflected verbatim into the `x-request-id` response header, and written into the JSON log's
`request_id` field. No length cap, no charset allow-list. I did attempt CRLF injection via raw
sockets: **not achievable** — uvicorn's h11 parser rejects bare CR and control characters with
`400 Bad Request`, and `json.dumps` escapes the log path. So the impact is log-volume amplification
and header bloat, not injection. Add a length cap (e.g. 128) and a charset allow-list, falling back
to a generated id.

**M5 — `GET /metrics` is attributed to E15-S1 but returns 404.** `specs/design/api-contracts.md:38`
assigns `/metrics` to **E15-S1**, and `project-manifest.json` sets `observability.enabled: true` with
`metrics_path: /metrics`. Live: `404`, and `/openapi.json` exposes only `/health`. Consequently
`slo-check.js` returns `{"verdict":"unreachable","error_rate_pct":null,"p95_ms":null}` — the runtime
SLO sensor cannot function. No AC and no matrix row covers `/metrics`, which is how a
design-committed endpoint slipped through the acceptance net. I do not treat this as a contract BLOCK
(it is outside A.json's three checks) but it is more than informational: an observability story that
ships with the observability scrape path missing has not delivered its own NFR surface.

**M6 — both float guards are materially weaker than the ACs they certify.** The ACs say "reports 0
float **arithmetic operations**." The backend AST counter counts only `float()` calls and float
literals; the frontend uses five regexes. Measured misses:

| Case | Backend | Frontend |
|---|---|---|
| `a / 3`, `1 / 3` (true division → float) | missed | — |
| `math.sqrt(a)`, `round(p / n, 2)` | missed | — |
| `.toNumber()`, `.valueOf() * 2` | — | missed |
| `Math.round(p / n)` | — | missed |
| `0.1 + 0.2` → `0.30000000000000004` | caught (literal) | missed |
| `+x.toFixed(2) * 3` | — | missed |

Note `/\bNumber\s*\(/` does **not** match `.toNumber(` — there is no word boundary between `o` and
`N`. D-G/D-J's "no float ever touches money" guarantee for all 20-plus downstream stories rests on
these two checks, and they would not notice the most natural way a float enters money code: dividing.

**M7 — E9-S1-AC1 is verified by proxy.** AC1 says *"when a schedule is computed from each triple."*
No schedule generator exists in group A; the test does ad-hoc `Money` arithmetic instead. The test
docstring is candid about it. This is a story-sequencing defect rather than an implementation one —
the same class of problem as QA-VM-003 — and AC1 should be re-verified when the schedule lands.

---

## Notes on things I checked and cleared

- **Layering: clean.** Every `src.*` import is layer-legal. `config/delinquency.py` imports
  `types/delinquency.py` (Config→Types, allowed). Nothing in `types/` imports any other layer.
- **E11-S1 classifier placement is a justified deviation.** The bundle's operation 2 said put
  `classify` in `types/delinquency.py` *"reading the floors from config"* — which would have forced
  Types→Config and violated the architecture. The implementation inverted it and documented why.
  Correct call; both files are in E11-S1's `owned_files`.
- **Error surface: no leakage.** 404 → `{"detail":"Not Found"}`, 405 → `{"detail":"Method Not
  Allowed"}` with a correct `allow: GET`. No stack traces, no internal paths.
- **`/health` discloses nothing.** `{"status":"ok"}` only. `/openapi.json` exposes one path and
  `version: 0.1.0`. `/docs` and `/redoc` are open (FastAPI default) — worth closing in production,
  but they are not business endpoints and do not breach E15-S1's `scope_out`.
- **`regression-suite-full`**: verdict file reports `pass` with the note that there are no prior
  contracts to replay. Group A is the first landed group, so the earlier 50/54-finding run was a
  misapplied check, not a product regression. I agree with the pack here, having checked the verdict
  rather than the narrative.
- **Perf ratchet: WARN, not FAIL.** No baseline at `specs/brownfield/perf-baseline.json`. Per the
  ratchet rule a missing baseline on a first build is a WARN. Absolute latency is far inside budget.
- **Security gate: not mine to close.** `specs/reviews/security-verdict.json` does not exist.
  `security-scan.json` reports 0 findings at tier `standard` but lists `gitleaks` as **missing** from
  the toolchain, so the secrets tier did not actually run. Recorded `untested`.
- **`evidence-integrity`** remains pre-evaluator and reads the canonical
  `specs/reviews/evaluator-evidence.json`, which instance 1 owns. My ledger is at
  `evaluator-evidence-instance3.json` by instruction and will not clear that gate.
- **Working-tree governance items** (`project-manifest.json` edited outside the envelope's
  `allowed_paths`; `task-envelope.json` rotated with `previous_envelope_hash: null` and
  `amendments: []` despite two history files) are real process defects, but they are the diff
  reviewer's and the orchestrator's call, not runtime evidence. I confirmed the manifest parses and
  has exactly one `verification.mode`.

---

## Structured failure

```json
{
  "failure": {
    "layer": "api",
    "gate": "evaluator",
    "check": "QA-VM-003: GET /health -> 200 with X-Request-ID: req-abc; 100% of log lines emitted while serving parse as JSON and carry request_id == req-abc",
    "actual": {
      "status": 200,
      "log_lines_emitted_while_serving": 2,
      "log_lines_parsing_as_json": 1,
      "json_pct": 50.0,
      "offending_line": "INFO:     127.0.0.1:56803 - \"GET /health HTTP/1.1\" 200 OK"
    },
    "stack_trace": null,
    "error_type": "assertion_error",
    "files_likely_involved": [
      "backend/src/config/logging.py:70",
      "backend/src/api/app.py"
    ],
    "artifacts": [".claude/state/uvicorn.log"],
    "prior_attempts": []
  }
}
```

Fix direction: give uvicorn a `log_config` whose handlers use `JSONLogFormatter`, or set
`access_log=False` and rely on the middleware's own correlated line. Either makes the api-layer
assertion true instead of unobservable.

## Deterministic suites (re-run by me)

| Command | Exit | Result |
|---|---|---|
| `cd backend && uv run pytest -q` | 0 | 42 passed, 2 warnings |
| `cd backend && uv run mypy src/` | 0 | no issues found in 12 source files |
| `cd backend && uv run ruff check .` | 0 | All checks passed! |
| `cd frontend && npm test` | 0 | 11 passed (1 file) |

All four green, matching the pack. They are necessary but not sufficient: the one contracted
assertion that the unit suite cannot observe is the one that fails.

## Recommendation

**Do not merge.** Return to the generator for BLOCK-1 (uvicorn log wiring), BLOCK-3 (ownership row),
and M1 (traceback redaction — cheap now, expensive after twenty handlers exist). BLOCK-2 (plan-seal)
needs a re-approval or an immateriality diff from the orchestrator. M5 and M6 should be logged as
follow-ups if they are not fixed in this pass; M6 in particular is a guard that will be trusted by
every later money story.
