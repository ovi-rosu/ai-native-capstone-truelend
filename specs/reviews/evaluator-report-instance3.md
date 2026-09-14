# Evaluator Report — instance 3 of 3 — /gate --group A, round 4

**Axis:** functional (money/domain half, plus traceability)
**Worktree:** `C:/Users/rosuo/WORK/ai-native-capstone-truelend/.claude/worktrees/agent-a1839d1b42959ad3b`
**HEAD evaluated:** `f3c25eb`  ·  **Port used:** 8013
**Model tier:** Opus 5 (1M context), runtime mode

## FUNCTIONAL VERDICT: PASS

- **Frozen API checks: 3/3** (all executed live against a real uvicorn process)
- **Story ACs: 14/14** (E15-S1 5, E9-S1 3, E11-S1 4, E15-S4 2)
- **Gate recommendation (separate from the axis vote):** ALLOW, with three mandatory pre-merge
  follow-ups. See the recommendation section.

### Reading note on the context pack

The pack in `specs/reviews/review-context-pack.md` is the **round 3** pack, headed `ba457bf`.
The reviewed HEAD is `f3c25eb`, two revisions later (`ab0fd6e`, `f3c25eb`). The round-4 delta
came from the task brief, not the pack. Deterministic figures below were re-measured in my own
tree and differ from the pack accordingly (108 backend tests, not 104; 20 frontend, not 18).

## 1. Deterministic baseline, re-measured in my own tree

| Check | Result |
|---|---|
| `backend: uv run pytest -q` | **108 passed** (pack: 104) |
| `backend: uv run ruff check .` | clean |
| `backend: uv run mypy src/` | clean, 12 source files |
| `frontend: npx vitest run` | **20 passed** (pack: 18) |
| `frontend: npm run lint` | clean |
| `frontend: npm run typecheck` | clean |
| tree after all 8 mutants | no modified files, no differences against `f3c25eb` |

## 2. Frozen contract — 3/3, executed live

A real uvicorn subprocess on `127.0.0.1:8013` with stdout captured; requests via httpx.

| Check | Measured | Verdict |
|---|---|---|
| QA-VM-003 | 200; echoed `X-Request-ID: req-abc`; 1 log line while serving; **1/1** parsed as JSON; `request_id == req-abc` | pass |
| QA-VM-004 | 200; generated `a1dc3673263b455f8475850754b14339` echoed on the response; exactly **1** distinct `request_id`, equal to the echoed id, non-empty | pass |
| QA-VM-005 | 200; `application/json`; body `status ok, database unconfigured, version 0.1.0`; **23.1 ms** against a 1000 ms budget | pass |

Caveat worth recording: each request emits **exactly one** log line (the server access logger is
disabled), so the QA-VM-003 phrase *100 percent of the log lines* is satisfied at n = 1. True,
but a weak statement — see OBS-1.

## 3. Acceptance criteria — 14/14

| AC | Verdict | Measurement |
|---|---|---|
| E15-S1-AC1 | pass (surrogate) | Filter on **9/9** configured loggers, 0 missing. Zero `register_sensitive` call sites in `backend/src`, and live traffic logged a raw PAN x2 and raw Aadhaar x2. Counted pass because the AC premise is a served application payload and no such surface exists; see V-1/F-1. |
| E15-S1-AC2 | pass | 9 loggers enumerated, set lacking `RedactionFilter` is **empty**. Root handler also carries one, so a late-created logger still redacts by propagation. |
| E15-S1-AC3 | pass | see QA-VM-003 |
| E15-S1-AC4 | pass | see QA-VM-004 |
| E15-S1-AC5 | pass | see QA-VM-005 |
| E9-S1-AC1 | pass | 200 randomized principal/rate/tenure triples, every money field a `Decimal` at exponent -2. Mutation M2 kills 5 tests, M1 kills 15. Surrogate: no schedule generator exists (deferred; `test_no_float_money.py:8` acknowledges it). |
| E9-S1-AC2 | pass | AST guard reports **0** float ops for `money.py` and `serializers.py`; mutation M1 makes the guard test fail. Guard counts `float()`, float literals, `math` import/attr, and both division node types. |
| E9-S1-AC3 | pass | static check reports **0** float risks for the shipped `money.ts`; mutation M6 (`.toNumber()`) makes it fail. See FE-GUARD for blind spots. |
| E11-S1-AC1 | pass | `classify_by_days_past_due(35)` = `DPD-30` |
| E11-S1-AC2 | pass | exhaustive **0..1000** (superset of 0..400): 0 mismatches, exactly one bucket per value, all 5 reachable, no gap/overlap. |
| E11-S1-AC3 | pass | due tomorrow / due today / due in 365 days all give `CURRENT`; sanity, due 35 days past gives `DPD-30`. |
| E11-S1-AC4 | pass | bare `StrEnum` member; attributes beyond `str` are only the 5 member names plus `name`/`value`. Mutation M4 kills the assertion. |
| E15-S4-AC1 | pass | `/metrics` after 13 requests: 30 histogram lines, labelled `method="GET"` `route="/health"`, 12 cumulative `le` buckets 0.005..+Inf all = 13, **p95 computable**. |
| E15-S4-AC2 | pass | 0 injected series, 0 exposition lines with raw CR/NUL/ESC, 0 log lines with raw control chars, one line per record. Raw-socket hostile header gave `400 Bad Request`. See ESC-CR. |

### Delinquency ladder — exact boundary table (measured)

```
floor 0    n=-1:ValueError   n=0:CURRENT    n=1:CURRENT
floor 30   n=29:CURRENT      n=30:DPD-30    n=31:DPD-30
floor 60   n=59:DPD-30       n=60:DPD-60    n=61:DPD-60
floor 90   n=89:DPD-60       n=90:DPD-90    n=91:DPD-90
floor 180  n=179:DPD-90      n=180:NPA      n=181:NPA
```

Matches the AC1 declared floors exactly. Note that mutation M3 (DPD-30 floor 30 to 31) was
**not** caught by the AC1 35-day case (35 is still at least 31) — only by the AC2 sweep and the
boundary parametrisation. The AC2 sweep is the load-bearing oracle for this ladder.

## 4. Findings

### CR-306 — MAJOR — re-derived by live request, CONFIRMED

`backend/src/api/serializers.py:24` (wire pattern), `:52` (plain validator), `:75-83` (schema hook).

The 2dp wire pattern is declared in the **JSON schema only**. `_validate_money` is a
`no_info_plain_validator_function` and never applies it. Measured live on port 8013 against a
FastAPI app using the shipped `MoneyField`:

```
principal "12.3"       -> 200 {"principal":"12.30"}
principal "1234"       -> 200 {"principal":"1234.00"}
principal "1e2"        -> 200 {"principal":"100.00"}
principal "12.345"     -> 200 {"principal":"12.35"}   (silent rounding)
principal 12.3 (number)-> 422  (float rejected)
schema: {"type":"string","pattern":"^-?\d+\.\d{2}$", ...}
```

So `"12.3"` really does return 200 `"12.30"` while both the declared pattern and
`test_no_float_money.py:342` call one decimal place invalid; line 343 likewise calls a bare
integer invalid, and `"1234"` is accepted too. The served contract is strictly wider than the
documented one, and surplus client precision is **silently rounded rather than refused** — the
failure class decision D-G exists to prevent.

**Fix:** apply the pattern in validation, not only in documentation — chain
`core_schema.str_schema(pattern=_WIRE_PATTERN)` ahead of `_validate_money`, or `re.fullmatch`
inside `_validate_money` for `str` input.

**Reachability:** latent. `MoneyField` has **zero** production call sites and no shipped route
carries money (only `/health` and `/metrics` exist). It binds the moment E1-S1 or E4-S1 lands.

### SEC3-011 / F-6 — MAJOR — CONFIRMED, and refined beyond prior rounds

`backend/src/types/money.py:101` (multiply), `:73-76` (quantizer); `backend/src/api/errors.py:160-165`.

```
issubclass(decimal.Overflow, decimal.InvalidOperation) -> False
Money("1.00").multiply(Decimal("1E+1000000"))  -> LEAKED decimal.Overflow   (0.0 ms)
Money("1.00").multiply(Decimal("1E+999999999"))-> LEAKED decimal.Overflow   (0.0 ms)
Money("1.00").multiply(Decimal("1E+400"))      -> InvalidMoneyAmountError   (typed)
```

The multiply happens *before* the `Money` constructor, and `Overflow` is a sibling of
`InvalidOperation`, not a subclass, so neither handler catches it. **The refinement prior rounds
missed:** converting it to `InvalidMoneyAmountError` would not produce a 422 either. Measured
live over HTTP with the real app factory and error handlers:

```
GET /probe/overflow -> 500 {"error":"InternalServerError","detail":"internal server error"}
GET /probe/typed    -> 500 {"error":"InternalServerError","detail":"internal server error"}
```

`errors.py` registers handlers only for `AppError`, `StarletteHTTPException`,
`RequestValidationError` and `Exception`. `InvalidMoneyAmountError` extends `ValueError`, not
`AppError`, so it falls through to the catch-all. So "Overflow leaks as a 500 instead of a 422"
is **half the story** — the typed error is a 500 too.

**Fix (both parts needed):** (1) catch `decimal.DecimalException`, not just `InvalidOperation`,
around the multiply/quantize; (2) give money errors a 4xx mapping — make
`InvalidMoneyAmountError` an `AppError` subclass or register a handler. Part (1) alone only
relabels a 500.

**Resolves the round-2 timing dispute:** eval-3 measured 9,708 ms and sec-3 measured 109 ms
because they used *different inputs*, not because they disagreed about the bug. With a `Decimal`
scalar the Overflow raises in **0.0 ms**. With an `int` scalar `10**999999999` the cost is
constructing a billion-digit Python integer, which did not finish inside a 300 s timeout here.
The decimal operation is instant; the integer literal is the expense.

### B-4 — RESOLVED — the `ab0fd6e` rewrite is correct, not merely fast

`frontend/src/types/money.ts:84-101`.

This was my primary assignment: prove equivalence, because a linear-but-wrong grouping would be
worse than a quadratic-but-right one. I bundled the **real shipped module** with esbuild and
differential-tested `format()` against a faithful reproduction of the exact pre-`ab0fd6e` regex,
both operating on the same sign-stripped digit string.

```
LENGTH_SWEEP 1..500 digits, both signs      mismatches: 0
EDGE_CASES   21 hand-picked                  mismatches: 0
RANDOM       200,000 amounts, 1-15 digits     mismatches: 0
BOUNDARY_TABLE {"1":"1.00","12":"12.00","123":"123.00","1234":"1,234.00",
  "12345":"12,345.00","123456":"123,456.00","1234567":"1,234,567.00",
  "12345678":"12,345,678.00","123456789":"123,456,789.00"}
```

Boundary behaviour is exactly right in both directions: **no** comma at 1, 2 or 3 digits; a comma
appears at 4; exact multiples of three digits emit no leading comma (`123456` gives `123,456`,
not `,123,456`); negatives keep the sign outside the grouping; zero and `0.01` are unchanged.

**Timing, and the flakiness question I was asked to check independently:**

```
toWire() alone at 100,001 digits:                   0.8 ms
new format(), n=40:  min 0.4  median 0.9  p95 2.6  max 4.9 ms
OLD regex, identical input:                       4,146 ms
```

The 4,146 ms reproduces the commit claim of 4,091 ms and the reviewers 4,088-4,301 ms, so B-4 was
real and is genuinely fixed. The test asserts `elapsed < 250`; against a measured max of 4.9 ms
that is roughly **50x headroom**, so **the test is not flaky** — a machine would have to be fifty
times slower than this one to trip it. Its companion assertions (`endsWith(".00")` and
`split(",").length === 33334`, which equals `ceil(100001/3)`) are exact and machine-independent.

### V-1 / F-1 — MAJOR — CONFIRMED independently; redaction is inert

`backend/src/config/logging.py:74` is the definition; `:10` and `:60` are docstrings. **Zero call
sites in `backend/src`.** Call sites exist only in `specs/bundles/E1-S1.json` and `E4-S1.json` —
story Operations text for future stories, which is what `ba457bf` actually changed.

Live on the running app, through the only surfaces that exist:

```
{"logger":"truelend.access","message":"GET /applicants/ABCDE1234F/123412341234 -> 404", ...}
{"logger":"truelend.access","message":"GET /health -> 200","request_id":"ABCDE1234F-123412341234"}

occurrences of PAN      ABCDE1234F    in captured buffer: 2
occurrences of AADHAAR  123412341234  in captured buffer: 2
```

**Discriminating experiment — the filter is installed and functional, merely inert.** On 9/9
configured loggers, and after `register_sensitive(PAN)` the identical log call rendered:

```
before: "message": "GET /applicants/ABCDE1234F -> 404"
after:  "message": "GET /applicants/[REDACTED] -> 404"
```

**Where I correct prior rounds.** Earlier rounds (including my own round-3 entry) framed AC1 as
passing *vacuously*. Measured, it does not:

| Mutant | Tests killed |
|---|---|
| M8 `RedactionFilter.filter` becomes a no-op | **7**, incl. `test_sensitive_application_values_never_appear_in_any_log_line` |
| M7 `scrub_text` becomes the identity | **only 2**, both in `test_error_envelope.py` |

So the AC1 test has real oracle power over the redaction *machinery*; M7 additionally shows the
log path does not route through `scrub_text` at all. What the test does **not** verify is that any
production code ever registers anything. The gap is **production wiring, not oracle strength.**

**Scope-Out tension.** `specs/stories/E15-S1.md` Scope **Out** states: *"must not write applicant
PAN, Aadhaar or salary-document content to any log sink."* I measured PAN and Aadhaar in the log
sink. The mitigating reading is that these arrived because *I, as client*, put them in a URL path
and a correlation header — not from applicant data flowing through an origination endpoint, which
does not exist. I did not fold this into the AC vote; I raise it as a gate question below.

**Round-2 escalation trigger has still not fired** ("if call sites now exist in code, severity
rises") — there are still none.

**Fix:** land a production call site, or add a request-time assertion so E15-S1-AC1 cannot pass
while the substrate is inert. Must close before E1-S1 or E4-S1 merges.

### FE-GUARD — MINOR — new this round — the AC3 guard is weaker than its backend twin

`frontend/tests/unit/money.test.ts:79-89`.

The backend guard deliberately counts division, with an explicit rationale at
`test_no_float_money.py:47-54`: *"`principal / months` over two ints yields a float in Python 3,
which is exactly the shape an EMI calculation takes."* The frontend pattern list has **no
division pattern at all**. Measured against the shipped pattern list:

```
FLAGGED  .toNumber()                (baseline control)
MISSED   const per = total / months;
MISSED   const r = 7 / 2;
MISSED   const r = 1e-2;             (needs a literal dot to match)
MISSED   Number.EPSILON             (needs a paren to match)
MISSED   amount.valueOf()
MISSED   raw | 0
```

AC3 still passes: the shipped module genuinely contains none of these and mutation M6 is caught.
But the guard that "every later money story inherits" is materially weaker precisely on the side
where EMI arithmetic will be written. **Fix:** add a division pattern and an exponent-literal
pattern, mirroring the backend rationale.

### ESC-CR — MAJOR — answers the pack open B-1 question: yes, CR is still unescaped

`backend/src/api/platform/routes.py`, the label escaper. Measured per character:

```
backslash        -> escaped
double quote     -> escaped
newline (LF)     -> escaped
carriage return  -> RAW 0x0d remains
tab              -> RAW 0x09 remains
esc              -> RAW 0x1b remains
nul              -> RAW 0x00 remains
combo a\r\ninjected{x="1"} 9 -> LF escaped, CR still raw
```

AC2 still holds end to end (0 injected series, 0 raw control chars, one line per record) because
the label is the bounded matched route template and the HTTP parser rejects a hostile header with
`400 Bad Request` before it reaches a label. That is defence in depth, not the escaping.

**Internal inconsistency worth flagging:** `ab0fd6e` argues the parser is *"an optional C
extension nothing here pins, under a middleware written to be server-agnostic"* when justifying
bounding the `method` label. The same argument cuts against relying on that parser to keep
control characters out of the escaper. **Fix:** escape or strip every codepoint below 0x20 rather
than enumerating three characters, and extend the direct escaper test to cover CR/TAB/ESC/NUL.

### TRACE-A — traceability is clean; round 3 renumbering hazard REFUTED for group A

Cross-referenced `sprint-contracts/A.json`, `verification-matrix.json`, `test-traces.json` and
`story-traces.json`:

```
VM-003 -> ac_id=E15-S1-AC3  layers=["unit","api"]
VM-004 -> ac_id=E15-S1-AC4  layers=["unit","api"]
VM-005 -> ac_id=E15-S1-AC5  layers=["unit","api"]
```

The frozen `matrix_ids` resolve to the ACs their descriptions claim, and each row api-layer check
description matches the contract `api_checks` description **verbatim**. All 14 group-A ACs map
1:1 onto 14 matrix rows — VM-001..005, VM-009..011, VM-070..073, VM-108..109 — numerically
matching the A.json feature ids F001-F005, F009-F011, F070-F073, F108, F109.  `test-traces.json`
yields exactly **1** trace per AC with consistent ids.

**No id points at a different AC than its test claims.** Round 3 recorded a live AC-renumbering
hazard; it does not manifest in group A at this HEAD. I report that as refuted for this group,
not as untested.

### INFRA-1 — MAJOR — gate infrastructure, not product code

My worktree was provisioned from the **wrong revision**: my branch pointer addressed `c4189ec`
("Add README", 1 file) rather than the `f3c25eb` code under review (878 files). The worktree
inventory shows sibling `agent-a11f6dc1ac49f131f` is **also** at `c4189ec`; only
`agent-a796ad1a6d6d03a67` was at `f3c25eb`. I repointed my own branch pointer onto `f3c25eb`
from a clean tree, affecting only my own pointer, in order to evaluate anything at all.

Two of the three round-4 evaluator worktrees therefore had no application code. A sibling that
did not notice would either report on an empty tree or fall back to reading the primary working
copy — which would re-create exactly the shared-tree cross-contamination that round-4 isolation
was introduced to eliminate. **Treat any sibling verdict that does not state its HEAD with
suspicion.** Fix: provision from the reviewed HEAD explicitly and assert a sentinel path exists
before the evaluator starts.

### OBS-1 — informational

1. Each request emits exactly **one** log line (server access logger disabled), so QA-VM-003 *100
   percent of log lines* is satisfied at n = 1. True but weak.
2. A logger created **after** logging configuration has no filter of its own (measured `False`,
   empty filter list) — **but** the root handler carries a `RedactionFilter`, so a propagated
   record still redacts (measured `late module saw [REDACTED]`). This partially **refutes** the
   worry that late loggers leak: protection is handler-level defence in depth, and the AC2
   per-logger assertion is the weaker of the two statements.

## 5. Mutation testing — were the ACs genuinely exercised?

All eight mutants applied to production files in my isolated tree, and all eight reverted; the
tree ends with no modified files and no differences against `f3c25eb`.

| # | File | Mutation | Result |
|---|---|---|---|
| M1 | `types/money.py` | quantum becomes `Decimal(1/100)` | **KILLED** — 15 failed |
| M2 | `types/money.py` | `ROUND_HALF_UP` to `ROUND_DOWN` | **KILLED** — 5 failed |
| M3 | `config/delinquency.py` | DPD-30 floor 30 to 31 | **KILLED** — sweep + boundary; AC1 35-day case *survived* |
| M4 | `types/delinquency.py` | add `fee` + `penal_interest_rate` | **KILLED** — AC4 assertion |
| M5 | `types/money.ts` | grouping modulus 3 to 4 | **KILLED** — 4 failed |
| M6 | `types/money.ts` | insert `.toNumber()` | **KILLED** — AC3 static check |
| M7 | `config/logging.py` | `scrub_text` to identity | **KILLED ONLY 2** — both error-envelope |
| M8 | `config/logging.py` | `RedactionFilter.filter` to no-op | **KILLED 7** — incl. the AC1 test |

Every AC in my remit has a live oracle. Two results are informative beyond a simple pass:
M3 shows the AC1 35-day case is *not* boundary-sensitive (the AC2 sweep carries the ladder), and
M7/M8 together locate the redaction gap precisely in production wiring rather than in the test.

## 6. Gate recommendation (separate from the axis vote)

My functional axis vote is **PASS**. Separately, as a gate recommendation:

**ALLOW group A, with three mandatory follow-ups that must close before E1-S1 or E4-S1 merges.**
All three are latent today only because the codebase has just two routes and no money endpoint —
they become live defects the moment group B or E lands:

1. **CR-306** — enforce the money wire pattern in validation, not only in documentation.
2. **SEC3-011/F-6** — catch `decimal.DecimalException` **and** give money errors a 4xx mapping.
3. **V-1/F-1** — land a `register_sensitive` call site, or a request-time assertion so
   E15-S1-AC1 cannot pass while the substrate is inert.

I would additionally fix **ESC-CR** now (escape all codepoints below 0x20): it is a one-line
change, and the project has already accepted the argument that the HTTP parser must not be
relied upon as a security boundary.

**The one condition under which I would flip to BLOCK:** if the gate lead reads the E15-S1 Scope
Out clause strictly — *"must not write applicant PAN, Aadhaar or salary-document content to any
log sink"* — then that constraint is violated by direct measurement (PAN x2, Aadhaar x2 in the
live buffer) and group A should not merge. I did not fold this into the AC vote because the PII
in my measurement arrived via a client-supplied path and header rather than from applicant data
through an origination endpoint, and no such endpoint exists yet. This is a judgement call about
constraint scope, and it belongs to the gate lead, not to me.

## 7. What I could not verify (stated as unverified, not as passed)

- **Raw CR/TAB/ESC could not be delivered to a log call or a metrics label.** httpx raised
  `LocalProtocolError`, and a raw socket received `400 Bad Request` from the server HTTP parser.
  ESC-CR is therefore proven **at the function level and latent end to end** — I did not
  demonstrate an exploit.
- **CR-306 was measured against a constructed FastAPI app** using the shipped `MoneyField`,
  because `MoneyField` has zero production call sites and no shipped route carries money.
- **E9-S1-AC1 literal premise** ("when a schedule is computed") could not be exercised: no
  schedule generator exists. Verified over 200 randomized triples through `Money` arithmetic —
  the surrogate the test itself documents.
- **Security, performance/SLO, accessibility and code-review axes** — outside my axis, not
  evaluated. I make no claim about them.
- **`/metrics` authentication deferral, SEC3-003 volume dilution, B-1 method cardinality, B-2** —
  sibling observability axis. I measured only what touched AC2 and the frozen checks.
- **GI-002 / GI-003 harness-defect gate checks and the ownership-check waiver** — not re-run.
- **gitleaks, semgrep and pip-audit remain unprovisioned** per the pack; I did not re-run the
  computational security scan, so the SAST and secrets tiers stay **unscanned**, not passed.

## 8. Harness limitations encountered (affects reproducibility, not the verdict)

- The pre-write gate resolves paths against the main project directory, so the Write tool rejects
  every path inside this worktree. I could not add an in-tree differential test file; instead I
  bundled the real shipped `money.ts` with esbuild into the scratchpad and drove it from node,
  which still exercises the actual shipped code.
- The worktree isolation checker refuses **every** heredoc, including a two-line one, so these
  artefacts were assembled with `printf` appends and all probes ran as inline `python -c` /
  `node -e`.
- The pre-bash gate reads ASCII arrows inside a heredoc body as shell redirections.

