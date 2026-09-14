# Security Review (instance 3 of 3) — TrueLend story group A — 2026-09-14

Range reviewed: `14e9487..f4abd41` (`backend`, `frontend`). Judged independently at
HEAD; no prior-round verdict was read.

## Summary

- BLOCK findings: **0**
- WARN findings: **10**
- INFO findings: **9**
- Overall verdict: **WARN** (gate result **PASS** — no critical/high finding)

The three fix commits hold up on their merits. The 500 path was driven live and
in-process: it returns a plain `Internal Server Error` body with no stack trace
and no exception message, while still echoing `X-Request-ID` (CR-003 verified).
`Money` rejects `NaN`/`sNaN`/`Infinity` and fails closed on overflow (CR-001
verified). Log/JSON injection through the caller-supplied correlation id is
genuinely blocked, and HTTP response splitting through it is rejected at the
parser — both refuted with live probes rather than assumed.

What is left is a set of *latent* weaknesses rather than live exploits: the PII
redaction control is opt-in and provably escapable on the exception path, the new
error `context` mapping is an unfiltered outbound channel, the correlation id is
unbounded and unvalidated, and the single money wire parser accepts far more than
the frozen format. None of them has an attacker-reachable path at HEAD because
group A exposes exactly one route (`GET /health`) and no endpoint yet accepts
applicant data — which is precisely why each is a WARN and not a BLOCK. Several
become BLOCK-class the moment the first PII-accepting endpoint lands; they are
written so the generator can close them now, while the surface is one file wide.

### Method

Read the context pack, the range diff, and all 24 changed files. Verification was
empirical where it could be: a real uvicorn instance on port 8032 driven with
raw-socket requests carrying hostile header values, 60-way concurrent
correlation-id probes, in-process probes of the redaction filter and the error
handler, `npm audit` on the changed manifest, and timing measurements of the
decimal paths on both sides of the wire. Scratch artifacts were removed; no
production source, `specs/design/**` or `sprint-contracts/**` file was edited.

### Verified NOT vulnerable (recorded so the next round does not re-litigate)

- **CR/LF response splitting and ANSI / control-character injection via
  `X-Request-ID`** — refuted. Values containing `\r\n`, a bare `\n`, an obs-fold
  continuation, `\x1b[31m`, `\x00`, `\x07` or `\x0b` are all rejected by the HTTP
  parser before the app ever sees them (httptools 0.8.0 → `400 Invalid HTTP
  request received`). The h11 0.16 fallback validates field values equally
  strictly, so the mitigation survives losing `uvicorn[standard]`. Tab and
  latin-1 high bytes are accepted and echoed, but both are legal header octets.
- **Log / JSON-line injection via `X-Request-ID`** — refuted. `JSONLogFormatter`
  renders through `json.dumps` with the default `ensure_ascii`, so control and
  non-ASCII characters are escaped; the live log shows `"a\tb"` and
  `"caféÿþ"` as escaped scalars inside a well-formed JSON line.
  An attacker cannot forge a second log record or break the JSON envelope.
- **Cross-request correlation-id bleed** — refuted. 60 concurrent requests with
  distinct ids: every response echoed its own id and every id appears in exactly
  one access line. The contextvar is per-task and reset in a `finally`.
- **The 500 path** — no information disclosure. Body is `Internal Server Error`
  (`text/plain`, 21 bytes); an exception message deliberately seeded with a
  fake credential and an absolute path reached neither the body nor the headers.
- **Query-string PII in access logs** — refuted. `uvicorn.access` is disabled
  (not reformatted, contrary to the pack's description) and the middleware logs
  `scope["path"]` only. A request carrying a synthetic PAN and Aadhaar in the
  query string produced zero occurrences of either value in the log stream.
- **Redaction and nesting depth** — refuted. The scrub runs on the *rendered*
  message, so arbitrarily nested dicts, lists, tuples and sets are covered. There
  is no walk depth to exceed. `extra=` fields cannot leak because the formatter
  never emits them at all.
- **`Money` numeric integrity** — no wrong value, no overflow, no DoS. Non-finite
  input is rejected; magnitudes that cannot be quantized fail closed with a typed
  error instead of truncating; a 1,000,000-digit input is rejected in 8 ms
  (linear); `ROUND_HALF_UP` is applied consistently and matches the frontend on
  negative ties; the wire form is always plain 2dp and never E-notation.
- **Frontend XSS** — none. No raw-HTML injection prop, no `innerHTML`, no `eval`,
  no `document.write`. `MoneyText` renders a formatted string as a text child of
  a `<span>`, which React escapes.
- **Secrets** — none hardcoded anywhere in the diff, no `.env` committed, and
  `Settings` does not configure `env_file` at all, so no dotenv is read.
- **Injection sinks** — there is no SQL, shell, template, LDAP or
  deserialization sink in this diff to inject into.

## BLOCK Findings

None.

## WARN Findings

### [I3-VULN-001] Correlation id is accepted unbounded, and every log line carries it in full
File: `backend/src/api/middleware.py` lines 50-51 (also 58, 61)
Severity: medium (WARN) · Category: resource exhaustion (CWE-770)

The inbound header is taken verbatim with no length cap and no charset
validation, then echoed into the response header and into the `request_id` field
of every log line for that request. Measured against the live server: a ~1 MB
`X-Request-ID` was accepted and produced a single 1,048,722-byte JSON log line
plus a 1 MB response header echo, from one small request. Amplification scales
with the number of log lines a request emits, so it grows as later stories add
logging, and the 500 path already emits more than one line. There is no rate
limiting anywhere in the app to damp it. A reverse proxy would normally cap
header size, but nothing in this repo deploys one yet (no compose file until
group B), and the app should not depend on that.

Fix: cap the accepted value (64-128 characters is ample for a trace id), restrict
it to a safe charset such as `[A-Za-z0-9._:-]`, and fall back to the generated
`uuid4().hex` when the inbound value fails either check. Add a test that a
1 MB header yields a generated id and a bounded log line.

### [I3-VULN-002] Caller-supplied correlation id is trusted verbatim and is indistinguishable from a generated one
File: `backend/src/api/middleware.py` lines 50-51
Severity: medium (WARN) · Category: audit-trail integrity (CWE-117 adjacent)

Any caller can choose the correlation id for its own request. Verified live: a
32-hex-character value supplied by the client is echoed and logged exactly as a
server-generated `uuid4().hex` would be, with nothing in the log payload marking
it as caller-supplied. An attacker can therefore (a) stamp their requests with an
id they know is already in use so that a later investigation cannot separate the
two actors, or (b) flood the logs with ids shaped exactly like legitimate
generated ones. For a loan-origination platform whose log stream is the
diagnostic and audit substrate (NFR-03 / NFR-06), that is a real integrity
weakness, even though it exposes no data. There is no cross-request contamination
— that was tested and refuted — so the impact is confined to log attribution.

Fix: always generate the server-side id and keep the inbound value in a separate
field (`client_request_id`), or validate the inbound shape and record a boolean
in the log payload marking ids that came from the caller. `E15-S1-AC3` requires
echoing the inbound value, so a separate field preserves the AC while removing
the ambiguity.

### [I3-VULN-003] PII redaction is scope-bound and is bypassed by the exception path
File: `backend/src/config/logging.py` lines 34-42 and 80-97
Severity: medium (WARN) · Category: sensitive data exposure (CWE-532)

`RedactionFilter` only scrubs values a caller has registered through
`redact_values(...)`, and only while that context manager is still on the stack.
The scope unwinds *during* exception propagation, so anything logged by an outer
layer after an exception escapes sees an empty sensitive-value set. Verified
in-process by reproducing exactly what uvicorn does for an unhandled exception
(log the traceback after the ASGI stack unwinds): an exception whose message
carried a synthetic PAN, raised inside a `redact_values` scope, was emitted at
ERROR level with the PAN present in the rendered traceback. The correlation id is
likewise empty on that line, so the one record containing the stack trace is both
unredacted and uncorrelated.

Compounding this, there is no production call site for `redact_values` anywhere
in the tree, so the control is entirely opt-in and `E15-S1-AC1` passes only
because its own test registers the values it then asserts absent — the suite's
own docstring at `backend/tests/unit/test_log_redaction.py:251` concedes this and
adds a grep-based guard for the future. The guard checks that a module mentioning
a PII field name also mentions `redact_values`; it cannot check that the scope
actually wraps the code that logs, and it does not cover the exception path at
all.

Not a BLOCK at HEAD only because group A exposes one route (`GET /health`) and no
code path yet carries applicant data, so there is no attacker-reachable leak to
demonstrate. This becomes a data-exposure BLOCK the moment `POST /applications`
lands.

Fix: add format-based redaction that does not depend on a caller's scope — a
small set of patterns for PAN, Aadhaar and account-number shapes applied in
`RedactionFilter` as defense in depth — and/or register the request's sensitive
values once in `CorrelationIdMiddleware` so the scope spans the whole request
including the unwind. Add a test that a PII-bearing exception escaping a handler
reaches the sink redacted.

### [I3-VULN-004] Redaction misses transformed representations of a registered value
File: `backend/src/config/logging.py` lines 45-68
Severity: medium (WARN) · Category: sensitive data exposure (CWE-532)

Matching tolerates only whitespace and hyphens between characters. Verified by
probe against a registered PAN / Aadhaar: the same value written with dots,
underscores or slashes between characters, URL-encoded, or base64-encoded passes
through unredacted. Base64 matters concretely here — the story names
"salary-document content" as a redaction target, and a document body is the one
value most likely to be logged in an encoded form different from the one
registered. Separately, any registered value shorter than 6 characters is
silently never redacted (a deliberate trade-off, documented at line 63, but it
fails silently: `redact_values("12345")` reports nothing and redacts nothing).

Fix: normalize the haystack (strip all non-alphanumerics, casefold) and match the
normalized needle against it, mapping matches back to the original span; or at
minimum extend the tolerated separator class. Emit a warning — or raise — when a
registered value is too short to be redactable, so the silent failure becomes
visible.

### [I3-VULN-005] The error `context` mapping is an unfiltered outbound channel
File: `backend/src/api/errors.py` lines 25-31; `backend/src/types/errors.py` lines 23-32
Severity: medium (WARN) · Category: information disclosure (CWE-209)

`AppError.context` is typed `Mapping[str, object]` and is copied verbatim into the
response body. There is no allowlist, no key or type restriction, and no
redaction — `RedactionFilter` covers the *log* sink only, so a value that would
be scrubbed from logs still ships to the client through `context`. Verified by
raising an `AppError` whose context carried SQL text, an absolute source path and
a nested config mapping: all three arrived intact in the JSON body.

No production subclass populates `context` today, so nothing internal actually
leaks at HEAD — that is why this is a WARN. But the frozen contract invites
population (`E4-S4-AC2` requires `threshold_kind` and `configured_value` there),
and the natural implementation is to pass whatever the service layer has to hand.
The `detail` field carries the same exposure for free-form messages: an
`AppError` constructed from `str(some_internal_exception)` would publish it.

Fix: give each `AppError` subclass a declared, typed context (a `TypedDict` or
pydantic model per subclass) restricted to primitive values, and build the
response from that declaration rather than from an open mapping. Add a test that
asserts the envelope cannot carry filesystem paths, SQL fragments or unexpected
keys.

### [I3-VULN-006] A non-JSON-serializable `context` value converts the intended error into a 500
File: `backend/src/api/errors.py` lines 25-31
Severity: medium (WARN) · Category: improper error handling / availability

`JSONResponse` serializes `context` with no coercion. Verified: an `AppError`
raised with `status_code=422` and a `Decimal` in `context` produced a plain-text
`500 Internal Server Error` instead — the `TypeError` escapes the handler and is
caught by `ServerErrorMiddleware`. The intended status code, error name and
detail are all lost, and the client gets a response outside the frozen envelope.
This is a likely first-contact failure, because `configured_value` in the
contract is a money threshold and the money type on this codebase is `Decimal`;
the existing test passes only because it uses the string `"25000.00"`.

Fix: coerce context values to JSON primitives (or validate them) in
`AppError.__init__` or in the handler, and test the handler with a `Decimal` and
a `Money` in `context`.

### [I3-VULN-007] Interactive API docs and the OpenAPI schema are enabled unconditionally and unauthenticated
File: `backend/src/api/app.py` line 36
Severity: medium (WARN) · Category: insecure default / information disclosure

Verified live: `/docs`, `/redoc` and `/openapi.json` all return 200 with no
authentication. Today the schema discloses only `/health` and the service name,
so present-day disclosure is trivial — but the factory has no environment switch,
so the complete API surface (paths, parameters, schemas, error shapes) becomes
publicly readable the moment group B adds business routes. The Swagger page is
also HTML that loads scripts and CSS from `cdn.jsdelivr.net`, adding a
third-party script dependency to an otherwise pure JSON service.

Fix: pass `docs_url=None, redoc_url=None, openapi_url=None` unless an explicit
setting (e.g. `TRUELEND_ENABLE_DOCS`, default off) turns them on, and add a test
that the three paths return 404 with the default settings.

### [I3-VULN-008] The single money wire parser accepts far more than the frozen format, with no magnitude bound
File: `backend/src/api/serializers.py` lines 20-26; `backend/src/types/money.py` lines 59-69; `frontend/src/types/money.ts` lines 24-35
Severity: medium (WARN) · Category: input validation / financial integrity

Decision D-G fixes the wire form as a quoted 2-decimal-place string, but neither
side enforces it — both hand the string straight to a decimal constructor.
Verified: the backend field accepts leading/trailing whitespace, Python-style
underscore digit separators, scientific notation and a leading `+`, and accepts
26 integer digits, which the `NUMERIC(14,2)` column D-G specifies cannot store
(so such a value validates at the API boundary and fails later at the database).
The two sides also disagree on validity: whitespace-padded input is accepted by
the backend and rejected by the frontend, while a 101-digit magnitude is accepted
by the frontend and rejected by the backend. A parser differential on the one
value that must mean the same thing on both sides of the wire is exactly the
coupling risk D-G was written to avoid.

Fix: enforce a strict pattern (`^-?\d{1,12}(\.\d{1,2})?$`, matching
`NUMERIC(14,2)`) in `_validate_money` and in `toQuantizedDecimal` before
constructing the decimal, and add matching negative tests on both sides.

### [I3-VULN-009] Quadratic grouping regex in `Money.format()` is a main-thread DoS on a long amount
File: `frontend/src/types/money.ts` lines 74-80; `frontend/src/ui/components/MoneyText.tsx` lines 13-16
Severity: medium (WARN) · Category: DoS (CWE-1333)

The thousands-separator regex uses a repeated group inside a lookahead evaluated
at every position, which is quadratic in the digit count. Measured in node:
10,000 digits 37 ms, 50,000 digits 1.01 s, 200,000 digits 18.7 s of synchronous
main-thread work. `Money.fromWire` accepts a 100,000-digit string in 3.4 ms
without complaint, and `MoneyTextProps.money` is declared as `Money | string`, so
the component will parse and format an unvalidated string. The only producer of
money strings today is the backend, which rejects anything over 28 digits, and
`MoneyText` is not yet rendered by any page — hence WARN, not BLOCK. It becomes
reachable as soon as a money string originates from, or is echoed back from, user
input.

Fix: bound the integer-digit count at parse time (see I3-VULN-008), and replace
the grouping regex with a linear loop or `Intl.NumberFormat`.

### [I3-VULN-010] Vulnerable dev dependencies in the changed manifest (advisory critical/high, refuted to medium in this context)
File: `frontend/package.json` lines 20-33
Severity: medium (WARN) · Category: dependency vulnerabilities

`package.json` is in the change set, so `npm audit` was run: 5 advisories — 1
critical, 1 high, 3 moderate.

- `vitest` (`^2.0.5`, vulnerable `<=4.1.10`) — **critical** advisory
  GHSA-5xrq-8626-4rwp: arbitrary file read and execution while the Vitest UI
  server is listening; plus GHSA-82fw-gwwq-j7x9 (mocker path traversal).
- `vite` (`^5.4.3`, vulnerable `<=6.4.2`) — **high**: GHSA-4w7w-66w2-5vf9 (path
  traversal in optimized-deps `.map` handling), GHSA-v6wh-96g9-6wx3 (launch-editor
  NTLMv2 hash disclosure via UNC path handling on Windows), GHSA-fx2h-pf6j-xcff
  (`server.fs.deny` bypass on Windows alternate paths).
- Moderate: `esbuild` (any website can drive the dev server and read responses),
  `@vitest/mocker`, `vite-node`.

Refutation applied before assigning severity: all five are devDependencies; the
frontend ships no build artifact in this group and is not deployed; the test
script is `vitest run`, which never starts the UI or API server the critical
advisory requires; `vite.config.ts` sets no `server.host`, so the dev server binds
localhost. None is reachable from the running application, so I did not raise
this to BLOCK. The residual risk is real but local: anyone running `npm run dev`
on this Windows workstation is exposed to the high-severity dev-server vectors,
including an NTLM hash disclosure.

Fix: bump `vite` and `vitest` out of the vulnerable ranges (npm reports the
available fixes as `vite@8.3.0` and `vitest@5.0.0`, both semver-major), or pin
patched versions, then re-audit. Backend dependencies were checked and are clean
at the installed versions (fastapi 0.141.1, starlette 1.6.0, uvicorn 0.52.4,
pydantic 2.13.5, h11 0.16.0).

## INFO Findings

### [I3-VULN-011] No hardening response headers; server product disclosed
File: `backend/src/api/app.py` lines 31-39 · Severity: low
No `X-Content-Type-Options`, `X-Frame-Options`/CSP `frame-ancestors`,
`Referrer-Policy` or HSTS on any response, and `server: uvicorn` is advertised.
Mostly moot for a JSON API with no cookies or browser auth yet, but `/docs`
returns HTML with no CSP while loading third-party scripts. Fix: add a small
header middleware (and suppress the server header) when the UI surface lands.

### [I3-VULN-012] Registered PII values persist in a process-global cache
File: `backend/src/config/logging.py` lines 49-58 · Severity: low
`_redaction_pattern` is an `lru_cache(maxsize=256)` keyed on the sensitive value,
so up to 256 PAN/Aadhaar/document values stay resident (as cache keys and inside
compiled patterns) long after their redaction scope ends, and would appear in a
heap dump or core file. Fix: key the cache on a hash, or cache nothing and accept
the compile cost, or clear the cache when the scope exits.

### [I3-VULN-013] `extra=` fields are silently discarded by the formatter
File: `backend/src/config/logging.py` lines 103-118 · Severity: low
The JSON payload is a fixed five-key shape, so `logger.info(..., extra={...})`
is dropped. Leak-safe today, but a developer who believes `extra` is recorded may
put PII there and reason about it incorrectly, and structured context cannot be
logged at all. Fix: either merge an allowlisted set of extras through the same
scrub, or document the omission.

### [I3-VULN-014] The stack-trace line for a 500 carries an empty `request_id`
File: `backend/src/config/logging.py` lines 100-118; `backend/src/api/middleware.py` lines 54-67 · Severity: low
The contextvar is reset before uvicorn logs the unhandled exception, so the one
line containing the traceback is uncorrelated (`request_id: ""`), as observed in
the live log. The middleware's own access line does carry the id and the real
status, so `E15-S1-AC4` holds — this is an operator-experience gap, not an AC
failure. Fix: log the exception inside the middleware scope, or have uvicorn's
handler read the id from the scope.

### [I3-VULN-015] The public error code is a Python class name
File: `backend/src/types/errors.py` lines 34-37 · Severity: low
`error` is `type(self).__name__`, so an internal class rename silently changes the
wire contract, and any class named after an internal component publishes that
name. The frozen contract does require an error *name*, so this is not a leak in
itself. Fix: declare an explicit `error_code` class attribute per subclass and
assert the set of codes in a test.

### [I3-VULN-016] No secret-handling convention in `Settings`
File: `backend/src/config/settings.py` lines 18-24 · Severity: low
Nothing hardcoded today and no dotenv is read, but the docstring says DB URL and
JWT settings land in this same class later, and nothing would stop a future
`logger.info("%s", settings)` from dumping them (model repr prints all fields).
Fix: adopt `pydantic.SecretStr` for every credential field and add a test
asserting `repr(Settings())` contains no secret value.

### [I3-VULN-017] `TRUELEND_LOG_LEVEL` is unvalidated
File: `backend/src/config/settings.py` line 24; `backend/src/config/logging.py` line 130 · Severity: low
An invalid value fails startup (acceptable, fail-fast); `DEBUG` in production
widens log content while redaction is still opt-in. Fix: constrain the field to
the standard level names via a `Literal`.

### [I3-VULN-018] Sub-cent amounts are silently accepted as zero
File: `backend/src/types/money.py` lines 59-69 · Severity: low
`1e-400` and `0.004` are accepted and quantize to `0.00`. Correct 2dp rounding,
but a future minimum-amount or non-zero check must run *after* quantization or it
will pass a value that is later stored as zero. Fix: reject inputs with non-zero
digits below the second decimal place, or document the rounding contract at the
API boundary.

### [I3-VULN-019] Frontend decimal context relies on a mutable library default
File: `frontend/src/types/money.ts` lines 15, 24-35 · Severity: low
Rounding is passed explicitly at every call site (good), but `Decimal.precision`
is never set, so the module inherits decimal.js's default 20 significant digits —
and `Decimal.set()` is process-global, so any other module sharing the instance
can change money arithmetic app-wide. Results at 2dp are unaffected for
`NUMERIC(14,2)` magnitudes, so this is hardening only. Fix: create a configured
`Decimal` clone for this module.
