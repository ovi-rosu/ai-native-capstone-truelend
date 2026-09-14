# Security Review — TrueLend (Horizon Bank loan origination) — 2026-09-14

**Gate:** `/gate --group A` (re-run, round 2) · **Instance:** 1 of 3 (independent)
**Range:** `14e9487..HEAD` · **HEAD:** `9112495` · **Base:** `14e9487`
**Group:** A · **Stories:** E15-S1, E9-S1, E11-S1
**Scope read:** `specs/reviews/review-context-pack.md`, `git diff 14e9487..HEAD -- backend frontend`,
the 27 files it touches, and their immediate data-flow neighbours. No repo-wide grep.
`.claude/state/uvicorn.log` not read.

## Summary

- **BLOCK findings: 3** (severity `high`)
- **WARN findings: 9** (severity `medium`)
- **INFO findings: 10** (severity `low`)
- **Overall verdict: BLOCK**

Prior-BLOCK disposition: **SEC-001 closed** (confirmed fixed; a fresh adversarial
sweep of five *different* backtracking shapes found nothing — the axis is clean).
**SEC-002 closed** (the request-scoped design genuinely works, proven on both the
async and the threadpool handler path). **SEC-003 partially closed** — the new
`sanitise_context` allow-list stops string PII and the canonical credential URI,
but two of its four value paths bypass scrubbing entirely (SEC-103, new BLOCK).
**SEC-004/005 unchanged** at HEAD and re-rated with the CRLF/log-injection sub-claim
explicitly refuted. **SEC-010/011 unchanged**; the lockfile is not merely missing,
it is actively `.gitignore`d.

Two of the three BLOCKs are new and were found in the code the fix commits added
(`/metrics`, shipped by `9112495`). Both are unauthenticated and proven live.

### BLOCK reachability framing

This distinction was disputed last round, so every BLOCK carries it explicitly.

| ID | HTTP-reachable at HEAD? | Evidence |
|---|---|---|
| SEC-101 | **Yes** — live, unauthenticated, no precondition | 100,000 counter keys created over one keep-alive connection in 18.6 s against `uvicorn src.api.app:app` |
| SEC-102 | **Yes** — live, unauthenticated, no precondition | forged sample `http_requests_total{...,route="/forged",...} 424242` read back from `GET /metrics` on the live server |
| SEC-103 | **No** — latent until a later story wires it | nothing in `backend/src/**` calls `register_sensitive`/`redact_values` or raises `AppError`; reachable the moment a group B/E story uses `context` as designed |

SEC-103 is nevertheless filed at BLOCK because the defective artefact *is* group A's
deliverable: it is the designated PII control on the outbound channel, and it was
demonstrated passing registered PII through unmodified. The exploit is a downstream
story away, not an attacker step away.

---

## BLOCK Findings

### [SEC-101] Unbounded metric cardinality → unauthenticated memory exhaustion
**File:** `backend/src/api/middleware.py` line 75 (writer), line 49 (store), `backend/src/api/platform/routes.py` line 129 (reader)
**Severity:** high · **Level:** BLOCK · **Category:** dos
**HTTP-reachable at HEAD:** yes, unauthenticated, no precondition.

The RED counter is keyed on the **raw request path** rather than the matched route
template, and the store is a process-global `collections.Counter` with no bound, no
TTL and no eviction — the only reset is a test helper. Every distinct URL an
anonymous client invents becomes a permanent key, including URLs that route
nowhere and return 404: the counter is incremented inside the `http.response.start`
wrapper, which runs for *every* response, before any routing decision matters.

Measured at HEAD:

| Probe | Result |
|---|---|
| 500 unique 404 paths (TestClient) | 500 counter keys retained, 0 evicted |
| 100,000 unique 404 paths (live uvicorn, one keep-alive connection) | 18.6 s total, ~4,900 req/s, `GET /metrics` body grew 0 → **9.08 MB**, strictly linear, no eviction |
| retained bytes per key (`tracemalloc`, 200k keys) | **191 B/key** → 1M keys ≈ 191 MB, 10M keys ≈ 1.9 GB |
| max path length accepted | 8,000 chars (404, still counted) → ~8.2 KB **per key** |

Two amplifications compound it. First, an 8 KB path at the measured ~4,900 req/s
retains roughly 40 MB/s of unreclaimable heap — about a gigabyte a minute from a
single connection, with no auth and no throttle anywhere in the stack (see
SEC-122). Second, `GET /metrics` renders the whole snapshot into a Python list and
joins it, so one 40-byte unauthenticated request already returns 9 MB after a
20-second flood (≈47,000x amplification) and grows without bound — the render is
itself a second memory spike on top of the retained state.

**Fix:** key the counter on the **matched route template**, not the raw path —
read `scope["route"].path` / `request.scope.get("route")` after routing, and bucket
anything unrouted under a single fixed `"<unmatched>"` label. That makes cardinality
a function of the route table, which is the Prometheus contract for a label. Also
cap the counter (reject new keys past a fixed ceiling) as defence in depth, and
prefer a real `prometheus_client` registry over a hand-rolled `Counter`.

---

### [SEC-102] Prometheus exposition injection via unescaped path in a metric label
**File:** `backend/src/api/platform/routes.py` lines 129-133
**Severity:** high · **Level:** BLOCK · **Category:** injection
**HTTP-reachable at HEAD:** yes, unauthenticated, no precondition.

The exposition line is built by f-string interpolation of the raw path into a
quoted label value, with no escaping of `"`, `\` or newline. ASGI `scope["path"]`
is **percent-decoded**, so `%22` and `%0A` in the request target arrive as a literal
quote and a literal newline. An anonymous client therefore controls line structure
in the `/metrics` output.

Proven against a real `uvicorn` server over raw HTTP (not just TestClient): a single
`GET` with a percent-encoded path payload caused `GET /metrics` to return, as its own
line, a fully forged sample:

```
http_requests_total{method="GET",route="/x"} 999
http_requests_total{method="GET",route="/forged",status="200"} 424242
```

A plain `%22` also breaks label quoting (`route="/y"quoted"`), which is enough to make
a scraper reject the payload outright.

Impact is monitoring integrity and availability of the observability channel: an
attacker can forge arbitrary counter names and values into the operator's
time-series database, or corrupt the exposition so nothing is ingested at all. This
project's own runtime-SLO sensor reads `/metrics` for the `{error_rate_pct: 1,
p95_ms: 500}` SLO, so forged samples can mask a real breach — an attacker-controlled
input to a control the harness itself trusts.

**Fix:** escape label values per the Prometheus exposition spec (`\\` → `\\\\`,
`"` → `\"`, newline → `\n`) at render time, and — jointly with SEC-101 — stop using
the raw path as a label at all, so the label value comes from a fixed route-table
allow-list rather than from the request.

---

### [SEC-103] `sanitise_context` bypass: int values and mapping keys skip scrubbing entirely
**File:** `backend/src/api/errors.py` lines 155-183 (`_scalar` line 162, key handling line 182)
**Severity:** high · **Level:** BLOCK · **Category:** sensitive-data-exposure
**HTTP-reachable at HEAD:** **no** — latent. Nothing in `backend/src/**` raises
`AppError` or calls `register_sensitive`; both are exercised only by tests. Reachable
as soon as any group B/E story populates `context`, which is the field's documented
purpose (`src/types/errors.py` cites E4-S4-AC2).

`sanitise_context` applies its three protections — credential-URI drop, 200-char cap,
`scrub_text` — only on the `str` branch. Two other paths reach the wire unfiltered:

1. **`int`/`bool` values are returned verbatim** (`_scalar`, line 162) and never see
   `scrub_text`. Aadhaar is a 12-digit number, as are account and phone numbers, so
   `int` is the natural representation a developer will reach for.
2. **Mapping keys are only `str(key)`-coerced** (line 182) — no scrub, no length cap,
   no credential-URI check. A key is as attacker-relevant as a value; `{pan: "..."}`
   is an ordinary shape for a per-field error map.

Demonstrated at HEAD. With `register_sensitive("ABCDE1234F", "234512345678")` active
and a `409 AppError`, the response body shows the control firing on the string path
and silently not firing on the other two, **in the same envelope**:

```json
{ "error": "AppError",
  "detail": "rejected for PAN [REDACTED]",
  "context": { "pan": "[REDACTED]",
               "aadhaar_int": 234512345678,
               "ABCDE1234F": "pan-as-key" } }
```

The registered Aadhaar egressed as an integer and the registered PAN egressed as a
key, to an unauthenticated HTTP client, while the identical values were correctly
redacted one field away. Note the logs for the same request were clean — this is
purely the outbound-wire control, which is exactly the channel SEC-003 was about.

**Fix:** in `_scalar`, coerce non-string scalars through `scrub_text(str(value))` and
re-type only after scrubbing (keep `Decimal` → `str` as-is); in `sanitise_context`,
run keys through the same pipeline as values (`scrub_text`, the 200-char cap and the
credential-URI drop) and drop a key that changes under scrubbing rather than emitting
`[REDACTED]` as a key. Add a regression test that registers a numeric Aadhaar and a
PAN-as-key and asserts neither crosses the boundary.

---

## WARN Findings

### [SEC-104] `lru_cache(maxsize=256)` thrashes into a per-log-line recompilation DoS
**File:** `backend/src/config/logging.py` lines 102-119 (cache), line 128 (`_scrub`)
**Severity:** medium · **HTTP-reachable at HEAD:** no (no caller of `register_sensitive`).

This is the axis the orchestrator asked me to open, and it is the one place the
bounded-pattern fix left a sharp edge. `_scrub` iterates every registered value and
compiles a pattern per value through a 256-entry LRU. A sequential scan over N > 256
keys is the classic LRU worst case: the entry needed next is always the one just
evicted, so the hit rate collapses to **zero** and every log line recompiles every
pattern.

| distinct registered values | cost per log line | cache |
|---|---|---|
| 10 | 0.00 ms | 10 hits / 10 misses |
| 256 | 0.10 ms | 256 hits, full |
| **257** | **0.77 ms** | **0 hits**, 514 misses |
| **1000** | **95.18 ms** | **0 hits**, 2000 misses |

A ~1000x per-log-line regression at a threshold nothing enforces or warns about.
Compilation cost is also linear in value length and unbounded — a 50,000-char
registered value compiles a 650 KB pattern in **424 ms**, per log line, forever
(it can never stay cached alongside others). A story that registers per-token
content from a parsed salary document, or a bulk/batch endpoint that registers
values for many applicants in one request, reaches both conditions naturally.

**Fix:** replace the global `lru_cache` with a **per-request pattern cache** held in
the redaction scope (a `dict` beside the sensitive set in the contextvar), sized by
that request's own registrations rather than a global 256. Reject or truncate
registrations above a sane length ceiling (a PAN is 10 chars, an Aadhaar 12). This
one change also fixes SEC-105.

### [SEC-105] Registered PII outlives the request scope inside the pattern cache
**File:** `backend/src/config/logging.py` lines 102-119, versus lines 84-91
**Severity:** medium · **HTTP-reachable at HEAD:** no (no caller); unconditional once used.

The module contract is that registration is request-scoped and
`CorrelationIdMiddleware` owns the lifetime. The `lru_cache` silently breaks that:
its key is the **raw sensitive value**, and the cached `re.Pattern` embeds the
escaped literal, so both survive `end_redaction_scope`. Proven at HEAD — after
closing the scope (`_sensitive_values.get()` is `None`), asking for the PAN's
pattern is a cache **hit**, i.e. the PAN string is still live in the process.

So up to 256 PANs/Aadhaars/document ids sit in resident memory indefinitely, across
requests and across users, reachable from a core dump, a heap dump, a crash
reporter, or any future debug/introspection endpoint. Note no cache keyed on the
plaintext can avoid this — the compiled pattern contains the value either way.

**Fix:** the per-request cache from SEC-104 (dies with the request context). If the
global cache is kept for performance, call `_redaction_pattern.cache_clear()` from
`end_redaction_scope` and accept recompilation.

### [SEC-106] `X-Request-ID` accepted unbounded → reflected into every log line and the response
**File:** `backend/src/api/middleware.py` lines 86-87
**Severity:** medium · **HTTP-reachable at HEAD:** yes, unauthenticated.

The inbound header is taken verbatim — no length limit, no character allow-list, no
shape check. Measured against live uvicorn: a **60,000-character** `X-Request-ID`
returns `200` and is echoed in full in the response header; uvicorn imposes no
practical ceiling here. The value is also stamped onto every structured log line
for that request, so an 8 KB id turned one trivial `GET /health` into **8,744 bytes**
of log output versus ~330 normally (~26x; ~190x at 60 KB). That is cheap,
unauthenticated log-volume amplification against disk and against any per-GB log
pipeline, and it is the same knob an attacker uses to make request tracing unusable.

**Fix:** validate on ingress — accept the inbound id only if it matches a strict
allow-list (e.g. `^[A-Za-z0-9._-]{1,64}$`), otherwise generate a fresh `uuid4().hex`
and ignore the caller's value. Truncate rather than reflect, and never echo an
unvalidated caller string in a response header.

### [SEC-107] Correlation id is caller-controlled → audit-trail forgery and collision
**File:** `backend/src/api/middleware.py` lines 86-88
**Severity:** medium · **HTTP-reachable at HEAD:** yes, unauthenticated.

Because any client can set the id, any client can choose it: replay another
request's id to interleave their own actions into that trace, collide every request
onto one id to destroy correlation, or pick an id that impersonates an internal
caller's format. For a loan-origination platform whose Correlation Id is the
audit-trail spine (`specs/design/CONTEXT.md`), that is an integrity defect, not
merely an observability one — the log record can no longer be trusted to attribute
an action to a requester.

**Fix:** either generate the id server-side unconditionally, or trust an inbound id
only from an authenticated internal peer (a gateway on a trusted network path) and
record it in a **separate** field (`upstream_request_id`) while keeping the
server-generated `request_id` authoritative.

### [SEC-108] `_CREDENTIAL_URI` allow-list is bypassable; credentials still egress
**File:** `backend/src/api/errors.py` line 150
**Severity:** medium · **HTTP-reachable at HEAD:** no (latent with SEC-103).

The regex models exactly one credential shape, scheme, then user, colon, password, at-sign, host, and its
password class `[^/\s@]+` forbids `/` — so a password containing a slash (common in
base64/random secrets) defeats detection. Non-URI credential formats are not modelled
at all. Both confirmed egressing from a live `409` envelope at HEAD:

- a `postgresql`-scheme DSN whose password contains a **slash** → **passed through**
- an ODBC-style `Server=...;Uid=...;Pwd=...;` key=value string → **passed through**

(The canonical DSN with inline credentials and a slash-free password was correctly dropped, so
the control works on the one shape it models.)

**Fix:** relax the password class to `[^\s@]+` to cover slashes, and add a
key=value credential heuristic (`(password|passwd|pwd|secret|token|api[_-]?key)\s*=`).
Better still, invert the control: `context` should carry only values a subclass
explicitly declares wire-safe, rather than everything minus a denylist.

### [SEC-109] The SEC-002 leak is still reachable through the exported `redact_values`
**File:** `backend/src/config/logging.py` lines 56-71
**Severity:** medium · **HTTP-reachable at HEAD:** no (no caller in `src/`).

The fix added the safe API but kept the unsafe one public. `redact_values` withdraws
its values in its `finally`, so an exception escaping the `with` block is logged
*after* the values are gone — the original SEC-002 shape, verbatim. Reproduced at
HEAD against a route that exits a `with redact_values(PAN)` block and then raises
with the PAN in the message: **the PAN appears in the logged traceback unredacted,
`[REDACTED]` count 0**, while the `register_sensitive` equivalents on the same app
were clean. The docstring warns about this, but a docstring is not a guardrail and a
future story picking the plausibly-named helper reintroduces a high finding.

**Fix:** make `redact_values` delegate to `register_sensitive` without withdrawing
(the safe superset), or make it withdraw only on a clean exit and keep the values
bound when the block exits via an exception. Failing that, mark it private
(`_redact_values`) and add an architecture test that fails on any `src/` caller.

### [SEC-110] `GET /metrics` is unauthenticated and discloses the full raw path list
**File:** `backend/src/api/platform/routes.py` lines 122-134; `backend/src/api/app.py` line 38
**Severity:** medium · **HTTP-reachable at HEAD:** yes, unauthenticated.

Anyone can read traffic volume, error rates and — because the label is the raw path
(SEC-101) — the **verbatim set of URLs other clients requested**. At HEAD only
`/health` and `/metrics` exist, so today's disclosure is thin. Once group B/E land
resource routes, every `/applications/{id}`, borrower id or document id that ever
appeared in a URL is enumerable by an anonymous reader, which is an IDOR
reconnaissance primitive on a lending platform. It is also a probe oracle: an
attacker reads back exactly which paths and statuses their own scans produced.

**Fix:** bind `/metrics` to a separate internal port or restrict it to the scrape
network (deny by default at the ingress), or require an auth token; and switch to
route templates so ids never become label values. Fixing SEC-101 removes most of
the disclosure as a side effect.

### [SEC-111] Frontend dev-dependency advisories: 1 critical, 1 high, 3 moderate (npm labels)
**File:** `frontend/package.json` lines 18-31
**Severity:** medium (deliberately **downgraded** from npm's critical/high — rationale below)
**HTTP-reachable at HEAD:** no (not in any deployed artefact).

`npm audit` at HEAD: **5 vulnerabilities — 1 critical, 1 high, 3 moderate**; 320
dependencies (5 prod, 314 dev). Resolved on this machine: `vite@5.4.21`,
`vitest@2.1.9`, `esbuild@0.21.5`.

| Package | npm severity | Advisory | Note |
|---|---|---|---|
| `vitest` | critical (CVSS 9.8) | GHSA-5xrq-8626-4rwp — arbitrary file read/exec when the **Vitest UI server** is listening (`<3.2.6`) | precondition not met: the only script is `vitest run` — no `--ui`, no watch |
| `vite` | high (CVSS 7.5) | GHSA-fx2h-pf6j-xcff — `server.fs.deny` bypass on Windows alternate paths (`<=6.4.2`) | dev server only; this is a Windows host, so the platform precondition *is* met |
| `esbuild` | moderate | GHSA-67mh-4wv8-2f99 — any website can read dev-server responses | dev server only |
| `@vitest/mocker`, `vite-node` | moderate | GHSA-82fw-gwwq-j7x9 path traversal | dev/test only |

**Production tree is clean** — `react`, `react-dom`, `decimal.js` carry zero
advisories. I downgrade to medium because none of these ship in the built artefact
and none are reachable from the running application; the residual risk is to a
developer workstation running `npm run dev`/`vitest`, which is real (the vite
`fs.deny` bypass needs only a lured browser visit on Windows) but not a production
exploit path. npm's raw labels are preserved in `dependency_audit` in the verdict
JSON so the decision is auditable rather than hidden.

**Fix:** `npm audit fix --force` requires `vite@8`/`vitest@5` (semver-major) — take
that deliberately in a dedicated chore commit, or at minimum bump within range and
re-audit. Never run `vitest --ui` on this tree until `vitest >= 3.2.6`. Add
`npm audit --audit-level=high` to CI so the posture is measured, not assumed.

### [SEC-112] No committed lockfile — `package-lock.json` is actively `.gitignore`d
**File:** `.gitignore` lines 48-49 (`*.lock`, `package-lock.json`); `frontend/package.json`
**Severity:** medium · **HTTP-reachable at HEAD:** n/a (supply chain).

The lockfile exists on disk (157 KB) but is untracked **by rule**, not by omission —
`git check-ignore` confirms `.gitignore:49` matches it. Consequences: `npm ci` is
impossible, so every install re-resolves caret ranges and no two builds are
guaranteed identical; there are no integrity hashes pinning artefacts, so a
compromised or typosquatted transitive release is installed silently; and the
advisory posture in SEC-111 describes only *this* machine's resolution, which CI
cannot reproduce or verify. For a regulated lending platform, an unpinned
320-package dev tree is a genuine supply-chain gap.

**Fix:** remove both patterns from `.gitignore`, commit `frontend/package-lock.json`,
and use `npm ci` in CI and in `init.sh`. (`*.lock` also suppresses `uv.lock` and
`Cargo.lock` — the same argument applies to the backend.)

---

## INFO Findings

### [SEC-113] No security headers on any response
`backend/src/api/app.py` (no header middleware). Live responses carry only
`date`, `server`, `content-length`, `content-type`, `x-request-id` — no
`X-Content-Type-Options: nosniff`, `X-Frame-Options`/`frame-ancestors`, CSP,
`Referrer-Policy`, HSTS, or `Cache-Control: no-store`. Low today (JSON/plain-text
API, no browser-rendered surface in group A), but `/metrics` is cacheable by any
intermediary and the frontend arrives in a later story. **Fix:** add a small
header middleware in the app factory now, while there is one mount point.

### [SEC-114] `/openapi.json` and `/docs` are exposed unauthenticated
`backend/src/api/app.py` line 36 (`FastAPI(title=...)`, defaults kept). Both return
`200` on the live server. Harmless at HEAD (two endpoints); becomes a complete
unauthenticated map of the origination API — routes, schemas, field names — as
stories land. **Fix:** disable in production via settings
(`docs_url=None, redoc_url=None, openapi_url=None`) or gate behind auth.

### [SEC-115] `/health` discloses version and infrastructure state unauthenticated
`backend/src/api/platform/routes.py` lines 111-119. Returns
`{"status","database","version"}` to anyone; `version` aids version-specific
vulnerability targeting and `database` reveals backend liveness to an attacker
timing an outage. Standard for a liveness probe; **fix:** keep the public probe
minimal (`{"status"}`) and expose the detailed payload only on the internal port.

### [SEC-116] Values shorter than 6 characters are silently never redacted
`backend/src/config/logging.py` lines 94, 123-125. `_MIN_REDACTABLE_LENGTH = 6`
skips short registrations with no warning and no error. PAN (10) and Aadhaar (12)
are safe, but an OTP, CVV, 4-digit PIN or short account suffix registered by a
future story is silently unprotected — a control that fails open and quietly.
**Fix:** log a warning (or raise) when a registration is rejected as too short, so
the caller learns the value is not protected.

### [SEC-117] The `{0,4}` separator bound narrows redaction coverage
`backend/src/config/logging.py` line 99. The ReDoS fix means PII rendered with 5+
separators between characters no longer matches. A correct trade-off and
acknowledged in the context pack, but it is a documented behaviour change that
callers cannot see from the API. **Fix:** state the bound in `register_sensitive`'s
docstring and keep a test pinning it, so a future widening is a deliberate act.

### [SEC-118] The 200-char cap drops silently; `detail` has no cap at all
`backend/src/api/errors.py` lines 152, 179 and 196. Dropping is the **right**
security choice over truncating — a truncated value still emits its first 200
characters, which is most of a PAN, an Aadhaar or a token. Two residuals: the drop
is silent, so a caller relying on `context` for machine-readable specifics
(E4-S4-AC2's `threshold_kind`/`configured_value`) loses them with no signal; and
`detail` is scrubbed but uncapped, so an over-long internal message crosses whole.
**Fix:** log at DEBUG when a key is dropped, and cap `detail` too.

### [SEC-119] The redaction guarantee rests on the root handler being the only sink
`backend/src/config/logging.py` lines 195-250. `_install_redaction_filter_everywhere`
covers root plus loggers registered **at configure time**; `_route_server_loggers_through_root`
handles the known uvicorn/gunicorn cases. A logger created *after*
`configure_logging()` with its own handler and `propagate=False` — precisely what a
library's own `dictConfig` does, and what uvicorn itself did before this fix —
bypasses redaction entirely. **Fix:** re-run the installer at app startup after all
imports, or move the guarantee into the formatter (scrub in `JSONLogFormatter.format`)
so it cannot be bypassed by handler topology.

### [SEC-120] `Settings()` is re-instantiated on every `/health` request
`backend/src/api/platform/routes.py` line 118. Each unauthenticated probe constructs
a fresh pydantic-settings object, re-reading the environment and any `.env` file from
disk — a small per-request I/O amplification on the one endpoint an attacker can hit
freely, and a config-reload race if `.env` ever changes at runtime. **Fix:** build
`Settings` once in the app factory and inject it (FastAPI dependency or module-level
singleton).

### [SEC-121] The 422 handler reflects an attacker-controlled field name
`backend/src/api/errors.py` lines 215-224. `field` is joined from pydantic's `loc`,
which for a dict-typed or extra field contains the **client-supplied key**, so
attacker input is echoed into `context.field`. Bounded and low risk: it passes
through `sanitise_context` (scrubbed, 200-char cap) and the response is
`application/json`, so there is no XSS sink. Noted because the handler's own
docstring promises it never echoes rejected input, and the key half of that input
does come back. **Fix:** emit only the field *path shape* or an allow-listed name.

### [SEC-122] No rate limiting or request throttling anywhere in the stack
`backend/src/api/app.py`. Group A has no login/reset/OTP endpoint, so the OWASP
"missing rate limiting on auth endpoints" check is not yet applicable — recorded
because throttling is the compensating control absent from SEC-101/SEC-106, both of
which are cheap precisely because nothing limits request rate. **Fix:** add a global
throttle at the ingress or in the app factory before auth endpoints land in group B.

---

## Refuted candidates

Recorded explicitly; each was a live candidate that did not survive refutation.

1. **SEC-001, alternative backtracking shapes — AXIS CLEAN.** I did not re-litigate
   the confirmed-fixed shape. I built five *different* adversarial shapes against
   `_scrub`/`_redaction_pattern` and scaled each over value lengths 8→64: repeated-char
   value against an alternating char/separator haystack; the same with a failing
   sentinel forcing full backtracking at every position; a value whose characters are
   all separator-adjacent; a tab/space/hyphen-mixed haystack; and a digit value against
   a grouped-digit haystack. Every shape stayed **under 0.7 ms with linear growth**
   (worst: 0.65 ms at n=64). The structural reason is that the joined branch's
   alphabets are **disjoint** — `_SEPARATOR_RUN` matches only `[ \t-]` and that branch
   is taken only when the value contains *no* separator — so at any position the
   separator run that can be consumed is unique, the match is effectively
   deterministic, and there is nothing to backtrack over. The `re.escape(value)`
   literal branch is a plain literal with no quantifier. **No ReDoS shape exists on
   this design.** What the cache *did* yield is a non-regex DoS, filed honestly as
   SEC-104 rather than as a ReDoS.
2. **Log injection (CRLF / JSON forgery) via `X-Request-ID` — refuted.** Two
   independent barriers. `JSONLogFormatter` renders through `json.dumps`, which
   escapes quotes, backslashes and every control character below `0x20`: a
   `","level":"CRITICAL","message":"forged log line"` id produced a log line that
   still **parsed as valid JSON** with exactly the five expected keys and the payload
   confined inside the `request_id` string. And uvicorn's parser rejects the raw
   bytes anyway — bare `LF`, `NUL` and `ESC` inside a header value each returned
   **400 Bad Request** before the app was invoked. Terminal-escape injection into a
   log viewer is blocked by the same two mechanisms.
3. **HTTP response splitting via the echoed `X-Request-ID` — refuted.** The header is
   reflected verbatim into `MutableHeaders`, which would be the classic setup, but the
   inbound value can never contain `CR`/`LF`: the HTTP parser rejects such a request
   with 400 (verified over a raw socket). Absent a CRLF source, reflection is
   contained. SEC-106/107 cover what remains (length and trust), not splitting.
4. **SEC-002 as originally reported — genuinely closed.** Proven, not accepted from
   the commit message. Against `create_app()` with a route calling
   `register_sensitive(PAN, AADHAAR)` and raising with both in the exception message:
   status 500, body `{"error":"InternalServerError","detail":"internal server error"}`
   with no PII, traceback **present** in the logs, PAN absent, Aadhaar absent,
   two `[REDACTED]` substitutions, request id on the access line. The threadpool
   path (`def` handler, which runs on a *context copy*) is also clean — the
   mutable-set-in-a-contextvar design works exactly as its comment claims. The
   ordering that makes this work is real: Starlette's `ServerErrorMiddleware`
   re-raises after sending the 500, so the exception reaches the middleware's
   `except BaseException` while both contextvars are still bound, which is why the
   traceback is both scrubbed and correlated. Residual: SEC-109 (the other API).
5. **Credential URI split across two context keys — refuted as its own finding.**
   Splitting a DSN so one key holds the scheme-and-user half and another the password-and-host half does egress both
   halves (neither is a URI alone), and reassembly is trivial. But this requires a
   developer to have deliberately split a DSN across two keys, which is not a
   realistic shape and not attacker-influenced. Folded into SEC-108 as evidence that
   the check is per-value and heuristic, rather than filed separately.
6. **Frontend XSS — refuted.** No `dangerouslySetInnerHTML`, `innerHTML`,
   `Function(`/`eval` anywhere in the change set. `MoneyText.tsx` renders
   `{value.format()}` as JSX text, which React auto-escapes; the prop type is
   `Money | string` and the string path goes through `Money.fromWire` validation
   before display.
7. **Hardcoded secrets — none.** A targeted scan of the change set matched only
   `token`-named local variables holding contextvar reset tokens
   (`middleware.py:88-89`, `logging.py:89`). `Settings` sources everything from the
   environment with a `TRUELEND_` prefix and no default credential.
8. **Injection/SSRF/path-traversal/deserialization sinks — absent.** No SQL, no ORM,
   no `subprocess`/`os.system`, no outbound HTTP client, no `open()`, no
   `pickle`/`yaml.load` anywhere in the change set. Group A ships no Repository or
   Service layer, so these categories have no reachable sink. The only injection in
   the diff is SEC-102, into the metrics exposition format.
9. **Cross-request PII bleed from the deliberately-unreset contextvars — refuted.**
   The failure path resets neither contextvar (by design). Uvicorn runs each
   request/response cycle in its own task, so each gets its own context copy and the
   leak dies with the task; and the worst case of a shared context would be
   *over*-redaction of another line, not exposure. `request_id_var` is overwritten at
   entry regardless.

## Out of scope for this review

- `backend/pyproject.toml` — no backend dependency manifest is in the change set, so
  no Python dependency audit was run (step 5 skipped per scope rules). Worth running
  when a backend manifest next changes; note `.gitignore`'s `*.lock` also suppresses
  `uv.lock` (see SEC-112).
- Authentication and authorization implementation — group A ships no auth layer, no
  JWT, no roles and no protected routes, so auth-bypass/IDOR/privilege-escalation
  have no implementation to review. `/health` and `/metrics` being unauthenticated is
  reported as SEC-110/114/115 rather than as an auth-bypass finding.
- CSRF — no state-changing endpoint and no cookie exists at HEAD.
- Pre-existing untouched code outside the change set and its data-flow neighbours.
- The `canvas-sync` and `regression-suite-full` registry BLOCKs (invocation artefacts
  per context pack §5) and `.claude/state/uvicorn.log`.

## Method

- Read: context pack; `git diff 14e9487..HEAD -- backend frontend` (27 files, +2,429);
  full content of all 12 production source files, both frontend source files, and the
  config/manifest files; test files consulted only to establish caller reachability.
- Reachability established by a change-set-scoped grep for `register_sensitive`,
  `redact_values` and `AppError(` in `backend/src/**`: **no production callers**.
- Live server: `uv run uvicorn src.api.app:app --port 8009` (per pack §8, distinct
  port), exercised with `curl --path-as-is`, raw `socket` requests for malformed
  headers, and `http.client` keep-alive floods. Server terminated after the probes.
- In-process probes: `TestClient(create_app(...))` with throwaway routes on the inner
  app; `tracemalloc` for per-key memory; `time.perf_counter` for regex and cache
  timings; `lru_cache.cache_info()` for hit/miss and retention evidence.
- Dependency audit: `npm audit --json` in `frontend/`; `npm ls` for resolved
  versions; `git ls-files` and `git check-ignore -v` for lockfile tracking.
- Every candidate BLOCK was put through the find-then-refute pass; the nine entries
  above are the ones that did not survive it.
