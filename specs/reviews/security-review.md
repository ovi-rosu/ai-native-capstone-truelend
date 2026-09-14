# Security Review — ai-native-capstone-truelend (Group A) — 2026-09-14

Reviewer: `security-reviewer` instance 1 of 3 (canonical outputs)
Range: `14e9487..d0b5c94` plus the uncommitted working tree
Branch: `feat/harness-scaffold-and-planning`
Stories: E15-S1 (logging/correlation/health), E9-S1 (Money), E11-S1 (delinquency ladder)
Runtime target: `http://127.0.0.1:8000`, live throughout this review
Machine-readable verdict: `specs/reviews/security-verdict.json`

## Summary

- BLOCK findings: **1**
- WARN findings: **7**
- INFO findings: **6**
- Overall verdict: **BLOCK**

One finding is exploitable today against the live service and is proven with a
reproduction. Everything else is either a latent weakness that becomes dangerous
when the next story lands, or a configuration default that should be corrected
before the API surface grows.

Nine additional candidate vulnerabilities — including three of the four vectors the
task brief flagged as highest priority — were **refuted with evidence** and are
recorded in the "Refuted candidates" section rather than reported as findings. In
particular, the CRLF header-injection string suggested in the brief does not
inject, and the caller-supplied correlation id cannot forge a log entry.

## Scope and verification of the pack's claims

Production files read in full: the 13 backend/frontend source files listed in the
context pack, plus `frontend/package.json` and `frontend/vite.config.ts`. No files
outside the change set and its immediate data-flow neighbours were searched.

The pack asserts there is no authn/authz, no persistence, no migrations, no
outbound network, no uploads and no payment execution. **All six claims are
accurate.** A grep across `backend/src/` for `httpx`, `requests.`, `sqlalchemy`,
`psycopg`, `alembic`, `UploadFile`, `Depends`, `subprocess`, `os.system`, `eval(`,
`exec(`, `pickle` and `yaml.load` returns nothing; `httpx` appears only in the dev
dependency-group. The only route is `GET /health`, which accepts no input.

Consequently the entire OWASP injection family (SQL, command, LDAP/XPath/NoSQL),
path traversal, SSRF, insecure deserialization, CSRF, open redirect, IDOR, auth
bypass and privilege escalation are **not applicable** to this diff — there is no
code of that shape to be vulnerable.

---

## BLOCK Findings

### [VULN-001] Unbounded caller-controlled `X-Request-ID` reflected into the response and written 1:1 to disk

- **File:** `backend/src/api/middleware.py` line 32 (echo at line 36; log write at `backend/src/config/logging.py` line 66)
- **Severity:** high → **BLOCK**
- **CWE:** CWE-770 (allocation of resources without limits), with CWE-400
- **Matrix IDs:** VM-003, VM-004

**Description.** `dispatch` takes the inbound header with
`request.headers.get("X-Request-ID") or uuid4().hex` and applies no length cap, no
charset allow-list and no validation of any kind. That untrusted value is then used
twice: echoed verbatim into the `X-Request-ID` response header, and written verbatim
into the `request_id` field of every structured log line emitted for the request.

A correlation id has a natural bound of a few dozen characters (the generated one is
a 32-character hex UUID). Accepting an 8 MB value and persisting it is a remote,
unauthenticated resource-exhaustion primitive. `GET /health` requires no
authentication and has no rate limit, and there is no reverse proxy, ingress, or
header-size cap anywhere in the reviewed stack — `project-manifest.json#verification.mode`
is `local` and there is no `docker-compose.yml` until E15-S2 — so **no compensating
control exists in the system under review.**

**Reproduction (run against the live server).**

Single oversized request — accepted, echoed in full:

```
python - <<'PY'
import socket
head = (b"GET /health HTTP/1.1\r\nHost: 127.0.0.1\r\nX-Request-ID: "
        + b"D"*8388608 + b"\r\nConnection: close\r\n\r\n")
s = socket.create_connection(("127.0.0.1", 8000), timeout=15)
s.sendall(head)
buf = b""
while True:
    c = s.recv(262144)
    if not c: break
    buf += c
print(buf.split(b"\r\n")[0], len(buf))
PY
```

Observed: `b'HTTP/1.1 200 OK' 8388783` — an 8 MB header value accepted, 200 OK, and
the full 8 MB echoed back in the response header. Values of 8 KB, 15 KB, 64 KB,
256 KB, 1 MB, 4 MB and 8 MB were all accepted (`full_echo=True` in every case).

Sustained disk-fill rate — 20 sequential 1 MB requests:

```
LOGBYTES_BEFORE=15770862
20 sequential requests of 1.0 MB header in 1.28s
  sent   ~20.0 MB  (15.6 MB/s)
  echoed ~20.0 MB back in response headers
LOGBYTES_AFTER=36746522
```

**+20.98 MB written to `.claude/state/uvicorn.log` in 1.28 seconds from a single
client** — about 15.6 MB/s, or roughly 1.3 GB per minute, with amplification
slightly above 1:1 because the JSON line carries the value plus envelope overhead.
Every additional request-scoped log line added by a future story multiplies that
factor. A single attacker exhausts the log volume in minutes and takes the service
down; on a loan-origination platform that is an availability incident with
regulatory reporting consequences.

**Adversarial refutation attempted and failed.** I looked for any mitigation between
source and sink: there is no validation in `dispatch`, no `max_header_size` setting
on the uvicorn invocation, no proxy in the repo, and `httptools` itself accepted
8 MB in a single header field without complaint. The exploit path is source
(unauthenticated request header) → sink (response header + persistent log file) with
nothing in between. The finding survives.

**Fix.** Validate before binding, and regenerate rather than truncate so the caller
cannot control the stored value:

```python
_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

inbound = request.headers.get(_REQUEST_ID_HEADER, "")
request_id = inbound if _ID_RE.match(inbound) else uuid4().hex
```

Truncating and using the prefix is not sufficient — it still lets a caller pin the
id to a value of their choosing. Add a request-rate limit on public routes as
defence in depth (see VULN-012).

---

## WARN Findings

### [VULN-002] `RedactionFilter` does not scrub exception tracebacks, and the live plain-text sink renders them

- **File:** `backend/src/config/logging.py` line 45
- **Severity:** medium → WARN · **CWE-532**

`RedactionFilter.filter` operates only on `record.getMessage()`. It never touches
`record.exc_info` or `record.exc_text`. PII carried in an exception message
therefore bypasses redaction entirely.

This matters because the JSON formatter is not the only sink. `JSONLogFormatter.format`
silently drops `exc_info`, so tracebacks never appear there — but uvicorn's own
`uvicorn.error` logger keeps its own handler and its own plain-text formatter, which
does render tracebacks. That sink is live in this exact deployment: the server log
currently holds **184 plain-text uvicorn lines alongside 124 JSON lines.**

**Reproduction** (in-process, against the real module):

```python
with redact_values("ABCDE1234F"):
    try:
        raise ValueError("KYC failed for PAN ABCDE1234F")
    except ValueError:
        uvicorn_error_logger.exception("unhandled error")
```

Output, with a `RedactionFilter` attached to *both* the logger and the handler:

```
ERROR: unhandled error
Traceback (most recent call last):
  ...
ValueError: KYC failed for PAN ABCDE1234F
>>> PAN PRESENT IN PLAIN SINK: True
```

**Why WARN and not BLOCK.** No borrower PII exists in the system yet — the only
route is `GET /health`, and nothing constructs an exception around applicant data.
There is no attacker-reachable path to a PII leak today, so per the gate's own
standard this is a control gap rather than an exploitable vulnerability. It will
become high the moment the origination endpoint lands.

**Fix.** Render the traceback in the filter (`Formatter.formatException` or
`traceback.format_exception`), apply the same replacement, write the scrubbed text
back to `record.exc_text` and clear `record.exc_info`. Add a regression test that
asserts a PII-bearing exception is redacted through a non-JSON formatter.

### [VULN-003] The `request_id` log field is structurally unredactable

- **File:** `backend/src/config/logging.py` line 66
- **Severity:** medium → WARN · **CWE-532**

`JSONLogFormatter.format` reads `request_id_var` and writes it into the payload.
Formatters run *after* filters, so nothing placed in that field can ever be
redacted — the filter has already finished by the time the value is introduced.

**Reproduction:** set the contextvar to a PAN, enter `redact_values(PAN)`, log a
line. Result:

```
{"timestamp": "...", "level": "INFO", "logger": "truelend.origination",
 "message": "serving", "request_id": "ABCDE1234F"}
>>> PAN PRESENT IN request_id FIELD: True
```

The field is caller-supplied (VULN-001), so any client that embeds a customer
identifier in its correlation id — a common anti-pattern — writes unredactable PII
into the log.

**Fix.** Inject `request_id` onto the record inside the filter so the filter scrubs
it, or apply the replacement inside `format` before `json.dumps`. The VULN-001
allow-list also mitigates this: an id constrained to `[A-Za-z0-9_-]{1,64}` cannot
carry structured PII.

### [VULN-004] PII redaction is inert by default, has no deny-list, and is case-sensitive

- **File:** `backend/src/config/logging.py` line 32
- **Severity:** medium → WARN · **CWE-311**

Three compounding weaknesses in the same control:

1. **No production caller.** `grep -rn redact_values backend/src/` returns only the
   definition itself. The sole caller in the repo is
   `backend/tests/unit/test_log_redaction.py`. The control is exercised only by its
   own test.
2. **No default deny-list.** Redaction is entirely opt-in per request scope. There
   is no key-name matching and no format-based matching, so nothing is redacted
   unless business code remembers to wrap itself.
3. **Case-sensitive exact substring match.** `message.replace(value, ...)` misses
   any casing variant. With `redact_values("ABCDE1234F")` active, logging
   `abcde1234f` emits it **unredacted** (verified).

The module docstring claims the filter "drops PAN, Aadhaar and salary-document
content before a record is formatted." It does not — it drops whatever strings a
caller has registered, in the exact case registered. That overstatement is itself a
risk, because the next story author will reasonably trust it.

Values passed via `extra=` are silently *dropped* by `JSONLogFormatter` rather than
redacted, so they do not leak to the JSON sink — but they would leak through any
handler whose formatter renders them.

**Fix.** Add an always-on layer that does not depend on opt-in: a key-name deny-list
over `record.__dict__`/`extra` (`pan`, `aadhaar`, `ssn`, `account_no`, `email`,
`phone`, `salary`, `dob`, `token`, `password`) plus format regexes for PAN and
Aadhaar. Make value matching case-insensitive. Correct the docstring. Land the first
production `redact_values` call with the story that introduces PII.

### [VULN-005] `AppError` defaults to 500 and echoes its message to the client

- **File:** `backend/src/types/errors.py` line 14 (handler at `backend/src/api/errors.py` line 20)
- **Severity:** medium → WARN · **CWE-209**

`AppError.__init__` defaults `status_code` to 500, and `_handle_app_error` returns
`exc.message` verbatim in the body at whatever status was given.

**Reproduction** (TestClient against the real app):

```
raise AppError("internal: /srv/truelend/src/service/underwriting.py line 88 rule table missing")
→ 500 {"error":"internal: /srv/truelend/src/service/underwriting.py line 88 rule table missing"}
```

An internal filesystem path disclosed to an unauthenticated client. The insecure
part is the *default*: a 5xx should never echo a developer-authored string, and this
default makes the leaky path the path of least resistance for every future story.
No production raiser exists yet, so nothing leaks today.

**Fix.** Make `status_code` required (or default it to 400). In the handler, return
a fixed `{"error": "Internal Server Error"}` for any status of 500 or above while
logging `exc.message` server-side with the bound `request_id`. Echo `exc.message`
only for 4xx.

### [VULN-006] `/docs`, `/redoc` and `/openapi.json` are unauthenticated, and `/docs` executes CDN script on the app origin

- **File:** `backend/src/api/app.py` line 23
- **Severity:** medium → WARN · **CWE-1188**, with **CWE-829**

`FastAPI(title=settings.service_name)` is constructed without `docs_url`,
`redoc_url` or `openapi_url` overrides, so all three interactive surfaces are live
and unauthenticated. Verified against the running server:

```
/docs         -> 200 text/html
/redoc        -> 200 text/html
/openapi.json -> 200 application/json
```

`/openapi.json` discloses the service name and version (`truelend-backend`, `0.1.0`)
and the complete route schema. That is trivial today with only `/health`, but it
will publish the entire loan-origination API surface — every path, parameter and
model — as stories land.

Separately, `/docs` loads and executes third-party script on the application origin:

```
https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js
https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css
```

An unpinned major version with no `integrity` attribute, and no
`Content-Security-Policy` on the response (see VULN-011). A CDN or DNS compromise
yields arbitrary script execution on the bank's own origin.

**Fix.** Gate the docs surface on an explicit setting — pass `docs_url`/`redoc_url`/
`openapi_url` as `None` unless a new `Settings` flag (e.g. `enable_api_docs`,
default `False`) is set. If docs must stay reachable in a deployed environment,
self-host the Swagger UI assets rather than loading them from a CDN.

### [VULN-007] `Money` accepts `NaN`, and serializes it onto the wire

- **File:** `backend/src/types/money.py` line 56
- **Severity:** medium → WARN · **CWE-20**

`Decimal("NaN")` constructs without raising `InvalidOperation`, and `quantize()`
propagates a quiet NaN rather than rejecting it. So:

```
Money("NaN")   -> OK, amount = Decimal('NaN')
Money("nan")   -> OK, amount = Decimal('NaN')
Money("-NaN")  -> OK, amount = Decimal('-NaN')
MoneyField wire representation -> {"amount":"NaN"}
```

This violates decision D-G, which requires a quoted 2dp string, and the frontend
rejects it (`money.ts` `isFinite` check throws), so the two ends of the wire
disagree. Worse, NaN propagates silently through the value type:

```
Money("NaN").add(Money("10.00"))  -> NaN
Money("NaN") == Money("NaN")      -> False
```

A NaN amount therefore does not raise anywhere; it quietly poisons arithmetic, and
because `NaN != NaN`, balance reconciliation and paid-in-full equality checks
silently evaluate `False` instead of erroring. On a lending ledger that is a
financial-integrity failure mode, not just a type nit.

Credit where due: `Infinity`, `-Infinity`, `inf`, `sNaN`, `1E999999999` and a
400-digit input are **all correctly rejected**, so there is no decimal
memory-exhaustion vector here. There is one further asymmetry: `Money("1_000.00")`
is accepted (Python's underscore digit separator) but `decimal.js` rejects that
string.

**Why WARN.** `MoneyField` is the designated untrusted-input parser, but no endpoint
currently accepts a money value, so this is not attacker-reachable today. It becomes
high the moment a money-accepting endpoint lands.

**Fix.** After constructing the `Decimal`, reject non-finite values explicitly:
`if not decimal_amount.is_finite(): raise InvalidMoneyAmountError(...)`. Constrain
accepted strings to a canonical grammar (e.g. `^-?[0-9]{1,12}([.][0-9]{1,2})?$`) so
Python and `decimal.js` agree. Add unit tests for `"NaN"`, `"nan"`, `"-NaN"` and
`"1_000.00"`.

### [VULN-008] Critical and high npm advisories in the changed frontend manifest (dev-only)

- **File:** `frontend/package.json` line 27
- **Severity:** medium → WARN · **CWE-1395**

`npm audit` on the changed manifest reports 5 advisories:
`{info: 0, low: 0, moderate: 3, high: 1, critical: 1}`.

| Package | Severity | Advisory |
|---|---|---|
| `vitest` | critical | Arbitrary file read/execute when the Vitest UI server is listening; `@vitest/mocker` path traversal |
| `vite` | high | Path traversal in optimized-deps `.map` handling; `server.fs.deny` bypass on Windows alternate paths |
| `esbuild`, `vite-node`, `@vitest/mocker` | moderate | transitive |

**Refuted as BLOCK.** Both direct offenders are `devDependencies` and are absent
from the production bundle; the runtime dependencies (`decimal.js`, `react`,
`react-dom`) are clean. The critical advisory requires `vitest --ui`, which this
project never runs (`npm test` is `vitest run`). The `vite` advisories do affect
developer workstations, which are Windows here — a real but bounded exposure.
Remediation requires a semver-major bump (vite 8, vitest 5) that breaks the
toolchain and belongs in its own story, not in group A.

**Fix.** File a follow-up story to upgrade `vite` to 8.3.0 or later and `vitest` to
5.0.0 or later together with `@vitejs/plugin-react`, then re-run `npm audit`. Until
then, do not run `vitest --ui` and do not bind the vite dev server to a non-loopback
interface.

---

## INFO Findings

### [VULN-009] No charset allow-list on `X-Request-ID`
`backend/src/api/middleware.py` line 32 · CWE-20

Byte-by-byte enumeration against the live server: `httptools` rejects all C0
controls and DEL with 400, but **HTAB (0x09) and every byte 0x80–0xFF — including
the C1 control 0x9B (8-bit CSI) — are accepted and echoed verbatim into the response
header.**

```
echoed verbatim: [0x9, 0x80..0x9f, 0xff]
rejected (400):  [0x0..0x8, 0xa..0x1f, 0x7f]
```

The log sink is safe: `json.dumps(ensure_ascii=True)` stores these as literal
`	` / `` / `ÿ` text (confirmed in the log file), so there is no
terminal-escape injection. Residual risk is malformed, non-UTF-8 header bytes
reflected to clients and intermediaries. Covered by the VULN-001 allow-list.

### [VULN-010] Error paths produce no access log line and no correlation header
`backend/src/api/middleware.py` line 37 · CWE-778

The access-log call and the header echo both sit *after* `await call_next(request)`
inside the `try`, so when a request raises, neither runs. Verified: a route that
raises returns 500 with **no `x-request-id` header** and produces **no
`truelend.access` line**, while the handled `AppError` route produces both. The
paths that matter most for audit at a regulated lender are the only paths with no
correlation id and no structured record. Additionally `JSONLogFormatter` emits
neither `exc_info` nor `extra`, so no traceback reaches the JSON sink at all.

**Fix.** Wrap `call_next` in `try/except`, log the failure with the bound
`request_id`, re-raise; and add `exc_info` plus selected `extra` fields to the
formatter.

### [VULN-011] No security headers on any response
`backend/src/api/app.py` line 24 · CWE-693

Verified absent on `GET /health`: no `Content-Security-Policy`,
`X-Content-Type-Options`, `X-Frame-Options`, `Strict-Transport-Security` or
`Referrer-Policy`. Low impact while the surface is one JSON probe, but `/docs`
already serves HTML that executes third-party script, and the frontend is not yet
wired. **Fix.** Add a response-header middleware (`nosniff`, `DENY`, `no-referrer`,
a CSP); add HSTS at the TLS terminator.

### [VULN-012] No host validation and no rate limiting
`backend/src/api/app.py` line 24 · CWE-770

`app.user_middleware` contains only `CorrelationIdMiddleware`. No
`TrustedHostMiddleware`, so the `Host` header is unvalidated; no rate limiter on any
route. Impact is low today — nothing generates absolute URLs or redirects and there
is no authentication — but both become material with the first auth or
password-reset story, and the missing rate limit is what makes VULN-001 sustainable.

### [VULN-013] A non-`str` sensitive value would raise inside the logging filter
`backend/src/config/logging.py` line 51 · CWE-703

`redact_values` is annotated `*values: str` but does no runtime check, and
`message.replace(value, ...)` is unguarded. A non-`str` would raise `TypeError`
inside logging's filter chain, which is not wrapped in `try/except`, so the
exception propagates back to the `logger.info()` call site and fails the request.
`mypy --strict` protects in-repo callers, so this is latent. **Fix.** Coerce with
`frozenset(str(v) for v in values if v)` and make the filter fail closed (drop the
record) rather than raise.

### [VULN-014] Gate evidence provenance chain is not verifiable
`.claude/state/task-envelope.json` · no CWE

Noted for completeness; outside the application security surface and owned by the
gate rather than this review. The working-tree envelope was **rotated** — `created_at`/
`expires_at` moved ~9h forward, `integrity.hash` rebuilt — while
`previous_envelope_hash` is still `null` and `amendments` is still `[]`, despite
history files existing for the superseded hashes. Moving `created_at` forward also
resets the "evidence created after the envelope" window that
`finalize-task-evidence.js` enforces. `project-manifest.json` was likewise edited
outside the envelope's `allowed_paths`. No application vulnerability, but it weakens
the integrity of this gate's own evidence. **Fix.** Record an amendment with
`previous_envelope_hash` set to the superseded hash instead of rotating in place.

---

## Refuted candidates (adversarial verification)

Each of these was investigated as a potential BLOCK and dropped on evidence. They
are recorded so the finding is not re-raised without new information.

| Candidate | Verdict | Evidence |
|---|---|---|
| **CRLF response-header injection via `X-Request-ID`** | **Refuted** | `uvicorn[standard]` uses the **httptools** parser (not h11). A CR/LF in the value is consumed as the header separator: `X-Request-ID: abc\r\nX-Injected: 1` yields `request_id == "abc"` and `X-Injected` as its own *request* header; the response echoes only `x-request-id: abc`. Obs-fold continuation (`CRLF`+TAB and `CRLF`+SPACE), bare LF, and NUL all return `400 Bad Request / Invalid HTTP request received.` No byte that can terminate a header line reaches the echoed value. **The exploit string suggested in the task brief does not inject.** |
| **Forged JSON log entry via `X-Request-ID`** | **Refuted** | Payload `x","level":"CRITICAL","message":"forged` returns 200 and is stored as a *single* line: `{... "request_id": "x\",\"level\":\"CRITICAL\",\"message\":\"forged"}`. `json.dumps` escapes the quotes; the record stays one valid JSON object with `level: INFO`; no second line and no overridden field. All 124 JSON lines in the live log parse cleanly (0 unparseable). |
| **ANSI / terminal escape injection into logs** | **Refuted** | ESC (0x1b) and BEL (0x07) are rejected at the parser with 400. C1 `0x9b` and high bytes do reach the header, but `ensure_ascii=True` stores them as literal ``/`ÿ` text, so no escape sequence reaches a terminal. |
| **Stack trace / internal path / secret leak in the unhandled-exception response** | **Refuted** | `app.debug` is `False`. A route raising `ValueError` containing a Postgres DSN, a password and a PAN returns `500 Internal Server Error`, `text/plain`, 21 bytes. Checked explicitly for `Traceback`, `postgres://`, `s3cr3t`, `ABCDE1234F`, `underwriting.py`, `site-packages`, `ValueError` — none present. |
| **`GET /health` discloses version / config / env / dependency state** | **Refuted** | Body is exactly `{"status":"ok"}`. No version, environment, settings or dependency health. (Version and schema disclosure lives on `/openapi.json` instead — VULN-006.) |
| **XSS in `MoneyText.tsx`** | **Refuted** | Renders `<span>{value.format()}</span>` — a React text child, auto-escaped. No `dangerouslySetInnerHTML`, `innerHTML`, `outerHTML`, `document.write`, `insertAdjacentHTML`, `eval`, `new Function`, `postMessage`, `target="_blank"`, or web-storage use anywhere in `frontend/src`. `format()` output derives from a `Decimal` via `toFixed(2)` plus a digit-grouping regex, so it cannot contain markup regardless of input. |
| **Hardcoded secrets / insecure defaults in `settings.py`** | **Refuted** | `Settings` carries only `service_name` and `log_level`, both non-sensitive, from env with prefix `TRUELEND_`. No `.env` or `.env.example` in the repo, no `VITE_`/`NEXT_PUBLIC_` values in frontend source, no debug flag. The only `token` matches in the diff are contextvar reset tokens (`middleware.py:33`, `logging.py:35`). |
| **Nested dicts/lists escaping redaction** | **Refuted** | The filter replaces over the fully rendered message, so a PAN nested in `{'applicant': {'ids': [PAN], 'name': ...}}` **is** redacted (verified). The real gaps are `exc_info` (VULN-002), `request_id` (VULN-003) and case mismatch (VULN-004). |
| **Permissive CORS** | **Refuted** | No `CORSMiddleware` registered; `app.user_middleware` contains only `CorrelationIdMiddleware`. No cross-origin access granted — secure by omission. Revisit when the frontend is wired. |
| **Production dependency CVEs** | **Refuted** | `decimal.js`, `react`, `react-dom` carry no advisories. All 5 npm findings are dev tooling (VULN-008). `backend/pyproject.toml` is **not** in the change set, so no Python dependency audit was in scope. |
| **Injection family: SQL / command / path traversal / SSRF / deserialization / CSRF / open redirect / IDOR / auth bypass** | **Not applicable** | No database, ORM, raw query, subprocess, request-derived filesystem path, outbound HTTP client, deserializer, cookie/session, redirect or object-by-id lookup exists in the change set. The only route takes no input. Confirms the pack's claim. |

---

## Notes for the orchestrator

1. **Reviewing this diff inflated `.claude/state/uvicorn.log` from ~0.4 MB to
   ~36.7 MB** — that growth *is* the VULN-001 proof. Truncate the log before the
   next gate run so it does not skew other checks.
2. Observed while proving VULN-002 but **out of security scope**: 184 of 308 lines
   in the live server log are plain-text uvicorn lines carrying no `request_id`.
   Whether that satisfies QA-VM-003's "100% of log lines emitted while serving parse
   as JSON" is a question for the evaluator, not this gate.
3. `specs/reviews/security-verdict.json` carries a top-level `"verdict": "blocked"`
   **and** `"pass": false`. `blocked` is the token in `FAIL_VERDICTS` in
   `.claude/hooks/lib/sensor-schema.js`; `"block"` is not, and would only be caught
   by the `pass === false` fallback. Both keys are set so either normalization path
   reaches the same conclusion.

**Verdict: BLOCK.** One high-severity finding (VULN-001) is exploitable against the
running service. Do not merge group A until it is fixed; return to the generator.
