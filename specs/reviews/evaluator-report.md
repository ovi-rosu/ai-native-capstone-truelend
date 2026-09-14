# Evaluator Report — /gate --group A, round 4, instance 1 (CANONICAL)

- **Axis:** functional — do the frozen contract and the story ACs hold?
- **Worktree:** `C:/Users/rosuo/WORK/ai-native-capstone-truelend/.claude/worktrees/agent-a796ad1a6d6d03a67`
- **HEAD under test:** `f3c25eb`
- **App under test:** `uvicorn src.api.app:app --host 127.0.0.1 --port 8011 --http h11` (verification.mode = local)

## FUNCTIONAL VERDICT: PASS

Frozen API checks **3/3**. Story acceptance criteria **14/14**. Nothing recorded untested.

A separate gate recommendation follows in section 8; it is deliberately NOT folded into the axis vote.

## 0. Worktree provisioning defect (found before any measurement)

This worktree was created from `master` (commit `c4189ec`, a README-only tree) rather than from
`feat/harness-scaffold-and-planning`. `specs/`, `backend/` and `frontend/` did not exist, so there was
nothing to evaluate. Fixed inside my own worktree by resetting hard to `f3c25eb`, verified by
`log --oneline -1`. `frontend/node_modules` was also absent (untracked); installed with `npm ci`.
Filed as **GI-008** below, because the round-4 isolation fix (GI-005) will silently produce vacuous
PASS verdicts from any instance that does not notice.

## 1. Frozen API checks — 3/3 PASS

Health-check retry loop first: `GET /health` returned 200 on attempt 1.

| Check | Measurement | Observed | Verdict |
|---|---|---|---|
| QA-VM-003 | `GET /health` with `X-Request-ID: req-abc`, byte-offset capture of the log stream | 200; header echoed `req-abc`; 1 line in window; 1/1 parsed as JSON; 1/1 carried `request_id == req-abc`; 0 non-JSON; 0 wrong-id | PASS |
| QA-VM-004 | `GET /health` with no inbound id | 200; echoed `c72ea1cd01414a45866e3a4187e8632c`; distinct request_ids in window == {that id}; non-empty | PASS |
| QA-VM-005 | 12 timed `GET /health` after 3 warmups | 200; `application/json`; body `{status:ok,database:unconfigured,version:0.1.0}`; **max 16.32 ms** against a 1000 ms budget | PASS |

Two round-3 instances were right that three `GET /health` calls are too narrow to carry a merge
decision. I concur: the frozen contract exercises one route and zero write paths. Every finding below
came from work outside it.

## 2. PRIORITY 1 — `ab0fd6e` restructured request accounting: measured by execution

Driven in-process through `create_app()` with a hand-rolled ASGI `send` I could make fail, so the
status carried in `seen: list[int]` is observable. Counters reset before each scenario.

| # | Scenario | `_request_counts` after | Duration obs | Correct? |
|---|---|---|---|---|
| S1 | normal 200 `/health` | `{(GET, /health, 200): 1}` | 1 | yes |
| S2 | 404 unmatched path | `{(GET, <unmatched>, 404): 1}` | 1 | yes |
| S3 | 405 wrong method | `{(POST, /health, 405): 1}` | 1 | yes |
| S4 | app raises `RuntimeError` | `{(GET, /boom, 500): 1}` | 1 | yes |
| S5 | `send` fails **at** `http.response.start` | `{(GET, /health, **200**): 1}` | 1 | **NO** |
| S6 | `send` fails at body, after 200 start | `{(GET, /health, **200**): 1}` | 1 | **NO** |
| S7 | mid-stream failure after 200 start | `{(GET, /stream, **200**): 1}` | 1 | **NO** |
| S8 | handler raises `asyncio.CancelledError` | `{(GET, /cancel, **500**): 1}` | 1 | **NO** |
| S9 | outer task cancelled mid-request | `{(GET, /slow, **500**): 1}` | 1 | **NO** |
| S10 | handler raises `SystemExit` | `{(GET, /sysexit, **500**): 1}` | — | **NO** |

**Double counting: not reachable.** `_observe` ran exactly once per request on both branches in every
scenario above — S1 through S10 each produced exactly one counter entry and exactly one duration
observation. The only theoretical double-count is that `self._observe(...)` sits *inside* the `try`
(middleware.py:212), so if `_observe` itself raised, the `except BaseException` at 213 would call it a
second time. I could not make `record_request` raise, so I record this as a latent structural hazard,
not a defect.

**Wrong status: reachable, two ways.**

- S5/S6/S7 — `seen.append(status)` happens at middleware.py:175, *before* `await send(message)` at 177.
  A response that never reached the client is therefore recorded as **served with the status it
  intended**. This is **CR-314, still open in a new form**.
- S8/S9/S10 — the `seen[0] if seen else 500` default at middleware.py:193 fires only for `BaseException`
  escapes, because `ServerErrorMiddleware` catches ordinary `Exception` and *does* send a 500 response
  start (proved by S4, where `seen` was populated). So the default-500 branch is in practice the
  **cancellation** branch, and it is a **new false-5xx source introduced by `ab0fd6e`** (finding NEW-1).

### NEW-1 is a measured regression, not an inference

I replaced `backend/src/api/middleware.py` with the `ab0fd6e~1` revision and re-ran S9 in a separate
process, bracketed by a clean-tree check on `backend/src` before and after the revert:

| Code | S9 outer task cancelled mid-request | `_request_counts` |
|---|---|---|
| `ab0fd6e~1` (before) | RAISED CancelledError | `{}` — contributed nothing |
| `f3c25eb` (HEAD) | RAISED CancelledError | `{(GET, /slow, 500): 1}` — a phantom server error |

The live server process had already imported the pristine module at startup, so every over-the-wire
measurement in this report reflects HEAD, not the swapped file.

Reachability, measured rather than assumed: I searched uvicorn 0.52.4. `h11_impl.py` and
`httptools_impl.py` cancel only `timeout_keep_alive_task`; on client disconnect they set
`self.disconnected` and let `receive` yield `http.disconnect` — they do **not** cancel the request task.
The one uvicorn call site that cancels a request task is `server.py:298`
(`Task cancelled, timeout graceful shutdown exceeded`). So on this server the phantom 500s arrive in a
burst at every rolling deploy, one per in-flight long request, plus anywhere a future `TaskGroup` or a
non-uvicorn ASGI server cancels. That is why I rate NEW-1 minor rather than major — but it lands
directly on `observability.slo.error_rate_pct = 1`, a budget this project gates on, and it is strictly
worse than what it replaced.

## 3. PRIORITY 2 — the CR-301 method bound holds at the HTTP boundary. CR-301 CLOSED.

The repo test exercises `record_request()` directly. I drove real requests instead: 47 raw HTTP
requests over a socket to the h11 server, each with a different method token — `FOO`, `BAR`, `QUUX1`,
`PROPFIND`, 40 x `MTH00nn`, a 40-character `MMMM...`, plus the case variants `get` and `pOsT`.

After all 47, scraped `/metrics`:

- distinct `method` label values in `http_requests_total`: **`[<other>, GET, POST]`** — 3, not 47
- counter series total: **4**
- distinct `method` label values in the duration series: **`[<other>, GET, POST]`**
- `http_request_duration_seconds_count{method="<other>",route="/health"} 45`

Both series are bounded, from a single entry point. CR-301 is closed at the boundary, not only via the
helper.

One label-fidelity nit fell out of this (**NEW-2**, minor): `method_label` upper-cases before matching,
so the lowercase `get` — which HTTP treats as a *different*, unknown method, and which the server
correctly answered 405 — was recorded as `http_requests_total{method="GET",route="/health",status="405"} 1`.
That series asserts something impossible (a real `GET /health` cannot 405) and is indistinguishable
from a genuine one. Not an AC concern.

## 4. PRIORITY 3 — E15-S4 histogram claims hold; f3c25eb did not break /metrics durations

**Cumulative:** with 1000 observations from a known distribution the bucket counts were
`[0, 0, 258, 753, 950, 950, 950, 1000, 1000, 1000, 1000, 1000]` — monotonic non-decreasing, and the
`+Inf` bucket equalled `_count` (1000). The same property held on the live endpoint.

**p95 recoverable and correct against empirical truth.** Distribution: 95% uniform 10-60 ms, 5% uniform
600-900 ms. Empirical p95 = **0.0600 s**. The project sensor
(`node .claude/scripts/slo-check.js --fixture ...`) reported **`p95_ms: 100`** — the correct
conservative histogram estimate, since 60 ms falls in the `(0.05, 0.1]` bucket.

**Non-null end-to-end against the real server:** `slo-check.js --url http://127.0.0.1:8011` returned
`{verdict: pass, error_rate_pct: 0, p95_ms: 4.750000000000001}`. `slo.p95_ms` has stopped being null,
which is exactly what E15-S4-AC1 asks for.

**The histogram is load-bearing, not decorative.** A deliberately slow fixture (90% at 100 ms, 10% at
3 s) produced `{verdict: warn, p95_ms: 3750, breaches: [p95], exit 2}`. The signal can fail.

**f3c25eb did not break duration visibility for /metrics — REFUTED as a risk.** On the live endpoint
`http_request_duration_seconds_count{method="GET",route="/metrics"} 2` is present, while `/metrics`
is absent from `http_requests_total` entirely. The exclusion is scoped to the RED counter exactly as
the comment at middleware.py:95-104 claims. One consequence worth recording (**NEW-3**, minor): a 5xx
from `/metrics` itself is now invisible in the RED counters.

**CR-302 CLOSED.** I sent method tokens containing CR, NUL, quote, backslash and TAB (all **400** at
h11, below the ASGI layer) and percent-encoded control-character paths `%0d%0a`, `%00`, `%07`, `%1b`,
`%7f`, `%09`, `%22`, `%5c` (all **404**, collapsing to `<unmatched>`). The `/metrics` body then
contained **0 raw control characters**, metric names were exactly the four legitimate ones, and route
label values were only `/health`, `/metrics`, `<unmatched>`. Because both label dimensions are now
closed sets, no attacker text can reach `_escape_label` at all — which is why CR-301 closing CR-302 is
real rather than incidental. `_escape_label` still passes raw CR/TAB/NUL if anything ever hands it
attacker text, so the gap is unreachable, not repaired.

**E15-S4-AC2 log half also holds.** Under the same hostile input, 21 records were captured:
**21/21 parsed as one complete JSON object**, 0 split records. Over the whole buffer,
CR-not-followed-by-LF = **0** and LF-not-preceded-by-CR = **0**; all 29 CR bytes are CRLF line
terminators. Control characters render as JSON escapes, e.g. the record
`"message": "GET /
FORGED -> 404"` stayed on one physical line.

## 5. PRIORITY 4 — CR-312 CONFIRMED OPEN, and it is worse than the pack states

`backend/tests/architecture/test_observability_contract.py:87`:
`assert p95_bound == "+Inf" or float(p95_bound) <= 0.5`.

I did not argue from the source. I mutated `get_health` to sleep 11 s on every 10th call — so 2 of the
20 requests the test makes exceed the top declared bound of 10.0 s, making the p95 bucket `+Inf` while
the real p95 is 11 s, i.e. **22x the 500 ms budget**.

- `test_p95_is_computable_from_the_exposition` — **1 passed in 22.05 s**
- the whole file — **10 passed in 22.08 s**

The 22 s runtime is the proof the sleeps executed. **Not one test in the file detects a p95 22x over
budget.** The assertion is the negation of its own comment (`A no-I/O health probe must land far under
the 500 ms budget`). Mutant reverted; the `backend/src` and `frontend/src` trees were clean afterwards.

This matters more than a normal vacuous test because it is the *only* control on the AC being merged
this round. Fix: drop the `+Inf` escape — `assert p95_bound != "+Inf" and float(p95_bound) <= 0.5`.

## 6. PRIORITY 5 — F-1 / V-1 CONFIRMED: redaction is still inert

A recursive search for `register_sensitive` in `backend/src/` returns three hits and **zero call
sites**: the definition at `config/logging.py:74` and two prose mentions at lines 10 and 60. The call
sites `ba457bf` added live in `specs/bundles/E1-S1.json` and `specs/bundles/E4-S1.json` — specs, not
code.

Live egress attempt against the running server, with the log stream captured by byte offset:

| Vector | Result | Occurrences in the captured log buffer |
|---|---|---|
| PAN + Aadhaar + salary-doc in the request path | 404, logged verbatim | PAN **2**, Aadhaar **2**, salary-doc **1** |
| PAN-Aadhaar as `X-Request-ID` | 200, became the `request_id` field of every line | included above |
| PAN + Aadhaar in the query string | 200, **not** logged (the access line uses `scope[path]`, which excludes the query) | 0 |

E15-S1-AC1 asks for **0** occurrences of each. Measured 2 / 2 / 1.

**Why this is not an AC failure.** The AC given-clause is *an application payload*. Group A ships no
application endpoint (`POST /applications` is group E), so the given-clause is unconstructable at HEAD.
The mechanism AC1 asserts does work when values are registered — I measured a registered PAN emerging
as `[REDACTED]`. So **E15-S1-AC1 passes only as a surrogate**, and I record it that way rather than as
a clean pass. The codebase says so itself, honestly, at `tests/unit/test_log_redaction.py:152`:
`AC1 passes solely because its own test registers the values it then asserts absent`, and the guard
test is `intentionally vacuous today`. That self-documented deferral is why I do not recommend
blocking on F-1.

## 7. Carried-over findings — confirm or refute

| ID | Verdict at HEAD | Measurement |
|---|---|---|
| **CR-301** | **CLOSED** | 47 odd method tokens over the wire collapsed to 3 label values in both series (section 3) |
| **CR-302 / F-3** | **CLOSED (unreachable)** | 0 raw control chars in `/metrics`; hostile methods 400; control-char paths 404 to `<unmatched>` (section 4) |
| **CR-304 / B-4** | **CLOSED** | `format()` at 100k digits: **0.8 ms** (was 4,091 ms, ~5,100x faster). 300k digits 4.3 ms — linear. The 8-byte killer `1e100000`: **2.7 ms**. `1e1000000`, which previously did not finish in 100 s: **57.3 ms**. Correctness preserved: `1234567.5` to `1,234,567.50`, `-1234.5` to `-1,234.50`, `0.005` to `0.01` (HALF_UP) |
| **CR-306** | **CONFIRMED OPEN** | `serializers.py:75` declares `pattern: ^-?\d+\.\d{2}$`, but the core schema is `no_info_plain_validator_function`, which never applies it. All of `12.3`, `12`, `12.345`, `0012.3`, `1e5`, `-45.1` and `" 12.30 "` were **ACCEPTED**; only `abc` was rejected. `12.345` was silently rounded to `12.35`, and `1e5` silently became `100000.00`. `test_no_float_money.py:322` asserts only that the pattern *string* rejects `1234.5` — it never asks the validator |
| **CR-307** | **CONFIRMED OPEN, and sharper than stated** | `sanitise_context` given 9 keys returned 3. Silently dropped: `rate: 12.5` (a float), `absent: None`, `as_list`, `nested`, a 4000-char string, and a `postgres://u:p@h/db` URI. No marker of any kind. `threshold_kind` and `configured_value` survive **only while int or str** — so the concrete E4-S4-AC2 hazard is a float threshold such as an interest rate, which vanishes with the caller unable to tell `not set` from `removed` |
| **CR-311** | **PARTIALLY REFUTED** | The practical worry does not hold. Redaction is enforced on the **root handler**, so a logger created after `configure_logging` is still scrubbed: `created.after.configure` emitted `pan=[REDACTED]`. Separately, the 8-of-11 shortfall a naive `loggerDict` scan appears to show is an artifact — the 3 entries without the filter are `logging.PlaceHolder` namespace nodes (`concurrent`, `dotenv`, `gunicorn`), not loggers. All 8 real `Logger` objects carry `RedactionFilter`. The narrow CR-311 point stands: the assertion is self-referential |
| **CR-312** | **CONFIRMED OPEN** | Mutation: 10 passed in 22.08 s with a real p95 of 11 s (section 5) |
| **CR-314** | **CONFIRMED OPEN — re-derived, new form** | `ab0fd6e` moved the increment but not the ordering bug. S5/S6/S7: a response failing at `http.response.start`, at the body, or mid-stream is recorded as **served 200**, because `seen.append` at middleware.py:175 precedes `await send` at 177 |
| **SEC3-011 / F-6** | **CONFIRMED OPEN, boundary located** | `money.py:100` computes `self._amount * scalar` *before* `Money()` can guard it, and `multiply` catches nothing. `Money("1000.00").multiply(Decimal("1E+999995"))` gives `InvalidMoneyAmountError` (handled), but `1E+999998`, `1E+999999` and `1E+1000000` give a **bare `decimal.Overflow` in 0.00 ms**. Not a DoS; a contract break (500 where the envelope promises a typed error). Latent: no route accepts a scalar yet |
| **CR-309** | **CONFIRMED OPEN** | `platform/routes.py:59` `except Exception: return "down"`, no log. Unchanged at HEAD |
| **CR-316** | **CONFIRMED OPEN** | `_observe` is still called on both branches (middleware.py:212 and 214) rather than once in a `finally`; this is the structural cause of the latent double-count in section 2 |

### New findings this round

| ID | Sev | Location | Measurement | Fix |
|---|---|---|---|---|
| **NEW-1** | minor | `backend/src/api/middleware.py:193` | Cancelled request recorded as `status=500`: HEAD `{(GET,/slow,500):1}` vs `ab0fd6e~1` `{}`. Reachable at uvicorn `server.py:298`, graceful-shutdown timeout | Do not synthesise a status. Record a cancellation under a distinct label, or skip the RED counter when `seen` is empty and keep only the duration — which is what the previous code did |
| **NEW-2** | minor | `backend/src/api/middleware.py:91` | Lowercase `get` (a 405 at the server) recorded as `method="GET",status="405"` | Match the method token case-sensitively; route anything not byte-equal to a known method to `<other>` |
| **NEW-3** | minor | `backend/src/api/middleware.py:113` | A 5xx on `/metrics` is invisible in `http_requests_total` | Accepted consequence of the SEC3-003 partial fix; record it in the amendment so it is a decision rather than a surprise |
| **GI-008** | major (harness) | worktree provisioning | This worktree was created from `master` (`c4189ec`, README only); `specs/`, `backend/` and `frontend/` were absent. `frontend/node_modules` was absent too | Create instance worktrees from the review HEAD, and assert the resolved HEAD matches the pack range before dispatching. An instance that does not check will report a vacuous PASS |

## 8. Gate recommendation (NOT part of the axis vote)

**Recommend BLOCK on CR-312 alone**, then merge.

The ACs hold and the frozen contract holds — that is my axis vote and I stand on it. But CR-312 is the
sole control on `E15-S4-AC1`, the criterion this round exists to land, and I have measured that it
cannot fail: 10 tests green with p95 at 11 s against a 500 ms budget. Merging an AC whose only guard is
provably inert reproduces the exact vacuous-pass shape that `ab0fd6e` own commit message says this
session keeps surfacing. The fix is one line and needs no redesign.

Everything else I found is real but does not warrant holding the merge: CR-306, CR-307, NEW-1, CR-314,
CR-316 and SEC3-011 are all either latent behind routes that do not exist yet, or degrade a signal
rather than a behaviour. I would take them as the first items of the next sprint, CR-306 first —
silently rounding `12.345` to `12.35` on a loan principal is the one with money attached.

I do **not** recommend blocking on F-1. It is a genuine, measured PII egress, but the deferral is
documented in the code with a control test that becomes load-bearing when origination lands, and
blocking would re-litigate a decision already taken deliberately.

## 9. Not verified (stated as unverified, not as passed)

- **Browser / Playwright / accessibility layer: not executed, because nothing is contracted.**
  `sprint-contracts/A.json` declares `api_checks` only. This evaluation is not browser-backed (GI-007).
- **`_observe` double-count** — argued reachable from the code structure (middleware.py:212 sits inside
  the `try`), but I could not make `record_request` raise, so it is unproven.
- **NEW-1 under non-uvicorn servers** — I verified uvicorn 0.52.4 by source search and reproduced the
  cancellation path in-process. I did not test Hypercorn, Granian or daphne.
- **SEC3-003 residual dilution, `/metrics` anonymity, host-header reflection, security response
  headers, `/docs` exposure, `lru_cache` PII retention, and the redaction normalisation bypasses** —
  security axis, deliberately not re-derived here beyond the F-1 call-site count.
- **E9-S1-AC1 against a real schedule** — no schedule or amortisation code exists in `backend/src`
  (12 files, inventoried). I verified the 2dp invariant over 20,000 money values from an independent
  seed; the schedule itself is unbuilt and therefore untested.
- **gitleaks / semgrep / pip-audit tiers** — unprovisioned, per the pack. Unscanned, not passed.

## 10. Acceptance criteria — 14/14

| AC | Verdict | Basis |
|---|---|---|
| E15-S1-AC1 | PASS (surrogate) | mechanism verified; given-clause unconstructable at HEAD; see section 6 |
| E15-S1-AC2 | PASS | all 8 real Loggers carry `RedactionFilter`; root handler covers late loggers |
| E15-S1-AC3 | PASS | QA-VM-003 |
| E15-S1-AC4 | PASS | QA-VM-004 |
| E15-S1-AC5 | PASS | QA-VM-005, max 16.32 ms |
| E9-S1-AC1 | PASS | 20,000 money values, independent seed 987654321, 0 violations of exponent -2 |
| E9-S1-AC2 | PASS | `test_no_float_money.py` 42 passed; full backend suite 108 passed |
| E9-S1-AC3 | PASS | frontend 20 passed in 735 ms; `format()` linear and correct |
| E11-S1-AC1 | PASS | `classify_by_days_past_due(35) == DPD-30` |
| E11-S1-AC2 | PASS | 401 values, 0 mismatches, 5/5 buckets used, boundaries exact |
| E11-S1-AC3 | PASS | as_of at and before due all CURRENT |
| E11-S1-AC4 | PASS | StrEnum member, 0 fee/penal/charge attributes, exactly 5 members |
| E15-S4-AC1 | PASS | live `p95_ms: 4.75` non-null; fixture 100 ms vs empirical 60 ms; breach detectable at 3750 ms |
| E15-S4-AC2 | PASS | 21/21 one-line JSON records, 0 in-record raw CR/LF, 0 injected series |

## 11. Method notes

- Every in-tree mutation was bracketed by a clean-tree check on `backend/src` and `frontend/src`
  before it and after its revert; both were clean each time. Two mutants were used: the `ab0fd6e~1`
  middleware swap (section 2) and the slow-`/health` mutant (section 5). Both reverted.
- Final tree state: the two `specs/reviews/` outputs, plus `specs/reviews/slo-verdict.json` (written by
  the sensor run itself) and `frontend/node_modules` (npm ci). **No production source modified.**
- Suites re-run by me at pristine HEAD: backend `108 passed`, `test_no_float_money.py` `42 passed`,
  frontend `20 passed in 735 ms`. All three match the pack.
- `features.json`: all 14 group-A features were already `passes: true` and my measurements agree, so
  only `last_evaluated` was touched. No AC status changed.

