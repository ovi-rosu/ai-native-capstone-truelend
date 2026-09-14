# Code Review — /gate --group A (round 2, fresh context)

**Range:** `14e9487..9112495` · **Branch:** `feat/harness-scaffold-and-planning`
**Stories:** E15-S1 (platform logging + health), E9-S1 (Money), E11-S1 (delinquency bucket)
**Verdict:** **BLOCK** — 2 BLOCK, 16 WARN, 8 INFO
**Method:** every finding below was reproduced by executing the code at HEAD
(`uv run python` probes against `src.api.app:create_app()` under `TestClient`).
No code comment, commit message or prior verdict file was accepted as evidence.

---

## 1. Prior BLOCK re-verification

### CR-001 — frozen error envelope applied only to `AppError` → **CLOSED**

`backend/src/api/errors.py:131-136` registers four handlers. Verified by probing a
live app with injected routes for each status; every non-2xx body came back as the
exact frozen shape `{"error","detail","context"}` with `content-type:
application/json`:

| probe | status | body |
|---|---|---|
| unknown path | 404 | `{"error":"NotFound","detail":"Not Found","context":{}}` |
| `POST /health` | 405 | `{"error":"HTTPError","detail":"Method Not Allowed","context":{}}` |
| `HTTPException(401)` | 401 | `{"error":"Unauthorized","detail":"no token","context":{}}` |
| `HTTPException(403)` | 403 | `{"error":"Forbidden","detail":"wrong role","context":{}}` |
| `HTTPException(409)` | 409 | `{"error":"Conflict","detail":"illegal transition","context":{}}` |
| body validation | 422 | `{"error":"ValidationError","detail":"request validation failed","context":{"field":"body.n"}}` |
| `AppError` subclass | 422 | `{"error":"PolicyViolationException","detail":"nope","context":{"threshold_kind":"min_income"}}` |
| `raise RuntimeError` | 500 | `{"error":"InternalServerError","detail":"internal server error","context":{}}` |

Key names and nesting match `specs/design/api-contracts.md:26-27` exactly. The 500
leaks neither the exception message, the absolute path nor the SQL it carried. The
`<ErrorName>` slot correctly carries the *name* (`AppError.error` →
`type(self).__name__`), not the message.

Residual, not the original finding: the same handler that closed CR-001 **drops
`exc.headers`** — see `CR2-002` below.

### CR-002 — registered PII leaked unredacted with an empty `request_id` → **CLOSED**

Design at HEAD: `logging.py:44` holds a **mutable set** in the contextvar,
`register_sensitive` (`logging.py:74-81`) mutates it in place, and
`middleware.py:89/96-102` opens the scope and logs the exception *before*
re-raising, without unwinding.

I specifically tested the FastAPI sync-handler-in-threadpool case the comment
claims to handle (`def` handler → `run_in_threadpool` → `anyio` worker thread runs
on a *copy* of the context). Registering `ABCDE1234F` / `123456789012` in a sync
handler and raising:

- `middleware.py:95` traceback frame chain confirms the real threadpool path was
  taken (`anyio/_backends/_asyncio.py:1100 result = context.run(func, *args)`).
- Emitted line: `RuntimeError: boom pan=[REDACTED] aadhaar=[REDACTED]`,
  `"request_id": "rid-sync_fail"`.
- 0 leaking lines and 0 lines with a wrong/empty `request_id` across sync-fail,
  async-fail and sync-success paths.

The in-place mutation genuinely survives the context copy, so the claim in the
comment holds. Both halves of the original finding (unredacted PII **and** empty
`request_id`) are gone.

### CR-003 — per-line money-guard exemption muted every float category → **CLOSED**

`backend/tests/architecture/test_no_float_money.py:82-86`:

```python
if is_division and getattr(node, "lineno", None) in exempt:
    continue
if is_float_call or is_math_attr or is_float_literal or is_division:
    count += 1
```

The `continue` is now gated on `is_division`, so the marker exempts exactly one
category. `test_division_exemption_does_not_silence_other_float_categories`
(:272-297) is a real regression test — it asserts `> 0` for a marked line carrying
`float(...)`, a marked line carrying `+ 0.5`, and a marked `import math`. All three
would have returned 0 under the pre-fix whole-line `continue`.

---

## 2. Your four hypotheses — verified or refuted

**(a) `_install_redaction_filter_everywhere` iterates `loggerDict` once → later
loggers get no filter.** *Partially real, narrow.* Refuted for the common case:
handler-level filters apply to every record reaching that handler, so the
`RedactionFilter` on the root `StreamHandler` (`logging.py:199`) covers any
logger created later that propagates. I confirmed this — a `logging.getLogger("biz")`
created *inside* a request handler after `configure_logging` had its PAN scrubbed
on the root handler's output. Confirmed real only for a logger created after
startup that sets `propagate = False` **and** installs its own handler: probe
`logging.getLogger("late.thirdparty")` has `RedactionFilter` on neither the logger
nor its handler. → `CR2-W02` (WARN), plus the test-honesty consequence `CR2-W03`.

**(b) `middleware.py:102` leaks both contextvars on the failure path.**
**Refuted.** Uvicorn and `TestClient` both run each request cycle in its own task,
so per-PEP-567 the `set()` lives in that task's context copy and dies with it. Probed
directly: after a 500 that registered a PAN, the next request saw
`{"vals": [], "rid": "<fresh id>"}` and the module-level contextvar read back
`None` / `""`. No cross-request bleed, and the non-unwind is what keeps the
server's own traceback line scrubbed. → `CR2-I01` (INFO).

**(c) module-level globals in `platform/routes.py` + the `Counter` in
`middleware.py`.** *Partly a defect.* The `Counter` is a genuine BLOCK, but for
its **label**, not its globalness — see `CR2-001`. The globalness itself is a
testability/isolation WARN (`CR2-W07`): state is shared across every `create_app()`
in a process, which is why `test_health_probe.py` has to call `reset_database_probe()`
inline. Thread-safety is not a live issue: `_request_counts[k] += 1` runs only on the
event-loop thread.

**(d) bare `assert isinstance(...)` for narrowing in `errors.py`.** **Refuted.**
Under `python -O` the asserts vanish, but the handler bodies then only read
attributes (`exc.status_code`, `exc.error`, `exc.message`, `exc.context`,
`exc.errors()`), and Starlette only ever dispatches a matching exception type to
each handler. Stripping the assert removes the type narrowing, not a guard. →
`CR2-I02` (INFO).

**(e) `get_health` constructs `Settings()` per request.** Measured: 0.073 ms per
construction (1000 in 73 ms), against a 500 ms p95 SLO, and `SettingsConfigDict`
names no `env_file` so there is no per-request disk read. Not a defect. →
`CR2-I03` (INFO).

**(f) the three `reset_*` functions exist only for tests.** Confirmed — production
surface shaped by test needs. → `CR2-W07` (WARN).

---

## 3. BLOCK findings

### CR2-001 — `/metrics` `route` label is the raw request path: unbounded cardinality

`backend/src/api/middleware.py:75` (path captured at `:91` from `scope.get("path")`)

The RED counter is keyed on the **literal request path**, not the matched route
template, and the `Counter` at `middleware.py:49` has no bound and no eviction.
Probed against the real app:

```
500 requests to /random-path-0 .. /random-path-499
  -> counter series: 500
  -> GET /metrics body: 36,980 bytes, 502 lines
```

Two reachable consequences:

1. **Unbounded growth from unauthenticated input.** Any client can add a new
   permanent counter series per unique URL. Memory and the `/metrics` response both
   grow without limit; nothing ever evicts. `GET /metrics` is itself public.
2. **The label breaks the contract's aggregation.** `specs/design/api-contracts.md:315`
   requires "RED metrics labelled `method`, `route`, `status`", and
   `routes.py:72` promises the same. Once a path-param route lands
   (`/applications/{application_id}` — E8-S1, next group), every application id
   becomes its own series and the runtime-SLO sensor can no longer compute a p95 or
   an error rate per route. The defect is latent for group A only because group A
   has no path params; the 404 case above already triggers it today.

**Remediation (minimal):** label from the matched route template instead of the raw
path, resolved lazily inside `send_with_correlation_id` (the router has populated
`scope["route"]` by the time `http.response.start` is sent — verified:
`path=/apps/123 → route=/apps/{app_id}`), and collapse unmatched paths to one
constant series:

```python
route = getattr(scope.get("route"), "path", None) or "<unmatched>"
```

Keep the raw `path` for the access-log line if the operator wants it; it is the
*counter key* that must be bounded.

### CR2-002 — the new `HTTPException` handler discards `exc.headers`

`backend/src/api/errors.py:103-107`

`handle_http_error` builds the envelope with `_envelope(...)` and never forwards
`exc.headers`. FastAPI's default `http_exception_handler` — the one this handler
replaces — does `headers=getattr(exc, "headers", None)`. So the diff *regressed*
header behaviour while fixing the body. Probed:

```
POST /health        -> 405, headers: {content-length, content-type, x-request-id}
                       Allow: None                       <-- RFC 9110 §15.5.6 requires it
HTTPException(401, headers={"WWW-Authenticate": "Bearer"})
                    -> 401, WWW-Authenticate: None       <-- challenge silently dropped
```

Reachable today: every wrong-method request returns a 405 with no `Allow`, so a
conformant client cannot discover the allowed methods. Reachable next group: **D-F**
makes `require_roles` the single auth enforcement point and
`api-contracts.md:26-29` specifies `401 no or invalid token`; a Bearer challenge
raised as `HTTPException(401, headers=...)` will be swallowed by this handler, and
no test would notice because every current test asserts only on the body.

**Remediation (one line):**

```python
def _envelope(status_code, error, detail, context=None, headers=None) -> JSONResponse:
    return JSONResponse(status_code=status_code, headers=headers, content={...})

# handle_http_error:
return _envelope(exc.status_code, name, str(exc.detail),
                 headers=getattr(exc, "headers", None))
```

Add one assertion that `POST /health` returns a 405 carrying `Allow`.

---

## 4. WARN findings

| id | file:line | finding |
|---|---|---|
| CR2-W01 | `src/api/platform/routes.py:55-56` | `except Exception: return "down"` swallows the probe's cause entirely — no log line, no `exc_info`. Returning `"down"` is correct, but this is the observability story and an operator gets no way to tell a connection refusal from a permission error. Log at WARNING with `exc_info=True` before returning. |
| CR2-W02 | `src/config/logging.py:241-250` | The filter is installed on `loggerDict` **once**, at configure time. A logger created afterwards that sets `propagate=False` and installs its own handler is covered by neither the logger filter nor the root handler filter (probed: `late.thirdparty` → `False`/`False`). The function name promises "everywhere" and cannot deliver it. Either rely solely on the root-handler filter and rename/delete this function, or install the filter on the handler class/`logging.setLogRecordFactory` so late loggers are covered. |
| CR2-W03 | `tests/unit/test_log_redaction.py:43-65`, `:190-220` | Both AC2 tests call `create_app()` / `configure_logging()` and *then* enumerate `loggerDict` — so they pass by construction and restate the implementation of `_install_redaction_filter_everywhere` rather than asserting a durable property. The `pytest.raises(AssertionError)` on a hand-built `logging.Logger` (:63-65) proves the helper, not the system. Assert the behaviour instead: create a logger *after* configure and assert a registered value is scrubbed from its output. |
| CR2-W04 | `tests/unit/test_log_redaction.py:205`, `tests/unit/test_correlation_id.py:62` | Both apply `logging.config.dictConfig(uvicorn.config.LOGGING_CONFIG)` globally with **no teardown**, mutating process-wide logging for the remainder of the session and making the suite order-dependent. The two blocks are also near-duplicates. Extract one fixture that restores the prior config in `finally`. |
| CR2-W05 | `tests/unit/test_health_probe.py:58-68` | Mutates the `_database_probe` module global and resets it on the last line, not in `try/finally`. A failing assertion mid-test leaves `lambda: False` registered and silently changes `/health` for every later test. Use a fixture with `finally`. |
| CR2-W06 | `src/api/middleware.py:86-87` | Inbound `X-Request-ID` is reflected into the response header and every log line with no validation and no length cap. Probed: a 5,000-character header is echoed back verbatim at 5,000 characters, and lands in every JSON log line for that request. `json.dumps` prevents log injection, but this is unbounded attacker-controlled log volume. Cap the length and reject/regenerate on non-token characters. |
| CR2-W07 | `src/api/platform/routes.py:35,38-47`; `src/api/middleware.py:49,57-59` | Two module-level globals with `global` statements plus three `reset_*` functions that exist only so tests can undo them — production API shaped by test needs, and state shared across every `create_app()` in one process. Hold the probe and the counters on the app instance (`app.state`) or in an injected registry object so each app is isolated and the `reset_*` functions can be deleted. |
| CR2-W08 | `src/api/app.py:52` | Module-level `app = create_app()` runs `Settings()` and `configure_logging()` — including `root.handlers.clear()` (`logging.py:202`) — as an **import side effect**. Merely importing `src.api.app` destroys the host's logging handlers. `tests/conftest.py:36-39` has to make `log_capture` depend on `client` to work around exactly this. Build `app` behind a factory call in the ASGI entrypoint, or guard the module-level construction. |
| CR2-W09 | `src/config/logging.py:102` | `@lru_cache(maxsize=256)` on `_redaction_pattern` is keyed by the **raw sensitive value**, so up to 256 PANs/Aadhaars stay resident in a process-global cache long after the request scope that registered them ended — the opposite of the request-scoped design the rest of the module is built on. Cache on a digest, or move the compiled-pattern cache into the request-scoped set. |
| CR2-W10 | `src/config/logging.py:122-128` | Values shorter than `_MIN_REDACTABLE_LENGTH = 6` are silently skipped. `register_sensitive("12345")` returns normally and the caller has no way to learn the value will never be redacted. The threshold is sound; the silence is not — log once at WARNING, or expose a return value. |
| CR2-W11 | `src/api/serializers.py` (whole file) | `MoneyField` has **zero behavioural tests**. The only reference from the suite is `test_no_float_money.py:26,100`, which reads the file as text for the AST float scan. `specs/design/architecture.md` decision D-G names this "the ONE module" converting `Money` to the wire, and every later money field depends on it. I probed it and it is correct (`"100.00"` round-trips; `100`, `100.5`, `"abc"`, `null` each give a 422, not a 500 — because `InvalidMoneyAmountError` subclasses `ValueError`). That correctness is currently unguarded by any test. Add a round-trip test through a real route. |
| CR2-W12 | `src/api/platform/routes.py:62-67` | `/health` returns `database: "unconfigured"` and can return `status: "degraded"`. Neither value appears in the frozen `api-contracts.md:314` (`{"status":"ok","database":"ok","version":"..."}`), and `specs/design/amendments/group-a-gate-remediation.md` states the contract is deliberately **not** amended because "it is the authoritative frozen side, so the code changes to match it". The code therefore still does not match the side the amendment calls authoritative. Separately, `status:"degraded"` is served with HTTP **200**, so an orchestrator probing on status code alone never sees the degradation. Either amend the contract to enumerate the three `database` values, or return a non-2xx for `degraded`. |
| CR2-W13 | `src/config/logging.py`, `src/api/middleware.py`, `src/api/errors.py`, `src/api/platform/routes.py`, and 5 test files | ~14 production docstrings/comments narrate the *history* of prior defects rather than the current design: "It previously returned `{"status": "ok"}` alone" (`routes.py:7`), "The gate measured 0.58 -> 314 ms" (`test_log_redaction.py:236`), "Five reviewers found this independently and it was demonstrated live" (`:262`), "the code is the stale side" (`test_health_probe.py:33`), "went unreported" (`test_no_float_money.py:85`). This is commit-log content in source: it will be stale within one story and it tells a future reader about a bug that no longer exists instead of about the invariant. Keep the *rationale* ("separator-bearing values are matched literally to avoid quantifier/literal ambiguity"), delete the gate archaeology. |
| CR2-W14 | `frontend/package-lock.json` (untracked), `.gitignore:49` | The lockfile exists on disk (157 KB) but `.gitignore:49` excludes it, so `npm install` on another machine or in CI resolves fresh semver ranges — `frontend/package.json:13-31` is all `^`. For an application (not a published library) the lockfile belongs in git. Remove the `.gitignore` entry and commit it. |
| CR2-W15 | `frontend/src/types/money.ts:64-66` | `multiply` builds `new Decimal(scalar)` outside `toQuantizedDecimal`, so an invalid numeric string throws a raw `DecimalError` rather than the module's own `InvalidMoneyAmountError` — inconsistent with `fromWire` (`:46`), which is the module's documented contract. Route the scalar through the same guard. |
| CR2-W16 | `src/config/logging.py:44`, `_current_values()` at `:47-53` | `_current_values()` silently creates and `set()`s a scope-less set when none is bound. Inside a threadpool copy that `set()` is discarded, so `register_sensitive` called with no middleware scope open is a **silent no-op** — the exact failure mode CR-002 was about, minus the middleware. Every production path opens the scope today, so this is latent. Raise, or log, when no scope is bound. |

---

## 5. INFO findings

| id | file:line | note |
|---|---|---|
| CR2-I01 | `src/api/middleware.py:96-102` | The deliberate non-unwind on the failure path is **sound** — verified no cross-request bleed. Worth one line in the docstring stating the assumption it rests on (one task context per request cycle), because that is what a future reader would need to re-check if the mount point changes. |
| CR2-I02 | `src/api/errors.py:99,105,116` | `assert isinstance(...)` narrowing is safe under `python -O`; the bodies read attributes only and Starlette dispatches by type. `cast()` would express the intent without relying on a statement that can be compiled out. |
| CR2-I03 | `src/api/platform/routes.py:66` | `Settings()` per request measured 0.073 ms; no `env_file`, so no disk read. Still redundant — the factory already builds one at `app.py:33`. |
| CR2-I04 | `src/api/errors.py:117-119` | The 422 envelope reports only `errors[0]`'s location. Fine for the contract as written; E4/E5 form submissions will likely want every field. |
| CR2-I05 | `src/api/errors.py:106` | 405 maps to error name `"HTTPError"`, which is outside the contract's enumerated vocabulary (`api-contracts.md:28-29`). Harmless, but a client switching on `error` sees an undocumented value. |
| CR2-I06 | `tests/unit/test_correlation_id.py:29-30,44-45,75-76,108-109`; `test_error_envelope.py:31-32,62-63`; `test_log_redaction.py:42-43,65-66,97-98` | Top-level `def`s with no blank line between them, unlike every production module in the diff. `ruff` does not select E301/E302 here, so this is drift the gate cannot see. |
| CR2-I07 | `backend/` (out of diff scope) | `pytest-cov` is not installed — `pytest --cov` errors out. `CLAUDE.md` states a 100% meaningful-coverage target and an 80% floor; neither is currently measurable. Noted because `CR2-W11` (untested `serializers.py`) is exactly what a coverage floor would have caught. |
| CR2-I08 | `frontend/src/types/money.ts` vs `backend/src/types/money.py` | `decimal.js` defaults to 20 significant digits for `times`/`plus`; Python's default context is 28. Rounding mode matches (`ROUND_HALF_UP` is away-from-zero on both — I verified `-45.005 → -45.01` on both sides). The precision gap can only bite at magnitudes far beyond any loan principal, but it is an unstated cross-runtime assumption behind D-G. |

---

## 6. What is clean

- **E11-S1** (`types/delinquency.py`, `config/delinquency.py`, `test_bucket_ladder.py`)
  is the strongest part of the diff. `classify_by_days_past_due` is a correct
  last-floor-wins scan, negatives are rejected, and `test_bucket_ladder.py:14-24`
  uses an **independent oracle** written from D-B's literal ranges rather than the
  production floor table — so the 0..400 sweep actually cross-checks the
  implementation instead of restating it. AC1/AC2/AC3/AC4 all have real assertions.
  (The story's Operation 2 names `types/delinquency.py` for the classifier while
  HEAD puts it in `config/delinquency.py`; that is layering-correct — Types may not
  import Config — and `component-map.md:33,131` authorises the file, so it is not a
  deviation.)
- **`Money`** (`types/money.py`) rejects `float`, `bool`, non-numeric strings and —
  notably — `NaN`/`sNaN`/`±Infinity`, which is an edge case most implementations
  miss. `__slots__`, no `float` anywhere, every operation re-quantizes.
- **The E9-S1 float guards** on both sides are real oracles, not decoration. The
  backend AST scan catches `/`, `//`, `float()`, float literals, `**0.5`,
  `import math` and `from math import`; the frontend regex scan strips comments and
  string literals first (so a `"1,234.50"` example does not force the checks to be
  weakened) and has seven positive-control cases.
- **No file over 300 lines, no function over 24 lines.** Largest file is
  `test_log_redaction.py` at 304; largest production file `logging.py` at 251.
- **Layering holds.** `api → config`, `api → types`, `config → types`. No Types
  module imports anything above it.
- **SEC-001 spot-check.** `test_log_redaction.py:229-258` asserts the *structural*
  property (`"]*" not in pattern.pattern`) with a timing check only as a backstop —
  the right way round, since a stopwatch threshold passes or fails on machine speed.
  I did not find a different backtracking shape.

---

## 7. Gate implication

`pass: false` on 2 BLOCK findings. Both fixes are surgical and local — one label
expression in `middleware.py`, one `headers=` parameter in `errors.py` — plus one
assertion each. Neither requires a design change or an amendment. The 16 WARNs are
logged for the next sprint; `CR2-W02`/`W03`, `CR2-W07`/`W08` and `CR2-W12` are the
ones with the shortest fuse, because group B's first story (E1-S1) registers the
real database probe, adds the first path-param route and raises the first 401.
