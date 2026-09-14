# Gate handoff — group A, round 4

- **Command:** `/gate --group A` (on-demand pre-merge)
- **HEAD reviewed:** `f3c25eb` · **base:** `14e9487`
- **Date:** 2026-09-14
- **Stories:** E15-S1, E9-S1, E11-S1, E15-S4
- **Reviewers:** 3 × evaluator, 3 × security-reviewer (2-of-3 majority per axis), 1 × code-reviewer (outside the vote), each in **its own git worktree**

## Verdict

```
GATE VERDICT: BLOCK — on 2 findings, both escalated by the gate lead.
NO REVIEWER RAISED A BLOCK.

security    PASS  unanimous 3/3, 0 BLOCK   (round 3: PASS 3/3)
functional  PASS  unanimous 3/3, 3/3 frozen checks, 14/14 ACs
code-review PASS  0 BLOCK, 18 WARN, 9 INFO (round 3: BLOCK on CR-301)
```

Round 3's sole BLOCK, **CR-301, is CLOSED** — confirmed by five instances including the
reviewer who raised it. So is **CR-303/V-0** (round 3's most valuable finding: the escaping
had zero coverage; the identity mutant is now killed) and the performance half of
**B-4/CR-304**. The remediation did what it claimed.

**The gate is nevertheless BLOCK.** This is the lead's escalation of two triple-confirmed
WARNs, not a reviewer verdict, and it is recorded as such.

### GATE-B1 — the only control on E15-S4-AC1 is *inverted*

`backend/tests/architecture/test_observability_contract.py:87`

```python
assert p95_bound == "+Inf" or float(p95_bound) <= 0.5
```

This **accepts the worst case** (p95 above every declared bound) and **rejects the merely
bad one**. Proven three times, independently:

| Instance | Method | Result |
|---|---|---|
| evaluator 1 | mutated `get_health` to sleep 11 s → real p95 = 22× the 500 ms budget | **10 passed in 22.08 s** (runtime proves the sleeps ran) |
| evaluator 2 | all-observations-into-`+Inf` mutant | **survives, 108 passed**; all-into-10s is killed |
| code review | every bucket bound → 1e-12, p95 in `+Inf` | **10 passed** |

**Fix (1 line):** `assert p95_bound != "+Inf" and float(p95_bound) <= 0.5`

### GATE-B2 — `f3c25eb` fixed the wrong half of its own problem

`backend/src/api/middleware.py:113`

The commit excluded `/metrics` from the RED **counter** but not from the latency
**histogram** — `observe_duration` is still called unconditionally. An anonymous scraper
therefore still dilutes p95, while no longer leaving *any* trace in `http_requests_total`.

| Instance | Measurement |
|---|---|
| code review | reported `histogramP95` **5 ms** vs business-only p95 **4,875 ms**, budget 500 ms |
| security 3 | genuine 975 ms breach → **4.8 ms PASS** after 2,000 anonymous scrapes; `errorRate` read 0.0000% throughout |
| evaluator 1 | a 5xx on `/metrics` is now counted nowhere (NEW-3) |

**Fix (1 line):** apply `_SLI_EXCLUDED_ROUTES` to `observe_duration` too.

**Why this blocks:** E15-S4 was added to this group for exactly one purpose — to make the
declared runtime SLO measurable. As shipped, the metric under-reports a real breach by
~1000× and the test guarding it cannot fail. Merging banks a "the runtime SLO is
measurable" claim that is neither correct nor protected. That is the same
vacuous-verification hazard this project already accepted as grounds for reverting approved
work (see the AC-RENUMBERING note at the top of `claude-progress.txt`). Evaluator 1
independently recommended BLOCK on GATE-B1; evaluator 2 independently said its class must be
closed before merge or recorded as explicit debt.

**GI-012 corollary:** the gate's own `slo-verdict.json` reports `p95_ms 4.75` — the same
few-millisecond figure the attack produces. The SLO row measures the *observer*, not the
application. Do not read that `pass` as evidence the runtime SLO holds.

## Required in the same fix cycle (not independently blocking)

Fixing GATE-B1/B2 without these leaves the same vacuity shape in the same two files:

| ID | File:line | Why |
|---|---|---|
| **V2-01** | `middleware.py:193` | `seen[0] if seen else 500` → `else 200` leaves **108/108 green**. The input to the SLO error-rate gate is unprotected, and the branch is live. |
| **V2-03** | `middleware.py:128` | `_sum` never accumulating leaves **108/108 green** — only substring presence is asserted. Breaks `rate(sum)/rate(count)`. |
| **CR-401 / CR-314** | `middleware.py:175` | `seen.append` precedes `await send`, so a send raising at `response.start` records **200 while the client got 500** and no byte reached the wire. `ab0fd6e` *moved* this defect, it did not fix it. |
| **CR-402** | `middleware.py:210` | Two `_observe` call sites, not one `finally` — measured `http_requests_total = 2` vs `_count = 1` from a single request when `observe_duration` raises. |
| **CR-407** | `test_observability_contract.py:180` | The new cardinality tests cover `record_request()` only, **not the HTTP boundary**: an `_observe`-bypass mutant leaves both green. |
| **CR-408** | `test_observability_contract.py:225` | `route="/metrics" not in body` is vacuous and false on a second scrape. |
| **NEW-2 / V2-05 / CR-411** | `middleware.py:89` | `method_label` uppercases *before* the membership test, so lowercase `get` (answered 405) records `method="GET", status="405"` — a series asserting an impossible event. `"OPTION"+U+017F` folds onto `OPTIONS`. Cardinality is bounded; fidelity is not. |
| **NEW-1** | `middleware.py:193` | Measured regression from `ab0fd6e`: an outer task cancelled mid-request records `(GET,/slow,500)` where `ab0fd6e~1` recorded nothing. Reachable at uvicorn's graceful-shutdown timeout, so shutdown injects false 5xx into the SLO signal. |

## Carried WARNs, third round, all verified one-line fixes

`CR-305` (two false sentences in a docstring), `CR-309` (`_database_status` swallows the
probe reason), `CR-310` (avoidable `# type: ignore`, fix verified clean in round 3),
plus `CR-307` (silent context drops), `CR-313` (latent, see below).

**`CR-306` is worse than round 3 recorded** and is now a money-correctness issue, not a
documentation gap: `"12.345"` → **200, silently rounded to `12.35"`**; `"1e2"` → `"100.00"`;
`"0.001"` → `"0.00"`; `"1234"` → `"1234.00"`. The declared JSON-schema pattern is never
applied because `no_info_plain_validator_function` bypasses schema validation. Latent —
`MoneyField` has zero production call sites. Confirmed live by evaluators 1, 2 and 3.

## Before group B or E (unchanged in substance, sharpened in detail)

1. **F-1/V-1 — redaction is INERT.** Zero `register_sensitive` call sites in `backend/src`;
   `ba457bf` put them in `specs/bundles/*.json`, the **specs**, not the code. All six
   instances confirmed; two logged live raw PAN and Aadhaar via the request path and
   `X-Request-ID`. **Corrected:** E15-S1-AC1 is *not* vacuous — the filter-to-no-op mutant
   kills 7 tests. The gap is production **wiring**, not oracle strength.
2. **Redaction bypass breadth — round 3's "ALL forms bypass" is partly refuted.** Plain,
   4-space, dash and lowercase forms **do** redact; 12 of 18 bypass. The realistic leakers
   for Indian KYC are **NBSP**, **soft hyphen** and a **5-space run** — the last one *new*,
   because it defeats the 0-to-4 bound added to fix SEC-001. Also **bidirectional**.
   Normalize-then-match (NFKC) remains required.
3. **SEC2-004 — the tripwire the F-1 deferral rests on is itself bypassable.**
   `test_log_redaction.py:147` misses `national_id`/`uid`/`kyc_number`/`tax_id`/
   `document_number`, and a call named only in a comment passes; meanwhile `expand`/`company`
   false-positive, so the cheapest way to silence it *is* the bypass. A deferral is only as
   good as its guard.
4. **SEC4-002/SEC3-003 residual — harness-owned.** `errorRate` at
   `.claude/hooks/lib/prom-parse.js:37-47` sums every series with no route dimension, so
   50 errors + 50 successes (50.0000% breach) reads **0.2488%** after 20,000 anonymous
   `/health`; only ~4,900 extra requests are needed. Stays WARN because the fix is outside
   this repo's allowed paths.
5. **SEC3-011/F-6 — the fix is bigger than round 3 thought.** Converting to
   `InvalidMoneyAmountError` would **not** give 422; no handler maps `ValueError`, so
   `/probe/typed` also returns 500. Needs *both* a `DecimalException` catch **and** a 4xx
   mapping. Boundary located: `1E+999995` is handled, `1E+999998`+ leaks bare `Overflow`.
6. **CR-409 / SEC4-003 — frontend `Money` is unbounded.** `1e20000000` → 1,888 ms and a
   26.7 MB string; `1e400000000` → **V8 OOM, exit 134, from an 11-byte input**. The backend
   rejects `>1e25` in 0.0 ms. Bound `toQuantizedDecimal` to the declared wire form.
7. **FE-GUARD — the frontend float guard has no division pattern**, while the backend counts
   it precisely because `principal / months` is the shape an EMI calculation takes.
8. **SEC4-004 — `X-Request-ID` is structurally un-scrubbable**: `JSONLogFormatter` injects
   `request_id` *after* `RedactionFilter` runs, so no registered value can ever scrub it.
9. **Pin `--http httptools`** when E15-S2 writes the Dockerfile. Several bounds are verified
   under both parsers now, but CR-302's unreachability still rests on parser behaviour.

## Refutations worth keeping (stop re-litigating these)

- **CR-311 REFUTED.** The prior round reasoned from the enumeration code and never tested
  propagation. A late-created logger has no filter of its own, but `propagate=True` and the
  **root handler** carries `RedactionFilter` — a registered PAN through such a logger gave
  `[REDACTED]`. The 3 apparently unfiltered entries are `logging.PlaceHolder` namespace
  nodes, not loggers.
- **CR-313 DOWNGRADED to latent.** 11 orderings all give 108 passed. Critically,
  **`pytest-randomly` is not installed**, so round 3's `-p no:randomly` was a no-op — the
  prior ordering evidence did not test what it claimed.
- **The round-3 AC-renumbering hazard is REFUTED for group A.** All 14 ACs map 1:1 to
  VM-001..005/009..011/070..073/108..109 with verbatim descriptions, one trace per AC. No id
  points at a different AC than its test claims. This materially de-risks the deferred AC
  decision.
- **`format()` is correct, not just fast.** Zero disagreements against an independent
  reference grouper over 2,400 cases (code review), 0 mismatches across 200,000 random
  amounts (evaluator 3), byte-identical to the old regex for n=1..60 (security 3). The 250 ms
  test bound has 50–80× headroom and is **not** flaky.
- **The `500` default is not an attacker vector.** 5 × `curl --max-time 1` aborts against a
  5 s handler recorded `6 × /slow status=200` and zero 5xx — uvicorn does not cancel on
  client disconnect. (It *is* a shutdown-time regression; see NEW-1.)
- **Round 2's `Money.multiply` timing dispute is settled — both were right about different
  scalars.** `multiply(Decimal)` = 0.00 ms; `multiply(10**1000000)` = 9,538 ms, of which
  **9,531 ms is CPython's int→Decimal coercion**, not the multiplication.
- **No contract drift.** All 13 frozen hashes byte-identical; the apparent mismatch is
  `core.autocrlf` (raw `df24b294…` vs LF-normalised `a0625d4b…`, the latter matching).

## Deterministic results

| Check | Result |
|---|---|
| `uv run pytest -q` | **108 passed** (round 3: 104) |
| `npm test` | **20 passed** (round 3: 18) |
| ruff / mypy / eslint / tsc | all clean |
| registry sweep (`--lane gate`) | 6 pass, 3 BLOCK — **all three re-verified as harness artifacts** |
| canvas-sync, product scope | 0 issues, 14/14 synchronized |
| ownership-check | only `backend/src/__init__.py`, covered by a ratified unexpired waiver |
| regression-gate, B–M excluded | **pass** |
| quality-card | **FAIL** — 8 pass / 2 fail (`ownership`, `regression`: both artifacts); `security_scan` unknown (GI-009) |
| finalize-task-evidence | **BLOCK** — correct. `signed_approvals 0/2`, `threat_model` stale, sast/dependency_scan unprovisioned. The unit/acceptance/integration "failures" all resolve to `gate-checks.json`, which is `pass:false` only because of the three registry artifacts — **not** because tests fail. |
| task lifecycle | left **ACTIVE**, deliberately **not** sealed |

**UNSCANNED, NOT PASSED:** gitleaks (secrets), semgrep (SAST), pip-audit (Python CVE).
`npm audit` against `frontend/` explicitly: 1 critical + 1 high + 3 moderate, **all
devDependency-only**, prod dependency count 5. Three inferential security instances were
again the only real coverage for the injection/authz/PII classes.

## Harness defects

**Fixed this round:** **GI-005** — per-instance worktrees eliminated the file-level mutant
leakage that made round 3's measurements unvouchable. All seven instances verified their own
tree pristine afterwards.

**New, in priority order:**

- **GI-010 (high).** `Agent(isolation: "worktree")` provisions from **`origin/main`, not the
  session HEAD**. All seven branches show `Created from origin/main` at `c4189ec` — a
  README-only commit 18 behind, with no `backend/` or `frontend/` at all. All seven detected
  and reset it, but an instance that did *not* check would have found nothing to review and
  could have returned a clean PASS on an empty tree — **a vacuous verification
  indistinguishable from a genuine one in the vote trail**. The GI-005 fix introduced a fresh
  vacuity risk. Fix: provision from the reviewed HEAD and assert a sentinel path + resolved
  HEAD before dispatch.
- **GI-013.** Worktree isolation does **not** isolate the OS process table or port space.
  Security 2 ran `taskkill /F /IM python.exe` — killing every Python process while two
  evaluators had live servers — and found an unidentified process on its assigned port 8022.
  Fix: harness-enforced per-instance port ranges, a prohibition on image-wide kills, or
  container isolation.
- **GI-011.** `pre-write-gate.js` normalises `.claude/worktrees/<id>/specs/reviews/...` and
  fails to match its own `specs/reviews/**` allow-entry, because `allowed_paths` resolve
  against the main project root. Security 3 declined to bypass and reported inline (its
  artifacts were transcribed by the lead); evaluator 2 used a Python heredoc; security 1's
  write nevertheless succeeded — so the block is **inconsistent**, not absolute.
- **GI-014.** The context pack was written but **not committed**, so every worktree instance
  read the committed **round-3** pack. Evaluator 3 caught the staleness (re-measuring 108/20
  against the pack's 104/18). The round-4 framing survived only because it was duplicated in
  each dispatch prompt. Fix: commit the pack, or write it into each worktree, before dispatch.
- **GI-015.** `specs/brownfield/code-graph.json` is **empty** (`status: "empty"`, `reason:
  "source index unavailable"`, generated 2026-09-13 before any source existed) and has never
  been rebuilt. Both mandated human trust surfaces are therefore vacuous: `docs/CODEBASE.md`
  reports **0 indexed files / 0 edges / 0 concepts**, and the walkthrough's **Blast radius**
  section reports "no graph neighbors". `specs/brownfield/**` is outside the task envelope's
  allowed paths, so this needs `/code-map` run deliberately.
- **GI-012.** `slo-verdict.json` measures the observer, not the application (see GATE-B2).

**Reconfirmed:** GI-001 (`--all --staged --boundary-only` scans zero files and self-reports
clean; `runDeps()` only probes the repo root), GI-002 (registry omits `--exclude-group`),
GI-003 (no harness-state exclusion in canvas-sync), GI-004 (`npm run sensor-waivers` ENOENTs;
the real validator is `.claude/scripts/validate-sensor-waivers.js`), GI-006 (no waiver path in
`run-gate-checks.js`), GI-007 (`evidence-integrity` passes `applicable:false` — vacuous for
group A), GI-009 (`security-scan.json` has no `pass` field; `missing` omits pip-audit).
**GI-008 did not bite this round** — the `evaluator` row parsed as pass.

## Next action

1. **GATE-B1** (1 line) and **GATE-B2** (1 line).
2. The seven **required-in-same-cycle** items above — mostly tests that must be made to bite.
3. Re-run `/gate --group A` (round 5). Per GI-010, **assert each instance's resolved HEAD
   before trusting its verdict**, and commit the context pack first (GI-014).
4. Do **not** build group B until GATE-B1/B2 are closed, and not before the F-1 redaction
   wiring + normalize-then-match land (items 1–3 of "Before group B or E").

Opening a PR is `/auto --sealed`'s job. This gate never approves and never merges.
