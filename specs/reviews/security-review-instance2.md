# Security Review — truelend `/gate --group A` round 3 — instance 2 of 3 — 2026-09-14

**HEAD:** `ba457bf` · **base:** `14e9487` · **branch:** `feat/harness-scaffold-and-planning`
**Scope:** the 14 changed production files in review-context-pack §5 plus their immediate
data-flow neighbours (`.claude/hooks/lib/prom-parse.js` and `.claude/scripts/slo-check.js` as
the exposition sink, `backend/tests/**` only as evidence).
**Method:** every verdict below was re-derived at HEAD by execution against a live
`uvicorn` on **port 8035** (killed; port has no listener, no production file edited —
`git status --short` carries no product-source change from this review).

## Summary

- BLOCK findings: **0**
- WARN findings: **11**
- INFO findings: **8**
- **Overall verdict: PASS (no BLOCK)**

Round 2's two security BLOCKs are both closed at HEAD by measurement. One residual of B-2
survives as a WARN (the `method` label dimension), and the round-2 WARN set is largely intact.

## BLOCK Findings

None. Every candidate BLOCK was pushed through a refutation pass and downgraded with a
measurement; the refutations are recorded inline below.

## Priority 1 — the two round-2 BLOCKs, re-tested

### B-1 `/metrics` exposition injection — **CLOSED (refuted at HEAD)**

Nine hostile paths were fired at the live server (`%22`, `%0A`, `%0D`, `%0D%0A` carrying a
complete forged `http_requests_total` line, `%5C`, `%7B…%7D`, `%00`, `%09`, `%1B`). Result:

- all nine → 404, all nine collapsed into the single series
  `http_requests_total{method="GET",route="<unmatched>",status="404"} 9`
- forged series in the exposition: **0**; raw control characters outside `\n` in the whole
  document: **0** (19 lines, 1,408 bytes)
- the project's own sensor agrees: `node .claude/scripts/slo-check.js --url http://127.0.0.1:8035`
  → `{"verdict":"pass","error_rate_pct":0,"p95_ms":4.75}` (round 2: 99.90% error rate against
  a 1% budget)

Why the raw path can no longer reach a label: `route_label()` reads the *matched route
template* off the ASGI scope, never `scope["path"]`, so the percent-decoded path is no longer a
label channel at all — the escape table is a second line of defence rather than the fix.

**Carriage return, specifically (the pack's question):** `_LABEL_ESCAPES` in
`backend/src/api/platform/routes.py:78` does **not** cover `\r`, `\t`, `\x00` or any other C0
character. I could not find a channel that delivers one. The only two remaining label inputs are
`method` and the route template:

- `method` — with the dependency set this repo actually installs (`uvicorn[standard]` →
  `httptools` 0.8.0 present, and `--http auto` selects it), the parser rejects *anything* that
  is not one of its known methods **before the ASGI app runs**: unknown method, 300-char
  method, 5,000-char method, and methods containing `"`, `\`, `{` or `\x0b` all returned
  **400 Bad Request** with no series created. Under the pure-Python fallback (`--http h11`)
  arbitrary methods pass, but `"`, `\`, `{`, `\x0b` are still rejected as non-token characters,
  and CR/LF cannot appear in a request line at all. So no injection channel exists on either
  protocol implementation.
- the route template is developer-controlled.

Residual escaping gap recorded as **SEC2-I1** (defence-in-depth), not a finding against B-1.

### B-2 `/metrics` unbounded cardinality — **CLOSED for `route`; residual on `method` (WARN)**

Measured: 20,000 requests carrying 20,000 distinct paths down **one keep-alive connection**.

| | before | after |
|---|---|---|
| series lines | 555 | **556** (+1) |
| exposition bytes | 44,188 | 44,313 |
| series carrying an attacker path | — | **0** |
| server working set | 57.1 MB | 57.8 MB |

All 20,000 landed in `route="<unmatched>"`. Round 2's 60,000 label values / +28.2 MB is gone.

The **new** histogram state inherits the bound: `_duration_counts` / `_duration_totals` are keyed
`(method, route)` — the same `route_label()` output, one key short of the counter's `status` —
and the measurement above shows a single `<unmatched>` histogram key holding all 20,001
observations. An ASGI scope with no matched route (including the 307 slash-redirect, which
runs before routing completes) also lands in `<unmatched>`, verified live.

`method` is the residual, and it re-opens unbounded growth wherever the C parser is not the
one in use — see **SEC2-W1**. A very large number of *distinct registered routes* does not
change the picture: routes are developer-controlled and the exposition grows linearly in them.

## WARN Findings

### [SEC2-W1] `method` is an unvalidated metrics-label dimension, bounded only by an optional C parser
File: `backend/src/api/middleware.py` lines 124, 132, 141–143 (`_stamping_send`, `_observe`)
Severity: medium
`route_label()` bounds the route component but `scope["method"]` is used raw as a label on both
the counter and the new histogram. The application itself imposes no allow-list and no length
cap; the only thing bounding it is `httptools`' method table.

Measured under `uvicorn --http h11` (the pure-Python protocol uvicorn falls back to when
`httptools` is absent), 20,000 requests with distinct 67-character methods down one keep-alive
connection:

| | before | after |
|---|---|---|
| exposition lines | 79 | **300,094** |
| exposition bytes | 85,353 | **42,186,513** |
| server working set | 57.2 MB | 73.6 MB (retained) |

300,000 of those series carry an attacker-chosen method; each request mints 15 permanent
series. A single 5,000-character method adds ~75 KB of exposition permanently, so the public
unauthenticated `/metrics` is also an amplifier (15× the injected bytes on every scrape).

**Refutation attempted and partially successful:** with this repo's own `pyproject.toml` /
`uv.lock` (`uvicorn[standard]` pulls `httptools`) and the documented run command
(`uv run uvicorn src.api.app:app`), the exploit fails closed at 400 — verified. That is why this
is medium and not a BLOCK. It is a *configuration-dependent* mitigation, not an application
control: the escalation trigger is E15-S2's Dockerfile installing `uvicorn` without the
`standard` extra, or any deployment passing `--http h11`.
Fix: bucket the method label through an allow-list in `middleware.py` (the ~9 methods the API
actually serves, everything else to a single `<other>` bucket) so the bound is owned by the
application. This also collapses the 35 × 14 = 490 `405`-only histogram lines the current
code emits for two real routes.

### [SEC2-W2] `X-Request-ID` is accepted unvalidated and unbounded, then reflected and logged
File: `backend/src/api/middleware.py` line 151
Severity: medium
Measured on the live server, one unauthenticated request:

| id bytes | response bytes | bytes written to the log sink |
|---|---|---|
| 16 | 235 | 164 |
| 5,000,000 | 5,000,219 | **5,000,148** |

~30,000× log amplification per request, from an unauthenticated endpoint with no rate limiting;
~200 requests write 1 GB. A PAN-format id (`4111111111111111`) is accepted, echoed and logged
verbatim — it is not registered as sensitive, so `RedactionFilter` never sees it. High bytes
(`\xff\xfe\xfd`) are accepted and reflected. CR/LF and NUL in the header value are rejected by
the parser, so no response-splitting or log-injection path exists (`json.dumps` escapes control
characters in the log line besides).
Fix: validate on entry — accept only `^[A-Za-z0-9._-]{1,128}$`, otherwise generate a fresh id.

### [SEC2-W3] `sanitise_context` applies its *drop* rules to values only, never to keys
File: `backend/src/api/errors.py` lines 92–101
Severity: medium
`f5a5ace` closed the round-2 key gap only for scrubbing (`scrub_text(str(key))`). The two rules
that actually *drop* data — the credential-URI pattern and `_MAX_CONTEXT_VALUE_CHARS` — are
applied inside `_sanitise_value`, which never runs on keys. Measured:

- a DSN carrying an inline password, as a **value** → dropped (`{}`); the same DSN as a **key**
  → egressed complete with the password
- a 5,000-character key → egressed at full length (the 200-char cap is value-only)
- `\r`, `\n`, `\x00` in a key → egressed (JSON-escaped, so no splitting)

Reachability: `context` is developer-supplied and no production code raises `AppError` yet, which
is why this is medium rather than high. It becomes a live egress the moment a group-B/E handler
puts a connection string, path or free-form identifier in a context key.
Fix: run keys through the same `_sanitise_value` gate (or a dedicated key gate with a short
length cap and an identifier charset).

### [SEC2-W4] Redaction is still defeated by formatting variants — confirmed latent, not escalated
File: `backend/src/config/logging.py` lines 102–129
Severity: medium
Re-tested with a registered 12-digit Aadhaar: `1234 5678 9012` (spaced) and the lowercase PAN
redact correctly; **dot-separated**, **NBSP**, **zero-width-space** and **fullwidth-digit**
forms all pass through untouched. `_SEPARATOR_CHARS` is `" \t-"` only and there is no
normalisation step.

**The pack's escalation question, answered:** `ba457bf` does **not** add production call sites.
Its diff touches `specs/bundles/E1-S1.json`, `specs/bundles/E4-S1.json`, `specs/stories/E1-S1.md`,
`specs/stories/E4-S1.md` and harness state — no `backend/**` file. A grep of `backend/src` finds
`register_sensitive`/`redact_values` only in `config/logging.py`'s own definitions and docstrings;
the only `scrub_text` callers are in `api/errors.py`. So **zero production PII is registered
today** and the bypass stays latent — severity unchanged from round 2. It escalates to high the
first time an E4-S1 or E1-S1 handler lands, because at that point a reformatted PAN/Aadhaar
reaches a log sink.
Fix: NFKC-normalise and strip separators/zero-width characters in both the pattern and the
haystack (normalise-then-match), keeping the bounded separator run for the literal case.

### [SEC2-W5] Registered PII is retained process-wide as `lru_cache` keys
File: `backend/src/config/logging.py` line 102
Severity: medium
`_redaction_pattern` is `@lru_cache(maxsize=256)` keyed on the sensitive value itself, and the
compiled pattern embeds that value. Verified: after the redaction scope is torn down the cache
still returns the same compiled object for the PII key and the value is recoverable from
`pattern.pattern`. Up to 256 PANs/Aadhaars therefore live for the process lifetime — visible in
a core dump or heap inspection, and outliving the request-scoped lifetime the module docstring
claims. Latent today (no call sites, SEC2-W4).
Fix: cache on a salted digest of the value, or drop the cache and compile per scope.

### [SEC2-W6] No security response headers on any response
File: `backend/src/api/app.py` (no middleware registered)
Severity: medium
Live `GET /health` returns only `date`, `server`, `content-length`, `content-type`,
`x-request-id`. Missing `Content-Security-Policy`, `X-Content-Type-Options: nosniff`,
`X-Frame-Options`/`frame-ancestors`, `Referrer-Policy`, `Strict-Transport-Security`. This is
what makes SEC2-I2's JSON reflection worth a fix rather than nothing.
Fix: one header middleware in `create_app`, ordered inside `CorrelationIdMiddleware`.

### [SEC2-W7] Host-header-reflected redirect
File: `backend/src/api/app.py` (Starlette `redirect_slashes` default)
Severity: medium
`GET /health/` with `Host: evil.example` → `307` with `location: http://evil.example/health`,
verified over a raw socket. The redirect target is built from the untrusted `Host` header.
Fix: add `TrustedHostMiddleware` with an allow-list from `Settings`, and/or set
`redirect_slashes=False`.

### [SEC2-W8] `/docs` and `/openapi.json` are unauthenticated, and `/docs` loads assets from a third-party CDN
File: `backend/src/api/app.py` line 36
Severity: medium
Both return 200 with no auth. `/docs` is HTML that pulls `swagger-ui.css`/JS from
`cdn.jsdelivr.net` with no CSP and no SRI, so a CDN compromise executes script in the
application origin. `/openapi.json` will enumerate every guarded route once group B lands —
and `E1-S2-AC3` reads its route list from that document, so the exposure grows.
Fix: gate both behind an environment flag (off in production) or behind the E1-S1 auth layer,
and self-host the Swagger assets.

### [SEC2-W9] `/metrics` is unauthenticated — deferral defensible, but scope it
File: `backend/src/api/platform/routes.py` line 126
Severity: medium
Judged as the pack asks, on the deferral rather than the absence. What the endpoint actually
exposes at HEAD: the route inventory, per-route/method/status request counts, and latency
distributions. No PII, no secrets, no tenant data — so deferring auth to the `api-contracts.md`
amendment plus E1-S1 is **defensible**, and I am not filing it as a fresh BLOCK.
Two conditions on that judgement: (a) the endpoint is also the amplification surface in
SEC2-W1, so it should not stay open past E1-S1; (b) an interim, zero-contract-change mitigation
exists today — bind or firewall `/metrics` to the scrape network, or gate it on
`observability.enabled` plus a settings flag.

### [SEC2-W10] Frontend `Money.format()` grouping regex is quadratic — real, currently unreachable
File: `frontend/src/types/money.ts` line 78
Severity: medium
Untouched by every remediation commit. Isolated the cost to the lookahead alone (no `toFixed`
in the timed region), which settles round 2's disagreement about the sink:

| digits | ms |
|---|---|
| 1,000 | 0.5 |
| 4,000 | 5.7 |
| 16,000 | 100.8 |
| 32,000 | 417.1 |
| 100,001 | **4,116.5** |

Clean 4× per doubling — quadratic, confirmed. `MoneyText` takes `money: Money | string` and
calls `Money.fromWire` on the string with no magnitude bound, so a 100k-digit amount freezes the
tab for ~4 s (1M digits ≈ 400 s).
**Refutation that keeps it out of BLOCK:** there is no reachable path from attacker-controlled
input at HEAD. `MoneyText` has no consumer anywhere in `frontend/src` (it is an unwired leaf),
and the backend cannot deliver such a string: `Money.__init__` → `_quantize` rejects anything
beyond the 28-digit decimal context (`1e100`, `1e26`+2dp all raise `InvalidMoneyAmountError`,
verified), so the wire form is magnitude-bounded before it reaches the UI. This becomes
reachable the moment a page renders a money string from any source other than this backend.
Fix: bound the magnitude in `toQuantizedDecimal` (reject `abs(e) > 15` or similar) and/or group
digits with a linear loop instead of the lookahead.

### [SEC2-W11] Dev-dependency advisories: 1 critical + 1 high
File: `frontend/package.json`, `frontend/package-lock.json`
Severity: medium
`npm audit` at HEAD: **critical** `vitest` (arbitrary-file-read via the UI server / `@vitest/mocker`),
**high** `vite` (path traversal in optimized deps), moderate `esbuild`, `vite-node`,
`@vitest/mocker`. All five resolve to `devDependencies` — production deps are `decimal.js`,
`react`, `react-dom` only, none with an advisory. Not downgraded to INFO because the critical
one is a real developer-workstation exposure while `npm run test`/`dev` is listening.
Fix: bump `vite` / `vitest` to the patched majors and re-run `npm audit`.
Backend dependency tier is **unscanned** — see SEC2-I7.

## INFO Findings

### [SEC2-I1] `_escape_label` omits CR and every other C0 control character
File: `backend/src/api/platform/routes.py` line 78
Severity: low
The translation table covers `\`, `"`, `\n` only. A raw `\r` in a label value is invalid
exposition and would corrupt a scrape; no channel delivers one at HEAD (see B-1). Defence in
depth: escape or strip all `\x00-\x1f`, since the label inputs will broaden as routers land.

### [SEC2-I2] The 422 envelope reflects an attacker-chosen body key verbatim and uncapped
File: `backend/src/api/errors.py` lines 139–148
Severity: low
`handle_validation_error` uses only `errors[0]["loc"]`, so no rejected *value* is echoed — but
with `extra="forbid"` the offending **field name** is attacker-supplied and becomes the `field`
context value: a probe with a `<script>` field name came back as
`{"field":"body.<script>alert(1)</script>"}` with `content-type: application/json`. No execution
is demonstrable (JSON is not rendered as HTML by current browsers), but there is no `nosniff`
header (SEC2-W6) and no length cap on the reflected name (SEC2-W3).
Fix: cap `field` length and restrict it to an identifier charset before it enters the envelope.

### [SEC2-I3] `decimal.Overflow` escapes `Money.multiply` untyped
File: `backend/src/types/money.py` lines 89–99
Severity: low
Verified: `Money("1000.00").multiply(10 ** 999999)` raises `decimal.Overflow`, not
`InvalidMoneyAmountError` — the method catches only `InvalidOperation`. Any service passing an
attacker-influenced scalar gets an unhandled `ArithmeticError` and a 500. Not an information
leak: the 500 envelope is clean (`{"error":"InternalServerError","detail":"internal server error",
"context":{}}`, verified through the real middleware chain).
Fix: catch `DecimalException` (or `ArithmeticError`) and re-raise as `InvalidMoneyAmountError`.

### [SEC2-I4] The gate's own Prometheus parser will go blind on parameterized route templates
File: `.claude/hooks/lib/prom-parse.js` line 27
Severity: low
`^name(\{[^}]*\})?\s+(\S+)` is not quote-aware, so any series whose `route` label contains `}` —
i.e. every template like `/applications/{application_id}`, arriving with group B — fails the match
and is **silently skipped**, taking its request counts and latency buckets out of
`slo-check.js`'s error-rate and p95 with no warning. Not a product vulnerability and not
attacker-reachable, but it is the measurement path this gate trusts.
Fix: make the label-block match quote-aware, or have the sensor fail loudly on an unparsed
non-comment line.

### [SEC2-I5] No rate limiting anywhere
Severity: low
Nothing throttles any endpoint. Group A ships no login/reset/OTP route so there is nothing to
brute-force yet, but SEC2-W1/W2 are both amplification findings that a throttle would blunt.
Fix: land a limiter with the E1-S1 auth layer; make `/metrics` and `/health` exempt by design.

### [SEC2-I6] `server: uvicorn` disclosed on every response
Severity: low
Minor stack disclosure. Fix: `uvicorn --no-server-header` or strip it in the header middleware.

### [SEC2-I7] SAST and secrets tiers are unscanned, and the backend dependency tier with them
Severity: low
`gitleaks`, `semgrep` and `pip-audit` are unprovisioned, so the computational scan's clean
result covers neither SAST nor secrets nor Python dependencies. My inferential pass over the
changed set found **no** hardcoded credential, no `eval`/`exec`/`subprocess`/`pickle`/
`yaml.load`, no raw SQL, no `innerHTML`/`dangerouslySetInnerHTML`, and no direct
`os.environ`/`process.env` read (settings come from `pydantic-settings` with the `TRUELEND_`
prefix). Treat that as inferential coverage, not a tool pass.

### [SEC2-I8] Test-fixture credentials
Severity: low
`backend/tests/**` contains PAN/Aadhaar-shaped fixtures. None appear in production config. INFO
per the standing convention.

### [SEC2-I9] `specs/reviews/slo-verdict.json` is a concurrently-written shared artifact
Severity: low
My sensor run wrote it (port 8035); by the time I checked `git status` a sibling instance had
overwritten it with a port-8036 run. I deliberately did not restore it. My own measurement is
recorded in B-1 above. Treat that file as unreliable evidence for this round.

## Disposition table

| Item | Round 2 | Instance-2 verdict at HEAD | Basis |
|---|---|---|---|
| B-1 injection | BLOCK | **CLOSED** | 9 hostile paths → 0 forged series, 0 raw control chars, slo-check pass |
| B-2 cardinality (`route`) | BLOCK | **CLOSED** | 20,000 distinct paths → +1 series, +0.7 MB RSS |
| B-2 residual (`method`) | — | **WARN** (SEC2-W1) | 20,000 distinct methods → 300k series / 42 MB under `--http h11`; refuted under the shipped `httptools` |
| B-3 dropped `HTTPException.headers` | BLOCK | **CLOSED** | 405 → `Allow: GET`; 401 → `WWW-Authenticate: Bearer`; 404/422/500 all enveloped with `X-Request-ID` |
| B-4 quadratic grouping regex | disputed | **WARN** (SEC2-W10) | quadratic confirmed (4.1 s at 100k digits); no reachable caller, backend magnitude-bounded |
| SEC-003 int/bool + key scrubbing | WARN | **CLOSED** | int, `Decimal`, key, lowercase, spaced forms all `[REDACTED]`; hostile `__str__` dropped without raising |
| SEC-003 residual: key drop-rules | — | **WARN** (SEC2-W3) | DSN password egressed through a key; 5,000-char key uncapped |
| Redaction formatting bypass | WARN | **WARN, not escalated** (SEC2-W4) | `ba457bf` touched specs only; zero production call sites confirmed |
| `X-Request-ID` unbounded | WARN | **WARN** (SEC2-W2) | 5 MB reflected, 5,000,148 bytes logged, per request |
| Host-reflected redirect | WARN | **WARN** (SEC2-W7) | `location: http://evil.example/health` |
| Public `/docs` / `/openapi.json` | WARN | **WARN** (SEC2-W8) | 200 unauthenticated; CDN assets, no CSP/SRI |
| Missing security headers | WARN | **WARN** (SEC2-W6) | only 5 headers on `/health` |
| `lru_cache` PII retention | WARN | **WARN** (SEC2-W5) | PII recoverable from the cached pattern after scope teardown |
| `Money.multiply` bare `Overflow` | disputed | **INFO** (SEC2-I3) | `decimal.Overflow` confirmed; 500 body clean |
| `/metrics` no auth | WARN | **WARN, deferral accepted** (SEC2-W9) | no PII/secrets exposed; interim bind-scope recommended |
| `HEAD /health` → 405 | WARN | **INFO** (correctness, not security) | reproduced: 405 with `Allow: GET` |
| AC2 tests pass by construction / `uvicorn.access` comment | WARN | **out of security scope** | evidence-quality items for the code reviewer |

## Not tested, and why

- **`gitleaks` / `semgrep` / `pip-audit`** — absent from the environment (SEC2-I7). No SAST,
  secrets-history or Python-CVE coverage this round; my grep-plus-read pass over the 14 changed
  files is the only coverage for those classes.
- **Container / compose posture** — there is no `Dockerfile` or `docker-compose.yml` at HEAD
  (E15-S2 unbuilt), so I could not test the deployed protocol choice, the reverse-proxy header
  caps that would blunt SEC2-W2, or TLS/HSTS. SEC2-W1's severity is explicitly conditional on
  that file when it lands.
- **Auth / IDOR / privilege escalation / CSRF** — no authenticated or state-changing route
  exists in group A (only `GET /health` and `GET /metrics`), so these classes have no surface
  yet. `/metrics` auth is judged as a deferral in SEC2-W9.
- **Real-world log-sink behaviour for SEC2-W2** — measured against a file sink on this host;
  the disk-exhaustion timeline in a real deployment depends on rotation policy, which does not
  exist in the repo yet.
- **Sustained-load DoS thresholds** — I measured amplification factors, not time-to-outage; no
  load harness was run.
