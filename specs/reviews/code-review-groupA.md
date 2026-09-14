# Code review — Group A (E15-S1, E9-S1, E11-S1)

Commit `e147f7e`. Reviewed by the orchestrating session, not the `/gate` reviewer
fan-out: that fan-out died five times on the 600s stall watchdog (`/auto` lead,
three group-A reviewers, then `/gate` itself while "spawning all 7 reviewers
concurrently"). The diff is 19 source files / ~700 lines, so it was read directly
instead. **This is a single-reviewer read, not the 3-instance adversarial
re-verification the security boundary normally triggers.** Treat it as partial
coverage and re-run the fan-out when the stall is resolved.

## Deterministic gates (from `/gate`'s completed phase)

| Gate | Result |
|---|---|
| sensors (secret-scan, layer-imports, bounded-context, refactor-purity, …) | 10 passed, 1 blocked |
| `ownership-check` | blocked → ratified waiver for `frontend/eslint.config.js` |
| `observability-verdict` | pass |
| `perf-smell-verdict` | pass |
| `sensor-waivers-verdict` | pass |
| `regression-gate` (re-run against a live server) | **group A: 0 findings** |
| backend `pytest` | 42 passed |
| frontend `vitest` | 11 passed |

Group A's three contract checks verified against a live uvicorn on `:8000`:
`GET /health` → 200 JSON in 0.029 s; `X-Request-ID: req-abc` echoed and carried
on the access-log line; with no inbound header a non-empty id is generated and
echoed.

The regression gate's global verdict is `blocked` only because it replays **every**
group's contract (A–M) regardless of what is built; the other 50 findings are 404s
for endpoints groups B–M have not written yet. Same scoping flaw as
`generation-contract`: the gate validates the whole backlog, not the current group.

## Findings

### 1. `/health` never checks the database — moderate

`backend/src/api/platform/routes.py:60` returns `{"status": "ok"}`. The contract
(`specs/design/api-contracts.md:313`) specifies
`{"status":"ok","database":"ok","version":"..."}`.

The probe does no I/O at all, so it reports healthy while Postgres is down. This
also weakens `E15-S2-AC1`, which asserts all three Compose services "report
healthy" — the backend's healthy signal currently carries no information about its
own dependency. `E15-S1-AC5` still passes, because it only requires 200 and a JSON
body.

**Failure scenario:** Postgres is stopped; `docker compose ps` shows the backend
healthy and `GET /health` returns 200; E15-S2's assertion passes against a stack
that cannot serve a single real read.

### 2. No access log and no correlation id on the error path — moderate

`backend/src/api/middleware.py:130-135` sets `response.headers[X-Request-ID]` and
emits the access line only *after* `await call_next(request)` returns. If the
downstream raises, both are skipped and only the `finally` reset runs.

So the one class of request where the Correlation Id matters most — a 500 — comes
back with no id to correlate on and leaves no access-log line. `E15-S1-AC4` is
exercised only on the success path, so nothing catches it.

**Failure scenario:** a route raises an unhandled exception; the client receives a
500 with no `X-Request-ID`, and no access-log record exists for the request, so the
error cannot be tied to the emitted log lines.

### 3. PII redaction is opt-in, so AC1's guarantee does not generalize — moderate

`RedactionFilter` (`backend/src/config/logging.py:45`) scrubs only values a caller
registered through `redact_values(...)`. The module docstring is candid that it
"does not know PAN/Aadhaar formats in advance". That is a defensible design, but
nothing enforces the contract on the callers who matter.

`E15-S1-AC1` passes because its own test wraps the call. When E4-S1 writes
`POST /applications` (group E), a handler that forgets the wrapper logs raw PAN and
Aadhaar with no gate objecting. This is now weaker still because VM-001 was reduced
to unit-only, so no api-layer check exercises redaction over a served request.

**Failure scenario:** E4-S1 logs the validated `Applicant` model at DEBUG without
entering a `redact_values` scope; synthetic PAN and Aadhaar reach the log sink and
`E15-S1-AC1`'s group-A test still passes.

**Suggested control:** make the origination path acquire the redaction scope through
a FastAPI dependency rather than a manual `with`, or add a sensor asserting every
handler taking an `Applicant` runs inside one.

### 4. Exception tracebacks are silently dropped — minor

`JSONLogFormatter.format` (`logging.py:60-68`) builds its payload from
`timestamp/level/logger/message/request_id` and never reads `record.exc_info`.
`logger.exception(...)` therefore emits a line with no stack trace.

Incidentally this prevents a traceback leaking PII, but that is a side effect, not
a control — and it costs every stack trace in production.

### 5. `create_app()` runs at import time and clears root handlers — minor

`backend/src/api/app.py:30` executes `app = create_app()` at module scope, so
importing `src.api.app` calls `configure_logging()`, which does
`root.handlers.clear()` (`logging.py:78`). Any import of this module mutates global
logging state as a side effect.

Observed during review: under `TestClient`, `httpx`'s own logger was re-formatted
into our JSON envelope and emitted `"request_id": ""` outside the request scope.
Harmless in production (no httpx client logging inbound requests), but note
`E15-S1-AC3` asserts "100% of the lines ... carry request_id equal to req-abc" — a
strict capture-everything reading of that assertion can trip on third-party lines
logged outside a request scope.

### 6. Error mapping is thinner than the published contract — forward risk

`backend/src/api/errors.py:50` returns `{"error": exc.message}`. The contract
specifies `{error, detail, context}` for the `422 PolicyViolation`, and
`E4-S4-AC2` requires the body to name the breached threshold and the configured
value it was checked against. E15-S1 publishes this mapping table as the interface
later stories consume, so the shape needs extending before group G rather than at
it.

### 7. `GET /metrics` is specified but owned by no acceptance criterion — informational

The endpoint index attributes `GET /metrics` to E15-S1, while the contract line
itself notes the path comes from `project-manifest.json#observability.metrics_path`,
"not from a story". No E15-S1 AC mentions metrics and `routes.py` implements health
only. Nothing will ever force this endpoint to exist; if the RED metrics surface is
wanted, it needs an AC.

## No findings

`backend/src/types/money.py` is sound: `ROUND_HALF_UP` applied consistently and
documented, float and bool rejected on both construction and `multiply`, every
operation returns a new quantized instance, `__slots__`, `__eq__`/`__hash__`
consistent. `divide` and ordering comparisons are absent but are E9-S3's need, not
this story's. The delinquency ladder and its config boundaries read correctly
against decision D-B.

---

## Resolution — fixes applied 2026-09-14

The `/gate` run that completed with all 7 reviewers returned **BLOCK** with four
product findings. All four are addressed below, test-first. Three of the four were
independently reproduced before being fixed.

### 1. AC3 — uvicorn loggers bypassed JSON formatting · FIXED

Reproduced under a real `uvicorn` run: one request carrying `X-Request-ID: req-abc`
produced our JSON line *and* a plain-text
`INFO: 127.0.0.1:55482 - "GET /health HTTP/1.1" 200 OK` with no `request_id` —
roughly half the request-scoped lines, against an AC demanding 100%.

`configure_logging()` now calls `_route_server_loggers_through_root()`: `uvicorn`,
`uvicorn.error` and `gunicorn.error` lose their own handlers and get
`propagate = True`, so they render through the JSON root handler.
`uvicorn.access` is **silenced** rather than reformatted, for the two reasons the
gate identified: `request_id_var` is already reset when it emits (it logs after the
response completes, outside the middleware scope) so it could only ever render
`request_id: ""`, and its `AccessFormatter` reads `record.args`, which
`RedactionFilter` clears — raising `ValueError` and dropping the line entirely.
`CorrelationIdMiddleware` already emits an equivalent JSON line with method, path,
status and the correlation id, so no information is lost.

Verified under a real `uvicorn` run after the fix: every line is JSON and the
`req-abc` request yields exactly one request-scoped line carrying it.

The regression test applies uvicorn's own `LOGGING_CONFIG` via `dictConfig` before
calling `configure_logging()` — the step whose absence is why the unit suite never
saw this.

### 2. PII redaction · PARTIALLY FIXED — one part cannot close in group A

Two real leaks closed:

- **Exception path.** `RedactionFilter` scrubbed only `record.getMessage()`, so a
  PAN carried in an exception reached the sink untouched. The filter now renders the
  traceback, scrubs it, stores it on `exc_text` and clears `exc_info` so no
  downstream handler can re-render the original. `JSONLogFormatter` now emits an
  `exception` field — previously every stack trace was silently dropped.
- **Case and separator sensitivity.** Matching was byte-for-byte, so a lowercase PAN
  or an Aadhaar written `2341 2341 2346` sailed past. Matching is now
  case-insensitive and tolerates separators between characters, with a 6-character
  floor so short values cannot over-match.

**Still open, by necessity:** `redact_values` has no production call site, because
no endpoint accepts PII until E4-S1 (`POST /applications`, group E). Hardening the
filter does not make it *invoked*. Rather than leave that to memory, group A now
ships the control: `test_modules_handling_applicant_pii_enter_a_redaction_scope`
fails any `src/` module naming `pan`/`aadhaar`/`salary_doc` that does not enter a
`redact_values` scope. It is vacuous today and becomes load-bearing the moment
origination lands; a companion test proves the check itself bites.

### 3. `Money` accepted `NaN` · FIXED

Reproduced: `Decimal('NaN')`, `'NaN'` and `'nan'` were all accepted, `NaN != NaN`,
and an ordering comparison raised `InvalidOperation` — not an `AppError`, so an
underwriting limit check would have surfaced as an unhandled 500. `Infinity` and
`sNaN` were already rejected, incidentally, by `quantize`.

`Money.__init__` now rejects any non-finite amount explicitly. This also brings the
backend in line with the frontend module, which already rejected non-finite values
via `!parsed.isFinite()` — the asymmetry was itself the tell.

### 4. Both float guards were decorative · FIXED

**Backend.** The AST counter looked only for `float(...)` calls and float literals,
missing the likeliest leak: `principal / months` over two ints yields a float in
Python 3, which is exactly the shape E9-S3's EMI takes. It now also counts true and
floor division and any use of the `math` module (whose functions all return floats),
with a reviewable per-line `# money-guard: decimal-division` exemption so E9-S3 can
annotate legitimate Decimal division line by line instead of disabling the guard.

**Frontend.** The regex list missed `.toNumber()`, `Math.*`, float literals and
unary `+`. All are now covered, and the scan first strips comments and quoted
strings — without that, `"1,234.50"` in a comment read as a float literal and the
honest fix would have been to weaken the real checks. `.toFixed()` is deliberately
**not** flagged: on a `decimal.js` Decimal it returns a string and is the correct
2dp wire rendering.

### Verification

backend `pytest` **68 passed** (was 42) · frontend `vitest` **18 passed** (was 11) ·
`ruff` clean · `mypy` clean over 12 files · frontend `lint` and `typecheck` clean.

### Not addressed in this pass

Unbounded `X-Request-ID` (header-length cap), the missing `database`/`version` fields
on `/health`, correlation loss on unhandled exceptions, and the thin error-mapping
shape are all still open — see findings 1, 2 and 6 above. The seven harness defects
remain outstanding and are not fixable from a build dispatch.
