# Security Review — TrueLend (group A) — INSTANCE 2 of 3 — 2026-09-14

Range `14e9487..HEAD` (`9112495`), branch `feat/harness-scaffold-and-planning`.
Independent re-verification round 2. Inputs read: `specs/reviews/review-context-pack.md`,
`git diff 14e9487..HEAD -- backend frontend`, the files it touches, `.gitignore`,
`.claude/claude-security-guidance.md`. No prior verdict file was used as authority.

**Method: every vector below was executed, not read.** Two live servers were booted
(`src.api.app:app` on :8102, and a throwaway app wrapping `build_fastapi_app()` on
:8103 to exercise the redaction scope), driven with raw sockets and keep-alive
`http.client`, plus in-process timing of `_scrub`/`_redaction_pattern` and
`sanitise_context`. Log sinks were parsed back as JSON. Probe scripts were run from
`.claude/state/sec-probe-i2/` and deleted afterwards; the measurements are quoted inline.

## Summary

- BLOCK findings: **2** (both `high`, both HTTP-reachable at HEAD, same root cause area)
- WARN findings: **13**
- INFO findings: **7**
- Overall verdict: **BLOCK**

Both BLOCKs are in the newly shipped `/metrics` surface. The two prior security
BLOCKs (SEC-001 ReDoS, SEC-002 PII in tracebacks) are **independently confirmed
fixed by measurement** — see "Refuted / confirmed-fixed" below.

---

## BLOCK Findings

### [SEC2-B01] Unbounded, never-evicted request-counter cardinality keyed on the raw URL path — remote memory exhaustion and response amplification
- **File:** `backend/src/api/middleware.py:49` (declaration) and `:75` (write), rendered by `backend/src/api/platform/routes.py:77`
- **Severity:** high → **BLOCK**
- **OWASP:** A04 Insecure Design / A05 Security Misconfiguration (CWE-770 allocation without limits, CWE-400)
- **HTTP-reachable at HEAD: YES**, unauthenticated, no rate limit, no auth anywhere in the app.
- **Description:** `_request_counts` is a process-global `Counter` keyed on
  `(method, scope["path"], status)` — the **raw, URL-decoded request path**, not the
  matched route template. Every distinct path an anonymous client invents creates a
  permanent new key. Nothing evicts, caps, or bounds it; the only reset
  (`reset_request_counters`) is test-only. The growth happens in the middleware on
  every request, so it does not even require anyone to call `/metrics`.
- **Measured (instance 2, live server on :8102):**
  - 60,000 distinct 300-char paths pushed from **one** keep-alive connection in
    **11.9 s** (5,047 req/s). All returned 404 — routing never has to succeed.
  - Server working set **92,268 KB → 121,156 KB**: **+28.2 MB retained**, ≈**493 bytes
    permanently held per distinct path**, i.e. ≈**142 MB per minute** of attack from a
    single connection. Nothing is released.
  - `/metrics` body grew to **45.6 MB / 124,012 series**. A ~60-byte unauthenticated
    `GET /metrics` therefore returns 45.6 MB — a ~760,000× bandwidth amplifier, and it
    grows without limit.
  - Earlier, smaller run: 4,000 distinct paths → 1,071,316-byte body, 4,008 series.
- **Refutation attempted and failed:** there is no LRU/TTL/`maxsize`, no allowlist of
  known routes, no auth on `/metrics`, no rate limiting, and no reverse proxy in the
  declared deployment (`verification.mode: local`; Compose arrives in E15-S2). Trailing
  -slash 307s and 405s are counted too, so even a strict router does not bound the key
  space. The path is attacker-chosen with no length or charset constraint.
- **Fix:** key the counter on the **matched route template**
  (`scope["route"].path` / `request.scope.get("route")`), falling back to a single
  literal such as `"<unmatched>"` when routing did not resolve; likewise fold unknown
  methods to `"<other>"`. Hard-cap the number of distinct series (drop into an
  `"<overflow>"` bucket past e.g. 500) and require auth or bind `/metrics` to an
  internal interface.

### [SEC2-B02] Prometheus label values interpolated from the decoded path with no escaping — exposition-format injection into the monitoring pipeline
- **File:** `backend/src/api/platform/routes.py:79-81` (f-string), tainted at `backend/src/api/middleware.py:75`, source `scope["path"]`
- **Severity:** high → **BLOCK**
- **OWASP:** A03 Injection / A09 Security Logging & Monitoring Failures (CWE-117 improper output neutralization, CWE-74)
- **HTTP-reachable at HEAD: YES**, unauthenticated.
- **Description:** the route label is written as `route="{route}"` with no escaping of
  `"`, `\` or newline, and uvicorn hands the middleware the **percent-decoded** path.
  An anonymous request whose path contains encoded `%22` and `%0A` therefore closes the
  label, terminates the line, and writes attacker-chosen lines into the scrape output.
- **Measured:** a single `GET` to a path containing an encoded quote + newline + a
  crafted counter line produced, verbatim in `GET /metrics`:
  - a truncated/malformed first line (`...route="/a` with an unbalanced quote), and
  - a **fully fabricated series of its own**:
    `http_requests_total{method="GET",route="/spoofed",status="200"} 999999`,
  - plus a stray `#`-prefixed fragment. Probe assertion
    `spoofed metric present as its own line: True`.
- **Impact:** either the scrape fails to parse (monitoring blackout) or the collector
  ingests attacker-authored counters. This project's runtime-SLO sensor
  (`{"error_rate_pct":1,"p95_ms":500}`) is fed from this surface, so an unauthenticated
  client can both fabricate healthy traffic and mask an error-rate breach — an
  integrity failure in an observability control for a regulated lending platform.
- **Refutation attempted and failed:** nothing sanitises the path anywhere on the way
  in (middleware writes it raw; the route renders it raw). The JSON *log* sink is safe
  (`json.dumps` escapes — see SEC2-I01), but the `/metrics` text sink is not; they are
  separate code paths. `PlainTextResponse` does no escaping of exposition syntax.
- **Fix:** escape label values per the exposition format (`\` → `\\`, `"` → `\"`,
  newline → `\n`) **and** stop using free-form input as a label at all by adopting the
  matched route template (SEC2-B01's fix removes this vector as a side effect).

---

## WARN Findings

### [SEC2-W01] `GET /metrics` is unauthenticated and reflects attacker-controlled content
`backend/src/api/platform/routes.py:70`. medium. Even once capped and escaped, the
endpoint exposes traffic volume, status mix and the internal route inventory to anyone,
and echoes attacker-chosen path strings back to the scraper. No auth, no allowlist, no
rate limit. Fix: require a bearer/mTLS credential or bind to a non-public port, and
never echo unmatched paths.

### [SEC2-W02] `sanitise_context` never scrubs non-string scalars — registered numeric PII egresses verbatim
`backend/src/api/errors.py:155-183` (`_scalar` returns `bool|int` before any scrubbing;
`sanitise_context` only calls `scrub_text` inside `isinstance(value, str)`). medium.
**Measured:** with a 12-digit Aadhaar and a salary registered via `register_sensitive`,
the string and `Decimal` forms came out `[REDACTED]` but the **int forms came out
whole** (`aadhaar_int -> 123412341234`, `salary_int -> 875000`). Aadhaar is a 12-digit
number and salary is money, so the int path is exactly the shape this PII takes.
Not reachable at HEAD (no production code raises an `AppError` with PII context), so
WARN not BLOCK — but it becomes a live PII egress the moment a group B/E story puts a
numeric identifier in `context`. Fix: scrub the stringified form of every scalar, or
allow only strings and `Decimal` and force callers to stringify.

### [SEC2-W03] `_CREDENTIAL_URI` misses several common credential shapes
`backend/src/api/errors.py:150`. medium. The regex requires a non-empty username
(`[^/\s:@]+` before the colon), so **a URI whose userinfo starts immediately with the
colon (empty username, the usual Redis/AMQP form) is not detected and egresses intact**
— confirmed by probe. Also egressed: credentials passed as a **query parameter**
(`...?user=...&password=...`), ADO/JDBC-style `Password=...;` key-value strings,
scheme-less `user:secret@host` forms, a URI with a space before the `@`, an
`AWS_SECRET_ACCESS_KEY=...` assignment, and a JWT. Fix: treat the filter as one layer
only — add key-name-based dropping (`*password*`, `*secret*`, `*token*`, `*dsn*`,
`*url*`), detect userinfo with an optional username, and inspect query strings.

### [SEC2-W04] Context **keys** are never scrubbed, capped or counted
`backend/src/api/errors.py:182` (`clean[str(key)] = value`). medium. **Measured:** a
key containing a PAN (`pan_ABCDE1234F`), a key containing a full credential URI, and a
**5,000-character key** all egressed unchanged; `sanitise_context` with 10,000 entries
returned all 10,000. The 200-char cap and the credential filter apply to values only,
so the key channel bypasses both, and the envelope size is unbounded. Fix: apply the
same scrub/cap to keys, restrict keys to a safe charset, and cap the entry count.

### [SEC2-W05] Redaction tolerance model is defeated by any separator outside `{space, tab, hyphen}` and by runs of 5+ — demonstrated leaking a registered PAN at INFO
`backend/src/config/logging.py:94-129` (`_SEPARATOR_RUN = r"[ \t\-]{0,4}"`, and the
literal-escape branch at `:115-116`). medium.
**Measured against a real log sink** (registered PAN, one INFO line through the
configured JSON logger): `ABCDE-----1234F` (5 hyphens), `ABCDE.1234F` and a
newline-split `ABCDE\n1234F` **all reached the log line unredacted** while the exact
and 4-separator forms were redacted. In-process matrix (registered value
`ABCDE1234F`): redacted for exact / 1 hyphen / 4 hyphens / 4-spaces-per-char /
lowercase; **not** redacted for 5 hyphens, 6 hyphens, 5 spaces, 5-spaces-per-char,
newline, `.`, `/`, `_`, `,`, NBSP, zero-width space, `%20`, literal `\n`. Same for a
grouped Aadhaar with 5 spaces or dots.
**Rating of the specific 5-separator gap the pack calls out:** real, confirmed, but the
*least* significant member of this class — the `{0,4}` bound is not the weakness, the
character-class allowlist is. Widening the run would reintroduce SEC-001, so the fix is
not a bigger bound. Not reachable at HEAD: `grep` shows **zero production call sites**
of `register_sensitive`/`redact_values`/`scrub_text` outside `errors.py`, so no PII is
registered or logged yet, and an attacker cannot choose the formatting of a value no
code handles. Hence WARN — but it **must** be closed before any origination story logs
applicant data, or it silently becomes the SEC-002 leak again in a new costume.
**Fix:** match on a normalised projection — strip every non-alphanumeric character from
both the value and the haystack, match on the normalised text, and map the match span
back to the original offsets — instead of a separator-tolerant pattern.

### [SEC2-W06] `_MIN_REDACTABLE_LENGTH = 6` silently skips short sensitive values
`backend/src/config/logging.py:94` and `:124`. medium. **Measured:** `"1234"`,
`"12345"`, `"999"`, `"cvv"`, `"Ravi"`, `"50000"` are **never** redacted; 6+ chars are.
Real PII/secret material under 6 characters in this domain: a 4–5 digit OTP or PIN, a
CVV, a card/account last-4, a 5-figure salary (`50000`), a short given name, a date
fragment. The skip is **silent** — `_scrub` `continue`s with no warning, metric or
exception — so a caller who registers a short value gets a false assurance of
protection. Fix: keep the skip (the over-matching rationale is sound) but make it
explicit: raise or emit a one-time warning from `register_sensitive` for values below
the threshold, and support short values via an anchored word-boundary literal match
rather than the tolerant run.

### [SEC2-W07] `lru_cache` retains PII-derived compiled patterns in process-global state for the process lifetime
`backend/src/config/logging.py:102`. medium. The module documents registration as
**request-scoped**, and the contextvar set is indeed torn down — but
`_redaction_pattern` is memoised on the raw sensitive value, and the cached
`re.Pattern` keeps the value's characters recoverable verbatim in `.pattern`
(**measured:** `'A[ \t\-]{0,4}B[ \t\-]{0,4}C...'` for a registered PAN). The cache
entry, and the raw value as its cache **key**, survive the request, the redaction
scope, and every later request (up to 256 entries). So applicant PAN/Aadhaar persist in
globally reachable process memory long after the request that handled them — reachable
in a core dump, a heap dump, a `/debug`-style introspection endpoint, or any future
in-process error reporter. Fix: memoise on a salted hash of the value (or on a
per-request cache discarded with the scope) so the cache key and the pattern source no
longer carry plaintext PII; store the pattern keyed by digest.
**Refuted sub-claims:** *unbounded memory* — no, `maxsize=256` bounds it.
*Cross-request misredaction* — no, the pattern is a pure function of the value, so
reuse cannot redact the wrong thing. *Cache-thrash DoS* — measured 5,000 lookups over
257 distinct values = 33.5 ms vs 0.8 ms warm (40× relative, but only ~6.7 µs per
recompile); real but negligible.

### [SEC2-W08] Inbound `X-Request-ID` is accepted unvalidated and unbounded, then reflected into the response and every log line
`backend/src/api/middleware.py:86-87`. medium. **Measured:** a **40,000-character**
`X-Request-ID` was accepted, echoed verbatim in the response header
(`echo_len=40014`) and written into the JSON access-log line (longest log line 40,146
bytes; 96,588 bytes of log produced by four such requests). No length, charset or
format constraint; any client can also **choose** the correlation id — colliding with
another tenant's id, replaying a known id, or seeding audit records with a value of its
choosing (repudiation / audit-trail poisoning). Honouring the inbound header is
contract-mandated (QA-VM-003), so the behaviour is right and the validation is
missing. Fix: accept the inbound value only if it matches something like
`^[A-Za-z0-9._-]{1,128}$`, otherwise generate one; and log the server-generated id
alongside the client-supplied one so the trusted correlation key is always present.

### [SEC2-W09] Interactive API docs and the OpenAPI schema are exposed unauthenticated, and Swagger UI loads third-party CDN scripts
`backend/src/api/app.py:118` (`FastAPI(title=...)` with default `docs_url`/`redoc_url`/
`openapi_url`). medium. **Measured:** `/docs` 200 text/html, `/redoc` 200, `/openapi.json`
200 — no auth, no environment gate. The served `/docs` page pulls
`swagger-ui-bundle.js` and `swagger-ui.css` from `cdn.jsdelivr.net` with no SRI and no
CSP, so a CDN compromise executes script in the context of the API origin. Group A's
schema is harmless; by group E it is a full map of the origination API. Fix: set
`docs_url=None, redoc_url=None, openapi_url=None` unless an explicit
`Settings.enable_docs` (default off outside dev) is set, and self-host or
SRI-pin the Swagger assets if docs stay on.

### [SEC2-W10] Host header is reflected into the trailing-slash redirect `Location` (host-header injection / open redirect)
`backend/src/api/app.py:118` (no `TrustedHostMiddleware`, default
`redirect_slashes=True`). medium. **Measured:** `GET /health/` with
`Host: evil.example` returned `307` and `location: http://evil.example/health`. Any
path with a trailing slash becomes an attacker-controlled absolute redirect, which also
poisons any path-keyed intermediary cache. Fix: add
`TrustedHostMiddleware(allowed_hosts=...)` from configuration, and/or
`FastAPI(redirect_slashes=False)`.

### [SEC2-W11] No security response headers on any route
`backend/src/api/app.py:113-131`. medium. **Measured** response headers on `/health`:
only `date, server, content-length, content-type, x-request-id`. No
`X-Content-Type-Options: nosniff`, `Content-Security-Policy`, `X-Frame-Options`,
`Referrer-Policy` or HSTS — and `/docs` serves HTML with remote scripts, and `/metrics`
echoes attacker-controlled text. `server: uvicorn` also discloses the stack. Fix: add a
small header middleware in the app factory (nosniff + `frame-options: DENY` +
`Referrer-Policy: no-referrer` + a locked CSP; HSTS once TLS terminates in E15-S2).

### [SEC2-W12] `npm audit`: 1 critical, 1 high, 3 moderate advisories in the new frontend manifest
`frontend/package.json:15-29`. medium (downgraded from BLOCK — rationale below).
**Measured** (`npm audit --json`): `{"critical":1,"high":1,"moderate":3,"total":5}`.
- `vitest` ≤4.1.10 — **critical** GHSA-5xrq-8626-4rwp (arbitrary file read/execute when
  the Vitest **UI** server is listening) and GHSA-82fw-gwwq-j7x9.
- `vite` ≤6.4.2 — **high**: GHSA-4w7w-66w2-5vf9 (path traversal in optimized-deps
  `.map` handling), GHSA-fx2h-pf6j-xcff (`server.fs.deny` bypass on Windows alternate
  paths), GHSA-v6wh-96g9-6wx3 (NTLMv2 hash disclosure via UNC handling on Windows —
  note this project builds on Windows).
- moderate: `@vitest/mocker`, `esbuild` (dev server accepts cross-origin requests),
  `vite-node`.
**Downgrade rationale (adversarial check):** every affected package is a
`devDependency`; none is reachable in the deployed artefact (`vite build` output is
static, the backend serves no Node runtime), the vitest UI is never started (`vitest
run`), and the fixes are semver-major (`vite` 7 / `vitest` 5). The residual risk is to
a developer workstation running `npm run dev` or `vitest --ui` while browsing —
real, but not an exploitable path in the merged product, so WARN rather than a build
failure. Fix: upgrade `vite`/`vitest` to the fixed majors in the next sprint, and never
expose the dev server or Vitest UI on a routable interface.

### [SEC2-W13] No lockfile can be committed — `.gitignore` excludes `package-lock.json` and `*.lock` repo-wide
`.gitignore:45,49`; `frontend/package.json` is the new manifest. medium.
`git ls-files frontend/` shows **no lockfile**, and `git check-ignore` confirms
`frontend/package-lock.json` is ignored by the repo-wide `package-lock.json` entry (the
adjacent `*.lock` entry does the same for `backend/uv.lock`). The local
`frontend/package-lock.json` (157 KB) exists but is untracked, so CI and every other
machine resolve caret ranges freshly with no integrity hashes — non-reproducible builds
and an unpinned supply chain (OWASP A08, CWE-1104). Those two `.gitignore` lines sit
under a "generated / large files Claude should skip" comment, i.e. a navigation
convenience with a supply-chain side effect. Fix: narrow the ignore rules to build
output (`*.min.js`, `*.map`) and commit `frontend/package-lock.json` and
`backend/uv.lock`; add `npm ci` to CI.

---

## INFO Findings

### [SEC2-I01] Probed and refuted: CRLF response-splitting and JSON log-forging via `X-Request-ID`
low. Raw-socket probes against the live server: a header value containing literal
`\r\n`, obs-fold continuation, bare `\n`, bare `\r`, or `NUL` produced **400 Bad
Request** from h11 (or was parsed as a separate, ignored request header) — no injected
response header in any case, and a high-byte value round-tripped harmlessly through
latin-1. Log-forging also fails: ids containing `"`, `\` and a full JSON object were
escaped by `json.dumps`, and **8,050 of 8,050** captured log lines parsed as valid JSON
(0 non-JSON). Worth recording because the control lives in the ASGI server and the
stdlib, not in application code — a different server, a `BaseHTTPMiddleware` rewrite,
or a plain-text log sink would remove it.

### [SEC2-I02] Redaction cost is linear in the number of registered values, per log line
`backend/src/config/logging.py:122-129`. low. **Measured** on a 2,220-char haystack:
~90 µs per registered value per log line, flat per value (100 values → 9.1 ms;
1,000 → 89 ms; 5,000 → 480 ms **per log line**). `register_sensitive` is additive with
no cap, so a future bulk/batch endpoint that registers thousands of values would make
every subsequent log line in that request cost hundreds of milliseconds — a
self-inflicted DoS reachable through a legitimate feature. Fix: cap the per-request set
and/or build one alternation pattern per request instead of N passes.

### [SEC2-I03] A logger created after `configure_logging` that sets `propagate=False` bypasses redaction entirely
`backend/src/config/logging.py:241-250`. low. `_install_redaction_filter_everywhere`
snapshots `logging.root.manager.loggerDict` once at startup; redaction for everything
else relies on propagation to the root **handler**. Any library imported later that
attaches its own handler and disables propagation (the classic case being SQLAlchemy
`echo` in E1-S1, which will log parameterised queries containing applicant data) writes
unredacted. Fix: install the filter on handlers at emit time (a `logging.Handler`
subclass or a `logging.setLogRecordFactory` hook), or re-run the installer after each
story wires a new logger.

### [SEC2-I04] `/health` discloses the service version unauthenticated; no endpoint is rate-limited
`backend/src/api/platform/routes.py:59-67`. low. `{"status","database","version"}` is
contract-mandated, but `version` plus `server: uvicorn` gives an unauthenticated client
a build fingerprint, and `database: down` leaks infrastructure state. No throttling
exists anywhere (relevant to SEC2-B01, and to the login/OTP endpoints arriving later).
Fix: gate `version` behind auth or reduce it to a build hash; add rate limiting at the
edge in E15-S2.

### [SEC2-I05] `assert isinstance(...)` in the exception handlers vanishes under `python -O`
`backend/src/api/errors.py:204, 210, 221`. low. Run with `-O`/`PYTHONOPTIMIZE`, a
mis-registered handler would raise `AttributeError` from inside the error path instead
of failing the assertion, producing Starlette's plain-text 500 and losing the frozen
envelope. Fix: use an explicit `if not isinstance(...): raise TypeError(...)` or narrow
the handler signatures.

### [SEC2-I06] Probed and refuted: cross-request leakage of the redaction scope
low. The middleware deliberately does not unwind `request_id_var` or the redaction set
on the failure path. Probed with a real server and a keep-alive connection: a request
that registered a PAN + Aadhaar and then raised was followed on the **same connection**
by `/probe/scope`, which returned `{"registered": [], "request_id": "probe-2"}` — no
leakage, because uvicorn runs each request cycle in its own task context. Recorded
because the guarantee is a property of the ASGI server's per-request context copy, not
of this code; a future synchronous runner or a shared-context worker would turn this
into a cross-request PII leak.

### [SEC2-I07] `Settings.log_level` is unvalidated and reaches `setLevel` directly
`backend/src/config/settings.py:158`, consumed at `backend/src/config/logging.py:204`.
low. Any `TRUELEND_LOG_LEVEL` value that is not a known level name raises `ValueError`
during `build_fastapi_app()` and the process never starts; a value of `DEBUG` in
production would also widen what reaches the log sink ahead of the PII controls above.
Fix: constrain the field to a `Literal[...]` of the five level names.

---

## Refuted / confirmed-fixed (probed, no finding)

| Claim | How probed | Outcome |
|---|---|---|
| **SEC-001** catastrophic backtracking in `_redaction_pattern`/`_scrub` | 44 timed shapes, including the prior gate's `'-'*n+'Z'` vs all-hyphen haystack up to n=201; separator-free value vs `A----`-repeating haystack; near-maximal runs followed by a mismatch; all-`A` haystacks; the literal-escape branch over a 400 KB haystack; alternating `A-` values | **Fixed.** Every shape sub-millisecond; prior-gate shape 0.027–0.123 ms (was 199,326 ms). Growth is linear, not exponential. Structural reason confirmed: the tolerant run matches only separators while every value character in that branch is a non-separator, so the partition is unique and there is no ambiguity to backtrack over; a value containing a separator takes the literal branch. The worst case found is the ordinary quadratic scan `"A"*30+"B"` vs `"A"*L`, which is **linear in L** at 0.445 ms (1 KB) → 42.7 ms (200 KB) — not attacker-reachable, since no HTTP input registers values. **No new blowup shape found.** |
| **SEC-002** PII in an exception message reaching a log sink unredacted | Live server; route registered a PAN + Aadhaar then raised with both in the message; parsed every resulting log line | **Fixed.** Both the middleware's `ERROR` line and `uvicorn.error`'s line carry `[REDACTED]`, contain neither raw value, and both carry `request_id == probe-raise`. The 500 body was the frozen envelope with an empty `context`. |
| Unbounded memory / cross-request pattern mixing via `lru_cache` | `cache_info()` after 300 distinct values; thrash timing; identity of cached patterns | Refuted (bounded at 256; pure function of the value). The *retention* half survives as SEC2-W07. |
| Response splitting / header injection via `X-Request-ID` | raw sockets, 9 hostile header encodings | Refuted — see SEC2-I01. |
| JSON log-record forgery via `X-Request-ID` or the request path | 8,050 log lines re-parsed | Refuted — `json.dumps` escapes; 0 malformed lines. |
| Cross-request PII leakage from the deliberately un-unwound scope | live keep-alive probe after a failing request | Refuted — see SEC2-I06. |
| `X-Forwarded-Host` / `X-Forwarded-Proto` spoofing from an untrusted client | forged forwarded headers | Partly refuted — `X-Forwarded-Host` was ignored; `X-Forwarded-Proto` was honoured only because the probe originated from `127.0.0.1`, which is uvicorn's default `forwarded_allow_ips`. Re-test in E15-S2 if the proxy config widens it. |
| Frontend XSS | `frontend/src/types/money.ts`, `frontend/src/ui/components/MoneyText.tsx` | Refuted — no `dangerouslySetInnerHTML`, `innerHTML`, `eval`, `new Function`, or `document.write`; `MoneyText` renders a formatted string as a text child. |
| SQL / command / path-traversal injection, auth bypass, IDOR, CSRF, insecure deserialization, hardcoded secrets | full read of all 12 changed production source files | None present — group A has no repository, service, auth or persistence layer, and `Settings` sources everything from `TRUELEND_*` environment variables with no hardcoded default credentials. Auth-bypass and IDOR checks are **not applicable at HEAD** (no authenticated route exists); they must be re-run when group B adds them. |
| npm advisories as BLOCK | `npm audit --json`, dependency-type and reachability check | Downgraded to SEC2-W12 with rationale. |

## Project threat-model rules (`.claude/claude-security-guidance.md`)

| Rule | Status at HEAD |
|---|---|
| NEVER log secrets/tokens/full PII at INFO+ | **No violation on a reachable path at HEAD** — no production code logs PII (zero production call sites of the redaction entry points; the architecture test at `backend/tests/unit/test_log_redaction.py:133-190` enforces that future PII-handling modules enter a scope). The *control* has demonstrated holes (SEC2-W05, SEC2-W06) which must be closed before group B/E logs applicant data. |
| NEVER build SQL/shell/HTML from unsanitized input | No SQL/shell/HTML sink in the diff. The Prometheus exposition text **is** an unsanitised output sink built from user input → SEC2-B02. |
| MUST validate and authorize every state-changing request server-side | No state-changing endpoint exists at HEAD (`/health`, `/metrics` are both GET). Not violated; re-check in group B. |
| MUST load credentials from environment/secret manager | Satisfied — `Settings` is `BaseSettings` with `env_prefix="TRUELEND_"`, no hardcoded credentials anywhere in the diff. |

## Verdict

**BLOCK** — `pass: false`. Two `high` findings, both HTTP-reachable at HEAD and both in
`/metrics`/the RED counter: SEC2-B01 (unbounded path-keyed cardinality → 142 MB/min
memory exhaustion and a 45.6 MB amplified response, measured) and SEC2-B02 (unescaped
exposition-format injection, demonstrated). Both are fixed by the same change — key the
counter on the matched route template, cap the series count, escape label values, and
put `/metrics` behind auth. The two prior security BLOCKs are confirmed fixed.
