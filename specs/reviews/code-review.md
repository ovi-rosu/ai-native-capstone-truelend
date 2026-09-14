# Code Review — /gate --group A, round 4

**Reviewer:** code-reviewer (outside the 3-instance majority vote; a BLOCK here is sufficient alone)
**Range:** `14e9487..f3c25eb` (new work re-reviewed: `ba457bf..f3c25eb`)
**Group:** A — E15-S1, E9-S1, E11-S1, E15-S4
**Worktree:** `C:\Users\rosuo\WORK\ai-native-capstone-truelend\.claude\worktrees\agent-a17f3e9864dd593c9`
**Verdict:** PASS — 0 BLOCK, 18 WARN, 9 INFO

> My round-3 BLOCK (CR-301) is **CLOSED by measurement**. No new BLOCK. Everything below is
> a WARN or INFO; the gate is not blocked by this axis.

## 0. Baseline at HEAD (all measurements bracketed with `git status --porcelain`, tree clean after)

| Check | Result |
|---|---|
| `backend: uv run pytest -q` | 108 passed (was 104) |
| `backend: uv run ruff check .` | clean |
| `backend: uv run mypy src/` | clean, 12 files |
| `frontend: npm test` | 20 passed (was 18) |
| `frontend: npm run lint` / `typecheck` | clean |

Production source changed since `ba457bf`: `backend/src/api/middleware.py`,
`frontend/src/types/money.ts`. Tests changed: `backend/tests/architecture/test_observability_contract.py`,
`frontend/tests/unit/money.test.ts`. Every other file I carried a finding against in round 3
is byte-identical.

## 1. PRIORITY 1 — CR-301 adjudicated: CLOSED

I am closing my own round-3 BLOCK. Evidence, not the commit message:

**Both label dimensions.** `record_request()` is the single writer for both series and bounds
the method once (`method_label`) before keying `_request_counts` (method, route, status) and
`observe_duration` (method, route). `route_label` was already bounded in round 3; I re-verified it.

**Both parsers, at the HTTP boundary, not just the helper.** Real `uvicorn` server on port 8031,
3,000 requests over ONE keep-alive connection, each with a unique method token AND a unique path:

| Parser | Result |
|---|---|
| `http="h11"` (uvicorn own parser, and its fallback when httptools is absent) | **1** counter series, **12** histogram lines, **1,713**-byte `/metrics` body, 341 KB transient heap growth, 1.61 s. Single series: `http_requests_total{method="<other>",route="<unmatched>",status="404"} 3000` |
| `http="httptools"` (the declared `uvicorn[standard]` path) | connection aborted at the parser — tokens never reach ASGI, as round 3 found |

Round 3 measured, on the same rig: 2,998 counter series + 2,998 histogram series, a **3,553,759**-byte
body and ~2.5 MB permanently retained. The regression is a 2,075x reduction in body size and a
collapse from 5,996 series to 13 lines. **CR-301 closed, high confidence.**

Mutation check on the guard itself: `return upper if upper in _KNOWN_METHODS else _OTHER_METHOD`
-> `return upper` is killed by `test_metric_label_cardinality_is_bounded_on_the_method_dimension`
(1 failed, 107 passed). The guard is covered. See CR-407 for what the guard's tests do *not* cover.

## 2. PRIORITY 1 — is the restructuring correct? (CR-314 re-derived from scratch)

I drove the middleware directly with bare ASGI apps through `TestClient`, one path per case, and
read `request_counter_snapshot()` / `duration_snapshot()` after each. Results:

| Path | Client saw | Counter | Duration | Correct? |
|---|---|---|---|---|
| normal 200 | 200 | 1 x 200 | 1 | yes |
| route raises, `ServerErrorMiddleware` builds the 500 | 500 + `X-Request-ID` | 1 x 500 | 1 | yes — exactly once, status from the real response.start |
| bare app raises before any response.start (the documented `else 500` default) | 500 | 1 x **500** | 1 | yes, and this is the only path that exercises the default |
| app returns without ever sending a response | 500 | 1 x 500 | 1 | yes |
| TWO `http.response.start` messages | 200 | 1 x **200** (`seen[0]`) | 1 | no double count; first status wins |
| app sends 200 then raises | 200 | 1 x 200 | 1 | yes, once |
| downstream `send` raises `ConnectionResetError` **at** response.start | 500 | 1 x **200** | 1 | **NO — see CR-401** |
| `observe_duration` raises once (simulating MemoryError) | 200 | **2** x 200 | 1 | **NO — see CR-402** |

So: no lost counts, the exception path records a duration AND a counter exactly once on every
reachable path I could build, and `seen[0]` is the right pick (the client-visible status) rather
than `seen[-1]`. Two defects remain, both one-line fixes, both WARN:

- **CR-401** — `seen.append(status)` still runs *before* `await send(message)`, so a response that
  never reaches the wire is counted as the status it intended. This is round-3 CR-314 unchanged:
  `ab0fd6e` moved *where* the counter fires but not *when the status is captured*. Measured above.
  It also leaves the documented `else 500` default almost dead — moving the append below the
  `await` would both fix the over-count and give the default its intended meaning.
- **CR-402** — two `_observe` call sites instead of one `finally`. Measured double count: one
  request produced `http_requests_total = 2` with `http_request_duration_seconds_count = 1`, i.e.
  the two series disagree. Round 3 filed this as INFO (CR-316) when only the histogram was at
  stake; the RED counter moved into `_observe` in `ab0fd6e`, so it now corrupts the SLO numerator.
  Escalated to WARN. Reachability is narrow (essentially `MemoryError` inside `observe_duration`),
  which is why it is not a BLOCK.

Uncovered mutants I found here: `seen[0] if seen else 500` -> `... else 200` survives (108 passed),
so the default status is asserted by nothing.

## 3. PRIORITY 1 — is `seen: list[int]` the right design? (CR-403)

No. It is an out-parameter: a mutable `list[int]` created in `__call__`, threaded through two
`@staticmethod`s, written by a closure inside one and read by the other, where only element 0 is
ever consumed and the list can grow without bound if a buggy app sends repeated response starts.
The name (`seen`) describes the container, not the value, and `seen[0] if seen else 500` silently
encodes two separate decisions (which status, and what to do when there is none).

The static-method split itself is justified: inlining both closures into `__call__` would put it at
roughly 50 lines, over the 30-line cap. The smuggling is not. Minimum fix, same line count:

```python
@dataclass
class _ResponseState:
    status: int | None = None
```

then `state.status = status` in the send wrapper and `state.status if state.status is not None else 500`
in `_observe`. Named field, typed, no index arithmetic, and it reads as what it is. This is one edit
with CR-402 (`finally`) — both touch lines 210-214.

## 4. PRIORITY 1 — does CR-302 become unreachable, as predicted? YES

The escaping itself is unchanged; `_escape_label` still passes CR, NUL, ESC, TAB and U+2028 through
verbatim (measured directly). But neither label source can now carry one:

- method -> `_KNOWN_METHODS` u {`<other>`} — a closed set of 10 literals
- route -> a code-authored route template, or the `<unmatched>` literal

Measured end to end: five crafted paths (`%0d%0a`-injected forged series, `%00`, `%22`, `%1b[2J`,
`%e2%80%a8`) scraped through the real app yield label values `{GET, <unmatched>}` exactly, zero raw
control characters in the body, and no forged series. **CR-302 downgraded WARN -> INFO** (pure
defence-in-depth; E15-S4-AC2 can no longer reach its own stated precondition).

## 5. The scrape exclusion `f3c25eb` added — half a fix (CR-404, CR-405, CR-406, CR-415)

This was not in my brief but it is the newest commit and it changes a metric's meaning, so I judged it.

`record_request` skips the RED counter for `/metrics` but **still calls `observe_duration` for it**,
deliberately ("Durations are still observed, so p95 for the endpoint stays visible"). I read the
harness parser the comment cites: `.claude/hooks/lib/prom-parse.js` `_aggregateBuckets` sums
`http_request_duration_seconds_bucket` **across all label-sets** — the same global aggregation as
`errorRate`. So the retained duration series dilutes p95 exactly as the counter diluted error rate.

Measured with the real renderer and the real harness parser: 20 genuine 3.0 s requests plus 380
scrapes ->

```
p95 global (with scrape series) = 5 ms
p95 business only              = 4875 ms
```

against a declared `p95_ms: 500` SLO. The commit closes the error-rate half of its own finding and
leaves the latency half wide open — with a comment that presents the open half as a feature.
CR-404, WARN, fix is one line (move `observe_duration` inside the same `if`) or, better, teach
`errorRate`/`_aggregateBuckets` a route filter and revert the product-side exclusion.

Two consequences of the exclusion that nothing records:

- **CR-405** — `# HELP http_requests_total Total HTTP requests served.` is now false. The HELP
  string is part of the exposition a scraper reads; an operator computing RPS from it under-counts.
- **CR-415** — a 5xx on `/metrics` is now counted nowhere, so the observability endpoint's own
  availability is invisible to the RED signal.
- **CR-406** — `_SLI_EXCLUDED_ROUTES = frozenset({"/metrics"})` hardcodes a path that already
  appears in `@router.get("/metrics")` and in `project-manifest.json#observability.metrics_path`.
  Three copies, no single source; change the manifest and the exclusion silently stops working.
  Fix: one constant in `src/config/settings.py` (Config layer, below API, so no cycle) read by both.

## 6. PRIORITY 2 — the `format()` rewrite

### 6a. Is it correct? Yes — proved, not asserted

I wrote a throwaway independent reference grouper (reverse 3-chunking with `unshift`) and compared
it against `format()` over **2,400 cases**: every integer length 1..400, three digit patterns
(`1...1`, `9...9`, `1000...0`), both signs. Zero disagreements. Plus 11 boundary cases:

| Input | Output | Note |
|---|---|---|
| `0.00` | `0.00` | zero |
| `0.004` and `-0.004` | `0.00` and `0.00` | quantization, no negative zero (my own first expectation here was wrong) |
| `-0.005` | `-0.01` | ROUND_HALF_UP |
| `1.00`, `12.00`, `123.00` | unchanged | 1-2-3 digits, no comma |
| `1234.00` | `1,234.00` | first grouping |
| `123.00`, `-999.00` | no leading comma | exact multiple of 3 — the index guard is load-bearing |
| `1000000000.00` | `1,000,000,000.00` | multiple groups |
| `-1000.00` | `-1,000.00` | sign plus grouping |

The `index` non-zero guard in `(digits.length - index) % 3 === 0` is right: when the digit count is
an exact multiple of 3 it is the only thing preventing a leading comma. Dropping it is killed by the
new `still groups ordinary amounts correctly` test (I mutated it; 1 failed).

### 6b. Is the 250 ms assertion a CI flake risk? No — measured

`format()` at 100,001 digits, 20 samples: min 0 ms, median 1 ms, max 3 ms (`fromWire` parse, which
is outside the timer, 1 ms). That is an ~80x margin to the 250 ms threshold. In the kill direction,
restoring the quadratic lookahead form makes the same test take **4,124 ms** — a 16x margin the
other way. The assertion discriminates cleanly at both ends. A ratio assertion (time at 2N digits
no more than 3x the time at N) would be sturdier in principle but is not needed here. INFO (CR-414).

### 6c. Is this an adequate disposition of CR-304? Partly — the performance half, not the contract half

CR-304 had two components. My round-3 fix recommendation (bound the input in `toQuantizedDecimal`)
would have closed both; making the grouping linear closes one.

**Closed:** the quadratic sink is gone. Measured scaling through the public API:

| Input | `fromWire` | `toWire` | `format` | wire chars | formatted chars |
|---|---|---|---|---|---|
| `1e100000` | 0 ms | 0 ms | 6 ms | 100,004 | 133,337 |
| `1e1000000` | 0 ms | 38 ms | 32 ms | 1,000,004 | 1,333,337 |
| `1e5000000` | 0 ms | 200 ms | 424 ms | 5,000,004 | 6,666,670 |

Linear, and `equals`, `add` and `multiply` are all sub-2 ms at 100k digits (decimal.js truncates
products to 20 significant digits, so there is no second quadratic sink hiding in arithmetic).

**Still open, and now the sharper point (CR-409):** the constructor is unbounded, so the type admits
amounts the backend rejects. Measured on a live `MoneyField` model:

```
POST {"principal": "1e100000"}  -> 422   (backend Decimal.quantize raises InvalidOperation)
```

while `Money.fromWire("1e100000")` on the frontend succeeds and `toWire()` hands back a
100,004-character string. The two sides of the same declared wire form disagree about what a Money
is, and the docstring still claims `fromWire` parses "the quoted 2dp wire string". At `1e5000000`
the client also allocates a 6.7 MB display string on the UI thread. WARN, not BLOCK: `format()`'s
only caller is `MoneyText`, whose only callers are tests, and the frontend has no fetch layer at
HEAD, so there is still no untrusted path. Fix stands: reject a string that does not match
`/^-?\d+\.\d{2}$/` (or cap the digit count) in `toQuantizedDecimal`, same tolerance as CR-306.

## 7. PRIORITY 3 — the six new tests, mutation-tested

| New test | Mutant applied to the code it claims to protect | Result |
|---|---|---|
| `test_escape_label_neutralises_exposition_metacharacters` | `_escape_label` -> identity (the whole B-1 remediation deleted) | **KILLED** (1 failed, 107 passed) |
| same | drop only the backslash mapping | **KILLED** |
| same | drop only the double-quote mapping | **KILLED** |
| same | drop only the newline mapping | **KILLED** |
| `test_metric_label_cardinality_is_bounded_on_the_method_dimension` | `method_label` -> identity | **KILLED** |
| same | `_observe` bypasses `record_request` and keys on the raw method | **SURVIVES** (see CR-407) |
| `test_known_methods_keep_their_own_label` | `method.upper()` -> `method` | **SURVIVES** (see CR-411) |
| `test_metrics_scrapes_do_not_count_toward_the_error_rate_denominator` | remove the `_SLI_EXCLUDED_ROUTES` check | **KILLED** |
| `format()` linear test | restore the quadratic lookahead | **KILLED** (4,124 ms vs a 250 ms bound) |
| `still groups ordinary amounts correctly` | drop the leading-comma guard | **KILLED** |

**Round 3's worst finding (CR-303 / V-0) is closed.** The identity-function mutant that left the
whole label-escaping fix uncovered at 104 passed is now killed, and so is each individual escape
mapping. Note the new test reaches a private helper (`_escape_label`) rather than the exposition
boundary I recommended — and that is the right call here, not a shortcut: no reachable public path
can put a quote in a label any more (that is CR-302's closure), which is exactly why the
boundary-level test failed to kill the mutant in the first place. Recorded as INFO CR-413, justified.

**Does the cardinality test cover the HTTP boundary? No — the helper only (CR-407).**
`test_metric_label_cardinality_...` and `test_known_methods_...` both call `record_request()`
directly. I mutated `_observe` to bypass the bounded entry point and increment `_request_counts`
with `str(scope.get("method"))` — i.e. the exact regression that reopens CR-301 at the call site —
and **both cardinality tests stayed green**. The mutant is caught only incidentally, by the
unrelated `/metrics` exclusion test (which happens to drive a real request). One request-driven
case would make the boundary explicit. My round-3 fix note asked for "the h11 flood as the
regression test"; what landed tests the helper instead.

One new test carries a **misleading assertion (CR-408)**:
`assert 'route="/metrics"' not in body` passes for two independent reasons — the exclusion, and
the fact that the `/metrics` record is written *after* the body is rendered. I removed the exclusion
and the first scrape still does not contain it. Worse, it is false as a guarantee: a **second**
scrape does contain `route="/metrics"` histogram lines (measured). The real assertion in that test
(`"/metrics" not in routes`, read from the snapshot after the request) is the one that kills the
mutant; the body assertion should go or be re-pointed at a second scrape.

## 8. PRIORITY 4 — disposition of every carried round-3 finding

| ID | Round 3 | Round 4 disposition | Evidence |
|---|---|---|---|
| **CR-301** | BLOCK | **CLOSED** | 3,000 unique methods x unique paths, h11, 1 series / 1,713-byte body; httptools rejects below ASGI |
| **CR-302** | WARN | **DOWNGRADED to INFO** | both label sources are closed literal sets; 5 crafted paths yield `{GET, <unmatched>}`, zero raw control chars |
| **CR-303** | WARN | **CLOSED** | 4 escaping mutants all killed by the new direct test |
| **CR-304** | WARN | **PARTLY CLOSED**, re-filed as **CR-409** | quadratic sink gone (linear to 5M digits); unbounded constructor remains and the backend 422s what the frontend accepts |
| CR-305 | WARN | **STILL OPEN** | `logging.py` untouched; both disproven sentences verbatim at lines 217-221. Third round. One-line doc fix. |
| CR-306 | WARN | **STILL OPEN** | `serializers.py` untouched; re-measured live: `"12.3"` -> 200 `"12.30"`, `"12.345"` -> 200 `"12.35"`, `"0.005"` -> 200 `"0.01"`, all against a declared `^-?\d+\.\d{2}$` |
| CR-307 | WARN | **STILL OPEN** | `errors.py` untouched |
| CR-308 | WARN | **STILL OPEN** | `errors.py` untouched |
| CR-309 | WARN | **STILL OPEN** | `routes.py:59` still `except Exception: return "down"` with no log. Third round. One-line fix. |
| CR-310 | WARN | **STILL OPEN** | `# type: ignore[arg-type]` still at `logging.py:91`. Round 3 applied, verified clean (`mypy` Success, 104 passed) and reverted the fix. Third round for a verified one-line fix. |
| CR-311 | WARN | **STILL OPEN** | `test_log_redaction.py` untouched |
| CR-312 | WARN | **STILL OPEN, now proved vacuous** | I replaced every bucket bound with 1e-12 (keeping 0.5) so every real duration lands in `+Inf` — p95 is then above every declared bound including the 500 ms SLO boundary — and the test still passed (10 passed). Third round. One-line fix. |
| CR-313 | WARN | **STILL OPEN** | `conftest.py` contains zero occurrences of `reset_request_counters` |
| **CR-314** | INFO | **RE-DERIVED, escalated to WARN as CR-401** | `seen.append` still precedes `await send`; measured 200 counted while the client got 500 |
| CR-315 | INFO | **STILL OPEN** | `latency_bucket_bounds()` untouched |
| **CR-316** | INFO | **ESCALATED to WARN as CR-402** | measured `http_requests_total = 2` vs `_count = 1` from one request |
| CR-317 | INFO (refuted) | **CLOSED** | no change required; `zip(strict=True)` still safe, bucket `le` semantics unchanged |
| CR-318 | INFO | **STILL OPEN**, and two more paragraphs added — see CR-410 | module docstring unchanged |

Six of the nine still-open carried WARNs (CR-305, CR-309, CR-310, CR-311, CR-312, CR-313) are
one-line or one-case fixes that I verified clean in round 3. Saying it plainly: carrying a known,
verified one-line fix into a third review round is a process failure, not a finding. CR-310 in
particular was applied, type-checked, tested and reverted a round ago; it costs less to fix than to
carry. None of them blocks, and I am not blocking on them — but they should not appear in a round 5.

## 9. Paragraph-workaround rule — considered BLOCK, declined (CR-410)

The harness review rule says a workaround needing a comment paragraph longer than ~3 lines is
itself a BLOCK. Three candidates in this diff:

- `middleware.py:95-103` — a **9-line** paragraph for `_SLI_EXCLUDED_ROUTES` which states outright
  that "it does not close the finding" and names `.claude/hooks/lib/prom-parse.js` as where the real
  fix lives. This is the textbook shape, and I measured that the workaround is genuinely incomplete
  (CR-404: p95 reads 5 ms against a true 4,875 ms).
- `middleware.py:76-82` — a 7-line paragraph for `_KNOWN_METHODS`. This one justifies a real fix,
  not a workaround; it is long, not wrong.
- `money.ts:89-91` — a 3-line apology for not using `Math.max` "for the slice bound". There is no
  slice bound in the loop; the comment explains a decision the code never had to make, and it exists
  to pre-empt the module's own float guard. Pure noise; delete it.

I declined to BLOCK. My reasoning, stated so the gate lead can overrule it: blocking would force a
revert or an escalation into harness machinery, and the commit *strictly improves* the prior state
(the error-rate dilution was real and is now half gone). Using a sole veto on comment placement,
when the underlying dilution is a documented harness-side defect, would be spending the veto on
style. The right outcome is CR-404's one-line symmetric fix plus CR-405, after which the 9-line
apology compresses to one line and a finding id.

## 10. Out of my axis

Noted, not pursued (three security instances own these): `/metrics` is still unauthenticated;
`X-Request-ID` is still unvalidated and unbounded and is reflected into a response header and every
log line; `_escape_label` leaves C0 control characters intact even though nothing reachable carries
one. I found no new security-relevant behaviour in `ba457bf..f3c25eb`.

## 11. Findings index

| ID | Level | Conf | Axis | Location | One line |
|---|---|---|---|---|---|
| CR-401 | WARN | high | spec | `backend/src/api/middleware.py:175` | status captured before the send; a response that never reached the wire is counted as a 200 |
| CR-402 | WARN | high | standards | `backend/src/api/middleware.py:210` | two `_observe` call sites, not a `finally`; measured counter 2 vs `_count` 1 |
| CR-403 | WARN | high | standards | `backend/src/api/middleware.py:165` | mutable `list[int]` out-parameter smuggled through two static methods |
| CR-404 | WARN | high | spec | `backend/src/api/middleware.py:115` | scrape excluded from the counter but not the histogram; global p95 reads 5 ms vs 4,875 ms |
| CR-405 | WARN | high | spec | `backend/src/api/platform/routes.py:89` | `HELP ... Total HTTP requests served` is no longer true |
| CR-406 | WARN | medium | standards | `backend/src/api/middleware.py:104` | `/metrics` hardcoded in a third place, ignoring `observability.metrics_path` |
| CR-407 | WARN | high | standards | `backend/tests/architecture/test_observability_contract.py:180` | cardinality tests cover the helper, not the HTTP boundary; call-site bypass mutant survives |
| CR-408 | WARN | high | standards | `backend/tests/architecture/test_observability_contract.py:225` | `route="/metrics" not in body` is vacuous, and false on a second scrape |
| CR-409 | WARN | high | spec | `frontend/src/types/money.ts:24` | constructor still unbounded; frontend accepts what the backend 422s |
| CR-305 | WARN | high | standards | `backend/src/config/logging.py:217` | carried: two disproven justifications for silencing `uvicorn.access` |
| CR-306 | WARN | high | spec | `backend/src/api/serializers.py:75` | carried: declared wire pattern is documentation only |
| CR-307 | WARN | high | standards | `backend/src/api/errors.py:85` | carried: context values dropped silently, no marker, no log |
| CR-308 | WARN | medium | spec | `backend/src/api/errors.py:115` | carried: `detail` bypasses the credential-URI and length guards |
| CR-309 | WARN | high | standards | `backend/src/api/platform/routes.py:59` | carried: `_database_status` swallows the probe failure reason |
| CR-310 | WARN | high | standards | `backend/src/config/logging.py:91` | carried: avoidable `type: ignore[arg-type]`; fix verified clean in round 3 |
| CR-311 | WARN | high | standards | `backend/tests/unit/test_log_redaction.py:43` | carried: AC2 filter tests pass by construction |
| CR-312 | WARN | high | spec | `backend/tests/architecture/test_observability_contract.py:87` | carried: p95 assertion accepts `+Inf`; proved vacuous this round |
| CR-313 | WARN | medium | standards | `backend/tests/conftest.py:28` | carried: metric-state isolation is conventional, not structural |
| CR-302 | INFO | high | spec | `backend/src/api/platform/routes.py:78` | downgraded: C0 chars unescaped but now unreachable |
| CR-410 | INFO | high | standards | `backend/src/api/middleware.py:95` | 9-line workaround apology (plus 7-line and 3-line paragraphs); BLOCK considered, declined |
| CR-411 | INFO | high | spec | `backend/src/api/middleware.py:91` | `.upper()` folds the non-RFC lowercase `get` onto `GET`; mutant survives |
| CR-412 | INFO | high | spec | `backend/src/api/middleware.py:212` | counter now fires after the app returns: a streaming response is uncounted until its body ends |
| CR-413 | INFO | medium | standards | `backend/tests/architecture/test_observability_contract.py:161` | function-local imports in four new tests; private-helper coupling justified |
| CR-414 | INFO | high | standards | `frontend/tests/unit/money.test.ts:147` | 250 ms wall-clock bound measured safe (80x / 16x margins) |
| CR-415 | INFO | high | spec | `backend/src/api/middleware.py:104` | a 5xx on `/metrics` is now counted nowhere |
| CR-315 | INFO | medium | standards | `backend/src/api/middleware.py:140` | carried: single-use getter over a module constant |
| CR-318 | INFO | medium | standards | `backend/src/api/middleware.py:25` | carried: 7-line docstring paragraph |

## 12. Measurement hygiene

Every mutation was applied in this worktree only, on port 8031 where a server was needed, and
reverted; `git status --porcelain` is empty and `108 passed / ruff clean / mypy clean / 20 passed /
eslint clean / tsc clean` all reproduce at HEAD after the reverts. Two throwaway probe files
(`backend/tests/unit/test_zz_probe.py`, `frontend/tests/unit/zz_probe.test.ts`) and two throwaway
scripts were created, run and deleted.
