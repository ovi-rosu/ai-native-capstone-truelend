# Security Review (INSTANCE 2 of 3) — ai-native-capstone-truelend — 2026-09-14

Scope: committed range `14e9487..d0b5c94` plus the uncommitted working tree.
Production surface: the 13 changed backend/frontend source files named in
`specs/reviews/review-context-pack.md`, plus their immediate data-flow neighbors.
Blocking threshold: `["critical","high"]` (`sprint-contracts/A.json` has no
`security_checks.block_severities` override).

Runtime target was live on `http://127.0.0.1:8000` for this review; all runtime
claims below are from exploit attempts actually sent, not inferred.

## Summary

- BLOCK findings: 0
- WARN findings: 7
- INFO findings: 4
- **Overall verdict: PASS (with WARNs)**

No finding survived adversarial verification at critical/high severity. The
headline items the context pack flagged as likely BLOCKs (CRLF/header injection,
JSON log injection, stack-trace leakage) were **empirically refuted** — see
"Refuted BLOCK candidates". The most important real defect is a money-validation
gap (VULN-001) that is currently unreachable over HTTP but becomes high severity
the moment the first money-accepting endpoint lands.

## Pack claims — verified

The pack asserts "no authn/authz, no persistence, no migrations, no outbound
network calls, no file uploads, and no payment execution in this diff." I
verified this by scoped pattern search across the 13 changed source files.
**The claim is accurate.** No `eval`/`exec`/`pickle`/`yaml.load`, no
`subprocess`/`os.system`, no SQL/cursor/ORM execution, no `requests`/`httpx`/
`fetch` outbound call, no `open`/`Path`/`os.path.join` filesystem access, no
`UploadFile`/multipart, no `md5`/`sha1`/`random`, no JWT or auth dependency, and
no hardcoded credential. The only matches for `token` are `ContextVar` reset
tokens in `middleware.py` and `logging.py` — false positives.

Consequently there is no SQL injection, command injection, SSRF, path traversal,
insecure deserialization, IDOR, privilege escalation, or missing-auth finding to
make in this diff. `/health` is intentionally unauthenticated and discloses only
`{"status":"ok"}` — no config, version, or secret. `settings.py` carries only
`service_name` and `log_level`, both environment-sourced under the `TRUELEND_`
prefix with no hardcoded secret and no debug flag.

## Refuted BLOCK candidates (found, then disproved)

These were pursued as candidate BLOCKs and dropped on evidence. Recording them so
the majority vote can see the refutation rather than re-litigate it.

1. **HTTP response-header injection / response splitting via `X-Request-ID`** —
   REFUTED. `middleware.py:36` writes an attacker-controlled value into a
   response header with no filtering, but uvicorn's h11 parser rejects the
   payload before it ever reaches application code. Sent over a raw socket
   (bypassing curl's own client-side sanitization, which silently strips CRLF and
   makes the `curl -H $'...\r\n...'` test inconclusive):
   - bare `LF` in value -> `HTTP/1.1 400 Bad Request` ("Invalid HTTP request received.")
   - bare `CR` in value -> `400`
   - obs-fold continuation (`CRLF` + TAB) -> `400`
   - `ESC` (0x1b, ANSI escape) -> `400`
   - `DEL` (0x7f) -> `400`
   - `NUL` (0x00) -> `400`
   A true `CRLF` split is parsed as two separate header lines, so `X-Request-ID`
   receives only `abc` and the injected header is not reflected. **Starlette/
   uvicorn normalizes this for you**; no CRLF or ANSI sequence can reach the log
   sink or the response header. Bytes 0x80-0xFF and TAB *are* accepted and
   echoed (latin-1 round-trip, no crash).
2. **JSON log injection / forged `request_id` key** — REFUTED. A payload of
   `a","request_id":"spoofed` is accepted and reflected, but `JSONLogFormatter`
   serializes through `json.dumps`, which escapes it. The emitted line is a
   single valid JSON object with one `request_id` key:
   `..."message": "GET /health -> 200", "request_id": "a\",\"request_id\":\"spoofed"}`.
   High bytes are escaped as `ÿ`. No structural breakout, no forged field,
   no embedded newline.
3. **Stack-trace / internal-detail leakage on the unhandled-exception path** —
   REFUTED. Probed in-process against the real `app` object with a route that
   raises `ValueError` carrying a fake DSN. `app.debug` is `False`; the response
   body is exactly `Internal Server Error` (plain text, 500). No traceback, no
   exception type, no secret in the body. `JSONLogFormatter` also omits
   `exc_info`, so nothing leaks to the log sink either.
4. **PII redaction bypass via nested containers / `extra=` / exception args** —
   REFUTED as a *leak*. Nested dicts and lists ARE redacted, because
   `record.getMessage()` stringifies the container before substring replacement
   (`payload={'applicant': {'pan': '[REDACTED]'}}`). `extra=` fields and
   `exc_info` never appear in output at all (the formatter emits only a fixed
   five-key payload), so they cannot leak. The real redaction gaps are different
   and are recorded as VULN-002.
5. **CORS misconfiguration** — REFUTED. No `CORSMiddleware` is registered.
   `GET /health` with `Origin: https://evil.example` returns **no**
   `Access-Control-*` headers, so browsers block cross-origin reads. Secure
   default; no finding.
6. **`project-manifest.json` duplicate `mode` key** — REFUTED. `json.load`
   succeeds and `verification` has exactly one `mode` (`"local"`). Matches the
   pack's own re-entry addendum.

## BLOCK Findings

None.

## WARN Findings

### [VULN-001] Money wire validator accepts `NaN`, poisoning arithmetic and raising an uncaught exception on any ordering comparison
File: `backend/src/api/serializers.py` line 20-26 (`_validate_money`), with root cause in `backend/src/types/money.py` lines 53-66
Severity: medium (WARN)
Category: input validation / data integrity

`Money` guards against `float` and `bool` and catches `InvalidOperation`, but
`Decimal("NaN")` constructs successfully **and** `Decimal("NaN").quantize(...)`
returns `NaN` without signalling, so both guards pass. Verified end to end
through the designated wire boundary:

- `_validate_money("NaN")` -> accepted, `amount` is `NaN`
- `_serialize_money(...)` renders it back on the wire as the string `"NaN"`
- `add`/`multiply` silently propagate `NaN` (every downstream amount becomes NaN)
- **any ordering comparison raises `decimal.InvalidOperation`** — both
  `amount.__gt__(limit)` and `amount.__le__(limit)` raise
- equality silently returns `False`, so dedupe/idempotency checks on amounts break

Ordering comparisons on money are exactly what underwriting limit, eligibility,
and threshold rules are made of. `decimal.InvalidOperation` is not an `AppError`,
so it bypasses `register_exception_handlers` and surfaces as an unhandled 500.
Other lenient-parsing results from the same root cause (no format validation,
just `Decimal()` coercion): `"1_000"` -> `1000.00`, `"  12.34  "` -> `12.34`,
`"1e-999999999"` -> silently `0.00`. None of these is the "quoted 2dp string"
that decision D-G specifies.

Note the asymmetry: the frontend already rejects this. `frontend/src/types/money.ts`
line 31 has an explicit `!parsed.isFinite()` guard; the Python side has no
equivalent.

Why WARN and not BLOCK: no request model currently binds `MoneyField`, and there
is no POST/PUT endpoint in this diff, so `_validate_money` is not reachable from
an HTTP request today. I could not trace an attacker-controlled path to it.
**This should be re-rated high (BLOCK) at the first endpoint that accepts a money
amount from a client.**
Fix: in `Money._quantize` (or `__init__`), reject non-finite values before
quantizing — `if not decimal_amount.is_finite(): raise InvalidMoneyAmountError(...)`.
`amount.is_nan()` / `is_finite()` are available and were confirmed to return
`True`/`False` correctly here. Additionally, constrain the wire validator to the
D-G format with an anchored 2dp pattern rather than accepting anything `Decimal()`
will coerce.

### [VULN-002] PII redaction is opt-in and exact-substring, so it misses case and format variants; the module docstring overstates the control
File: `backend/src/config/logging.py` lines 42-54 (`RedactionFilter`), lines 31-39 (`redact_values`)
Severity: medium (WARN)
Category: sensitive data exposure

`RedactionFilter` only removes values a caller explicitly registered via
`redact_values(...)`, using a case-sensitive, literal `str.replace`. Demonstrated
misses with `redact_values("ABCDE1234F", "123456789012")` active:

- lowercase PAN -> logged as `pan=abcde1234f` (**unredacted**)
- Aadhaar with dashes -> logged as `aadhaar=1234-5678-9012` (**unredacted**)
- Aadhaar with spaces -> logged as `aadhaar=1234 5678 9012` (**unredacted**)
- anything logged **outside** a `redact_values()` scope -> fully unredacted
  (`pan=ABCDE1234F`, `authz=secret-token`)

The module docstring claims a `RedactionFilter` "drops PAN, Aadhaar and
salary-document content before a record is formatted." It does not: it drops only
exactly-matching registered strings. There is **no pattern/format-based fallback**
for PAN or Aadhaar despite the claim, and **no production code in this diff calls
`redact_values`**, so redaction is currently a no-op in the running app.

Why WARN and not BLOCK: the only log statement in the diff is
`middleware.py:37`, which logs method, path, and status code. No PII or secret
reaches a sink today, so the threat-model rule "NEVER log secrets, tokens,
passwords, or full PII at INFO level or above" is **not** violated on any
currently reachable path. This is a latent control weakness, not a live leak.
Fix: add normalization before matching (case-fold, strip separators) and a
regex-based fallback for the PAN/Aadhaar formats the docstring advertises;
prefer redacting by field name at the structured-logging call site over
opt-in value registration, which fails silently whenever a developer forgets it.
Correct the docstring to describe what the filter actually does.

### [VULN-003] Unbounded, unvalidated `X-Request-ID` enables correlation-id forgery and log-volume amplification
File: `backend/src/api/middleware.py` line 32 (accept) and line 36 (reflect)
Severity: medium (WARN)
Category: audit integrity / resource consumption

`request_id = request.headers.get("X-Request-ID") or uuid4().hex` applies no
length cap, no charset allow-list, and no format validation. Measured live:

| sent length | result |
|---|---|
| 1 000 bytes | 200, echoed in full |
| 8 000 bytes | 200, echoed in full |
| 16 000 bytes | 200, echoed in full |
| 60 000 bytes | 200, echoed in full |

The longest line now in `.claude/state/uvicorn.log` is 100 146 bytes, produced by
this reflection. Two consequences:

1. **Correlation-id forgery.** Any unauthenticated caller can set an arbitrary
   `request_id`, including one colliding with a real id, so audit lines
   attributable to one actor can be made to appear under another's correlation
   id. The field that the design treats as a trustworthy incident-forensics
   anchor is entirely client-controlled with no marker distinguishing
   caller-supplied from server-generated.
2. **Log amplification.** Each request writes its full id into the JSON access
   line, so an attacker controls log bytes written per request (~1x request
   size, unbounded per request). Disk/ingestion pressure, not a dramatic
   amplifier.

Whitespace-only ids are also accepted (only the empty string is falsy and
triggers generation). Injection vectors on this same input are refuted — see
"Refuted BLOCK candidates" items 1 and 2.
Fix: validate before binding and reflecting — cap length (e.g. 64-128 chars) and
restrict to an id charset (e.g. `^[A-Za-z0-9._-]{1,128}$`); on mismatch, generate
a fresh `uuid4().hex` rather than echoing. Consider logging both the
caller-supplied id and a server-generated id in separate fields so the trusted
anchor is never client-controlled.

### [VULN-004] Interactive API docs and OpenAPI schema exposed unauthenticated with no environment gating
File: `backend/src/api/app.py` line 23 (`FastAPI(title=settings.service_name)`)
Severity: medium (WARN)
Category: information disclosure / insecure default

`create_app` accepts FastAPI's defaults, so all three discovery endpoints are
publicly reachable. Verified live: `GET /docs` -> 200, `GET /redoc` -> 200,
`GET /openapi.json` -> 200 disclosing the machine-readable schema (service name
`truelend-backend`, path, operationId, response schema).

Present disclosure is negligible — only `/health` exists. The finding is the
**insecure default persisting into production**: as origination, disbursement,
and repayment endpoints land, this publishes the complete API surface, parameter
names, and response schemas of a loan-origination platform to any anonymous
caller, with no code change required to make it worse. `/docs` and `/redoc` also
serve HTML that loads scripts from a third-party CDN with no CSP (see VULN-008).
Fix: gate `docs_url`, `redoc_url`, and `openapi_url` on an explicit setting —
e.g. add an environment-driven `enable_docs: bool = False` to `Settings` and pass
`docs_url=None, redoc_url=None, openapi_url=None` when it is false.

### [VULN-005] `AppError.message` is returned verbatim to the client with a default 500 status and no internal/client-safe separation
File: `backend/src/api/errors.py` line 20; `backend/src/types/errors.py` lines 14-17
Severity: medium (WARN)
Category: information disclosure

The handler is a faithful pass-through: `JSONResponse(status_code=exc.status_code,
content={"error": exc.message})`. Confirmed by raising
`AppError("internal detail: connect to postgres://user:p4ssw0rd@db.internal failed", 500)`
— the client received that full string, credential included, in the response body.
`AppError.__init__` also defaults `status_code` to `500`, which nudges callers
toward using it for internal faults, precisely the case where the message is most
likely to carry a driver string, host name, or DSN.

Why WARN and not BLOCK: nothing in this diff raises `AppError`, there are no
subclasses, and no message is currently constructed from an internal exception.
There is no reachable exploit path today — this is a footgun being locked in at
the API boundary, and the cheapest moment to fix it is now, while there is one
consumer.
Fix: separate the client-safe message from internal detail — e.g. give `AppError`
a `public_message` (returned) and a `detail` (logged only), have the handler
return a generic message for any `status_code` of 500 or above, and drop the
permissive `500` default so callers must state intent.

### [VULN-006] Dev-toolchain dependencies carry one critical and one high advisory
File: `frontend/package.json` (newly added in this diff) lines 18-31
Severity: medium (WARN)
Category: dependency vulnerability

`npm audit` on the change set's manifest reports 5 advisories (1 critical, 1
high, 3 moderate). Installed: `vite@5.4.21`, `vitest@2.1.9`.

| Package | Severity | Advisory |
|---|---|---|
| vitest | critical | GHSA-5xrq-8626-4rwp — arbitrary file read/execute **when the Vitest UI server is listening** |
| vite | high | GHSA-fx2h-pf6j-xcff — `server.fs.deny` bypass on Windows alternate paths |
| vite | moderate | GHSA-v6wh-96g9-6wx3 — launch-editor NTLMv2 hash disclosure via UNC paths on Windows |
| vite | moderate | GHSA-4w7w-66w2-5vf9 — path traversal in optimized-deps `.map` handling |
| esbuild / @vitest/mocker / vite-node | moderate | dev-server request forgery; mocker redirect path traversal |

Why WARN and not BLOCK, despite a critical: all affected packages are
`devDependencies`. `vite` is a build tool and `vitest` a test runner — neither
ships in the production bundle, so none of this code is reachable in the
deployed application. The critical is conditioned on the Vitest **UI** server
listening, and the project's own script is `vitest run`, which never starts it.
The `vite` advisories require an attacker to reach a running `npm run dev`
server, which binds localhost. Both fixes are semver-**major**
(`vite@8.3.0`, `vitest@5.0.0`). Failing a merge gate on a major dev-tool bump for
a first-landing scaffold, with no production reachability, would be a
false-positive BLOCK. It is still real developer-machine exposure on Windows
(this is a Windows environment) and should be scheduled.
Fix: plan the major upgrades to `vite@8.x` and `vitest@5.x` as their own change
with the test suite as the check; until then never run `vitest --ui` or expose
the vite dev server beyond loopback.

### [VULN-007] Build-provenance audit chain is broken: envelope rotated without chaining, and a frozen path edited outside the envelope
File: `.claude/state/task-envelope.json` (uncommitted); `project-manifest.json` (uncommitted)
Severity: medium (WARN)
Category: audit integrity / change control

Independently verified against the working tree:

- `created_at` moved `2026-09-13T19:30:08.588Z` -> `2026-09-14T04:37:07.592Z`
  (~9h forward), `expires_at` likewise, and `integrity.hash` was rebuilt
  `4034d3db...` -> `fb41b097...`.
- `previous_envelope_hash` is still `null` and `amendments` is still `[]`, even
  though the superseded hash `4034d3db...` exists as a file under
  `.claude/state/task-envelope-history/` (5 history files present). The envelope
  was **rotated, not amended**, so the chain does not reference its predecessor
  and is unauditable.
- Moving `created_at` forward resets the "evidence must be created after the
  envelope" freshness window that `finalize-task-evidence.js` enforces.
- `project-manifest.json` was edited (`verification.mode` `docker` -> `local`,
  plus a `mode_note`) while **not** appearing in the envelope's 15
  `allowed_paths`. I confirmed the exclusion directly: a write attempt in this
  session was refused with "outside task truelend-build's allowed_paths". The
  pack also lists this file as frozen. The change itself is defensible (no
  `docker-compose.yml` until E15-S2, Docker Desktop absent) but was made without
  an amendment.

In a project whose governing constraint is that every line of production code is
agent-generated under supervision, the envelope is the control that proves scope
compliance. A rotation that drops the hash link removes the tamper-evidence that
the allow-list was not widened after the fact.
Why WARN and not BLOCK: this is process/provenance integrity, not an exploitable
application vulnerability, and the `canvas-sync` and `ownership-check` gates
already block on the same working-tree edits. I am not double-blocking.
Fix: record the rotation as an amendment — set `previous_envelope_hash` to
`4034d3db61bdff6b223fd631480932d03510d6d52a32870b4bf0c2ee702e05da`, append an
`amendments[]` entry covering the `project-manifest.json` scope expansion, and
preserve the original `created_at` so the evidence window is not reset.

## INFO Findings

### [VULN-008] No security response headers
File: `backend/src/api/app.py` line 23
Severity: low (INFO)
Responses carry only `date`, `server`, `content-length`, `content-type`, and
`x-request-id`. Missing `X-Content-Type-Options: nosniff`,
`Content-Security-Policy`, `X-Frame-Options`, and HSTS. Impact is low for a
JSON-only API, but `/docs` and `/redoc` serve HTML that loads Swagger UI/ReDoc
from a third-party CDN with no CSP, and the frontend will need CSP once it is
served. `server: uvicorn` also advertises the stack.
Fix: add a small middleware setting `nosniff`, a frame-ancestors/CSP policy, and
HSTS behind TLS; consider `server_header=False` in the uvicorn config.

### [VULN-009] Unhandled exceptions lose the correlation id entirely
File: `backend/src/api/middleware.py` lines 35-42
Severity: low (INFO)
Verified: on an unhandled exception the 500 response carries **no**
`X-Request-ID` header (`echoed id = None`) and **no** `truelend.access` log line
is emitted. The header assignment and the access log both sit after
`await call_next(...)`, so an exception skips them, and `finally` resets the
contextvar before Starlette's outer `ServerErrorMiddleware` handles it. Errors
are exactly when correlation matters most for forensics; the sprint contract's
"every request-scoped log line carries the same generated non-empty request_id"
therefore holds only on the success path. (The `AppError` path is fine — it is
converted to a response inside the middleware and does log and echo correctly.)
Fix: wrap `call_next` in `try/except`, emit the access line and set the header in
a `finally`/except path so 500s are correlated too.

### [VULN-010] Formatter discards `exc_info` and `extra`; redaction filter clears `record.args`
File: `backend/src/config/logging.py` lines 57-68, line 53
Severity: low (INFO)
Two coupled robustness issues, neither a leak:
(a) `JSONLogFormatter` emits a fixed five-key payload, so `exc_info` tracebacks
and all `extra=` fields are silently dropped — `logger.exception(...)` records
the message only. Good for leak prevention, bad for diagnosability, and it means
`extra=` appears to work while being discarded.
(b) `RedactionFilter.filter` sets `record.args = ()` after pre-formatting the
message. Uvicorn's `AccessFormatter` unpacks `record.args` into its
`%(client_addr)s`-style fields, so once any `redact_values()` scope is active,
uvicorn access records will fail to format. Currently dormant because no
production code calls `redact_values`.
Fix: include `exc_info` (redacted) and whitelisted `extra` keys in the payload;
redact by rewriting `record.args` in place rather than clearing it, or scope the
filter to the application's own handler only.

### [VULN-011] `log_level` is an unvalidated free-form string
File: `backend/src/config/settings.py` line 24
Severity: low (INFO)
`log_level: str = "INFO"` accepts any value from `TRUELEND_LOG_LEVEL` with no
allow-list. Setting `DEBUG` in production enables third-party DEBUG logging into
the same sink where redaction is opt-in. This is not hypothetical: the root
handler captures third-party loggers, and `httpx` was observed emitting
`HTTP Request: GET http://testserver/... "HTTP/1.1 500 ..."` — i.e. full request
URLs — into the JSON sink. Any future token or PII in a query string would be
logged verbatim.
Fix: constrain to a `Literal["DEBUG","INFO","WARNING","ERROR","CRITICAL"]` and
refuse `DEBUG` when the environment is production; prefer keeping third-party
loggers at `WARNING` regardless of the app's own level.

## Notes for the majority vote

- I found **zero** critical/high findings. My verdict is **PASS**.
- If another instance reports the `X-Request-ID` reflection as a BLOCK for
  CRLF/header injection or ANSI log injection, note the raw-socket evidence in
  "Refuted BLOCK candidates" item 1: uvicorn/h11 returns `400 Bad Request` for
  bare CR, bare LF, obs-fold, `ESC`, `DEL`, and `NUL`. A `curl -H $'...\r\n...'`
  test cannot establish this either way, because curl strips CRLF client-side.
- If another instance reports the `npm audit` critical as a BLOCK, note that
  `vite`/`vitest` are `devDependencies` absent from the production bundle, the
  critical requires `vitest --ui` (never invoked by this project's scripts), and
  both fixes are semver-major.
- The one finding I would most want fixed before more code lands is **VULN-001**
  (`NaN` accepted by the money wire validator) — cheap to fix now, and it turns
  into a remotely-triggerable 500 plus a financial-integrity bug at the first
  money-accepting endpoint.
