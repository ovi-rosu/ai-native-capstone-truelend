# Security Review — TrueLend (group A) — INSTANCE 3 (runtime/empirical) — 2026-09-14

Range `14e9487..HEAD` (`9112495`). Scope per `specs/reviews/review-context-pack.md`:
the changed backend/frontend source and its immediate data-flow neighbours.

**Method: execution first.** Every claim below is backed by a live probe against a
booted app (`uvicorn src.api.app:app --port 8007`, plus a throwaway probe app that
adds PII-registering sync/async/failing routes to `build_fastapi_app()`), raw-socket
HTTP, `vitest` against the shipped TS module, and direct timing of the internals.
All probe scripts and the probe server were deleted/killed after the run.
Where I did not probe a vector I say so — see "Not probed".

## Summary
- BLOCK findings: 3
- WARN findings: 10
- INFO findings: 4
- Overall verdict: **BLOCK**

Two BLOCKs are HTTP-reachable at HEAD by an unauthenticated attacker with a single
request. One BLOCK is latent (needs a later story to render the component).

## BLOCK Findings

### [SEC3-001] Prometheus exposition-format injection into unauthenticated `/metrics`
File: `backend/src/api/platform/routes.py` lines 213-218 (sink);
`backend/src/api/middleware.py` line 75 + line 91 (source)
Severity: high · Level: BLOCK · Category: injection (OWASP A03) / A09 monitoring failure
Reachability: **HTTP-reachable at HEAD.** One unauthenticated GET. No auth, no proxy
(`verification.mode: local`, no `docker-compose.yml` until E15-S2).

The RED counter is keyed on `scope["path"]`, which Starlette hands over
**percent-decoded**, and `/metrics` interpolates that raw string into the exposition
line with an f-string and no escaping of a quote, a backslash or a newline.

Live evidence — one request to a path whose percent-encoding decodes to
`/inj"} 999999` + newline + `injected_metric{a="b"} 42 #` produced these lines in the
unauthenticated `/metrics` body:

```
http_requests_total{method="GET",route="/inj"} 999999
injected_metric{a="b"} 42 #",status="404"} 1
```

and a second payload produced a standalone forged series `injected2_metric 777`.
A bare `%22` alone also escapes the label: `route="/quote"test"`.

Impact: any unauthenticated client can (a) forge `http_requests_total` samples and so
poison the RED counters the project's own runtime-SLO sensor consumes, (b) inject
arbitrary new metric series into the scrape, and (c) emit a malformed exposition body
so Prometheus rejects the whole scrape — blinding monitoring. Integrity of
security-relevant telemetry is lost.

Refutation attempted and failed: no escaping exists on any path between
`scope["path"]` and the rendered line; `/metrics` has no auth; Starlette does not
reject `%22` or `%0A` in a path (verified — the 404 was served and the label written);
there is no reverse proxy in the deployment this gate verifies.

Fix: key the counter on the **matched route template** (the resolved
`scope["route"].path`), not the raw path, and escape backslash, quote and newline in
every rendered label value per the Prometheus text-format spec. Bucket unmatched
requests under one fixed label.

### [SEC3-002] Unbounded metric cardinality → unauthenticated memory-exhaustion DoS
File: `backend/src/api/middleware.py` line 49 (`_request_counts`), line 75 (write),
line 91 (raw path used as the key); rendered by
`backend/src/api/platform/routes.py` line 213
Severity: high · Level: BLOCK · Category: A04 insecure design (resource exhaustion)
Reachability: **HTTP-reachable at HEAD**, unauthenticated, no rate limit.

`_request_counts` is a process-global `Counter` keyed on `(method, raw_path, status)`
with **no eviction, no cap and no route normalisation**. Every distinct URL an
attacker invents — including 404s — creates a permanent key.

Live measurements against the booted app:

| step | unique paths total | server RSS | `GET /metrics` |
|---|---|---|---|
| baseline | — | 64.2 MB | ~1.1 MB |
| +10 000 (200-char paths) | 10 000 | 70.1 MB | 3.63 MB / 20 257 lines |
| +10 000 | 20 000 | 72.8 MB | 6.18 MB / 30 257 lines |
| +10 000 | 30 000 | 78.7 MB | 8.74 MB / 40 257 lines |

Linear and monotonic: ~500 B of permanent process memory and ~290 B of permanent
`/metrics` body per unique path, at ~550 req/s from one client on loopback. h11 caps
the request line (a 10 000-char path is accepted, 404ed and counted; a 100 000-char
path is rejected with 400 before the app and correctly leaves `/metrics` unchanged),
so the ceiling is roughly 10-64 KB pinned *forever* per request. Nothing frees it; the
only reset is `reset_request_counters()`, which is test-only.

Second-order: the same growth makes the unauthenticated `/metrics` response itself an
amplifier — it reached 9.1 MB in this session, and a 15 s Prometheus scrape would then
move ~35 MB/min.

Refutation attempted and failed: no `maxsize`, no TTL, no allow-list, no auth on
`/metrics`, and no rate limiting anywhere (30 000 unauthenticated requests were
accepted back-to-back without throttling).

Fix: key on the matched route template so cardinality is bounded by the number of
registered routes.

### [SEC3-003] Quadratic thousands-separator regex in `Money.format()` freezes the UI thread
File: `frontend/src/types/money.ts` line 78 (the `\B(?=(\d{3})+(?!\d))` lookahead),
reached from `frontend/src/ui/components/MoneyText.tsx` line 71
Severity: high · Level: BLOCK · Category: A04 insecure design (ReDoS / algorithmic complexity)
Reachability: **not reachable at HEAD** — `frontend/src` contains only `money.ts` and
`MoneyText.tsx`; there is no `index.html`, `main.tsx` or route that renders it.
Becomes reachable the moment any story renders `MoneyText` with a value that did not
come from the backend's `Money` (a second API, a stored value, a pasted field):
`MoneyTextProps.money` is typed `Money | string`, so an arbitrary string is accepted
by design.

The lookahead is re-evaluated to end-of-string at every position, so cost is O(n²) in
the digit count while the *input* is a handful of bytes.

Live evidence, measured against the **shipped** module via `vitest`
(`Money.fromWire(v)` then `.format()`):

| wire string (bytes) | `toWire()` | `format()` | digits |
|---|---|---|---|
| `"1234.50"` (7) | 0.1 ms | 0.1 ms | 7 |
| `"1e1000"` (6) | 0.0 ms | 0.4 ms | 1 004 |
| `"1e10000"` (7) | 0.1 ms | **36.8 ms** | 10 004 |
| `"1e50000"` (7) | 0.1 ms | **987.1 ms** | 50 004 |
| `"1e100000"` (8) | 0.3 ms | **4 152.2 ms** | 100 004 |
| `"1e1000000"` (9) | 29.7 ms | **did not complete in 100 s** (process killed) | 1 000 004 |

10x the digits costs 113x the time — quadratic, extrapolating to minutes at 10^6
digits and hours at 10^7. `toWire()` is cheap; the entire cost is the regex. Nine
bytes of JSON permanently freeze the browser main thread (no worker, no chunking).

Refutation attempted and failed: `toQuantizedDecimal` only rejects non-finite values,
and decimal.js's default `maxE` is 9e15, so `1e1000000` is finite and passes;
`toDecimalPlaces(2)` does not bound the exponent; nothing caps the digit count
anywhere between `fromWire` and `format`.

Fix: bound the magnitude in `toQuantizedDecimal` (reject anything outside a sane money
range) **and** replace the lookahead grouping with a linear formatter
(`Intl.NumberFormat`, or chunk the integer part).

## WARN Findings

### [SEC3-004] `X-Request-ID` accepted at unbounded length and reflected into the response and every log line
File: `backend/src/api/middleware.py` lines 86-88, 74, 76;
`backend/src/config/logging.py` line 183
Severity: medium · Category: A04 insecure design (amplification) / A09
Reachability: HTTP-reachable at HEAD.

The inbound header is taken verbatim with no length, charset or format validation.
Live: a **5 000 000-byte** `X-Request-ID` was accepted (200), echoed in full in the
response header (5 000 219-byte response) and written verbatim into the log line
(`request_id` length 5 000 000; the log file reached 6.2 MB after 20 requests). 1 MB
and 100 KB values likewise accepted. A failing request emits 3 log lines, each
carrying the whole value, so the log multiplier is ~3x.

Note the redaction filter never sees it: `JSONLogFormatter` writes
`request_id_var.get()` straight into the payload, outside `RedactionFilter`'s reach.

Fix: validate the inbound id (e.g. `^[A-Za-z0-9._-]{1,64}$`) and fall back to a
generated uuid4 hex when it does not match, rather than trusting client input.

### [SEC3-005] Redaction is bypassed by re-formatting a registered value
File: `backend/src/config/logging.py` lines 94-119 (`_SEPARATOR_RUN`, `_redaction_pattern`)
Severity: medium · Category: A02/A09 (sensitive data exposure in logs)
Reachability: **not reachable at HEAD** — no production code calls
`register_sensitive` (only `middleware.py` opens the scope and `errors.py` consumes
`scrub_text`). Reachable at the origination story that registers real PAN/Aadhaar.

`_redaction_pattern` tolerates only case differences and at most **4** characters from
`[ \t-]` between consecutive characters of the value. Every other rendering of the
same value reaches the sink in clear. Live results with `ABCDE1234F` registered:

| rendering | result |
|---|---|
| exact / lowercase / spaced every char / up to 4 dashes | redacted (correct) |
| 5+ dashes, 5+ spaces, 5+ tabs | **leaked** |
| newline, dot, underscore, slash, NBSP (U+00A0), soft hyphen (U+00AD) as separator | **leaked** |
| fullwidth digits/letters (NFKC-normalisable), Cyrillic homoglyph, Devanagari digits | **leaked** |
| percent-encoded, base64 | **leaked** |

Worse, the **literal-only branch** (lines 115-116): a registered value that itself
contains a separator is matched byte-for-byte with `re.escape`, so registering
`SALARYDOC-2024-0001` fails to redact `SALARYDOC 2024 0001`,
`SALARYDOC--2024--0001` or `SALARYDOC20240001`. An Aadhaar submitted in the spaced
form people actually type falls into exactly this branch. The likely production shape
— normalise on input, register the normalised value, log the raw submitted one —
leaks.

There is also no pattern-based backstop: a PAN or Aadhaar that no one remembered to
register is logged in the clear. Redaction coverage equals developer discipline.

Fix: normalise both the registered value and the haystack (NFKC plus strip
non-alphanumerics) and match on the normalised form, mapping spans back; or add a
pattern-based backstop for PAN/Aadhaar shapes on top of the value list.

### [SEC3-006] Registered values shorter than 6 characters are silently never redacted
File: `backend/src/config/logging.py` line 94 (`_MIN_REDACTABLE_LENGTH = 6`), line 124
Severity: medium · Category: A02 · Reachability: latent (same as SEC3-005)

Live: registering `12345` leaves `cvv=12345` untouched; `123456` is redacted. The skip
is silent — the caller gets no error and no warning, so `register_sensitive(otp)` for
a 4- or 5-digit OTP/PIN/CVV is a no-op that looks like protection.

Fix: keep the length floor, but make it loud — raise or warn when a caller registers a
value the filter will refuse to match.

### [SEC3-007] `sanitise_context` / `detail` is a type allow-list, not a content filter — PII, keys, SQL and paths still egress
File: `backend/src/api/errors.py` lines 66-78, 91, 107
Severity: medium · Category: A01/A02 (excessive data exposure)
Reachability: **not reachable at HEAD** (no route raises `AppError` or a detailed
`HTTPException`); this is the designated egress path for every later story.

Live probe — an `AppError(..., 409, context={...})` whose values were **not**
registered as sensitive returned all of these to the client in the response body:

- `"pan": "ABCDE1234F"`
- `"aadhaar": "123412341234"`
- `"api_key": "sk-live-AAAABBBBCCCCDDDDEEEE"`
- `"jwt": "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.sig"`
- `"sql": "SELECT * FROM applicants WHERE pan = 'ABCDE1234F'"`
- absolute server paths

Only a credential-bearing URI, nested mappings/lists, and strings over 200 chars were
dropped. `detail` is passed through `scrub_text` but has **no length cap and no
content filter at all**: `HTTPException(401, detail="bad token ... for pan ABCDE1234F")`
egressed verbatim. So the real guarantee is "registered values are removed", not
"`context` is sanitised" — while the module docstring (lines 13-16) claims the latter
and will mislead the next story author into putting PII in `context`.

Positive control: when the value *was* registered, both `detail` and `context` came
back `[REDACTED]`.

Fix: make `context` a **key** allow-list per error type, cap `detail`, and soften the
docstring to state the real guarantee.

### [SEC3-008] `/docs`, `/redoc` and `/openapi.json` served unauthenticated
File: `backend/src/api/app.py` line 141 (`FastAPI(title=settings.service_name)`)
Severity: medium · Category: A05 security misconfiguration · Reachability: HTTP-reachable at HEAD

Live: `/docs` 200 (1 015 B), `/redoc` 200 (897 B), `/openapi.json` 200 (4 094 B),
disclosing the full API surface, operation ids, schemas and docstrings, with no
environment gating. Low impact today (two platform endpoints), high as soon as the
origination and underwriting routers land.

Fix: `FastAPI(..., docs_url=None, redoc_url=None, openapi_url=None)` unless a new
`Settings` flag (default off outside development) enables them.

### [SEC3-009] No security response headers on any response
File: `backend/src/api/app.py` (no header middleware), `backend/src/api/middleware.py` line 74
Severity: medium · Category: A05 · Reachability: HTTP-reachable at HEAD

Live raw header dump of `GET /health` — the complete set is `date`, `server`,
`content-length`, `content-type`, `x-request-id`. Missing:
`Content-Security-Policy`, `X-Content-Type-Options: nosniff`,
`X-Frame-Options`/`frame-ancestors`, `Referrer-Policy`,
`Strict-Transport-Security`, and `Cache-Control: no-store` on error/JSON responses.
`/docs` serves HTML with CDN-loaded scripts under no CSP at all.

Fix: add a small header middleware alongside `CorrelationIdMiddleware`.

### [SEC3-010] No rate limiting and no request-size limiting on any endpoint
File: `backend/src/api/app.py`, `backend/src/api/platform/routes.py`
Severity: medium · Category: A04 · Reachability: HTTP-reachable at HEAD

Live: 30 000 unauthenticated requests accepted back-to-back at ~550 req/s with no
throttling, plus a 5 MB header (SEC3-004). This is the precondition that turns
SEC3-002 from a slow leak into a practical OOM.

Fix: throttle per-IP at the app or ingress edge; cap header and body size explicitly.

### [SEC3-011] `frontend/package-lock.json` is not committed
File: `frontend/package.json` (new in this diff)
Severity: medium · Category: A06/A08 supply chain · Reachability: N/A (build-time)

`git ls-files frontend` lists `package.json` but **not** `package-lock.json`
(`git ls-files --error-unmatch frontend/package-lock.json` reports it does not match
any file known to git); the lockfile exists on disk only, and `.gitignore` does not
ignore it — it was simply never added. Every dependency uses a caret range, so CI
resolves a different tree from the one audited here and the `npm audit` result below
is not reproducible.

Fix: commit `frontend/package-lock.json` and use `npm ci` in CI.

### [SEC3-012] Known advisories in the new frontend manifest (1 critical, 1 high, 3 moderate) — dev-only
File: `frontend/package.json` (`vite: ^5.4.3`, `vitest: ^2.0.5`)
Severity: medium (downgraded from the audit's critical/high — see refutation) ·
Category: A06 vulnerable and outdated components

`npm audit` metadata: `{"moderate":3,"high":1,"critical":1,"total":5}`

| pkg | audit severity | advisory |
|---|---|---|
| `vitest` <=4.1.10 (direct) | critical 9.8 | GHSA-5xrq-8626-4rwp — arbitrary file read and execution when the Vitest **UI** server listens |
| `vite` <=6.4.2 (direct) | high 7.5 | GHSA-fx2h-pf6j-xcff — `server.fs.deny` bypass on Windows alternate paths |
| `vite` | moderate | GHSA-4w7w-66w2-5vf9 (`.map` path traversal), GHSA-v6wh-96g9-6wx3 (NTLMv2 hash disclosure on Windows) |
| `esbuild` <=0.24.2 | moderate 5.3 | GHSA-67mh-4wv8-2f99 — any website can read dev-server responses |
| `@vitest/mocker` | moderate 5.9 | GHSA-82fw-gwwq-j7x9 |

Why not BLOCK: both packages are `devDependencies`, so nothing ships to production;
and the critical's precondition cannot occur in this tree — `@vitest/ui` is **not
installed** (`ls frontend/node_modules/@vitest/` yields only
`expect mocker pretty-format runner snapshot spy utils`) and the `test` script is
`vitest run`, never `--ui`. Kept at WARN rather than dropped because `npm run dev` on
Windows is this project's documented workflow, and GHSA-fx2h-pf6j-xcff plus
GHSA-v6wh-96g9-6wx3 are exploitable there against a developer workstation.

Fix: bump `vite`/`vitest` (major), or record a dated waiver naming the
`@vitest/ui`-absence as the compensating control.

### [SEC3-013] Registered PII is retained in a process-global LRU cache past the request scope
File: `backend/src/config/logging.py` line 102 (`@lru_cache(maxsize=256)` on `_redaction_pattern`)
Severity: medium · Category: A02 (sensitive data retention) · Reachability: latent (needs `register_sensitive`)

The cache is keyed on the sensitive value itself and lives for the process lifetime,
so up to 256 PAN/Aadhaar values (and compiled patterns embedding their characters)
stay resident long after the request that registered them ended. Live: after
`register_sensitive(pan, aadhaar)` followed by `end_redaction_scope(...)`,
`_redaction_pattern.cache_info()` reported `currsize=2`, and a `gc.get_objects()` scan
recovered **2** compiled patterns that de-escape back to the retired PII — while
`scrub_text` had correctly become a no-op. This contradicts the module's
"request-scoped" claim and leaves PII in core dumps and heap inspection indefinitely.

Fix: key the cache on a salted hash of the value, or clear/scope it at
`end_redaction_scope`, accepting the recompilation cost.

## INFO Findings

### [SEC3-014] `decimal.Overflow` escapes `Money.multiply` un-wrapped
File: `backend/src/types/money.py` line 101
Severity: low · Reachability: latent (no route accepts a `MoneyField` at HEAD)

`Money("1.00").multiply(Decimal("1" + "0"*10**6))` raises a raw `decimal.Overflow` in
5.7 ms — the multiplication on line 101 happens outside any `try`, and `Overflow` is
not an `InvalidOperation`, so `_quantize`'s handler never sees it. A caller following
the documented contract (`InvalidMoneyAmountError` for bad input) will miss it, so it
becomes an unhandled 500 once a money field reaches a route.
Fix: wrap the arithmetic in `add`/`subtract`/`multiply` and re-raise as
`InvalidMoneyAmountError`.

### [SEC3-015] Server banner disclosed
File: response headers produced from `backend/src/api/app.py`
Severity: low. `server: uvicorn` on every response.
Fix: `--no-server-header`, or strip it in the header middleware.

### [SEC3-016] `_scrub` cost is O(registered values x message length)
File: `backend/src/config/logging.py` lines 122-129
Severity: low. Measured with the cache warm, 256 registered values against a
10 KB / 100 KB / 1 MB / 5 MB message: 7.9 / 79.9 / 726.6 / 3 611.9 ms. Linear in both
factors (not catastrophic) and **not** client-controllable today, because the one
client-controlled unbounded string (`request_id`) is written by the formatter outside
the filter. Worth noting as a per-log-line multiplier before a story logs large
payloads.

### [SEC3-017] `redact_values` remains exported with a documented footgun
File: `backend/src/config/logging.py` lines 56-71
Severity: low. Its own docstring states that values withdrawn on exit mean an escaping
exception is logged unscrubbed — the exact defect SEC-002 was raised for. It has no
production caller, but leaving a known-unsafe API exported invites the regression.
Fix: make it private/test-only, or delete it.

## Refuted candidates (with the live evidence that refuted them)

### R1 — Cross-request PII bleed / request_id bleed on the deliberately-unwound failure path — REFUTED
The assignment's highest-value hypothesis. `middleware.py` lines 96-102 re-raise
without resetting `request_id_var` or the redaction scope, and `_sensitive_values`
holds a mutable set mutated in place. I probed it two ways against a booted server
with a probe app exposing `areg`/`afail`/`sreg`/`sfail` (register PII then succeed or
raise, async and sync/threadpool) and `witness`/`switness` (register **nothing**, log
all 64 candidate PII literals — a `[REDACTED]` there proves an inherited set):

1. **Randomised concurrency:** 1 200 requests, 40 concurrent keep-alive connections,
   mixed route kinds → 793 x 200, 403 x 500, 4 transport errors, 2 802 log lines.
2. **Forced adjacency:** 800 strictly serial `fail(PII)` then `witness` pairs on a
   **single** keep-alive connection, covering all four sync/async permutations
   (async→async, sync→sync, async→sync, sync→async).

Results across both: **0** invalid JSON lines (2 802 + 1 600 parsed), **0** witness
lines containing `[REDACTED]`, **0** foreign PII values in any line, **0** own-PII
leaks in the 808 logged tracebacks, **0** empty `request_id` on any request-scoped
line, **0** mismatches between the handler-observed `request_id`, the log line's
`request_id` and the echoed response header, and all 800 witness handler lines showed
all 64 literals in clear (correct — nothing was registered there).

Mechanism that refutes it: `uvicorn/protocols/http/h11_impl.py:259` creates each
request's task as
`loop.create_task(cycle.run_asgi(app), context=contextvars.Context())` — a **fresh
empty context per request** — so the intentionally un-reset contextvars die with the
task and cannot reach the next request on the same connection; and
`anyio.to_thread.run_sync` runs sync handlers via a copy of that per-request context,
which is why mutating the shared set works while staying confined. The design comment
is correct. Caveat recorded under "Not probed": this is a uvicorn implementation
detail, not an ASGI guarantee — a server that reused a context would break it.

### R2 — Log injection breaking the JSON log line — REFUTED
`X-Request-ID: a"b}\c{"evil":1}` (and `a%0d%0aX-Fake: 1`, and UTF-8 multibyte) were
accepted and reflected, and the emitted line stayed **one valid JSON object** —
`json.dumps` escapes the quote and braces are inert inside a string. 4 402 log lines
parsed across all probe phases, **0** invalid.

### R3 — HTTP response splitting / request-header injection — REFUTED
Raw-socket bytes, responses captured:
- `X-Request-ID: abc\r\nX-Injected-Header: pwned` → h11 parses the second line as a
  *separate request header*; only `x-request-id: abc` comes back, no injected
  response header.
- bare `\n` in the value → `HTTP/1.1 400 Bad Request` before the app.
- `\x00` in the value → `400`.
- obs-fold continuation (`\r\n  continued: yes`) → `400`.
- duplicate `X-Request-ID` → first value wins, single header out.

### R4 — ANSI / terminal escape injection into the log stream — REFUTED
`X-Request-ID: \x1b[31mRED\x1b[0m\x1b]0;title\x07` → `HTTP/1.1 400 Bad Request`; h11
rejects the ESC byte in a field value, so it never reaches the logger or the response.

### R5 — SEC-001 ReDoS in `_redaction_pattern` — CONFIRMED FIXED (four new shapes)
The pack asked for a *different* backtracking shape. Four the orchestrator did not
try, each with the cache cleared first:

| shape | value len | haystack len | time |
|---|---|---|---|
| `"A"*n` vs `("A"+"-"*4)*5000` | 20→320 | 25 000 | 0.31 → 2.81 ms |
| `"A"*n` vs `" \t-"*66666` | 20→160 | 199 998 | 0.63 → 0.64 ms |
| `"A"*n+"Z"` (fails at the last char) vs `("A"+"-"*4)*5000` | 21→321 | 25 000 | 2.76 → **37.41 ms** |
| `"AB"*n+"Z"` vs `"AB-"*20000` | 41→161 | 60 000 | 7.95 → 28.11 ms |
| 10-char PAN vs a 5 MB haystack | 10 | 5 000 000 | 40.94 ms |

Every curve is linear in value length x haystack length; doubling the value doubles
the time. No exponential blow-up. Structural reason: a value containing a separator
takes the literal `re.escape` branch, so the tolerant run and a literal separator are
never ambiguous, and the run itself is bounded at `{0,4}`.

### R6 — Backend `Money` decimal DoS (prior SEC-008's "~10 s CPU") — REFUTED
Each case in its own process with a 30 s hard timeout; **nothing timed out**:

| input | result | time |
|---|---|---|
| `Money("1"+"0"*10**6)` | rejected | 8.1 ms |
| `Money("1"+"0"*10**7)` (10 MB of digits) | rejected | 84.8 ms |
| `Money("0."+"9"*10**7)` | ok | 55.5 ms |
| `Money("0."+"9"*10**7).add(same)` | ok | **109.2 ms** (worst measured) |
| `Money("1E999999")`, `1E1000000`, `1E-999999`, `1E`+`9`*100 | rejected/ok | <=0.1 ms |
| `multiply(Decimal("1E999999"))` | rejected | 0.0 ms |
| `Money("1"*10**7 + ".5")` | rejected | 82.2 ms |

Cost is linear in input *bytes* (~11 ms per MB of digits) with no amplification: a
10 s burn would need roughly 1 GB of request body, which the transport bounds first.
Every pathological exponent is rejected in under 0.1 ms. The one residual is SEC3-014
(wrong exception type, not a DoS). No route accepts a money value at HEAD.

### R7 — 422 handler echoing the rejected input — REFUTED
`POST` with `{"pan": "ABCDE1234F", "amount": "not-an-int"}` and with a missing field
both returned exactly
`{"error":"ValidationError","detail":"request validation failed","context":{"field":"body.amount"}}`
— the submitted PAN did not appear in either response.

### R8 — CORS misconfiguration — REFUTED
No CORS middleware is registered; no `Access-Control-Allow-Origin` on any response;
`OPTIONS /health` with `Origin: https://evil.example` returned `405 Method Not
Allowed` with no CORS headers.

### R9 — SQLi / command injection / path traversal / SSRF / insecure deserialisation — REFUTED (no sink)
A scoped grep of `backend/src` for
`subprocess|os.system|popen|pickle|yaml.load|eval(|exec(|open(|requests.|httpx.|urllib|execute(`
returned only false positives on `scrub_text`/`sanitise_context`. Group A has no
repository, service, filesystem, outbound-HTTP or deserialisation code, so none of
these sinks exist in the change set.

### R10 — XSS in `MoneyText` — REFUTED
`MoneyText.tsx` line 71 renders `<span>{value.format()}</span>` — a React text child,
auto-escaped. A scoped grep of `frontend/src` for
`dangerouslySetInnerHTML|innerHTML|eval(|new Function` returned nothing.

### R11 — Hardcoded secrets — REFUTED
A scoped grep of `backend/src` and `frontend/src` for assignments of string literals
to `password|secret|api_key|apikey|token|private_key` returned nothing. `Settings`
sources every field from `TRUELEND_*` environment variables and holds only
`service_name`, `log_level`, `version`.

## Not probed (explicitly)

Recorded so that a `pass` on these is not mistaken for evidence of absence:

1. **WebSocket / non-HTTP scopes.** `middleware.py` line 82 returns early for
   `scope["type"] != "http"`, so a websocket would get **no** redaction scope and
   **no** request id. No ws routes exist, so I did not probe it. Flagging the shape
   for the story that adds one.
2. **Multi-worker behaviour.** `_request_counts` is per-process, so `/metrics` under
   `--workers N` reports one worker's slice. Not probed (single-worker boot only).
3. **Reverse-proxy / container deployment.** `docker-compose.yml` does not exist until
   E15-S2; whether an ingress would normalise `%22`/`%0A` (SEC3-001) or cap header
   size (SEC3-004) is untested and must not be assumed.
4. **Auth / authz / IDOR / privilege escalation / CSRF / session handling.** No auth
   layer, no cookies, no state-changing endpoint and no resource ids exist in group A.
   Nothing to probe; all three endpoints are unauthenticated by design at this stage.
5. **Backend dependency audit.** `backend/pyproject.toml` is not in `14e9487..HEAD`,
   so the manifest step does not apply; I ran no `pip-audit`.
6. **Log retention / rotation / sink ACLs.** `configure_logging` attaches a bare
   `StreamHandler`; where stdout lands, its rotation and who can read it belong to the
   deploy story. Not probed.
7. **`_redaction_pattern` cache thrash above 256 distinct values** (repeated
   recompilation under load) — noted as a consequence of SEC3-013, not measured.
8. **TLS / transport.** Booted over plain HTTP on loopback; no HTTPS/HSTS posture
   assessed.

## Probe hygiene
The probe server (PIDs 42636 and 71968 on port 8007) was killed; no listener remains
on 8007. All scratch files (`backend/_probe_*.py`, `backend/_probe_*.log`,
`backend/_probe_expect.txt`, `frontend/_probe_money.mjs`,
`frontend/tests/unit/_probe_redos.test.ts`) were deleted and
`git status --porcelain backend frontend` is clean. No product file was modified —
this instance only reviews.
