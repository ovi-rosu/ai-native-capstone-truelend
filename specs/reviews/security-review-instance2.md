# Security Review (instance 2 of 3) — ai-native-capstone-truelend, story group A — 2026-09-14

Range reviewed: `14e9487..f4abd41` (`git diff 14e9487..HEAD -- backend frontend`), judged at HEAD.
Prior-round verdict files were not read; every finding below was derived from the tree at HEAD
and, where marked, verified by running the code.

## Summary

- BLOCK findings (critical/high): **0**
- WARN findings (medium): **8**
- INFO findings (low): **7**
- Overall verdict: **PASS (WARN)** — nothing in this diff is exploitable at HEAD or exposes data today.

Scope: the 24 changed files plus their immediate data-flow neighbours (Starlette/uvicorn header
write path, pydantic serializer path). Not reviewed, per the context pack: authn/authz,
persistence, outbound network calls, uploads, payment execution.

## Live verification performed

To avoid both false positives and false negatives, the security-relevant paths were exercised
against the real app rather than reasoned about. A uvicorn instance on port 8031 served
`src.api.app:app`; a second instance on a private port served an **out-of-tree** probe module
(under a scratch dir since deleted) that wrapped `build_fastapi_app()` with a throwaway raising
route. No production source was modified.

| Probe | Result |
|---|---|
| `X-Request-ID: a\r\nX-Injected: pwned` (raw socket) | llhttp splits it into two request headers; response carries `x-request-id: a` only. No response splitting. |
| obs-fold continuation, `\x1b[31m` (ANSI), `\x00` | 400 Bad Request at the HTTP parser; request never reaches the app. |
| `x" , "request_id": "spoofed` | Emitted as a single JSON string value; all log lines still parse as JSON. |
| latin-1 high bytes (`\xc3\xa9\xff`), TAB | Accepted, round-tripped, escaped by `json.dumps`. No formatter break. |
| 16 000- and 200 000-char header | **Accepted in full** — echoed in the response header and in the log line (200 146-byte JSON line). |
| empty `X-Request-ID` | Falls back to `uuid4().hex`. Never empty. |
| unhandled exception on a route (live uvicorn) | Client gets `HTTP/1.1 500` + `Internal Server Error` (21 bytes, text/plain) with `x-request-id` stamped. **No stack trace, no internal detail in the body.** |
| same, with a PAN in the exception message inside `redact_values(PAN)` | `uvicorn.error` logged the full traceback with the PAN **in cleartext** and `"request_id": ""`. |
| PII nested in a dict/list interpolated into a log message | Correctly `[REDACTED]` (the filter scrubs the rendered string, so walk depth is irrelevant). |
| PII passed via `extra={...}` | Not emitted at all — `JSONLogFormatter` ignores `extra`. No leak. |
| `Money` / `_validate_money` with `1E+999999999`, `"9"*200000`, `NaN`, `snan`, `Infinity`, `0x1f` | All rejected in < 2 ms. No DoS, no non-finite value. |
| `new Decimal("1e999999999").toDecimalPlaces(2)` (decimal.js, frontend parser) | **V8 heap OOM — 4 GB allocated, process killed after ~16 s.** |
| `GET /health` | `{"status":"ok"}` only — no config, version, dependency or secret disclosure. |
| `GET /openapi.json`, `/docs`, `/redoc` | All **200, unauthenticated**. |
| `npm audit` (package.json is in the change set) | 1 critical, 1 high, 3 moderate — all in the dev toolchain (vitest/vite/esbuild). |

## Refuted candidates (documented so they are not re-raised)

Each of these was investigated as a potential BLOCK and refuted with the evidence above:

1. **CR/LF response splitting via `X-Request-ID`** — two independent mitigations: llhttp/h11 never
   deliver a bare CR or LF inside a header value (the request is rejected or split at parse time),
   and `uvicorn.protocols.http.httptools_impl.send` validates every outgoing value against
   `HEADER_VALUE_RE = [\x00-\x08\n-\x1f\x7f]` and raises before writing. Not exploitable.
2. **Log injection / JSON-breaking / ANSI escape injection** — `JSONLogFormatter.format` returns
   `json.dumps(payload)` with the default `ensure_ascii=True`, so quotes, backslashes, control
   bytes and non-ASCII are all escaped; a hostile id cannot forge a second field or emit a second
   line. Control bytes that would be dangerous in a raw-text sink (ESC, NUL) are additionally
   rejected by the HTTP parser before they arrive.
3. **Stack trace or internal detail on the 500 path** — verified on a live server: the body is the
   fixed string `Internal Server Error`. `FastAPI(title=...)` leaves `debug=False`, so
   `ServerErrorMiddleware` never renders a traceback. The ASGI middleware relocation in `f4abd41`
   did not open a leak; it correctly stamps `X-Request-ID` on that 500.
4. **Redaction misses in nested structures / lists / non-dict payloads** — the filter scrubs
   `record.getMessage()`, i.e. the already-rendered string, so nesting depth, container type and
   key naming are all irrelevant. There is no key deny-list to bypass.
5. **Hardcoded secrets / secrets in logs / secrets in the error `context`** — `Settings` declares
   only `service_name` and `log_level`, both non-secret; no credential literal exists anywhere in
   the diff; no `.env`, `.pem` or `.key` file is tracked; nothing writes a config value to a log
   line beyond the service name.
6. **`GET /health` disclosure** — returns two constant strings, does no I/O, reads no settings.
7. **Backend `Money` DoS / wrong-value via a pathological Decimal** — `quantize` raises
   `InvalidOperation` on any value needing more than the 28-digit context, so huge exponents and
   200 000-digit coefficients are rejected in microseconds; `is_finite()` (commit `5c13f54`) closes
   NaN/sNaN/Infinity, including the `"snan"` spelling.
8. **XSS in `MoneyText`** — renders `{value.format()}` as a React text child (auto-escaped); there
   is no `dangerouslySetInnerHTML`, no raw-HTML prop and no template-literal DOM write in the diff,
   and `format()` can only produce digits, `,`, `.` and `-`.

## BLOCK Findings

None.

## WARN Findings

### [SEC-I2-W01] Inbound `X-Request-ID` is trusted verbatim — unbounded length and forgeable value
File: `backend/src/api/middleware.py` lines 50-51 (used at 58, 61)
Severity: medium (WARN)
Description: `inbound = Headers(scope=scope).get("x-request-id")` is used with no length cap, no
character-set restriction and no format check, then written to a response header and to the
`request_id` field of every log line for the request. Two concrete consequences, both verified:
(a) a 200 000-character header was accepted and reproduced in full in both the response header and
the log line (a 200 KB JSON log line) — with per-request log volume scaling by the number of lines
a future handler emits, this is a cheap log-flood / storage-amplification primitive, and lines above
a pipeline's per-event cap are typically dropped, which silently destroys the audit trail for
exactly the requests an attacker chooses; (b) a caller can pick any value, including one shaped
exactly like the server's own `uuid4().hex`, so a hostile client can collide with or impersonate
another request's correlation id and nothing in the record distinguishes a client-supplied id from
a generated one. Neither is a data-exposure or code-execution path, hence WARN, but for a regulated
loan-origination audit trail the forgery half is more than cosmetic.
Fix: validate before use — accept the inbound header only if it matches a strict pattern (for
example `^[A-Za-z0-9._-]{1,64}$`), otherwise generate a fresh `uuid4().hex`; and when an inbound id
is honoured, log the generated id as `request_id` and the caller's value in a separate
`client_request_id` field so the two can never be confused.

### [SEC-I2-W02] Unhandled-exception tracebacks bypass PII redaction and lose the correlation id
File: `backend/src/config/logging.py` lines 80-97; `backend/src/api/middleware.py` lines 64-67
Severity: medium (WARN)
Description: `RedactionFilter.filter` returns early when `_sensitive_values.get()` is empty, and
`redact_values()` resets that contextvar in its `finally` block. An exception raised inside a
`redact_values(...)` scope propagates *out* of that scope before anything logs it: Starlette's
`ServerErrorMiddleware` re-raises, `CorrelationIdMiddleware`'s `finally` resets `request_id_var`,
and uvicorn finally logs `"Exception in ASGI application"` on `uvicorn.error` — at which point both
contextvars are gone. Verified live: a `RuntimeError` carrying `pan=ABCDE1234F` and a config path,
raised inside `redact_values(PAN)`, was written to the log with the PAN in cleartext and
`"request_id": ""`. The module docstring's claim that the filter covers the traceback and that "no
downstream handler can re-render the raw original" holds only for exceptions the handler catches and
logs itself. This is the classic PII-in-logs vector and the static guard
(`test_modules_handling_applicant_pii_enter_a_redaction_scope`) cannot catch it — a module that uses
`redact_values` perfectly still leaks this way. It is WARN rather than BLOCK only because no PII
exists anywhere in the tree at HEAD, so there is no reachable exploit path in this diff; it becomes
a live PII leak the moment the first PII-accepting endpoint (E4-S1) merges.
Fix: make redaction independent of the raising scope. Either register sensitive values for the whole
request scope (set them once in the middleware's context, cleared after `send` completes) so an
escaped exception is still inside a populated scope, or catch `Exception` in
`CorrelationIdMiddleware` around `await self.app(...)`, log it there through the redacting handler
while the contextvars are still bound, and re-raise. Assert the fix with a test that raises out of a
`redact_values` block through the real ASGI stack and asserts the value is absent from the captured
`uvicorn.error` record.

### [SEC-I2-W03] OpenAPI schema and Swagger/ReDoc UI are served unauthenticated with no environment gate
File: `backend/src/api/app.py` line 36
Severity: medium (WARN)
Description: `FastAPI(title=settings.service_name)` leaves `openapi_url`, `docs_url` and
`redoc_url` at their defaults, so `/openapi.json`, `/docs` and `/redoc` all answer 200 to anonymous
callers (verified). Today the schema discloses only `/health`, so the current disclosure is trivial
— but this is the app-factory story, and every route, request/response model, field name and error
schema added by later groups will be published to unauthenticated callers automatically, with no
flag anywhere in `Settings` to turn it off per environment. `/docs` additionally returns an HTML
page that loads Swagger UI JavaScript and CSS from a third-party CDN, with no CSP (see
SEC-I2-W08) and no subresource integrity.
Fix: gate the three URLs on an explicit environment setting — add e.g. `environment: str = "local"`
to `Settings` and pass `openapi_url=None, docs_url=None, redoc_url=None` when it is not a
development environment (or require auth on them once authn lands in a later group).

### [SEC-I2-W04] Error envelope `context`/`detail` is an unfiltered outbound channel, and `AppError` defaults to 500
File: `backend/src/api/errors.py` lines 25-31; `backend/src/types/errors.py` lines 23-32
Severity: medium (WARN)
Description: the handler serialises `exc.context` — typed `Mapping[str, object]`, populated freely by
any raiser — straight into the response body, and `exc.message` into `detail`. There is no
allowlist, no key/value filtering and, unlike log output, no `RedactionFilter` on this path, so a
future subclass that puts a file path, a SQL fragment, a config value or an applicant's PAN into
`context` ships it to the caller with nothing objecting. Nothing internal reaches a client at HEAD
(no production code raises `AppError` yet), which is why this is WARN, not BLOCK. Compounding it,
`AppError.__init__` defaults `status_code=500`: an error raised without an explicit status returns
an internal, developer-written message in `detail` on a 500 — precisely the response that should
carry no detail. (A secondary robustness note: a non-JSON-serialisable value in `context`, e.g. the
`Decimal` that `configured_value` naturally is, makes `JSONResponse.render` raise inside the handler
and turns the intended 4xx into a 500.)
Fix: treat `context` as a public, typed contract — restrict it to JSON-primitive values, and have
each subclass declare the keys it may publish rather than accepting an open mapping; suppress
`detail`/`context` for any 5xx (return a fixed message and log the specifics instead); and make
`status_code` a required argument (or default it to 400) so a 500 is never the accidental default.
Class-name disclosure via `error` is judged acceptable here: the frozen contract in
`specs/design/api-contracts.md` mandates it, and the names are a deliberate domain-level error
taxonomy, not framework internals — keep subclass names domain-worded and do not let them encode
infrastructure detail.

### [SEC-I2-W05] The two money wire parsers disagree, and both silently round caller-supplied amounts
File: `backend/src/api/serializers.py` lines 20-26; `backend/src/types/money.py` lines 59-69;
`frontend/src/types/money.ts` lines 24-35
Severity: medium (WARN)
Description: decision D-G specifies one wire form for money — a quoted 2dp string — but neither end
validates that form; each simply hands the string to its decimal library. Measured divergences on
identical inputs (Python `_validate_money` vs `decimal.js`): `" 10 "` -> `10.00` on the backend,
throws on the frontend; `"0x1f"` -> rejected on the backend, **`31.00`** on the frontend (`"0b101"`
-> `5.00`, `"0o17"` -> `15.00`); `"1E+26"` -> rejected on the backend, accepted on the frontend;
`"1_000"` -> `1000.00` on both, though it is not a contract-legal money string. Independently, both
ends silently round input finer than 2dp (`"10.005"` -> `10.01`, `"0.999"` -> `1.00`,
`"1e-999999999"` -> `0.00`), so an amount submitted by a caller can be accepted at a value that is
not the value submitted, with no error and no audit record of the adjustment. For a loan
origination and repayment ledger, a boundary that silently alters a monetary amount or interprets
the same string as two different amounts on two hops is a financial-integrity weakness, not a style
issue.
Fix: enforce a canonical form at the boundary on both sides before parsing — reject anything that
does not match `^-?(0|[1-9]\d{0,11})\.\d{2}$` (12 integer digits matches `NUMERIC(14,2)`) with a
422 rather than rounding it, and apply the identical regex in `toQuantizedDecimal` so the frontend
can never interpret a string the backend would have refused. Keep `ROUND_HALF_UP` for computed
values only, never for inbound parsing.

### [SEC-I2-W06] Frontend money parser can be driven into a heap-exhaustion DoS
File: `frontend/src/types/money.ts` lines 24-35 (reached from `MoneyText`, line 14)
Severity: medium (WARN)
Description: `toQuantizedDecimal` calls `new Decimal(value).toDecimalPlaces(2)` on whatever string
it is given, with no magnitude bound. `new Decimal("1e999999999").toDecimalPlaces(2)` expands the
value into a digit array: measured, it consumed 4 GB and killed the Node process with
`FATAL ERROR: Ineffective mark-compacts near heap limit` after ~16 s — in a browser this is a
renderer/tab OOM. `isFinite()` does not help, because the value is finite. Reachability at HEAD is
low (the string comes from an API response, and the backend rejects such magnitudes, and no
user-input form exists yet), so this is WARN; it becomes directly reachable the moment any form,
URL parameter or third-party payload feeds `Money.fromWire`.
Fix: bound the input before parsing — apply the canonical-format check from SEC-I2-W05 (which caps
both digit count and exponent) and reject anything else with `InvalidMoneyAmountError` instead of
handing it to `decimal.js`.

### [SEC-I2-W07] JS dependency tree is unpinned, and `npm audit` reports 1 critical / 1 high in the toolchain
File: `frontend/package.json` (dependency manifest, in the change set)
Severity: medium (WARN)
Description: two related supply-chain gaps. (1) `package-lock.json` is excluded from version control
by `.gitignore:49` (verified with `git check-ignore`), so no lockfile is tracked: every install
re-resolves the `^` ranges, no integrity hashes are pinned, builds are not reproducible, and a
compromised transitive patch release lands silently — a poor posture for a regulated financial
application. (2) `npm audit` against the landed manifest reports 5 advisories: **critical** `vitest`
(arbitrary file read/execute when the Vitest UI server listens), **high** `vite` (path traversal in
optimized-deps `.map` handling; NTLMv2 hash disclosure via UNC paths on Windows — relevant, this is
a Windows dev host), and moderate `@vitest/mocker`, `esbuild` (any website can issue requests to the
dev server and read the response) and `vite-node`. Installed: vite 5.4.21, vitest 2.1.9, esbuild
0.21.5. These are all `devDependencies` and none ships in a deployed artefact, and the critical one
additionally requires `vitest --ui`, which no script in this project starts — that is why this is
WARN and not BLOCK. The esbuild and vite advisories are nonetheless a live developer-workstation
exposure whenever `npm run dev` is running. Note for the orchestrator: if project policy is "no
critical/high from `npm audit` at merge", this finding is the one that converts to a BLOCK.
Fix: stop ignoring `package-lock.json`, commit it, and install with `npm ci`; then raise the
declared ranges to patched majors (`vite` >= 6.4.3, `vitest` >= 4.1.11 and their transitive
`esbuild`/`vite-node`/`@vitest/mocker`) and re-run `npm audit` to zero. (The `.gitignore` line is
outside this diff, so the change belongs to whoever owns that file.)

### [SEC-I2-W08] No security response headers on any response
File: `backend/src/api/app.py` (no header middleware registered)
Severity: medium (WARN)
Description: measured on `GET /health`, the response carries only `date`, `server`,
`content-length`, `content-type` and `x-request-id`. There is no `X-Content-Type-Options: nosniff`,
no `X-Frame-Options`/`frame-ancestors`, no `Content-Security-Policy` and no HSTS. The API is
JSON-only today, which limits the impact, but this same app already serves an HTML page at `/docs`
that pulls scripts from a third-party CDN with no CSP and can be framed, and later groups will
return money-bearing JSON that should not be stored by intermediaries (`Cache-Control: no-store`).
The `server: uvicorn` banner also advertises the stack unnecessarily.
Fix: add one small ASGI middleware (alongside `CorrelationIdMiddleware`) that sets
`X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, a restrictive
`Content-Security-Policy` (`default-src 'none'; frame-ancestors 'none'`), `Referrer-Policy:
no-referrer` and `Cache-Control: no-store` on API responses, and run uvicorn with
`--no-server-header` in deployment.

## INFO Findings

### [SEC-I2-I01] A handled `AppError` produces no log line at all
File: `backend/src/api/errors.py` lines 18-31
Severity: low (INFO)
Description: the handler returns a response without logging anything, so the only trace of a
rejected request is the `truelend.access` status line — the error name, message and `context` are
never recorded server-side. For an underwriting decline or policy rejection in a lending platform,
that is a missing audit record and it also makes the client the only party who knows why a request
failed.
Fix: log the error (name, status, `context`) at WARNING/ERROR inside the handler, where the
correlation id and redaction scope are both still bound.

### [SEC-I2-I02] `extra=` fields are silently discarded by the formatter
File: `backend/src/config/logging.py` lines 103-118
Severity: low (INFO)
Description: `JSONLogFormatter` builds its payload from five fixed keys, so anything passed as
`logger.info(..., extra={...})` never reaches the sink. This is currently a *safety* property — PII
placed in `extra` cannot leak (verified) — but it is undocumented and cuts both ways: a developer
who adds `extra={"applicant_id": ...}` will see the field vanish with no warning, and may conclude
the redaction filter handled it.
Fix: either document that `extra` is intentionally dropped, or emit an explicit allowlist of
`record.__dict__` keys through `_scrub` so structured fields are supported *and* redacted.

### [SEC-I2-I03] Redaction remains opt-in, skips short values, and can be bypassed by a late logger
File: `backend/src/config/logging.py` lines 34-42, 45-46, 167-176
Severity: low (INFO)
Description: three residual limits of the control, beyond SEC-I2-W02. (a) It is opt-in per call
site; `test_modules_handling_applicant_pii_enter_a_redaction_scope` is a good static guard but
matches only the literal field names `pan`/`aadhaar`/`salary_doc`, so a module naming the same data
`id_number`, `uid`, `payslip` or `taxId` passes the guard while logging it raw. (b)
`_MIN_REDACTABLE_LENGTH = 6` means any registered value shorter than six characters is never
redacted — fine for PAN (10) and Aadhaar (12), but an OTP, a 4-digit card suffix or a short account
alias would pass through. (c) `_install_redaction_filter_everywhere` only walks loggers that exist
at `configure_logging()` time; a library imported later that sets `propagate=False` and attaches its
own handler bypasses both the JSON formatter and the filter (the current `uvicorn`/`gunicorn`
handling is an explicit fix for exactly this shape, done by name).
Fix: extend the guard's field-name list as the domain vocabulary grows (drive it from
`specs/design/CONTEXT.md`), lower or remove the length floor for values registered explicitly (an
explicitly registered secret should always be scrubbed; anchor the pattern instead to control
false positives), and add a startup assertion that every logger reachable at request time
propagates to the JSON handler.

### [SEC-I2-I04] `Money` accepts amounts far outside `NUMERIC(14,2)`
File: `backend/src/types/money.py` lines 59-76
Severity: low (INFO)
Description: the only magnitude limit is the 28-digit decimal context, so `Money` accepts values up
to roughly 9.9e25 — measured, `"999999999999999.99"` (15 integer digits) is accepted. D-G stores
money as `NUMERIC(14,2)` (12 integer digits), so any amount above that is validated happily here
and then fails at the database, turning a caller input error into a 500 instead of a 422.
Fix: enforce the D-G domain bound in `Money.__init__` (reject `abs(amount) >= 10**12`), which is the
same bound as the canonical wire regex in SEC-I2-W05.

### [SEC-I2-I05] No environment/hardening flag in `Settings`, and `log_level` is unvalidated
File: `backend/src/config/settings.py` lines 18-24
Severity: low (INFO)
Description: no hardcoded secret and no insecure default exist here — but there is also nothing that
distinguishes a production run from a local one, which is what SEC-I2-W03 (docs endpoints) and
SEC-I2-W08 (headers) both need. `log_level` is a free-form `str` passed straight to
`root.setLevel()`, so `TRUELEND_LOG_LEVEL=DEBUG` in production silently widens log output (and with
it PII exposure), while a typo raises at startup.
Fix: add a constrained `environment: Literal["local","test","staging","production"]` field and make
`log_level` a `Literal`/validated enum.

### [SEC-I2-I06] `MoneyText` lets a parse failure escape into render
File: `frontend/src/ui/components/MoneyText.tsx` line 14
Severity: low (INFO)
Description: the component accepts `money: Money | string` and calls `Money.fromWire` during render;
`InvalidMoneyAmountError` therefore propagates into React's render phase and, with no error
boundary in the tree, unmounts the subtree. A single malformed amount in a list of loans blanks the
whole view.
Fix: validate/parse at the data-fetch boundary and pass a `Money`, or render a fallback for an
unparseable value; add an error boundary around money-bearing views.

### [SEC-I2-I07] Parser-rejected hostile requests produce no correlated access record
File: `backend/src/api/middleware.py` lines 56-62
Severity: low (INFO)
Description: requests rejected by the HTTP parser (obs-fold, NUL, ANSI bytes — all verified to
return 400) never reach the ASGI app, so `truelend.access` emits nothing for them; only a
`uvicorn.error` line records the rejection, with no `request_id` and no client address. Probing
traffic is therefore the least visible traffic in the log stream.
Fix: none required in this diff — note it for the observability/SIEM story so that 4xx parser
rejections are also ingested and alertable.
