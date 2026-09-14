# Security Review — truelend — instance 3 of 3 — round 3 — 2026-09-14

**Scope:** the 13 changed production files in `review-context-pack.md` §5 plus their immediate
data-flow neighbours (`.claude/hooks/lib/prom-parse.js` and `.claude/scripts/slo-check.js` as the
consumers of `/metrics`; `frontend/src/ui/components/MoneyText.tsx` as the only caller of
`Money.format()`).
**HEAD:** `ba457bf` · **Base:** `14e9487` · **Branch:** `feat/harness-scaffold-and-planning`
**Method:** every verdict below is either a **reproduction** (I executed an attack and it worked) or
a **refutation** (I executed a measurement and the attack did not work). Each finding says which.
**Live server:** `uvicorn src.api.app:app` on port **8036**, started 13:07:41 UTC, killed at the end
of the review; port confirmed closed.

## Summary

- BLOCK findings: **0**
- WARN findings: **11**
- INFO findings: **7**
- **Overall verdict: PASS** (no `critical`/`high` finding survived adversarial refutation)

| Round-2 BLOCK | Disposition at HEAD | Basis |
|---|---|---|
| **B-1** `/metrics` exposition injection | **CLOSED** | reproduction attempted, failed; two independent refutations |
| **B-2** `/metrics` unbounded cardinality | **CLOSED as filed**; bounded residual → WARN `SEC3-001` | measured zero growth over 5,000 distinct paths |
| **B-3** `HTTPException.headers` discarded | **CLOSED** | `405` now carries `allow: GET` over the wire |
| **B-4** `money.ts:78` quadratic regex | **CONFIRMED defect, downgraded to WARN** `SEC3-002` | regex reproduced at 4,301 ms; **no caller path exists** |

---

## Priority 1 — the two BLOCKs the last round's remediation introduced

### B-1 — `/metrics` Prometheus exposition injection — CLOSED

**Reproduction attempted.** I sent round 2's own payload as a percent-encoded request path:

```
/x"} 999\nhttp_requests_total{method="GET",route="/health",status="500"} 99999\n#
```

Result: `forged 99999 series present: False`. The route labels present in the exposition after the
attack were exactly `['/health', '/metrics', '<unmatched>']`, and the whole exposition contained
**zero control characters other than LF**. The payload was bucketed into `<unmatched>`, so the
request did arrive — it simply has no label channel any more.

**The carriage-return escalation the pack asked for: refuted twice, independently.**

*1 — no attacker-controlled channel can carry CR (or any C0, or `"` or `\`).* The exposition has
exactly four label channels. `route` is `route_label()`, which returns the **matched route template**
(a code constant) or the single `<unmatched>` literal. `status` is rendered `{:d}`. `le` is `{:g}` of
`_LATENCY_BUCKETS`, a module constant. That leaves `method`, and `method` never reaches
`scope["method"]` in a hostile form, because httptools/llhttp rejects it at the parser. Measured over
a raw socket:

| request line | server response |
|---|---|
| `GE"T /health HTTP/1.1` | **400 Bad Request** |
| `GE\T /health HTTP/1.1` | **400 Bad Request** |
| `GET\rX /health HTTP/1.1` | **400 Bad Request** |
| `GET\x0bX /health HTTP/1.1` | **400 Bad Request** |
| `GET\x00X /health HTTP/1.1` | **400 Bad Request** |
| `FOOBAR /health HTTP/1.1` (valid RFC 9110 token, unknown) | **400 Bad Request** |
| `PROPFIND /health HTTP/1.1` (in llhttp's table) | 405, reaches the app |

`uvicorn[standard]` makes httptools a hard dependency, `--http auto` prefers it, and
`specs/design/deployment.md:38` runs `uvicorn src.api.app:create_app --factory` with no `--http`
flag — so httptools is what production gets.

*2 — even with a CR, this project's sensor cannot be forged.* `.claude/hooks/lib/prom-parse.js`
splits on `'\n'` only and then `.trim()`s each line, which discards a stray CR. I fed it a
CR-forged label value directly: it parsed to **0 series**, not 2. A CR would corrupt a scrape, not
mint a series.

**Impact test with the project's own sensor**, after ~1,700 hostile requests:

```
node .claude/scripts/slo-check.js --url http://127.0.0.1:8036
{"verdict":"pass","error_rate_pct":0,"p95_ms":4.749999999999999,
 "budgets":{"error_rate_pct":1,"p95_ms":500},"breaches":[],"exit":0}
```

Round 2's forged 99.90% error rate against a 1% budget is gone, and `p95_ms` is non-null for the
first time (this is also the first evidence for **E15-S4-AC1**).

Residual: `_LABEL_ESCAPES` still omits `\r` and every other C0 character. Unreachable today →
`SEC3-012` (INFO, defense in depth).

### B-2 — `/metrics` unbounded cardinality — CLOSED as filed; bounded residual is a WARN

**Refuted by measurement.** One keep-alive connection minting 5,000 distinct unmatched paths:

| | series | distinct label sets | exposition bytes |
|---|---|---|---|
| before | 135 | 126 | 10,868 |
| after 5,000 distinct paths | **135** | **126** | **10,882** |

Zero growth. Round 2's 60,000 label values / +28.2 MB is not reproducible.

**The new histogram state inherits the bound.** `_duration_counts` and `_duration_totals` are keyed
`(method, route_label(scope))` — the *same* `route_label()` — and each bucket list is allocated
`[0] * (len(_LATENCY_BUCKETS) + 1)`. Measured: bucket list length 12, `bounds+inf` length 12.

**`method` does re-open a bounded amount of it.** These dicts are process-global module state that is
never evicted (`reset_request_counters()` is test-only). Sweeping llhttp's 35 accepted methods across
7 paths grew the exposition from ~10 KB to:

```
series 1611 · label sets 1506 · bytes 130289
distinct method labels: 35 · distinct route labels: 3  ['/health','/metrics','<unmatched>']
```

That is a *finite constant* — ~200x smaller than round 2 and not a memory DoS — but the ceiling is
`35 x (routes+1) x statuses` and grows linearly with every route groups B–M add. → `SEC3-001` (WARN).

### B-3 — `HTTPException.headers` discarded — CLOSED

Verified by request, not by reading the diff:

```
PROPFIND /health -> HTTP/1.1 405 Method Not Allowed   allow: GET
GET /nosuch      -> HTTP/1.1 404 Not Found            (envelope + x-request-id)
```

Both carry `content-type: application/json` and `x-request-id`.

---

## Priority 2 — B-4 and the items nobody assigned

### B-4 — `frontend/src/types/money.ts:78` quadratic grouping lookahead — CONFIRMED, WARN

**Reproduced.** The regex measured in isolation with `node` (not `toFixed`):

| digits | ms |
|---|---|
| 1,000 | 0.4 |
| 2,000 | 1.4 |
| 4,000 | 5.5 |
| 8,000 | 22.9 |
| 16,000 | 99.8 |
| 32,000 | 410.0 |
| 64,000 | 1,653.1 |

Clean 4x per doubling — O(n^2), as round 2's security-3 reported.

**The round-2 dispute is settled in security-3's favour.** Splitting the two candidate sinks for the
8-byte input `"1e100000"` (100,001 integer digits after expansion):

- `amount.toFixed(2)` → **1.23 ms**
- `digits.replace(/\B(?=(\d{3})+(?!\d))/g, ",")` → **4,301 ms**

Evaluator 3 refuted B-4 by timing `toFixed()`, which is the wrong sink by a factor of 3,500.
4,301 ms reproduces round 2's reported 4,152 ms.

**Reachability — the question the pack asked me to settle.**

- *Nothing upstream bounds the digit count.* `toQuantizedDecimal` checks only `isFinite()`;
  `toDecimalPlaces(2)` preserves the exponent; `toWire()` is `toFixed(2)`, which decimal.js always
  renders non-exponentially — 100,004 characters here. So `Money.fromWire("1e100000").format()` is a
  ~4.3 s single-threaded stall and `"1e1000000"` is ~430 s (extrapolated from the table; not run to
  completion).
- *No caller path exists today.* The only caller of `format()` is `MoneyText`, and `MoneyText` has
  **zero callers**: `frontend/src/` contains exactly two files (`types/money.ts`,
  `ui/components/MoneyText.tsx`) — no entrypoint, no router, no `fetch`.
- *The backend cannot supply such a value.* Measured: `Money("1e30")`, `Money("1e100000")` and a
  100,000-literal-digit string are **all rejected** with the typed `InvalidMoneyAmountError`, because
  `Decimal.quantize` exceeds the 28-digit default context precision. The wire is bounded to ~26
  integer digits, and `_WIRE_PATTERN` documents `^-?\d+\.\d{2}$`.

**Severity I can defend: WARN (medium).** It is a genuine CWE-1333 algorithmic-complexity defect,
unbounded at the type boundary, with no reachable attacker path in the product at HEAD. It becomes
**BLOCK/high** on the first commit that renders `MoneyText` from any string the backend did not mint
— a form field, a URL parameter, or a third-party payload. It is not INFO, because `Money.fromWire`
is a *public* API that advertises no length precondition. Fix is one line (see `SEC3-002`).

### `Money.multiply` and bare `decimal.Overflow` — round-2 timing dispute SETTLED

Measured, with `Money(Decimal("1.00"))`:

| scalar | elapsed | outcome |
|---|---|---|
| `10**40` | 0.0 ms | `InvalidMoneyAmountError` (typed) |
| `Decimal("1e100000")` | 0.0 ms | `InvalidMoneyAmountError` (typed) |
| `Decimal("1e1000000")` | **0.0 ms** | **`decimal.Overflow` LEAKED (untyped)** |
| `10**200000` | 387.3 ms | `InvalidMoneyAmountError` (typed) |

**Neither round-2 figure is right.** The real cost of the leak is **sub-millisecond** — evaluator 3's
9,708 ms and security 3's 109 ms both overstate it, and **there is no DoS here**. The 387 ms row is
big-integer construction inside my harness, and that path raises the *typed* error correctly.

Mechanism: `decimal.Overflow` derives from `ArithmeticError`, not from `InvalidOperation`, so both
`except InvalidOperation` clauses in `money.py` (lines 63, 75) miss it. `1e100000` stays under the
default `Emax` of 999999, so the multiply succeeds and `quantize` raises the typed error; only past
`Emax` does `Overflow` escape. Consequence is a 500 instead of the documented
`InvalidMoneyAmountError`/422 — no information leak, since `handle_unexpected` returns a fixed
message. → `SEC3-011` (WARN, contract/robustness, explicitly **not** a DoS).

### The new histogram code path as an attack surface — REFUTED

`observe_duration` accepts `0.0`, `1e-12`, `1e308`, `-1.0`, `nan` and `inf` without raising. `nan`
lands in the `+Inf` bucket (mis-bucketed) and poisons the exposition as
`http_request_duration_seconds_sum{...} nan`. **Not attacker-reachable:** the only caller passes
`time.perf_counter() - started`, which is monotonic, finite and non-negative.

`zip(bounds, counts, strict=True)` **cannot** raise from any input: `bounds` is
`len(_LATENCY_BUCKETS) + 1 = 12` and every counts list is allocated at exactly that length.
Measured 12 and 12; `_histogram_lines()` rendered 16 lines without raising even with `nan`/`inf`
forced into the state. Growth is bounded as established in B-2. → `SEC3-014` (INFO).

---

## WARN Findings

### [SEC3-001] `/metrics` label cardinality still multiplied 35x by the `method` label
File: `backend/src/api/middleware.py` line 60 (`route_label`), lines 50/72/73 (module state)
Severity: medium · Category: denial-of-service
Description: `route` is correctly bounded, but `method` is a free label taking any of llhttp's ~35
accepted methods, and `_request_counts` / `_duration_counts` / `_duration_totals` are process-global
and never evicted. Measured: one unauthenticated sweep of 35 methods x 7 paths took the exposition
from ~10 KB to 1,611 series / 1,506 label sets / 130,289 bytes, permanently. The ceiling is
`35 x (routes+1) x statuses` and scales with every route groups B–M add — at ~40 routes it is
~2 MB per scrape from a single anonymous sweep.
Fix: allow-list the `method` label to the methods the app actually serves and bucket the rest as a
single `<other>` value, exactly as `route_label()` already does with `<unmatched>`.

### [SEC3-002] Quadratic thousands-separator lookahead in `Money.format()`
File: `frontend/src/types/money.ts` line 78
Severity: medium · Category: denial-of-service (CWE-1333)
Description: `/\B(?=(\d{3})+(?!\d))/g` re-scans to end-of-string at every position — O(n^2), measured
4,301 ms for the 8-byte input `"1e100000"`. Nothing upstream bounds the digit count: `fromWire`
checks only `isFinite()` and `toWire()` expands the exponent to a 100,004-character string. No caller
path exists today (`MoneyText` has zero callers) and the backend rejects such values, which is why
this is WARN and not BLOCK — see the B-4 section for the full reachability analysis.
Fix: replace with the linear form `digits.replace(/\d(?=(\d{3})+$)/g, "$&,")`, or use
`Intl.NumberFormat`. Independently, cap the integer-digit count in `toQuantizedDecimal` so
`Money.fromWire` has a stated precondition rather than an implicit one.

### [SEC3-003] Unauthenticated request volume dilutes the SLO signal and masks a real outage
File: `backend/src/api/platform/routes.py` line 126 (anonymous `/metrics`); consumer
`.claude/hooks/lib/prom-parse.js` lines 36, 78
Severity: medium · Category: monitoring integrity
Description: `errorRate()` is `5xx / all http_requests_total` over **lifetime** counters, and
`histogramP95()` aggregates across all label sets. Counters are cumulative-since-boot and never
reset, `/metrics` is anonymous, and there is no rate limiting. Reproduced against the project's own
parser: a genuine outage at **50.00%** error rate is masked to **0.0100%** (under the 1% budget →
PASSES) by 1e6 anonymous 404s; a genuine **9,525 ms** p95 is masked to **4.8 ms** (budget 500 →
PASSES). One flood poisons both ratios for the process lifetime. This is the *volume* half of the
same threat B-1 was the *injection* half of. Not BLOCK: the exposition itself is correct Prometheus
semantics and the consequence lands on monitoring, not on data or auth.
Fix: the product already supplies the label needed — have the sensor exclude `route="<unmatched>"`
and compute a windowed rate rather than a lifetime ratio; authenticate `/metrics` with E1-S1.

### [SEC3-004] Redaction is defeated by formatting — needs normalize-then-match
File: `backend/src/config/logging.py` lines 95–119 (`_SEPARATOR_CHARS`, `_redaction_pattern`)
Severity: medium · Category: secrets/PII
Description: measured with `123456789012` and `ABCDE1234F` registered. **Redacted:** plain,
space-separated, dash-separated up to 4, lowercase PAN, spaced PAN, NFKD-normalised form.
**NOT redacted:** dot, underscore and slash separators; NBSP (U+00A0); soft hyphen (U+00AD);
zero-width space (U+200B); fullwidth digits (U+FF10–FF19); dotted PAN; and any separator run longer
than 4 (`"1234     5678     9012"`). Live impact today is **nil** — there are **zero
`register_sensitive` / `redact_values` call sites in `backend/src/`** (grep: only the definitions and
docstrings; call sites exist in tests and in `specs/bundles/E1-S1.json` / `E4-S1.json`, i.e.
`ba457bf` added them to the *spec*, not to code). Severity rises to **high** the moment E1-S1 or
E4-S1 lands a real call site.
Fix: NFKC-normalise and strip Unicode `Cf`/`Pd`/`Zs` categories from both haystack and needle before
matching, instead of enumerating separator characters.

### [SEC3-005] Registered PII is retained for the process lifetime as `lru_cache` keys
File: `backend/src/config/logging.py` line 102 (`@lru_cache(maxsize=256)`)
Severity: medium · Category: secrets/PII
Description: proven by measurement — after `end_redaction_scope()`, `_redaction_pattern(AADHAAR)` is
served from cache (`hits` 0→1, `misses` unchanged at 1), and the retained compiled pattern still
embeds the value (`1[ \t\-]{0,4}2[ \t\-]{0,4}3...`). The raw value is the cache **key**, so up to 256
applicants' PAN/Aadhaar survive request teardown in process memory, are visible in any core dump or
heap inspection, and are shared across users. Latent while `SEC3-004`'s call-site count is zero.
Fix: drop the cache (pattern compilation is cheap relative to a request), or key it on a salted
digest and never retain the plaintext.

### [SEC3-006] `X-Request-ID` is unvalidated and unbounded, and its content is logged verbatim
File: `backend/src/api/middleware.py` lines 151–152
Severity: medium · Category: user input handling
Description: measured — a **100,000-byte** `X-Request-ID` is accepted (200 OK), echoed back in the
response header (100,014 bytes), and written verbatim to the access log as a single **100,146-byte**
JSON line. A PAN-format id (`4111111111111111`) is logged unredacted, because redaction covers only
*registered* values and nothing registers the inbound header. Attacker-controlled log volume and
attacker-controlled content in the correlation field.
**Explicitly refuted:** there is no CRLF response-header injection here. Bare LF and bare CR in the
value are rejected at the parser with 400, and `abc\r\nX-Request-ID: ...\r\nX-Injected: 1` is
ordinary header framing (the injected name arrives as a *request* header and never appears in the
response).
Fix: accept the inbound id only when it matches `^[A-Za-z0-9._-]{1,128}$`; otherwise generate one.

### [SEC3-007] Host-header-reflected open redirect
File: `backend/src/api/app.py` line 36 (no `TrustedHostMiddleware`); Starlette `redirect_slashes`
Severity: medium · Category: network-adjacent
Description: reproduced — `GET /health/` with `Host: evil.example` returns
`307 Temporary Redirect` with `location: http://evil.example/health`. Starlette builds the redirect
URL from the request URL, which is built from the Host header. Material behind a shared cache or CDN,
and it becomes a credential-theft path as soon as a story generates a password-reset or callback link
from the request URL.
Fix: add `TrustedHostMiddleware` with an explicit `allowed_hosts` allow-list in `build_fastapi_app`,
and configure the deployed base URL rather than deriving it from the request.

### [SEC3-008] No security response headers on any response
File: `backend/src/api/app.py` lines 31–39
Severity: medium · Category: infrastructure
Description: confirmed by request — no `Content-Security-Policy`, `X-Frame-Options`,
`X-Content-Type-Options` or `Strict-Transport-Security` on any response, including the `/docs` HTML
(Swagger UI) response, which is the one HTML surface the service serves and therefore the one that is
framable and MIME-sniffable.
Fix: one small ASGI middleware setting `X-Content-Type-Options: nosniff`,
`X-Frame-Options: DENY`, a default-deny CSP, and HSTS behind TLS.

### [SEC3-009] `/docs` and `/openapi.json` are publicly readable
File: `backend/src/api/app.py` line 36 (`FastAPI(title=...)`, docs URLs left at defaults)
Severity: medium · Category: authentication/authorization
Description: both return 200 with no authentication. Content is harmless today (two operational
endpoints), but this is the document `E1-S2-AC3` enumerates the *guarded* routes from, so from
group B onward it is a complete, machine-readable attack-surface map — including the request-body
schemas `a807678` just made it emit correctly.
Fix: set `docs_url`/`redoc_url`/`openapi_url` to `None` outside development, or guard them with the
auth dependency arriving in E1-S1.

### [SEC3-010] `sanitise_context`'s 200-char value cap applies to `str` only
File: `backend/src/api/errors.py` lines 66–82 (`_sanitise_value`)
Severity: medium · Category: secrets/PII
Description: measured — a 5,000-character string is correctly dropped, but a **4,000-digit int
egresses whole** (4,020 bytes of `context` on the wire), because the
`len(value) > _MAX_CONTEXT_VALUE_CHARS` guard sits inside the `isinstance(value, str)` branch while
the non-string branch below it is uncapped. Related second-order defect: for an int above
`sys.get_int_max_str_digits()` (4,300 by default, reachable by arithmetic such as `10**5000`),
`str(value)` raises `ValueError` **inside** `_sanitise_value` — i.e. inside the exception handler —
converting a typed 4xx into an unhandled 500. Latent: there are zero production `AppError` subclasses
or raisers (grep: only the base class, the handler and the registration).
Fix: apply the length cap to the rendered text of *every* scalar before scrubbing, and wrap the
`str(value)` conversion so a pathological value is dropped rather than crashing the handler.

### [SEC3-011] `Money.multiply` lets a bare `decimal.Overflow` escape the typed-error contract
File: `backend/src/types/money.py` lines 63 and 75 (`except InvalidOperation`), reached from line 101
Severity: medium · Category: error handling
Description: `Money(Decimal("1.00")).multiply(Decimal("1e1000000"))` raises `decimal.Overflow`, which
derives from `ArithmeticError` and not from `InvalidOperation`, so neither handler catches it. The
class docstring promises `InvalidMoneyAmountError` for inputs it cannot build from. Result is a 500
where the contract specifies a 422. **Measured cost: 0.0 ms — this is not a DoS**, and it leaks
nothing, because `handle_unexpected` returns a fixed message.
Fix: catch `decimal.DecimalException` (or `ArithmeticError`) in `__init__` and `_quantize` instead of
`InvalidOperation` alone.

## INFO Findings

### [SEC3-012] `_LABEL_ESCAPES` omits carriage return and every other C0 character
File: `backend/src/api/platform/routes.py` line 78
Severity: low · Description: the table escapes `\\`, `"` and `\n` only. Unreachable at HEAD — no
attacker-controlled channel can carry any other character (see B-1) — and `prom-parse.js` splits on
LF only, so a CR could not forge a series even if it arrived. Recorded as defense in depth against a
future label channel.
Fix: add `\r` to the table and reject or hex-escape any remaining `C0`/`C1` character and U+2028/
U+2029 in `_escape_label`.

### [SEC3-013] Absolute filesystem paths still egress through the error envelope's `context`
File: `backend/src/api/errors.py` lines 45, 66–82
Severity: low · Description: measured — `{"path": "C:/Users/rosuo/secret/keys.pem"}` passes through
unchanged. `_CREDENTIAL_URI` correctly drops `postgresql://user:pw@host/db`, but there is no path
filter. Round 2's claim still holds; latent, since nothing raises `AppError` in production yet.
Fix: drop values matching an absolute-path shape (`^[A-Za-z]:[\\/]`, `^/`, `\\\\`) as well.

### [SEC3-014] `observe_duration` validates none of its input
File: `backend/src/api/middleware.py` lines 76–86
Severity: low · Description: `nan`, `inf` and negative durations are all accepted; `nan` is
mis-bucketed into `+Inf` and renders as `http_request_duration_seconds_sum{...} nan`, which would
make a scraper drop the series. **Not attacker-reachable** — the only caller passes a monotonic
`time.perf_counter()` delta. `zip(..., strict=True)` cannot raise (12 vs 12, measured).
Fix: ignore any `seconds` that is not finite and non-negative.

### [SEC3-015] `HEAD /health` returns 405
File: `backend/src/api/platform/routes.py` line 63
Severity: low · Description: RFC 9110 §9.3.2 requires HEAD wherever GET is supported. A container or
load-balancer probe configured for HEAD will mark the service unhealthy. Availability-adjacent rather
than a vulnerability; noted because `/health` is the group-A contract surface.
Fix: `@router.api_route("/health", methods=["GET", "HEAD"])`.

### [SEC3-016] `/metrics` has no authentication — deferral judged acceptable for group A
File: `backend/src/api/platform/routes.py` line 126
Severity: low · Description: the pack asks me to judge the *deferral*, not the absence. E15-S4 Scope
Out defers auth to an `api-contracts.md` amendment plus the auth layer arriving with E1-S1 (group B).
The exposition today carries request counts, route templates and latencies for two operational
endpoints — no PII, no secrets, and no version information beyond what `/health` already returns
publicly. I judge the deferral **acceptable for group A**, conditional on it closing in the same
sprint as E1-S1, because two of my WARNs (`SEC3-001`, `SEC3-003`) are only exploitable while the
endpoint is anonymous.

### [SEC3-017] SAST and secrets tiers are UNSCANNED, not passed
Severity: low · Description: gitleaks, semgrep and pip-audit are all unprovisioned and skipped, so
the computational scan's "no findings at or above high" is vacuous for those tiers. My own review
found no hardcoded credential pattern in the 13 changed files (grep for string-literal assignment to
`password`/`api_key`/`secret`/`token`/`private_key`: none) and no dangerous frontend sink
(`dangerouslySetInnerHTML`, `innerHTML`, `eval`, `new Function`: none) — but that is inferential
coverage of a 13-file diff, not a repository-wide secrets scan.
Fix: provision the three tools before the next gate round, or record an explicit sensor waiver.

### [SEC3-018] `npm audit`: 1 critical + 1 high, devDependency-only
File: `frontend/package.json`
Severity: low · Description: vitest (critical) and vite (high) plus 3 moderate, all
`devDependencies`, absent from any production image, and now genuinely auditable because
`frontend/package-lock.json` and `backend/uv.lock` are committed. No production dependency is
affected (`decimal.js`, `react`, `react-dom`).
Fix: bump on the next dependency-maintenance pass; not a merge blocker.

---

## Environment integrity — the gate lead needs both of these

**1. `middleware.py` was transiently mutated mid-review, and it was not me.** At 13:11:15 UTC,
`backend/src/api/middleware.py:63` appeared on disk as
`return str(scope.get("path", "-"))  # MUTANT: raw path label` — round-2's B-2 defect re-injected. It
was reverted before I could diff it (`git diff` clean, `git status` does not list the file). It came
from a sibling instance's mutation test: `backend/.eval-i3/`, `.claude/state/tmp-eval1/` and
`.claude/state/tmp-review3/` are present and are not mine.

**No finding of mine is derived from mutated code**, and I can show that without relying on mtimes:
my server was started at 13:07:41 UTC and the injection probe ran at 13:10:30 UTC — before the
mutation — and it observed `route labels seen: ['/health', '<unmatched>']`. Under the mutant the
label would have been the raw decoded payload path. The running process therefore held pristine HEAD
code, and uvicorn was started without `--reload`.

**2. `uv run ruff check .` currently FAILS with 8 errors — all in sibling scratch files.** All 8 are
in `backend/.eval-i3/` (`ac1_cumulative.py`, `escape_gap.py`). `ruff check src/` passes,
`mypy src/` is clean across 12 source files, and `pytest -q` is **104 passed**. The pack records the
repo-wide lint as "clean", which is no longer true of the working tree; siblings should clean up
before that gate check is trusted. Untracked leftovers not mine: `.claude/state/tmp-eval1/`,
`.claude/state/tmp-review3/`, `.qa003body.txt`, `backend/.eval-i3/`, `frontend/.eval-i3/`,
`frontend/tests/unit/_eval_i2_b4.test.ts`.

**My own cleanup:** `backend/sec3_probe.py` and `.claude/state/tmp-sec3/` deleted; the uvicorn
listener on port 8036 killed (PID 63516) and the port confirmed closed;
`git status --short -- backend/src frontend/src` is **empty**. I did not edit any production file at
any point — every finding above was produced by requests and by measurements of unmodified code.

## What I could not test, and why

- **A real 5xx-producing route.** The app raises no 5xx anywhere, so I could not measure `SEC3-003`
  end to end against the live server. I reproduced it against `prom-parse.js` directly with
  representative counter fixtures instead, which exercises the exact function `slo-check.js` gates
  on. The refutation would require a production route that returns 5xx; there is none in group A.
- **`"1e1000000"` to completion** in B-4. Round 2 reported it did not finish in 100 s; my quadratic
  fit puts it at ~430 s. I stopped at 64,000 digits (1,653 ms) and extrapolated rather than burn
  seven minutes to confirm an exponent.
- **The `h11` HTTP path.** Under `--http h11`, arbitrary RFC 9110 token methods are accepted, which
  would restore unbounded `method` cardinality and make `SEC3-001` genuinely unbounded. There is no
  Dockerfile or compose file at HEAD, and `specs/design/deployment.md:38` specifies uvicorn with no
  `--http` flag, so httptools is what production gets and I tested that. Flagging it because the
  bound in `SEC3-001` is a property of the *server configuration*, not of the application code —
  if a future deployment pins `--http h11`, re-open B-2.
- **The SAST and secrets tiers** — see `SEC3-017`. Tooling absent; my coverage there is inferential
  over 13 files.
