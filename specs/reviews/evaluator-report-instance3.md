# Evaluator report — group A, instance 3 of 3 (round 3)

**Lane:** `/gate` runtime re-verification · **Mode:** `local` (Docker not installed)
**HEAD at evaluation:** `ba457bf` · **Base:** `14e9487` · **Port owned:** 8033
**Model tier:** Opus 5 (runtime mode) · **Independent:** no sibling context consumed;
prior verdict files were not read as authority.

## FUNCTIONAL VERDICT: PASS

All 3 frozen `api_checks` pass, and all 15 story acceptance criteria across
E15-S1, E9-S1, E11-S1 and E15-S4 verify by execution. **E15-S4-AC1 and
E15-S4-AC2 pass on their merits, including the cumulative-bucket property and
p95 computability.**

**This does not mean the gate should open.** B-4 is a *confirmed, measured,
by-design-reachable* quadratic DoS that no remediation commit touched, and
`_escape_label` — the stated defence for half of AC2 — is *completely
unverified* by the suite (proved by a surviving mutant). Neither is covered by
an acceptance criterion, so neither moves the functional verdict; both belong
to the security / code-review axes of this gate.

---

## 1. Test-environment integrity (read this first)

Two facts materially affect how any round-3 verdict should be weighed.

**1a. The working tree was mutated by concurrent siblings during my run.**
At 16:11:15 local I observed `backend/src/api/middleware.py` on disk carrying
`return str(scope.get("path", "-"))  # MUTANT: raw path label` at line 63 —
not HEAD. It was restored by its author within seconds; `routes.py` was
touched in the same window (mtime 16:10:56). A sibling also wrote
`frontend/tests/unit/_eval_i2_b4.test.ts` into the tracked test tree.

Consequence: **any in-process measurement taken in the shared tree during
round 3 is of unknown provenance.** My own timeline is clean — the uvicorn
process (PID 79052) was started at 16:05:46 without `--reload`, so it holds
modules loaded from clean HEAD and is immune to on-disk edits; and my one
earlier in-process run finished at 16:07:07, before the mutation window.

From that point on I ran every in-process check against a **pristine HEAD
snapshot** (`git archive HEAD | tar -x` into a scratch dir), verified
byte-identical:

```
git hash-object <pristine>/backend/src/api/middleware.py -> 3fc9b46a9aea2de61fda97b82d0b495e1449e050
git rev-parse HEAD:backend/src/api/middleware.py         -> 3fc9b46a9aea2de61fda97b82d0b495e1449e050
```

Recommendation for round 4: give each evaluator its own `git worktree`, not
just its own port. Mutation testing in a shared tree is not safely
parallelisable.

**1b. My own tree is clean.** Every mutation I ran was applied to the pristine
scratch copy, never to `backend/src/**`. Final state:

```
$ git diff --stat -- backend/src frontend/src sprint-contracts specs/design
(empty)
```

Scratch dirs (`backend/.eval-i3`, `frontend/.eval-i3`) removed. Server killed
(`taskkill /PID 79052 /F` → SUCCESS; post-kill probe returns `000`).
`sprint-contracts/**`, `architecture.md`, `api-contracts.md` and
`data-models.md` were never opened for write.

---

## 2. Frozen `api_checks` — Layer 1

Health-check retry loop cleared on attempt 1 (`GET /health` → 200).

| Check | matrix | Result | Evidence |
|---|---|---|---|
| QA-VM-003 | VM-003 | **PASS** | `GET /health` + `X-Request-ID: req-abc` → `200`, `x-request-id: req-abc` echoed. 1 log line emitted while serving; it parses as JSON and carries `"request_id": "req-abc"`. |
| QA-VM-004 | VM-004 | **PASS** | No inbound header → `200`, generated `3a1129547efc44fca21087b0bdede3a8`, echoed on the response and carried by the request-scoped log line. |
| QA-VM-005 | VM-005 | **PASS** | 10 consecutive samples, all `200`, JSON body `{"status":"ok","database":"unconfigured","version":"0.1.0"}`, `time_total` 1.317–1.486 **ms** (budget 1 s). |

Whole-log integrity across the run: **26/26 emitted lines parse as JSON**, 0
non-parsing.

**Caveat on QA-VM-003/004 strength (not a failure).** "100% of the log lines
emitted while serving" is satisfied by a population of **one** line — the
middleware's own access line. The assertion is true but nearly unfalsifiable
at this population size; it will only become load-bearing once a handler emits
its own lines.

## 3. Story acceptance criteria

| AC | Verdict | How verified (execution) |
|---|---|---|
| E15-S1-AC1 | **PASS (mechanism)** | Redaction demonstrably works: `test_redaction_survives_an_exception_escaping_the_registration_scope` shows `[REDACTED]` present and the PAN absent through the real ASGI stack. **But see finding V-1** — the AC's premise ("an application payload … when the request is served") does not exist; the story's own Scope Out forbids the endpoint that would create it. |
| E15-S1-AC2 | **PASS (with caveat)** | 100% of loggers present at `configure_logging()` time carry a `RedactionFilter`. **Measured gap:** a logger created *after* configure (`story.e4.origination`) has **no own filter** (`False`); redaction still holds because the root **handler** carries one (`True`). No leak; the AC's "100%" is time-of-configure scoped. See V-2. |
| E15-S1-AC3 | **PASS** | = QA-VM-003, live over HTTP. |
| E15-S1-AC4 | **PASS** | = QA-VM-004, live over HTTP. |
| E15-S1-AC5 | **PASS** | = QA-VM-005, live over HTTP. |
| E9-S1-AC1 | **PASS** | 2 000 seeded random (principal, rate, tenure) triples × 4 derived money fields = **8 000 values, 0 with `as_tuple().exponent != -2`**. Note: no *schedule* exists in group A, so I exercised the `Money` add/subtract/multiply arithmetic a schedule composes from. The literal "schedule" premise defers to E9-S3/E3. |
| E9-S1-AC2 | **PASS** | Project's own static check green inside the 104-pass run, **plus** an independent `ast.walk` over `types/money.py` + `api/serializers.py`: the single `float` reference is `isinstance(value, float)` at `money.py:36` — a float *rejection*. **0 float arithmetic operations.** |
| E9-S1-AC3 | **PASS** | `vitest run tests/unit/money.test.ts` → 18/18. Independent scan of `money.ts` for `parseFloat`/`parseInt`/`Number(`/`toNumber`/`.valueOf()`/`Math.`/numeric operators: **no number-arithmetic constructs**. `private readonly amount: Decimal`. |
| E11-S1-AC1 | **PASS** | `classify_by_days_past_due(35)` → `DPD-30`. |
| E11-S1-AC2 | **PASS** | 0–400 exhaustive sweep against the **AC's own literal floor table typed out from the story file** (deliberately *not* re-derived from `DPD_BUCKET_FLOORS`, which would pass by construction): **0 mismatches over 401 values, exactly 5 distinct buckets, no gap, no overlap.** |
| E11-S1-AC3 | **PASS** | `classify(today + 5d, today)` → `CURRENT`; `classify(today, today)` → `CURRENT`. |
| E11-S1-AC4 | **PASS** | 5 enum members; 0 public attributes matching fee/interest/charge/penal; payload is `<DelinquencyBucket.NPA: 'NPA'>` — a bucket only. |
| **E15-S4-AC1** | **PASS** | See §4. |
| **E15-S4-AC2** | **PASS** | See §5. |

## 4. E15-S4-AC1 — histogram, cumulative buckets, p95 computable

**Exposition is present and correctly labelled.** Live scrape of
`http://127.0.0.1:8033/metrics`:

```
# TYPE http_request_duration_seconds histogram
http_request_duration_seconds_bucket{method="GET",route="/health",le="0.005"} 13
... 12 bucket lines including le="+Inf" ...
http_request_duration_seconds_count{method="GET",route="/health"} 13
http_request_duration_seconds_sum{method="GET",route="/health"} 0.008714
```

`method` and route **template** labels, a `+Inf` bucket, `_count` and `_sum`.

**Buckets are genuinely cumulative — and I proved it in the only way that can
distinguish the two implementations.** Every `/health` request lands in bucket
0, so a cumulative and an increment-only-the-matching-bucket renderer produce
*identical* output. I therefore registered a throwaway slow route on the inner
app (the documented test seam in `app.py`) and drove 19 fast + 1 × 700 ms
request through the **real** `CorrelationIdMiddleware` and the **real**
`_histogram_lines()`:

```
bucket counts: [19, 19, 19, 19, 19, 19, 19, 20, 20, 20, 20, 20]
monotone non-decreasing (cumulative): True
strictly cumulative (not increment-only): True
```

An increment-only renderer would have produced `[19,0,0,0,0,0,0,1,0,0,0,0]`.
Confirmed by mutation: rewriting `running += count` → `running = count` in the
pristine copy **fails** `test_histogram_buckets_are_cumulative_and_carry_count_and_sum`.

**p95 is computable, and no longer null.** This project's own sensor against
the live endpoint:

```
$ node .claude/scripts/slo-check.js --url http://127.0.0.1:8033 --root <scratch>
{"verdict":"pass","error_rate_pct":0,"p95_ms":4.75,
 "budgets":{"error_rate_pct":1,"p95_ms":500},"breaches":[]}
```

`p95_ms: 4.75` (was permanently `null`), `error_rate_pct: 0` against a 1%
budget. AC1's stated purpose — "measurable rather than always null" — is met.
I ran the sensor with `--root` pointed at a scratch dir so it would not
clobber the canonical `specs/reviews/slo-verdict.json` another instance owns.

## 5. E15-S4-AC2 — one line per record, no raw control character, no injected series

**Log half — PASS.** The hostile percent-encoded path (`%22 1%0D%0A…%00`) is
logged by the access line as **exactly one record**, with CR/LF rendered as
`\r\n` and NUL as ` `:

```json
{"timestamp":"…","level":"INFO","logger":"truelend.access",
 "message":"GET /x\" 1\r\nhttp_requests_total{method=\"GET\",route=\"/f\",status=\"500\"} 999999  -> 404",
 "request_id":"5826ff8fada54412b716b7d0565be3ea"}
```

Byte-level audit of the whole 17 MB server log: the **only** bytes below 0x20
other than LF are 27 × `0x0D`, and **all 27 are immediately followed by
`0x0A`** — i.e. Windows text-mode line terminators, not injected content.
First occurrence context: `…"request_id": ""}\r\n{`. 26/26 records parse as
JSON.

**Metrics half — PASS.** No forged series, no raw control character in the
exposition (`cat -A` shows only `$` line ends). Exactly 3 route label values.

## 6. Round-2 BLOCK re-verification

### B-1 — `/metrics` exposition injection: **CLOSED**

I attacked **every** channel that reaches a label, not just the path, using raw
sockets (not a client library that would normalise the attack away).

| Channel | Payload | Server response |
|---|---|---|
| `method` unknown token | `FOO /health` | **400 Bad Request**, no `x-request-id` → rejected by the protocol parser *before* the ASGI app |
| `method` with `"` | `GE"T /health` | **400** |
| `method` carrying a whole forged series with CR | `A"} 1\rhttp_requests_total{…} 999999 /health` | **400** |
| `method` with a C0 char | `GE\x01T /health` | **400** |
| `X-Request-ID` with CR + `"` + C1 | `a\rb"c\x01d` | **400** |
| `X-Request-ID` with NUL | `a\x00b` | **400** |
| path, percent-encoded CRLF + NUL + full forged counter | `/x%22%201%0D%0A…%00` | **404**, reached the app, **no forged series** |

The pack asked two specific questions:

- **Is `scope["method"]` attacker-controlled?** **No.** `uvicorn[standard]`
  parses with httptools/llhttp, which rejects any method outside its table
  with a 400 raised *below* the ASGI layer — those requests are never counted
  and never labelled. Every hostile method above, including plain valid-token
  `FOO`, was refused. So the `method` label is drawn from a small fixed set.
- **Is carriage return still unescaped?** **Yes, and 29 other C0 characters
  are too** — but it is **not reachable**, and even if it were it would not
  forge a series. Feeding the *real* `_histogram_lines()` a CR-bearing hostile
  label value, the quote escaping holds:

```
chars _escape_label leaves RAW: '\x01'…'\x08', '\t', '\x0b', '\x0c', '\r', '\x0e'…'\x1f'   (30 of them)
resulting exposition, parsed by this project's own prom-parse.js: []   errorRate: null
```

The forged series does **not** materialise (the `"` is escaped). The residual
effect would be *unparseable* lines → `errorRate: null` → `slo-check.js`
degrades to `warn` (exit 2) rather than reporting a forged 99.90%. That is a
metrics-availability gap, not a forgery, and it is unreachable today. Filed as
**V-3 (minor)**, not a BLOCK.

**Verified against this project's own sensor:** after all seven attack probes
plus 80 000 further requests, `slo-check.js` reports `error_rate_pct: 0` and
`verdict: pass`. A crafted request **cannot** move `error_rate_pct` or
`p95_ms` by writing the data plane. (It can still move the *denominator* by
sending ordinary unauthenticated traffic — inherent to an unauthenticated RED
endpoint, and the deliberate E15-S4 Scope Out deferral to E1-S1. I judge that
deferral acceptable: it is documented, it needs an `api-contracts.md`
amendment, and the forgery vector it used to compound is now closed.)

### B-2 — `/metrics` unbounded cardinality: **CLOSED (measured at the original 60 000 scale)**

Reproduced round 2's exact attack shape — pipelined keep-alive connections,
each request a distinct unmatched path:

| Requests | route label values | exposition lines | server RSS |
|---|---|---|---|
| — (before) | 3 (`/health`, `/metrics`, `<unmatched>`) | 49 | 57 212 K |
| 20 000 | **3** | **49** | 57 212 K (+708 K from the 56 504 K start) |
| 60 000 | **3** | **49** | **57 588 K (+376 K)** |

Round 2 measured **60 000 label values / +28.2 MB** for the same input. Now:
**3 label values, +0.37 MB, exposition size unchanged.**

**The new `_duration_counts` / `_duration_totals` dicts inherit the bound** —
they are keyed `(method, route_label(scope))` by the same function, and the
exposition stayed at 49 lines throughout, which it could not have done if the
histogram were minting keys. **`method` does not re-open it:** per B-1, an
arbitrary method token never reaches the counter at all (400 below the ASGI
layer), so `method` is a small fixed set.

Confirmed by mutation: reverting `route_label` to the raw path in the pristine
copy fails **4** tests, including both cardinality tests.

### B-3 — `errors.py` discarded `HTTPException.headers`: **CLOSED**

Verified by request on every path the pack named.

| Path | Status | Header preserved |
|---|---|---|
| `HEAD/POST/PUT/DELETE/OPTIONS/PATCH /health` (live HTTP) | 405 | **`allow: GET`** on all six |
| `/guard` | 401 | **`www-authenticate: Bearer realm="truelend"`** + `x-extra: kept` |
| `/limited` | 429 | **`retry-after: 120`** |
| `/validated` (missing param) | 422 | envelope `{"error":"ValidationError","detail":"request validation failed","context":{"field":"query.count"}}` — no rejected value echoed |
| `/boom` (unhandled) | 500 | `{"error":"InternalServerError","detail":"internal server error","context":{}}` — no path, no SQL, no credential URI |

Every one also carries `x-request-id`. Confirmed by mutation: dropping
`headers=exc.headers` fails `test_http_exception_headers_survive_the_envelope`
— this fix is genuinely covered, not accidentally green.

`HEAD /health → 405` remains true (RFC 9110 §9.3.2 expects HEAD wherever GET
is supported). Pre-existing round-2 WARN, unchanged, still open.

### B-4 — `frontend/src/types/money.ts:78` quadratic lookahead: **STILL OPEN**

The pack is right that the line is verbatim at HEAD, and right that round 2's
evaluator-3 refutation timed the wrong sink. **I measured the sinks
separately, which is what settles it.**

```
Input Decimal("1e100000") -> 100 001-digit integer part
  toFixed(2) only                     ->      3.2 ms
  regex /\B(?=(\d{3})+(?!\d))/g only  ->  4 042.6 ms
```

`toFixed()` is **1 260× cheaper** than the regex. The cost is essentially
100% in the lookahead. Scaling, measured in isolation:

| digits | ms |
|---|---|
| 1 000 | 0.4 |
| 10 000 | 36.5 |
| 19 953 | 155.0 |
| 50 119 | 1 010.8 |
| 100 000 | 4 056.1 |

10× input → ~100× time: **quadratic, confirmed empirically.**

**Reachability through the public API — confirmed, not inferred.** Executed
through the real `Money` class under vitest:

```
Money.fromWire("1e100000") succeeds; toWire().length === 100004
toWire()=0.4ms   format()=4102.0ms
format() by magnitude: 1e10000: 37.9ms | 1e20000: 164.4ms | 1e40000: 648.9ms | 1e80000: 2618.0ms
```

The path is not exotic — it is the component's declared contract:

```ts
// frontend/src/ui/components/MoneyText.tsx:10-15
readonly money: Money | string;
const value = typeof money === "string" ? Money.fromWire(money) : money;
return <span>{value.format()}</span>;
```

`MoneyText` accepts an **arbitrary string** and pipes it straight to
`fromWire().format()` with no length or magnitude bound. `fromWire` rejects
only non-finite values; `1e100000` is finite to decimal.js
(`Decimal.maxE` = 9e15). So an 8-character API response field freezes the
render thread for ~4 s, and the 9-character `1e1000000` extrapolates to
~410 s on the measured quadratic curve (not measured — I declined to burn
7 minutes on it; the curve is established by five points).

**Is it bounded upstream?** Not by anything that exists. The *backend* is safe
(`Decimal.quantize` raises `InvalidOperation` on such magnitudes, and
`MoneyField`'s `_WIRE_PATTERN` is `^-?\d+\.\d{2}$`), but that pattern
constrains **OpenAPI documentation**, not `Money.fromWire`, and there is no
inbound validation on the frontend at all. Today no endpoint returns money, so
this is **latent rather than live** — which is exactly why it will ship: it
becomes live the first time a group-B/E money field reaches a `MoneyText`, and
nothing in the codebase will object.

**Severity: high, still open.** No AC covers `format()` cost, so it does not
change my functional verdict — but it should block this gate. Fix is one line:
bound the integer part before grouping (or group with a right-to-left slice
loop instead of a lookahead).

---

## 7. Attacking the verification itself (task 4)

I mutated the pristine HEAD copy and re-ran the full 104-test suite. A mutant
that **survives** is a behaviour no test actually checks.

| # | Mutation | Suite result | Verdict |
|---|---|---|---|
| M1 | `_escape_label` → `return value` (**all escaping removed**) | **104 passed** | **SURVIVED** |
| M2 | `running += count` → `running = count` (non-cumulative histogram) | 1 failed | killed |
| M3 | `route_label` → raw `scope["path"]` | 4 failed | killed |
| M4 | `handle_http_error` drops `headers=exc.headers` | 1 failed | killed |

### V-0 (major) — `_escape_label` is entirely unverified; two tests named for it pass without it

Deleting every Prometheus label escape leaves **all 104 tests green**,
including both tests whose names assert the property:

- `tests/unit/test_health_probe.py::test_metrics_labels_cannot_be_injected_from_a_request_path`
- `tests/architecture/test_observability_contract.py::test_histogram_labels_cannot_be_injected_from_a_request_path`

Their PASS does not depend on the behaviour they name. They pass because
`route_label()` now returns a bounded template, so the crafted path never
reaches a label at all — which M3 confirms (those same tests are the ones M3
kills). Escaping is the *documented* defence for AC2's "no injected series"
(`routes.py:74-83` and the AC2 clause in Operation 2), and it is dead code
from the suite's point of view.

Why it matters concretely: the escape table omits CR and 29 other C0
characters (§6, B-1). That is harmless only while every label value is drawn
from a fixed set. The moment any story labels by a value derived from user
input — a product code, a tenant, an error class; all plausible next steps —
the only guard is an untested, incomplete escape table, and no test will
notice.

**Fix:** unit-test `_escape_label` directly against `\\`, `"`, `\n`, `\r` and
a C0 sample. Do not test it through a request; the request path can no longer
carry the payload to it.

### V-1 (major) — E15-S1-AC1 passes by construction; its premise cannot exist in this story

The AC says "*Given an application payload carrying synthetic PAN, Aadhaar and
salary-document content, when the request is served* …". No endpoint accepts a
payload, and the story's own **Scope Out** forbids adding one ("must not add
any business endpoint beyond /health"). The test satisfies the AC by calling
`redact_values(...)` **itself** and then asserting the values it just
registered are absent, while the *served* request is `GET /health`, which
carries no PII at all. There are **zero** `register_sensitive` /
`redact_values` call sites in `backend/src/`.

To the suite's credit this is documented rather than hidden — the docstring of
`test_modules_handling_applicant_pii_enter_a_redaction_scope` says "AC1 passes
solely because its own test registers the values it then asserts absent", and
a paired `test_pii_redaction_control_is_not_vacuous` proves the future control
bites. That is good engineering. It does not make AC1 *verified*: the AC as
written is unsatisfiable inside its own scope, which is a **spec** defect.
`ba457bf` claims to have added the call sites "to the spec Operations" — they
are in the spec, not in code, so the round-2 escalation trigger ("if call
sites now exist in code, severity rises") has **not** fired.

### V-2 (minor) — E15-S1-AC2's enumeration is circular, and "100%" is time-scoped

`test_redaction_filter_installed_on_every_configured_logger` walks the same
`logging.root.manager.loggerDict` that `_install_redaction_filter_everywhere`
had just walked — it cannot fail by construction. Its non-vacuity probe,
`logging.Logger("unregistered-probe-logger")`, is built by *constructor*, so
it never enters `loggerDict`; it proves only that the predicate returns
`False` for a bare object, not that the enumeration would catch a genuinely
registered logger missing the filter. Round-2 WARN confirmed **still open**.

Measured consequence: a logger created after `configure_logging()` has **no
own filter** (`False`). Redaction survives because the root *handler* carries
a `RedactionFilter` (`True`), so there is **no leak** — but the AC's claim
"installed on 100% of them" is true only at time-of-configure, and the
per-logger filters are belt-and-braces over the handler that does the real
work.

`test_redaction_filter_covers_every_logger_under_the_real_server_config` is a
genuine improvement (it applies uvicorn's `dictConfig` first) but shares the
same shape: it calls `configure_logging` *after* the dictConfig, so it again
asserts over exactly the set just processed.

### V-3 (minor) — `_escape_label` covers 3 of 32 control characters

`str.maketrans({"\\": r"\\", '"': r"\"", "\n": r"\n"})` leaves `\t`, `\r` and
28 other C0 characters raw (enumerated in §6). Unreachable today; would
degrade the exposition to unparseable (→ `errorRate: null` → sensor `warn`)
rather than forgeable, because the quote escape holds.

### V-4 (minor) — assertions that would miss a missing header

`test_observability_contract.py` asserts only on `client.get("/metrics").text`
— it never checks the response is `text/plain`. A `/metrics` that regressed to
`application/json` would keep every test green while no Prometheus scraper
could read it. Same class as B-3's original defect (body asserted, header
ignored). The live endpoint *is* correct (`PlainTextResponse`); the test just
would not notice if it stopped being.

### V-5 (minor) — E9-S1's Operation 4 artifact does not exist

The generation contract names `frontend/vitest.config.ts` (new). It is absent;
the test config lives inside `frontend/vite.config.ts`. Functionally
equivalent (18/18 tests run), so no AC is affected — a traceability
discrepancy between Operations and the tree.

---

## 8. Gate-adjacent signals

**Deterministic suites, re-run at HEAD in the pristine snapshot** (immune to
the §1a mutation window): **104 passed**. Matches the pack's claim.

**Performance ratchet: WARN (no baseline).** No `perf-baseline*` file exists
anywhere in `specs/reviews/` or `.claude/state/`, so there is nothing to
compare against — first-build WARN per the ratchet rule, not a FAIL. Absolute
figures are comfortable: `/health` p50 ≈ 1.4 ms over 10 samples, sensor
`p95_ms: 4.75` against a 500 ms budget.

**SLO sensor: pass.** `error_rate_pct: 0` (budget 1%), `p95_ms: 4.75`
(budget 500), `breaches: []`, exit 0 — after 80 000+ requests including seven
hostile probes.

**Accessibility / Playwright / design layers: not applicable.**
`sprint-contracts/A.json` contains `api_checks` only — no `playwright_checks`,
`design_checks` or `accessibility_checks`. There is no runnable UI in group A
(the frontend ships `Money` + `MoneyText`, no page and no
`ui_base_url` server). No contracted browser check was skipped, so no
`untested` ledger entry is owed for Layer 2.

---

## 9. Things I could not verify

1. **The 9-byte `1e1000000` B-4 case.** Extrapolates to ~410 s from five
   measured points. I declined to spend 7 minutes of wall clock to confirm a
   curve already established across a 250× input range.
2. **Whether round-3's *other* in-tree measurements are sound.** Per §1a, at
   least two production files were mutated and restored in the shared tree
   during the review window. I can vouch only for my own numbers.
3. **SAST / secrets tiers.** gitleaks, semgrep and pip-audit remain
   unprovisioned (pack §6). I did not re-provision them; treat those tiers as
   **unscanned**, not passed. Out of my lane, but it bears on the gate.
4. **`method`-label cardinality under a non-default HTTP parser.** Everything
   in §6 assumes `uvicorn[standard]`'s httptools. Under `--http h11` (or with
   httptools absent) arbitrary method *tokens* are accepted, which would
   reopen cardinality on the `method` axis — no injection, since h11's token
   grammar excludes quotes and control characters. `docker-compose.yml` does
   not exist yet (arrives with E15-S2), so the production invocation is
   unpinned. Worth pinning `--http httptools` explicitly when the deploy story
   lands.

## 10. Recommendation

**Functional: PASS.** Gate-level: **do not merge** until B-4 is fixed (one
line) and V-0 is closed with a direct `_escape_label` unit test. V-1 should be
recorded as a spec defect against E15-S1-AC1 rather than silently carried as a
green criterion.
