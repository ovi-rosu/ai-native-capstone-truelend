# Evaluator report — instance 2 of 3 · `/gate --group A` round 3

**HEAD:** `ba457bf` · **verification mode:** `local` (Docker absent) · **port:** 8032 (httptools),
8232 (a second boot with `--http h11`, for the cardinality question only)
**Boot:** `cd backend && uv run uvicorn src.api.app:app --host 127.0.0.1 --port 8032`
**Both servers killed; `git status --short` carries no change of mine; `sprint-contracts/` untouched
(`A.json` sha256 `a0625d4b…e99a7` still matches `specs/reviews/contract-freeze.json`).**

---

## Verdict

**FUNCTIONAL: PASS** — scoped exactly as instructed to *whether the acceptance criteria and the
frozen contract hold*. All **3/3** frozen `api_checks` pass and all **16/16** story acceptance
criteria across E15-S1, E9-S1, E11-S1 and E15-S4 verify by execution. Nothing in the AC set or the
contract is broken at `ba457bf`.

**GATE RECOMMENDATION: BLOCK.** The functional PASS is narrow and I want it read narrowly. The
frozen contract is three `GET /health` checks — a near-vacuous safety net, as the pack says — and
two independent BLOCK-class defects survive at HEAD that no AC happens to name:

- **B-4 is STILL OPEN and reproduced at full magnitude.** A 9-byte wire string costs **421 s** of
  main-thread CPU through `Money.fromWire(...).format()`.
- **SEC-103's claimed fix is empirically inert.** `f5a5ace` plumbed `scrub_text` into the int and
  key paths of `sanitise_context`, but `scrub_text` is registration-driven and there are **zero
  `register_sensitive` call sites in `backend/src/`**, so a 12-digit Aadhaar arriving as an `int`
  and a PAN carried in a context *key* still egress whole on the wire. Measured below.

I am the functional axis, so the BLOCK recommendation is advisory; the AC/contract verdict above is
the one I am accountable for.

---

## 1. Frozen contract — 3/3 PASS

| Check | Matrix | Result | Evidence |
|---|---|---|---|
| QA-VM-003 | VM-003 | **PASS** | `GET /health` + `X-Request-ID: req-abc` → 200, `x-request-id: req-abc` echoed. Exactly 1 log line emitted while serving; it parses as JSON and carries `"request_id": "req-abc"`. 1/1 = 100%. |
| QA-VM-004 | VM-004 | **PASS** | `GET /health` with no header → 200, `x-request-id: 6e2e8d01cd9e4de9bd6b021c809f5feb`; the single request-scoped line carries the identical non-empty id. |
| QA-VM-005 | VM-005 | **PASS** | 5 consecutive runs, all 200, `content-type: application/json`, body `{"status":"ok","database":"unconfigured","version":"0.1.0"}` parsed by `json.load`. `time_total` 0.001336–0.001597 s — three orders of magnitude under the 1 s budget. |

Stub-mode caveat does not apply; this was a real uvicorn process.

---

## 2. Story acceptance criteria — 16/16 PASS

| AC | Verdict | How it was verified (execution only) |
|---|---|---|
| **E15-S1-AC1** | PASS *(surrogate — see F-1)* | The literal *Given* ("an application payload") has no endpoint in group A; `POST /applications` was retargeted to group E. Verified at the substrate: with values registered, `scrub_text` returns `[REDACTED]` for the exact PAN, Aadhaar and salary-document strings, in-sentence and with a trailing dash. **Caveat F-1 is MAJOR.** |
| **E15-S1-AC2** | **PASS** | Independent enumeration under the *real* boot order (`import src.api.app`): **11/11** live loggers carry a `RedactionFilter` — root, asyncio, concurrent.futures, dotenv.main, fastapi, gunicorn.error, pydantic_settings, truelend.access, uvicorn, uvicorn.access, uvicorn.error. Empty miss-list. (A partial import that loads only `src.config.logging` shows `truelend.access` filterless; that is my import order, not a defect — `src/api/app.py` imports the middleware before `configure_logging` runs.) |
| **E15-S1-AC3** | **PASS** | = QA-VM-003. 100% JSON, 100% correct `request_id`. `uvicorn.access` is `disabled=True`, so no non-JSON line competes. |
| **E15-S1-AC4** | **PASS** | = QA-VM-004. Also holds on the failure path: a forced `RuntimeError` produced a 500 that still carried `x-request-id: 1a6a9f67e41a4f3ba8e6b36fcd0ad7aa` and a correlated `ERROR` line with the same id — CR-003 stays closed. |
| **E15-S1-AC5** | **PASS** | = QA-VM-005. |
| **E9-S1-AC1** | PASS *(scope-limited — see F-5)* | No schedule generator exists in group A; `tests/architecture/test_no_float_money.py:8` says so itself. Verified at the Money layer instead: **3,000** random principal/rate triples × 4 operations (construct, multiply, add, subtract) = 12,000 results, **0** that were not a `Decimal` with `exponent == -2`. `float`, `bool` and a `float` scalar are all rejected with `InvalidMoneyAmountError`. |
| **E9-S1-AC2** | **PASS** | `uv run pytest tests/architecture/test_no_float_money.py -q` → **42 passed**. Full suite 104 passed; ruff clean; mypy clean over 12 files. |
| **E9-S1-AC3** | **PASS** | `frontend/src/types/money.ts` and `MoneyText.tsx` contain no `Number(`, `parseFloat`, `parseInt`, `Math.*`, `toNumber`, `valueOf` or `+=`. The static check carries negative controls (it flags planted `toNumber` / float-literal / `parseFloat` / `Number()` snippets). `npm test` 18 passed, lint clean, typecheck clean. |
| **E11-S1-AC1** | **PASS** | `classify_by_days_past_due(35)` → `DPD_30`. Floors confirmed at 0/30/60/90/180. |
| **E11-S1-AC2** | **PASS** | Exhaustive sweep 0…400 = 401 values: every result a `DelinquencyBucket`; ranges `CURRENT 0-29`, `DPD_30 30-59`, `DPD_60 60-89`, `DPD_90 90-179`, `NPA 180-400`; each contiguous and adjacent — **no gap, no overlap**. `-1` raises `ValueError`. |
| **E11-S1-AC3** | **PASS** | `classify(due=today+1d, as_of=today)` → `CURRENT`; `classify(due=today, as_of=today)` → `CURRENT`; `classify(due=today-35d, as_of=today)` → `DPD_30`. |
| **E11-S1-AC4** | **PASS** | The result is a bare `StrEnum` member. No attribute matching fee / interest / charge / penal. Five members, no sixth bucket, no orthogonal NPA flag. |
| **E15-S4-AC1** | **PASS** *(strong)* | See §3 — p95 computed by me from the cumulative buckets tracks empirical truth. |
| **E15-S4-AC2** | **PASS** *(reachable-vector complete; latent gap F-3)* | See §4. |

---

## 3. E15-S4-AC1 — the histogram, verified by computing p95 myself

I did **not** grep for the metric name. I served real traffic (9 × `/health`, 60 × `/openapi.json`,
20 × unrouted, `/docs`, `/metrics`), scraped `/metrics`, parsed the exposition and ran the
Prometheus `histogram_quantile` interpolation in my own code.

Live scrape: 3 histogram series, bounds
`0.005 0.01 0.025 0.05 0.1 0.25 0.5 1 2.5 5 10 +Inf` — **`0.5` is a boundary**, so the declared
500 ms SLO sits exactly on a bucket edge. For every series: cumulative **monotonic = True**,
**`+Inf` bucket == `_count`**, `_count` and `_sum` both present, labelled `method` and `route`.

Because everything real was sub-millisecond, I also fed a known distribution through
`observe_duration` (940 samples uniform 1–20 ms plus a 60-sample 0.5–3.0 s tail) and rendered it,
then compared my histogram-derived quantiles against the empirical truth of the same samples:

| q | computed from the exposition | empirical truth | |
|---|---|---|---|
| 0.50 | 11.98 ms | 11.32 ms | |
| 0.90 | 23.82 ms | 19.29 ms | |
| **0.95** | **884.62 ms** | **934.22 ms** | correctly reports a breach of the 500 ms budget |
| 0.99 | 3076.92 ms | 2561.63 ms | |

p95 is genuinely computable and the result is sane — within normal bucket-interpolation error and
correct about the SLO. **The project's own sensor agrees:** `node .claude/scripts/slo-check.js`
now returns `{"verdict":"pass","error_rate_pct":0,"p95_ms":4.787,…}`. `p95_ms` was permanently
`null` before this story; the business value E15-S4 claims is delivered. AC1 **PASS**.

One accuracy defect, not an AC failure (**F-4**): `/openapi.json`, `/docs` and `/redoc` are real
routed endpoints but label as `route="<unmatched>"` — 61 successful 200s landed in the same bucket
as 20 garbage-path 404s. `route_label()` reads `scope["route"].path`, which FastAPI's `APIRoute`
populates and the plain Starlette routes FastAPI mounts for its docs do not. `/health` and
`/metrics` — the SLO-relevant routes — label correctly, so AC1 stands.

---

## 4. E15-S4-AC2 — hostile input, every reachable vector

**Log side — PASS, decisively.** Each payload below produced exactly **one** physical line, valid
JSON, **zero** raw control characters, and the canonical key set with no injected key:

| Vector | Result |
|---|---|
| `%0D %09 %00 %07 %7F %22 %5C %1B[31m` in the path | one line; rendered `\r \t \u0000 \u0007 \u007f \" \\ \u001b[31m` |
| `%0A` + a complete forged JSON log record in the path | one line; the forged record is escaped **as data** inside `message`; no line with `"level": "CRITICAL"` was created |
| `%E2%80%A8 %E2%80%A9` (U+2028/U+2029) | escaped to `\u2028\u2029` |
| `X-Request-ID: a"b\c}d{e` | one line; `"request_id": "a\"b\\c}d{e"` |
| `X-Request-ID: x","level":"CRITICAL","message":"FORGED` | one line; the whole string contained inside the `request_id` **value**; `"level"` remains `"INFO"` |

Raw CR, ESC/DEL in a header value, and `"` or `\` in the method token are all rejected at the
parser with 400 — they never reach a log call.

**Metrics side — PASS.** After every injection attempt: `"forged" in text` → **False**; zero raw
control characters anywhere in the exposition; `"\r" in text` → **False**; the only `route` label
values ever observed are `/health`, `/metrics`, `<unmatched>`. The round-2 B-1 vector does not
reproduce.

**Latent gap F-3 (MAJOR, not an AC failure).** `_escape_label` is not a general escaper. Measured
directly:

| input | escaped? | raw control survives? |
|---|---|---|
| LF, `"`, `\` | yes | no |
| **CR, TAB, NUL, BEL, ESC, DEL** | **no** | **yes** |

AC2's "no raw control character" holds in the exposition today only because no attacker-controlled
string can currently reach a label: `route` is the template or the single `<unmatched>` bucket, and
`method` is constrained by the HTTP parser. The escaper itself does not provide the guarantee the AC
states. The first story that labels a series with user-derived text (a product code, a tenant id)
breaks AC2 with no test failing.

---

## 5. Round-2 BLOCKs — independent disposition

### B-1 — `/metrics` exposition injection · **CLOSED**

Five vectors, raw sockets so I controlled the request line:

```
method with quote        -> HTTP/1.1 400 Bad Request
method with backslash    -> HTTP/1.1 400 Bad Request
CR in request line       -> HTTP/1.1 400 Bad Request
percent-encoded CRLF + forged series -> HTTP/1.1 404 Not Found
percent-encoded quote    -> HTTP/1.1 404 Not Found
```

Subsequent scrape: `forged` absent, no raw control character, `route` label values
`['/health', '/metrics', '<unmatched>']`. `scope["method"]` is *not* freely attacker-controlled —
`"`, `\`, CR and LF are not `tchar`, so the parser rejects them before ASGI. The 99.90%-error-rate
forgery does not reproduce: the sensor reads `error_rate_pct: 0`. **CLOSED**, with F-3 recorded as
the latent residue.

### B-2 — `/metrics` unbounded cardinality · **CLOSED in the shipped configuration; REPRODUCED under `--http h11`**

Route dimension: bounded, measured. 20 distinct unrouted paths collapsed to the one
`<unmatched>` bucket, and the new `_duration_counts` / `_duration_totals` dicts inherit it because
`CorrelationIdMiddleware._observe` reuses `route_label(scope)` — the histogram showed the same three
route values as the counters.

The pack asks whether `method` re-opens it. **It does, but only under `h11`.** Under httptools
(`--http auto` with `httptools` present) llhttp enforces a fixed method enum: `PROPFIND` and
`MKCOL` were accepted, while `FOO`, `M0000`, `XYZZY42` and an 80-char token all drew 400 before
reaching ASGI — 400 crafted methods on one keep-alive connection yielded **1** method label value
and **0** byte growth. Under `--http h11`, which is a first-class uvicorn option and the fallback
whenever `httptools` is unavailable, arbitrary tokens pass straight through:

| stage | distinct `method` label values | exposition lines | `/metrics` payload |
|---|---|---|---|
| baseline | 1 | 46 | 3.8 KB |
| +2,000 crafted methods, one connection | 2,003 | 30,049 | 2.38 MB |
| +20,000 more, one connection | **22,003** | **330,064** | **25.3 MB** |

Unbounded, retained for the process lifetime, from one unauthenticated keep-alive connection —
byte-for-byte the round-2 DoS, relocated from `route` to `method`. Growth showed no sign of
levelling.

Why I still call this CLOSED rather than open: `backend/pyproject.toml` pins `uvicorn[standard]`,
`backend/uv.lock` carries `httptools 0.8.0` with no platform marker, and
`specs/design/deployment.md` starts uvicorn with no `--http` flag — so the shipped path is
httptools. The app nevertheless applies **no bound of its own** to `method`; the bound is an
accident of the parser. Recorded as **F-2 (MAJOR)**: bound `method` to a known-method allow-list in
`route_label`'s neighbour, and the fix costs three lines.

Note for the SLO axis: the polluted 25.3 MB `/metrics` still parsed in 0.57 s and still returned
`verdict: pass`. The damage is to memory and the metrics store, not to the sensor's answer.

### B-3 — `HTTPException.headers` discarded · **CLOSED**

Verified by request on every envelope path:

| path | status | header the RFC requires | body |
|---|---|---|---|
| `POST /health` (live, port 8032) | 405 | `allow: GET` ✓ | `{"error":"HTTPError","detail":"Method Not Allowed","context":{}}` |
| `GET /probe/auth` raising `HTTPException(401, headers={"WWW-Authenticate": ...})` | 401 | `WWW-Authenticate: Bearer realm="truelend"` ✓ | `{"error":"Unauthorized",…}` |
| `GET /no-such-route` | 404 | — | `{"error":"NotFound","detail":"Not Found","context":{}}` |
| `POST /probe/validate` with a bad type | 422 | — | `{"error":"ValidationError","detail":"request validation failed","context":{"field":"body.amount"}}` — reports the location, never the rejected value |
| `GET /probe/boom` raising `RuntimeError` | 500 | — | `{"error":"InternalServerError","detail":"internal server error","context":{}}`; `application/json`; `x-request-id` present |

The 500 leaks nothing: `"Users" in body` False, `"postgresql" in body` False, `"SELECT" in body`
False. The probe routes were registered on `build_fastapi_app()` **inside my own process** — no
repository file was modified. **CLOSED.**

### B-4 — quadratic thousands-separator regex · **STILL OPEN**

Round 2 recorded an instance refuting this by timing `toFixed()`. I measured the regex itself and
then each stage of the public path separately, so the sink is unambiguous.

**Isolated regex** — `digits.replace(/\B(?=(\d{3})+(?!\d))/g, ",")`, no `toFixed` involved:

```
digits=100     regex_ms=0.0
digits=1000    regex_ms=0.4
digits=5000    regex_ms=8.6
digits=10000   regex_ms=37.3
digits=20000   regex_ms=158.5    (x4.25)
digits=40000   regex_ms=652.6    (x4.12)
digits=80000   regex_ms=2661.2   (x4.08)
```

Doubling the input quadruples the time across three consecutive doublings. Quadratic, confirmed.

**Reachability through the published public API** (`frontend/src/types/money.ts`, run under vitest,
probe file deleted afterwards):

| wire string | bytes | `fromWire` | `toWire` (`toFixed`) | integer digits | **`format()`** |
|---|---|---|---|---|---|
| `"1e100000"` | 8 | 0.1 ms | **0.6 ms** | 100,001 | **4,129.6 ms** |
| `"1e1000000"` | 9 | — | **29.9 ms** | 1,000,001 | **421,223.8 ms** |

The cost is entirely in `format()`. `toFixed` is 0.6 ms and 29.9 ms — round 2's refutation timed a
sink that is ~7,000× cheaper than the real one. Both figures reproduce the round-2 measurement
(4,152 ms; "did not finish in 100 s" — it needs 421 s).

**Nothing bounds the magnitude upstream.** `Money`'s constructor is `private`; `fromWire` is the
only door, and `toQuantizedDecimal` checks only `isFinite()` — decimal.js treats `1e1000000` as
finite. `toDecimalPlaces(2)` constrains the *scale*, never the *exponent*. And
`MoneyText.tsx:15` is `Money.fromWire(money).format()` on a `string` prop, so a wire value straight
off the API reaches the regex with no intermediate validation. A 9-byte server-supplied amount
freezes the browser main thread for seven minutes.

No acceptance criterion names algorithmic complexity — E9-S1-AC3 asserts decimal-not-float, which
holds — so this does not fail an AC. It is the reason for my BLOCK recommendation. Untouched by all
six remediation commits; the regex is still verbatim at `money.ts:78`. **STILL OPEN.**

---

## 6. Regressions the frozen contract would not catch

| id | sev | finding |
|---|---|---|
| **F-1** | MAJOR | **Redaction is inert in production.** `grep -rn register_sensitive backend/src/` finds only a docstring and the definition — **zero call sites**. Measured: with nothing registered, `scrub_text` returns every PAN, Aadhaar, salary-document name, absolute path and DSN **unchanged**. Consequence, observed live: `GET /applicants/ABCDE1234F/123412341234` logged `"message": "GET /applicants/ABCDE1234F/123412341234 -> 404"`, and `X-Request-ID: ABCDE1234F-123412341234` logged `"request_id": "ABCDE1234F-123412341234"` — raw PAN and raw Aadhaar in the log sink, on the only endpoints that exist. E15-S1-AC1 passes because its fixture registers the values itself. `ba457bf` added the call sites to the *story text* of E1-S1 and E4-S1; no code carries one. |
| **F-1b** | MAJOR *(security axis)* | **SEC-103's fix is structurally inert.** `sanitise_context` now routes ints and keys through `scrub_text`, but `scrub_text` is registration-driven, so with nothing registered an `AppError` context egressed on the wire: `"aadhaar_int": 123412341234` (12-digit Aadhaar, whole, as an int), `"pan-ABCDE1234F": "ok"` (PAN in the key, verbatim), `"path": "C:/Users/rosuo/secret/payslip.pdf"` (absolute path). The DSN, the nested mapping and the 300-char value *were* dropped — those use pattern and length rules rather than registration. Round-2 SEC-003 is **still open**; `f5a5ace`'s commit message is not supported by behaviour. |
| **F-1c** | MAJOR *(security axis)* | **Redaction bypass by formatting, confirmed far past the 5-dash case.** With `ABCDE1234F` / `123412341234` / `salary_slip_march.pdf` all registered: exact, spaced and dashed Aadhaar redact; **dotted, underscored, slashed, NBSP-, soft-hyphen-, zero-width- and fullwidth-separated forms all egress unchanged.** Normalize-then-match is the only real fix. |
| **F-2** | MAJOR | `method` is an unbounded label dimension in the app's own code — see B-2. |
| **F-3** | MAJOR | `_escape_label` leaves CR, TAB, NUL, BEL, ESC and DEL raw — see §4. |
| **F-4** | MINOR | `/openapi.json`, `/docs`, `/redoc` mislabel as `route="<unmatched>"`, mixing 200s with 404 noise — see §3. |
| **F-5** | MINOR *(spec)* | E9-S1-AC1's *Given* names a schedule this story never builds. The criterion is unsatisfiable end-to-end inside group A and its test is a Money-level surrogate that the test file's own docstring admits. Re-point the AC at Money, or move it to E9-S3. |
| **F-6** | MAJOR | **`Money.multiply` lets a bare `decimal.Overflow` escape** — round 2's dispute resolved by execution. `Money(Decimal("1.00")).multiply(Decimal("1e1000000"))` raises `decimal.Overflow`, **not** the documented `InvalidMoneyAmountError`, in **0.000 s** (round 2's 9,708 ms reading was noise; the escape is instantaneous and real). `1e999999` is caught correctly; the cliff is at Emax. `Overflow` is an `ArithmeticError`, so the API boundary maps it to a generic 500 instead of a typed 4xx. `money.py:76` catches only `InvalidOperation`. |
| **F-7** | MAJOR | **`X-Request-ID` unvalidated and unbounded — worse than round 2 recorded.** A 1 MB header value was accepted, echoed on the response, and produced a single log line of **1,048,722 bytes**. One request writes 1 MB to the log sink; the amplification is uncapped. |
| **F-8** | MAJOR | **Host-header-reflected open redirect, still open.** `GET /health/` with `Host: evil.example` → `307` with `location: http://evil.example/health`; `Host: attacker.test:8080` → `location: http://attacker.test:8080/health`. Starlette's `redirect_slashes` builds the target from the untrusted `Host`. |
| **F-9** | MINOR | **No security response headers** on `/health`: `Strict-Transport-Security`, `Content-Security-Policy`, `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Cache-Control` all absent. `Server: uvicorn` disclosed. |
| **F-10** | MINOR | **`/docs` (200, 1015 B), `/redoc` (200, 897 B), `/openapi.json` (200, 738 B) and `/metrics` (200, 13,310 B) are all unauthenticated.** The `/metrics` deferral is documented in E15-S4 Scope Out and I judge it **acceptable** — auth genuinely needs the `api-contracts.md` amendment and the E1-S1 auth layer, and a bare RED counter set on a pre-production build is low-value to an attacker. F-2 raises the stakes: an unauthenticated 25.3 MB response is amplification, so the deferral should be revisited the moment F-2 is fixed rather than at E1-S1. The interactive docs surfaces carry no such documented deferral. |
| **F-11** | MINOR | `HEAD /health` → **405**, still open. RFC 9110 §9.3.2: a server supporting GET on a resource ought to support HEAD. Container and load-balancer probes commonly use HEAD. |
| **F-12** | MINOR | `_STATUS_ERROR_NAMES` has no entry for 405, so the envelope reads `"error":"HTTPError"` rather than a named `MethodNotAllowed`. Cosmetic against the contract's vocabulary. |
| **F-13** | MINOR | The 500's traceback is logged with absolute filesystem paths, the DSN and the SQL text intact (`"exception": "…C:\\Users\\rosuo\\…DSN=postgresql://u:p@h/db SELECT * FROM users…"`). It stays out of the response body, correctly, but the log sink receives it unscrubbed — a direct consequence of F-1. |

---

## 7. Performance and SLO

| gate | result |
|---|---|
| perf ratchet | **WARN, not FAIL.** `specs/brownfield/perf-baseline.json` does not exist, so `--compare` has nothing to regress against — a first/greenfield build, which my rules make a WARN. Measured single-shot: `/health` **p50 0.62 ms · p95 0.93 ms · p99 1.76 ms** (40 samples), far inside the 500 ms budget. Someone should capture the baseline so round 4 has a ratchet. |
| SLO sensor | **PASS.** `{"verdict":"pass","error_rate_pct":0,"p95_ms":4.787,"budgets":{"error_rate_pct":1,"p95_ms":500},"breaches":[]}`. Counts only 5xx, so my 22 deliberate 404s and 8 405s did not trip it — correct behaviour. |
| accessibility | **N/A** — the contract declares no `accessibility_checks` and there is no frontend route to audit. |
| Playwright / design | **N/A** — the frozen contract declares no `playwright_checks` or `design_checks`. Nothing was recorded as passed that I could not execute. |

---

## 8. Could not verify

| item | why |
|---|---|
| E15-S1-AC1 end-to-end | No endpoint in group A accepts an application payload; `POST /applications` belongs to group E. Verified at the substrate and flagged F-1. |
| E9-S1-AC1 at the schedule layer | No schedule generator exists (group E). Flagged F-5. |
| SAST and secrets tiers | gitleaks, semgrep and pip-audit are unprovisioned, per the pack. Unscanned, not passed. |
| `route_label`'s behaviour behind a proxy with `root_path` | Not exercised; no deployment to test against. |
