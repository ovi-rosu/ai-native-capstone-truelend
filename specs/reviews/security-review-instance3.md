# Security Review (INSTANCE 3 of 3) — ai-native-capstone-truelend — group A — 2026-09-14

Range: `14e9487..d0b5c94` plus the uncommitted working tree.
Scope: the 13 production files named in `specs/reviews/review-context-pack.md`, their
data-flow neighbours, the changed test/config files, and the live runtime on
`http://127.0.0.1:8000`. Independent vote — no context shared with instances 1 and 2.

## Summary
- BLOCK findings: 2
- WARN findings: 6
- INFO findings: 10
- Overall verdict: **BLOCK**

Both BLOCK findings survived an explicit find-then-refute pass and are backed by a
reproduction I executed against the delivered code. Every refuted candidate is recorded
in "Refuted candidates" below so the majority vote can see what I dropped and why.

---

## BLOCK Findings

### [VULN-001] PII marked sensitive reaches a log sink in cleartext via the exception path
File: `backend/src/config/logging.py` lines 45-54 (`RedactionFilter.filter`)
Severity: high → BLOCK
Category: sensitive-data-exposure

`RedactionFilter.filter` rewrites only `record.msg` (and clears `record.args`). It never
touches `record.exc_info` or `record.exc_text`. Any value registered through the module's
own `redact_values()` API therefore survives untouched inside an exception's arguments, and
the standard `logging.Formatter` used by uvicorn's own handler renders that exception text
verbatim.

Reproduction (run in `backend/` under the real startup order — uvicorn's `LOGGING_CONFIG`
applied first, then `configure_logging()`, exactly as happens when `src.api.app:app` is
imported by uvicorn). A synthetic PAN was registered as sensitive, then raised inside an
exception and logged the way uvicorn logs every unhandled ASGI exception:

- message path (`uvicorn.error.error("applicant pan=%s", PAN)`) → `applicant pan=[REDACTED]` — correct.
- exception path (`uvicorn.error.exception("Exception in ASGI application")`) → the emitted
  line ended with the exception text carrying the **unredacted** PAN and the
  salary-document token, at ERROR level.

This violates the project threat model's rule "NEVER log secrets, tokens, passwords, or
full PII ... at INFO level or above" (`.claude/claude-security-guidance.md`), and it
violates this story's own scope_out in `specs/stories/E15-S1.md` — "must not write applicant
PAN, Aadhaar or salary-document content to any log sink" — as well as the stated intent of
E15-S1-AC1 ("redacted from every emitted log line, **however they reach the logger**",
`backend/tests/unit/test_log_redaction.py:22-23`).

Why this is BLOCK rather than a future-story concern: the defect is in the security control
this story exists to deliver, the bypass is on a code path the framework exercises
automatically for every unhandled exception (no new code required to reach it), and
E15-S1-AC2 plus its passing test certify the filter as installed on 100% of configured
loggers — producing false assurance that every later epic will build on. The story's own
description says this substrate is landed first precisely to avoid a retrofit pass.

Fix: redact inside the filter across the whole record, not just `msg` — apply the same
substitution to `record.exc_text` (after forcing it via `logging.Formatter.formatException`)
and to `record.exc_info`'s exception args, or stop the raw exception text reaching any
formatter (e.g. take ownership of uvicorn's `uvicorn`/`uvicorn.access` handlers in
`configure_logging` so no sink uses a formatter that renders `exc_info` unfiltered). Add a
regression test that registers a value with `redact_values()`, raises it inside an exception,
logs with `exc_info=True`, and asserts 0 occurrences in the captured sink.

### [VULN-002] Unbounded, unvalidated `X-Request-ID` is written to the log sink and echoed in the response
File: `backend/src/api/middleware.py` lines 32-36
Severity: high → BLOCK
Category: resource-exhaustion / denial-of-service (CWE-770, CWE-779)

`request_id = request.headers.get("X-Request-ID") or uuid4().hex` accepts the caller's value
with no length cap, no format constraint and no charset allow-list. That value is then
(a) bound to `request_id_var`, so `JSONLogFormatter` writes it into **every** log line for
the request scope, and (b) assigned to `response.headers["X-Request-ID"]`. `/health` is
unauthenticated and unthrottled, and there is no reverse proxy, ingress, or
`docker-compose.yml` anywhere in the repo to cap header size (the pack's own runtime target
is bare uvicorn, and `project-manifest.json#verification.mode` was just switched to `local`).

Observed against the live server (raw socket, so no client-side normalisation):
- 8 KB header → `200 OK`, value echoed in full.
- 100 KB header → `200 OK`, produced a 100,147-byte log line.
- **1 MB header → `200 OK`**, produced a 1,000,147-byte log line.
- 60,000 high bytes (`0xFF`) → each escaped by `json.dumps` into a 6-character JSON unicode escape sequence, producing a
  360,147-byte log line: a measured **6x write amplification** for non-ASCII input.
- `.claude/state/uvicorn.log` grew from ~414 KB to 15.7 MB during a handful of probe
  requests; the largest single line in that file reached 8,388,755 bytes. (That 8 MB line
  is attributable to a concurrently-running reviewer instance, not to me — I am citing my
  own independently verified 1 MB/1,000,147-byte result as the evidence, and the 8 MB line
  only as corroboration that no cap exists at any size.)

Beyond disk/log-pipeline exhaustion there is a memory dimension: the value is held
simultaneously as raw bytes in the h11 buffer, as a latin-1 `str` in Starlette's headers, in
the contextvar, in the response headers, and again in the formatted JSON string — several
multiples of the request size per in-flight request, with no concurrency or size limit.
Logging goes to a bare `logging.StreamHandler()` with no rotation configured.

Refutation attempts, all failed: uvicorn's `h11_max_incomplete_event_size` did not reject
1 MB or 8 MB; JSON escaping does not bound the value, it expands it 6x; no log rotation,
no rate limiting, and no edge proxy exists in this repository or its design artefacts.

This is availability-and-audit-integrity impact, not confidentiality — an anonymous caller
can also drown or prematurely rotate the audit log of a regulated lending platform. A
reviewer who wants to downgrade this to WARN should do so only against a *written,
enforced* edge header cap; none exists today.

Fix: validate before use — cap the accepted value (e.g. 64-128 characters), restrict it to
an allow-list charset (`[A-Za-z0-9._-]`), and fall back to `uuid4().hex` when the inbound
value fails either check. Both the log binding and the response echo then become bounded.

---

## WARN Findings

### [VULN-003] Redaction is opt-in and exact-substring only — case- and format-sensitive
File: `backend/src/config/logging.py` lines 31-54
Severity: medium → WARN

`RedactionFilter` does a literal `str.replace` of values explicitly registered by a
`redact_values()` scope. Verified misses, each reproduced in-process with `ABCDE1234F`
registered as sensitive:
- **Case variance** — logging `abcde1234f` emitted `pan=abcde1234f` in cleartext.
- **Format variance** — logging the value split as `ABCDE-1234F` emitted it in cleartext.
  This matters concretely for Aadhaar, which is conventionally written `1234 5678 9012`
  while the raw form is `123456789012`; either form registered leaves the other exposed.
- **Scope variance** — any log call outside a `redact_values()` block emits cleartext by
  design. `redact_values` currently has **zero** production callers, so the control is inert
  in the shipped app.

The story names PAN, Aadhaar and salary-document content specifically, and both have
well-defined formats (PAN `[A-Z]{5}[0-9]{4}[A-Z]`; Aadhaar 12 digits), yet there is no
pattern-based backstop — so a single forgotten wrapper in any future handler leaks in
cleartext with nothing to catch it.

Fix: normalise case (and strip separators) on both sides of the comparison, and add a
format-based backstop filter that masks PAN- and Aadhaar-shaped tokens unconditionally, so
redaction fails closed rather than depending on every caller remembering the wrapper.

### [VULN-004] `/docs`, `/redoc` and `/openapi.json` are exposed unauthenticated with no environment gate
File: `backend/src/api/app.py` line 23; `backend/src/config/settings.py` lines 18-24
Severity: medium → WARN

`FastAPI(title=settings.service_name)` leaves `docs_url`, `redoc_url` and `openapi_url` at
their defaults. Verified live: `GET /docs` → 200 (Swagger UI HTML), `GET /redoc` → 200,
`GET /openapi.json` → 200 with the full machine-readable schema. `Settings` has no
`environment` or `debug` field, so there is no switch to disable them per environment.
Today this discloses only `/health`, but every endpoint, parameter and model added by later
groups is published automatically to any anonymous caller.

Fix: add an environment field to `Settings` and pass `docs_url=None, redoc_url=None,
openapi_url=None` unless the environment is a development one.

### [VULN-005] Client-supplied correlation id is trusted verbatim as the audit key
File: `backend/src/api/middleware.py` line 32
Severity: medium → WARN

The inbound `X-Request-ID` is accepted from any anonymous caller with no format validation
and no notion of a trusted proxy, and becomes the sole correlation key on every log line for
that request. An attacker can therefore choose any correlation id, including one colliding
with a legitimate trace, and attribute their own activity to it — degrading log and audit
correlation in a system whose logs are regulatory evidence. Verified live: duplicate
`X-Request-ID: first` / `X-Request-ID: second` headers resolve to `first`, so an id chosen by
a client can also mask one injected by an upstream proxy depending on ordering.

Fix: always generate a server-side id as the authoritative `request_id`, and record any
inbound client value under a separate field (e.g. `client_request_id`) after validating its
charset and length; or accept the inbound id only from a configured trusted-proxy source.

### [VULN-006] No security response headers on any response; `/docs` executes third-party CDN scripts
File: `backend/src/api/app.py` lines 18-27
Severity: medium → WARN

Verified live — responses carry only `date`, `server`, `content-length`, `content-type` and
`x-request-id`. Missing: `X-Content-Type-Options: nosniff`, `X-Frame-Options` /
`Content-Security-Policy: frame-ancestors`, `Content-Security-Policy`, and
`Strict-Transport-Security`. The app already serves `text/html` from `/docs` and `/redoc`,
and that HTML loads Swagger UI / ReDoc JavaScript and CSS from `cdn.jsdelivr.net` (plus a
favicon from `fastapi.tiangolo.com`) with no Subresource Integrity and no CSP — third-party
script execution on the API origin. `server: uvicorn` also discloses the server software.

Fix: add a middleware that sets `nosniff`, a frame-ancestors/`X-Frame-Options` deny, and a
restrictive default CSP on every response; disable the CDN-backed docs outside development
(see VULN-004) or self-host the Swagger UI assets with SRI.

### [VULN-007] Unhandled exceptions lose all correlation — no response id, no access log line, empty `request_id`
File: `backend/src/api/middleware.py` lines 34-42
Severity: medium → WARN

`response.headers[...] = request_id` and the `_access_logger.info(...)` call both sit *after*
`await call_next(request)`, and the `finally` block resets `request_id_var` before the
exception leaves the middleware. So for any exception not converted by the inner
`ExceptionMiddleware` (i.e. anything that is not `AppError` or `HTTPException`): the 500
response carries **no** `x-request-id` header, **no** access-log line is emitted, and
uvicorn's "Exception in ASGI application" traceback is logged with `request_id` already
reset to `""`. The one class of record most needed for incident response and audit
reconstruction is the only one that cannot be correlated. Verified live that the *handled*
paths are fine: 404 and 405 responses do carry `x-request-id` (confirmed
`x-request-id: probe-405` on `POST /health`).

Fix: wrap `call_next` in `try/except`, log the access line and attach the header on the
error path too (or re-raise after logging), and keep the contextvar bound until after the
error has been logged — e.g. register a handler for `Exception` that runs inside the
correlation scope.

### [VULN-008] New frontend manifest introduces 1 critical / 1 high / 3 moderate npm advisories
File: `frontend/package.json` (new in this diff)
Severity: medium → WARN

`npm audit` on the manifest added by this diff reports
`{"moderate":3,"high":1,"critical":1,"total":5}`:
- **critical** `vitest` — arbitrary file read/execute when the Vitest UI server is listening;
  path traversal / arbitrary file read via `@vitest/mocker` redirect mock.
- **high** `vite` — path traversal in optimized-deps `.map` handling; `server.fs.deny`
  bypass on Windows alternate paths; `launch-editor` NTLMv2 hash disclosure via UNC path
  handling on Windows.
- **moderate** `@vitest/mocker`, `esbuild` (any website can send requests to the dev server
  and read the response), `vite-node`.

All five are `devDependencies`. Refutation applied: none reaches a production bundle
(`vite build` ships only `react`, `react-dom` and `decimal.js`), and `--ui` is not used
(`"test": "vitest run"`), so I did **not** block on this. It stays a WARN rather than an
INFO because the vite/esbuild dev-server advisories are reachable in the ordinary developer
workflow — `"dev": "vite"` is a declared script — and the Windows-specific `server.fs.deny`
bypass and NTLMv2 disclosure match this project's actual platform.

Fix: bump/pin the affected dev dependencies to patched majors (or add `overrides`), re-run
`npm audit`, and keep the dev server bound to loopback.

---

## INFO Findings

### [VULN-009] Log output is not 100% structured JSON; uvicorn's plain-text sink bypasses the JSON escaping
File: `backend/src/config/logging.py` lines 71-82
Severity: low → INFO

`configure_logging` clears handlers on the **root** logger only. `uvicorn.access` keeps its
own `StreamHandler` with `propagate=False`, and `uvicorn.error` propagates to the `uvicorn`
logger's own handler — both using uvicorn's plain-text `DefaultFormatter`. Measured on the
live log: **66 JSON lines vs 94 non-JSON lines**, e.g.
`INFO:     127.0.0.1:59071 - "GET /health HTTP/1.1" 200 OK` and
`WARNING:  Invalid HTTP request received.`, none carrying a `request_id`. The security
relevance is that this parallel sink is not protected by `JSONLogFormatter`'s escaping — the
property that neutralises VULN-002's control-character and line-forgery variants. (The
AC-conformance angle for E15-S1-AC3 / QA-VM-003 belongs to the evaluator, not to me.)

Fix: install the JSON formatter and redaction filter on uvicorn's own handlers too, or set
`propagate=True` with `handlers=[]` on `uvicorn`, `uvicorn.error` and `uvicorn.access`.

### [VULN-010] Tracebacks and `extra=` fields are silently dropped from the JSON sink
File: `backend/src/config/logging.py` lines 60-68
Severity: low → INFO

`JSONLogFormatter.format` builds a fixed five-key payload and never consults
`record.exc_info`, `record.exc_text`, or `record.__dict__`. Verified in-process:
`logger.exception("underwriting failed")` emitted a JSON line with the message only and no
trace whatsoever; `logger.info("saved applicant", extra={"pan": ...})` dropped the extra
field entirely. This limits confidentiality exposure on the JSON sink, but it destroys
forensic evidence — the JSON sink alone cannot support incident investigation, and it means
the useful trace only ever appears on the *unredacted* plain-text sink (VULN-001).

Fix: render exception information into the JSON payload as a dedicated field, **after** it
passes through redaction.

### [VULN-011] Error messages are echoed verbatim to clients and embed raw input
Files: `backend/src/api/errors.py` line 20; `backend/src/types/errors.py` line 14;
`backend/src/types/money.py` lines 33-38, 58, 66; `backend/src/config/delinquency.py` line 38
Severity: low → INFO

`_handle_app_error` returns `{"error": exc.message}` verbatim, and `AppError.__init__`
defaults to `status_code=500`. No leak exists today: `InvalidMoneyAmountError` is a
`ValueError`, not an `AppError`, so it reaches Starlette's `ServerErrorMiddleware`, which
with `debug=False` returns a generic `Internal Server Error` and no traceback — I verified
`FastAPI` is constructed without `debug=True`. The pattern is still worth noting, because
those messages interpolate the raw caller input (`f"invalid money amount: {amount!r}"`,
`f"cannot quantize amount: {value}"`, `f"...got {days_past_due}"`), so the first story that
wraps one in an `AppError` will reflect user input into a response body.

Fix: keep client-facing `message` values as fixed, non-interpolated strings and carry the
raw input only in the (redacted) log record; make `status_code` an explicit argument.

### [VULN-012] Non-ASCII bytes are echoed verbatim into the `x-request-id` response header
File: `backend/src/api/middleware.py` line 36
Severity: low → INFO

Verified live: a request id of raw bytes `e2 98 a0 f0 9f 92 a5 63 61 66 c3 a9` returned
`200 OK` with those exact bytes in the `x-request-id` response header (Starlette's latin-1
decode/encode round-trips them). RFC 9110 field values should be ASCII; downstream proxies
and log shippers may mis-decode or reject. No injection is possible — see the refutations.

Fix: covered by the charset allow-list in VULN-002's fix.

### [VULN-013] `MoneyText` can unmount the React subtree on malformed wire data
File: `frontend/src/ui/components/MoneyText.tsx` line 14
Severity: low → INFO

`Money.fromWire(money)` throws `InvalidMoneyAmountError` for any non-decimal string, and the
component neither catches it nor sits behind an error boundary, so a malformed or hostile
API value unmounts the surrounding tree. Availability/robustness only — **not XSS** (see
refutations).

Fix: validate at the API-response boundary, or render a fallback on parse failure.

### [VULN-014] Context pack's "no outbound network calls" claim is incomplete
File: `specs/reviews/review-context-pack.md` line 66
Severity: low → INFO

True for server-side code — I grepped the changed backend modules for `requests`, `httpx`,
`urllib`, `aiohttp`, `socket`, and found none. But the diff's default FastAPI configuration
serves HTML from `/docs` and `/redoc` that instructs the **browser** to fetch scripts and
styles from `cdn.jsdelivr.net` and a favicon from `fastapi.tiangolo.com`. Third-party origins
are therefore introduced by this diff. See VULN-004/VULN-006.

### [VULN-015] Documented `.env` isolation control is inert
File: `backend/src/config/settings.py` lines 9-10, 21
Severity: low → INFO

The docstring instructs tests to construct `Settings(_env_file=None)` "to isolate themselves
from any real `.env` file", but `SettingsConfigDict(env_prefix="TRUELEND_", extra="ignore")`
sets no `env_file`, so pydantic-settings never reads one. The documented control does
nothing. No secrets are hardcoded anywhere in `settings.py` (verified), `.env` is correctly
gitignored, and no `.env` file exists in the repository.

Fix: either configure `env_file` and keep the docstring, or drop the misleading instruction.

### [VULN-016] Synthetic PAN/Aadhaar values in test fixtures
File: `backend/tests/unit/test_log_redaction.py` lines 24-26
Severity: low → INFO

`ABCDE1234F`, `234123412346`, `SALARY-DOC-BASE64-CONTENT-XYZ` are clearly synthetic and
test-only, and are not reused in any production config. Acceptable — logged only so the
majority vote can see it was considered.

### [VULN-017] Harness audit chain is unauditable after an envelope rotation (governance, not product)
File: `.claude/state/task-envelope.json` (uncommitted)
Severity: low → INFO

I verified the pack's claim rather than trusting it, and it holds — and understates the case.
`created_at`/`expires_at` moved forward ~9h (`2026-09-13T19:30:08Z` → `2026-09-14T04:37:07Z`),
`integrity.hash` was rebuilt (`4034d3db…` → `fb41b097…`), yet `previous_envelope_hash` is
still `null` and `amendments` is still `[]` — while **five** files exist under
`.claude/state/task-envelope-history/`, one named for the superseded hash `4034d3db…`. The
tamper-evidence chain on the control that bounds what an autonomous agent may write is
therefore broken, and moving `created_at` forward resets the "evidence created after the
envelope" window. I also confirmed `project-manifest.json` is **not** in the envelope's
`allowed_paths` yet was modified in the working tree.

This is a governance/process control, not an application vulnerability, so I am not blocking
on it from the security gate — but the code-review/evaluator gate should, and the
`canvas-sync` and `ownership-check` BLOCKs are downstream of it.

### [VULN-018] `project-manifest.json` working-tree edit is valid JSON and security-neutral
File: `project-manifest.json` (uncommitted)
Severity: low → INFO

Verified the pack's "CLEARED" finding independently: the file parses, `verification` has keys
`['e2e_targets','mode','docker','mode_note']` — exactly one `mode` — and the three file-wide
`"mode"` matches are in distinct objects. The `docker` → `local` switch plus `mode_note` has
no security impact. The envelope/frozen-path violation is VULN-017's governance concern.

---

## Refuted candidates (checked, no finding)

Recorded so the majority vote can see what I actively tried to prove and could not.

| Candidate | Verdict | Evidence |
|---|---|---|
| HTTP response-header injection / response splitting via `X-Request-ID` | **REFUTED** | h11 normalises or rejects before the app sees it. Raw-socket `X-Request-ID: abc\r\nX-Injected: 1` was parsed as two separate headers — the app received only `abc` and the response echoed only `x-request-id: abc`, with no `x-injected`. Bare `LF`, obs-fold continuation, `NUL`, and `\x1b`/`\x07` control bytes each returned `400 Bad Request — Invalid HTTP request received.` So uvicorn/h11 does the normalising for you; the middleware's lack of CRLF filtering is not independently exploitable. |
| Log injection / forged log lines via `X-Request-ID` | **REFUTED** on the JSON sink | `json.dumps` (default `ensure_ascii=True`) escapes quotes, braces and all control characters. A printable payload `x"} {"level":"CRITICAL","message":"forged","request_id":"y` was emitted as a single properly escaped JSON string value; control characters cannot reach the app at all (see above). Retained only as the escaping-bypass note in VULN-009. |
| ANSI escape-sequence injection into terminal log viewers | **REFUTED** | `\x1b` in a header value is rejected by h11 with `400`; `json.dumps` would escape it to `` regardless. |
| `UnicodeEncodeError`/500 from echoing a non-latin-1 request id | **REFUTED** | Starlette decodes request headers as latin-1 and re-encodes as latin-1, so bytes round-trip; verified `200 OK`. Downgraded to VULN-012. |
| Empty `X-Request-ID` producing an empty correlation id | **REFUTED** | `or uuid4().hex` treats `""` as falsy; verified live that `X-Request-ID: ` yields a generated hex id. |
| XSS in `MoneyText.tsx` | **REFUTED** | `<span>{value.format()}</span>` is JSX text interpolation, which React escapes. Grepped the changed frontend files for `dangerouslySetInnerHTML`, `innerHTML`, `outerHTML`, `eval`, `new Function`, `document.write`, `insertAdjacentHTML`, `srcdoc`, `javascript:` — none present. `format()` output derives from `Decimal.toFixed(2)` and can only contain digits, `.`, `,` and `-`. Downgraded to VULN-013. |
| Stack-trace/config leakage in error responses | **REFUTED** | `FastAPI` is built without `debug=True`, so `ServerErrorMiddleware` returns a generic 500 with no traceback. `_handle_app_error` emits only `{"error": message}`. Downgraded to VULN-011. |
| `/health` information disclosure | **REFUTED** | Returns exactly `{"status":"ok"}` — no version, config, dependency status or hostname. The real unauthenticated disclosure is `/openapi.json` (VULN-004). |
| Hardcoded secrets / insecure defaults in `settings.py` | **REFUTED** | Only `service_name` and `log_level`; both non-sensitive, both env-overridable via `TRUELEND_`. No credentials anywhere in the changed set. |
| Over-permissive CORS | **REFUTED** | No `CORSMiddleware` is registered at all; browser same-origin policy applies. Absence is the secure default here. |
| SQL / command / template injection, SSRF, path traversal, insecure deserialization | **REFUTED** | Grepped the changed backend modules for `subprocess`, `os.system`, `os.popen`, `exec(`, `eval(`, `pickle`, `yaml.load`, `create_engine`, `psycopg`, `asyncpg`, `sqlalchemy`, `open(`, `requests`, `httpx`, `urllib`, `socket` — no matches. No DB driver is even in `pyproject.toml`. `GET /health/../health` returns 404. |
| CSRF | **REFUTED** | The only route is `GET /health`; no state-changing endpoint and no cookie-based session exists. |
| Missing rate limiting as an independent finding | **FOLDED** | No throttling exists anywhere, but with no auth/OTP/password-reset endpoints its only material consequence is the amplifier in VULN-002, so it is not double-counted. |
| Redaction filter missed on loggers created after startup | **REFUTED** | `_install_redaction_filter_everywhere` only covers loggers existing at `configure_logging()` time, but the filter is also attached to the **root handler**, which `Logger.callHandlers` reaches for any later-created propagating logger. Only a later-created child of `uvicorn` would slip past — too speculative to report. |
| Nested containers / `extra=` fields defeating redaction | **REFUTED** | Nested dicts and lists are redacted, because `record.getMessage()` is `%`-formatted to a string before the substring replace — verified `payload={'applicant': {'pan': '[REDACTED]', 'docs': ['[REDACTED]']}}`. `extra=` fields never reach the JSON sink at all (VULN-010). The real gaps are VULN-001 and VULN-003. |
| `%`-format injection via a user-controlled message | **REFUTED** | `RedactionFilter` sets `record.args = ()`, so `getMessage()` skips `%` formatting entirely; a literal `%` in data cannot trigger a format error. |
| Pack claims: no authn/authz, no persistence, no migrations, no file uploads, no payment execution | **CONFIRMED TRUE** | No auth code or middleware; no DB driver or repository module; no `migrations/` directory; no upload or multipart handling; no payment code. The one inaccuracy is the outbound-network claim (VULN-014). |

---

## Verdict

**BLOCK** — 2 high-severity findings (VULN-001, VULN-002). Both are in the group A
production files under review, both have reproductions I executed against the delivered
code, and both have local fixes. The remaining 6 WARN and 10 INFO findings should not hold
the merge on their own.
