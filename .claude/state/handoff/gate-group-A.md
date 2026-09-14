# Handoff — /gate --group A (round 3)

**Verdict: BLOCK.** Not merged, no PR opened. `.claude/state/gate-receipt.json` `pass:false`;
quality-card 7 pass / 3 fail. Task lifecycle deliberately left `active` —
`finalize-task-evidence.js` correctly refused.

HEAD `ba457bf` · base `14e9487` · branch `feat/harness-scaffold-and-planning`

## Axis results

| Axis | Verdict | Detail |
|---|---|---|
| security | **PASS** | unanimous 3/3, 0 BLOCK (round 2: BLOCK 3/3) |
| functional | **PASS** | unanimous 3/3; 3/3 frozen api_checks, all story ACs |
| code-review | **BLOCK** | single instance, outside the vote, sufficient alone — **CR-301** |

No fail-safe triggered: every instance returned a verdict. Vote trail:
`specs/reviews/reverify-votes.json`.

**Both voted axes flipped from round 2 to PASS.** The gate is BLOCK on one finding.

## The only open BLOCK — CR-301

**`backend/src/api/middleware.py:50,72-73,132,141-143` — the `method` label is unbounded;
round 2's B-2 is only half-closed.**

`f1367f5` bounded the *route* dimension (verified by 4 instances up to 60,000 distinct
paths: 3 route values, +376 KB). But `method` still flows from `scope["method"]` straight
into the keys of `_request_counts` and the **new** `_duration_counts`/`_duration_totals`,
which are process-global and never evicted, behind an unauthenticated `/metrics`.

Measured under `uvicorn --http h11` by three independent instances:

| Instance | Distinct methods | Result |
|---|---|---|
| code-review | 3,000 (one keep-alive conn, 0.7 s) | 2,998 counter + 2,998 histogram series; 3,553,759-byte body; ~2.5 MB retained |
| eval-2 | 22,003 | 330,064 lines; 25.3 MB retained; no levelling off |
| sec-2 | 20,000 | 300,094 lines; 42,186,513 bytes; +16.5 MB RSS |

**Refutation for the shipped config succeeded:** `uvicorn[standard]` + `uv.lock` +
`deployment.md` all resolve to httptools/llhttp, which answers **400** to any
unknown-token method before the ASGI app runs (`XPROBE1 → 400` under httptools vs `405`
under h11). sec-3 measured the httptools ceiling as llhttp's ~35-method table → a bounded
`35 × (routes+1) × statuses`, worst observed 1,611 series / 130,289 bytes.

**Held at BLOCK because** the bound rests entirely on an optional C extension's method
allow-list that nothing here documents, tests or pins, `middleware.py` is deliberately a
server-agnostic pure-ASGI middleware, and **no Dockerfile or compose file exists yet** to
fix the parser. E15-S2 (group B) is what creates that file — if it installs uvicorn without
the `standard` extra, this goes live.

**Fix: 3 lines mirroring `_UNMATCHED_ROUTE`** — clamp `method` to a known-method set with
one `<other>` bucket. Closes CR-302 at the same time.

## Round-2 BLOCK disposition

| ID | Status | Basis |
|---|---|---|
| **B-1** /metrics injection | **CLOSED** 6/7 instances | Route label is the matched template, so the raw path is no longer a label channel. `slo-check.js` → `error_rate_pct: 0` where round 2 measured a forged **99.90%**. `scope["method"]` is *not* attacker-controlled under httptools (`GE"T`, `GE\T`, `FOOBAR` all → 400 below ASGI) |
| **B-2** cardinality | **HALF-CLOSED** | Route bounded; `method` open → CR-301 |
| **B-3** lost HTTPException.headers | **CLOSED** 5/7 instances | Live: 405→`allow: GET`, 401→`WWW-Authenticate: Bearer realm="truelend"`, 409/429 keep custom headers; 404/422/500 envelopes intact. Real regression test at `test_error_envelope.py:189` |
| **B-4** money.ts quadratic regex | **OPEN — downgraded BLOCK→WARN** | See below |

### B-4: still open, untouched, downgraded on reachability

**Untouched by all six remediation commits** — the regex at `money.ts:78` is verbatim.
Reproduced at full magnitude by 5 instances, quadratic at ~4× per doubling across 3+
doublings:

- `format()` on the 8-byte `"1e100000"`: **4,088 / 4,129 / 4,167 / 4,301 ms** (four instances)
- the 9-byte `"1e1000000"`: **421,224 ms** (eval-2) and **429,464 ms** (eval-1's probe) — ~7 minutes
- no upstream bound: `fromWire` only checks `isFinite()`; `toDecimalPlaces(2)` constrains
  scale, not exponent; `MoneyField._WIRE_PATTERN` constrains OpenAPI docs only

**Round 2's refutation is now positively explained:** it timed `toFixed()`, a *linear* sink
measuring 0.6–3.2 ms — roughly **1,260–7,000× cheaper** than the real one. Recorded so this
does not recur.

**Downgraded to WARN** by four independent reachability analyses agreeing: `format()`'s only
caller is `MoneyText`, whose only callers are tests. `frontend/src` holds two files with no
entry point and no fetch layer, and the backend cannot emit such a value (`Money._quantize`
rejects past 28-digit precision — `1e30`, `1e100000` all raise).
**Escalates to BLOCK/high on the first commit that mounts `MoneyText` against non-backend
input.** eval-3 dissents and argues high now, on the grounds that `MoneyText.tsx:10-15`
declares `money: Money | string` and calls `fromWire(money).format()` with no bound — i.e.
the component's *public contract* already accepts unbounded input. One-line fix either way;
worth taking now rather than carrying a third round.

## Disputes settled this round

- **`Money.multiply` timing** (round 2: 9,708 ms vs 109 ms, unresolved) — **neither was
  right.** `decimal.Overflow` escapes in **0.0 ms**. No DoS. It is a contract break: a bare
  `ArithmeticError` instead of `InvalidMoneyAmountError`, so 500 rather than 422.
  `money.py` catches only `InvalidOperation`. (SEC3-011 / F-6)
- **method-cardinality magnitude** — not a contradiction, parser-dependent. See CR-301.
- **"AC2 passes by construction"** — *partially refuted*. Installing the filter on root only
  kills both AC2 tests, so "vacuous" overstates it. Real residual defects, both executed:
  the property holds only at the instant `configure_logging()` returns (a later `getLogger`
  is in `loggerDict` with no filter), and the docstring's non-vacuity claim is empirically
  false because a constructor-built probe logger never enters `loggerDict`.

## New this round — must not be lost

1. **V-0 / CR-303 (major): the entire B-1 escaping fix has ZERO test coverage.** Mutating
   `_escape_label` to the identity function leaves **all 104 tests green**. Both tests named
   `..._labels_cannot_be_injected_from_a_request_path` actually pass via `route_label`'s
   cardinality bound (mutating *that* to the raw path fails 4 tests). Found independently by
   eval-3 and code-review. The escaping that closed B-1 is unprotected — a refactor reopens
   the injection silently. The cumulative-bucket logic **is** genuinely covered.
2. **F-1 / V-1 / W-3 / SEC3-004 (major): redaction is inert.** **Zero
   `register_sensitive` call sites in `backend/src`.** eval-2 logged live raw PAN + Aadhaar
   from a request path and from `X-Request-ID`. `f5a5ace`'s SEC-103 fix correctly plumbs
   `scrub_text` into the int/key paths, but `scrub_text` is registration-driven, so an
   `AppError` context still egressed `"aadhaar_int": 123412341234`, the key
   `"pan-ABCDE1234F"` and an absolute path. `ba457bf` added the call sites to
   **`specs/bundles/E1-S1.json` and `E4-S1.json` — the specs, not the code.** So
   **E15-S1-AC1 currently passes as a surrogate**, and round 2's escalation trigger has not
   fired. With values registered, dotted/underscored/slashed/NBSP/soft-hyphen/zero-width/
   fullwidth Aadhaar forms **all still bypass** — the real fix is normalize-then-match.
   **Must close before group B/E logs applicant data.**
3. **SEC3-003 (WARN, nobody assigned it): unauthenticated volume dilution masks an SLO
   breach** — the twin of B-1's injection. `errorRate()` is 5xx over *lifetime* counters
   that never reset, `/metrics` is anonymous and unrated. Reproduced: a genuine **50.00%**
   outage reads **0.0100%** (passing the 1% budget) with 1e6 404s; a genuine **9,525 ms**
   p95 reads **4.8 ms**. One flood poisons both ratios for the process lifetime. The
   exposition is correct Prometheus semantics and already emits the `route="<unmatched>"`
   label the sensor needs in order to exclude it — so the fix belongs in `slo-check.js`.
4. **CR-306 (WARN): `MoneyField`'s declared `pattern` is unenforced.**
   `POST {"principal":"12.3"}` → **200 `"12.30"`** while the schema and
   `test_no_float_money.py:342` both say 1dp is invalid. A real defect in `a807678`.
5. **CR-302 / F-3 (WARN): `_escape_label` passes raw CR, TAB, NUL, BEL, ESC, DEL.**
   `_histogram_lines()` emitted 14 lines containing a raw CR, contradicting E15-S4-AC2's own
   "no raw control character". Unreachable under httptools; same root cause as CR-301.
6. **E15-S4 verified genuinely, not by grep.** AC1's buckets are **cumulative** (proved with
   a 700 ms observation: `[19,19,...,20,20]`, where increment-only would give `[19,0,...,1,0]`);
   eval-2 recovered **p95 884.62 ms vs 934.22 ms empirical truth**, correctly flagging a
   500 ms breach; eval-1 recovered 458 ms against a true 300 ms (expected bucket-resolution
   error, `0.5` an exact bound). **`slo-check.js` now reports `p95_ms: 4.75` where it was
   permanently `null`.** The runtime SLO is measurable for the first time.
   Residual W-5: `test_p95_is_computable_from_the_exposition` survives the non-cumulative
   mutant; only `test_histogram_buckets_are_cumulative_…` kills it.

## Carried WARNs (unchanged, all re-confirmed live)

`X-Request-ID` unvalidated/unbounded (1 MB accepted → a 1,048,722-byte log line; PAN-format
id logged unredacted; **CRLF response-splitting refuted** — `json.dumps` neutralises it) ·
host-header open redirect (`307 location: http://evil.example/health`) · no security response
headers · public `/docs`, `/redoc`, `/openapi.json` · PII retained as `lru_cache` keys past
scope teardown (proven by hit/miss counters) · `HEAD /health` → 405 · no 405 entry in
`_STATUS_ERROR_NAMES` · 500 traceback reaches the log sink unscrubbed · `sanitise_context`
drops floats/`None`/>200-char values with no marker, and its 200-char cap is `str`-only so a
4,000-digit int egresses whole · `/openapi.json`/`/docs` mislabel as `route="<unmatched>"` ·
`/metrics` unauthenticated — **deferral judged defensible by all 3 security instances**
(bounded RED/latency only, no PII or secrets, documented in E15-S4 Scope Out), but revisit on
CR-301's fix rather than at E1-S1, since CR-301 turns it into 25 MB of amplification.

## Deterministic state at HEAD

104 backend tests pass (was 88) · 18 frontend tests · ruff, mypy, eslint, tsc all clean ·
**13/13 sprint-contract sha256 match `contract-freeze.json`** — no contract drift; `A.json`
was legitimately re-frozen after E15-S4 was appended · `npm audit` 1 critical (vitest) +
1 high (vite), **devDependency-only** · lockfiles now tracked (`.gitignore` fixed), closing a
round-2 WARN.

**Unscanned, NOT passed:** semgrep (SAST), gitleaks (secrets) and pip-audit (Python CVE) are
all unprovisioned. Three inferential security instances were the only real coverage for the
injection/authz/PII classes this round.

## Why quality-card says 7 pass / 3 fail

Overall FAIL is the right outcome, but **only one of the three failing rows is a real
finding**:

| Row | Real? |
|---|---|
| `code_review` | **YES** — 1 BLOCK (CR-301) |
| `evaluator` | **NO — parser artifact (GI-008).** eval-1's report declares `FUNCTIONAL VERDICT: **PASS**` at line 12, but `md_verdict` in `.claude/hooks/lib/sensor-schema.js:60-66` regexes the whole document and takes the FAIL branch because the words "BLOCK"/"FAIL" appear 3× in *discussion* (lines 26, 338, 649). Any thorough evaluator report that merely mentions a block scores fail |
| `ownership` | **NO — waived.** A ratified `ownership-check` waiver names `backend/src/__init__.py` exactly (approved_by `ovi-rosu`, expires 2026-10-15) |

## Gate-integrity defects

- **GI-001** (reconfirmed) `security-scan.js --all --staged --boundary-only` scans **zero
  files** and self-reports a clean pass; `runDeps()` probes only the repo root for
  `package.json`, so npm audit never reaches `frontend/`. **Always pass explicit `--files`.**
- **GI-002** (reconfirmed) the registry invokes `regression-gate.js` with only `--replay`,
  never `--exclude-group`, so `discoverPriorContracts()` grades the **unbuilt** groups B–M
  as prior baselines and emits 404s. Correctly scoped re-run: **`regression-gate: pass`**.
- **GI-003** (reconfirmed) `canvas-sync-check.js` `changedFiles()` has no harness-state
  exclusion, so it blocks on `.claude/state/red-phase-presnap.json`. Product-scope run is
  synchronized (13 files, 0 missing).
- **GI-004** (new) the gate skill documents `npm run sensor-waivers`, but there is **no root
  `package.json`** so that command ENOENTs. The real validator is
  `.claude/scripts/validate-sensor-waivers.js` → pass, 5 waivers, none expired.
- **GI-005 (new, highest priority) concurrent 3-instance re-verification in ONE shared
  working tree is unsafe.** Instances mutation-test production files simultaneously; **three
  of seven agents** reported observing a sibling's live `# MUTANT` edit to
  `middleware.py`/`routes.py`, and the canonical security instance had to `git checkout` two
  live mutants before it could re-derive its verdicts. Collateral: `npm test` reported 20
  instead of 18 while a sibling probe file sat in `frontend/tests/unit/`; repo-wide `ruff`
  failed on a sibling scratch dir; a shared `slo-verdict.json` was overwritten mid-run.
  Every instance bracketed its measurements with `git diff` checks and the final tree is
  verified clean — but **no instance can fully vouch for another's in-tree measurements.**
  **Fix: give each instance its own `git worktree`, not merely its own port.**
- **GI-006** `run-gate-checks.js` has no waiver-application path (waivers apply at
  pre-commit only), so `ownership-check` re-reports as blocked even when a ratified waiver
  covers the exact file.
- **GI-007** (new) `evidence-integrity` (G39) passes with `applicable:false` — no sprint
  contract declares playwright checks. Honest but **vacuous** for group A; do not read it as
  evidence of browser-backed verification.
- **GI-008** (new) `quality-card.js`'s `md_verdict` parser cannot separate a report's verdict
  from its content. See the table above.
- **GI-009** (new) `security-scan.json` carries no `pass` field and no `verdict`, so the
  quality card scores it `unknown` (counted as not-pass). It also lists `missing:
  [gitleaks, semgrep]` while pip-audit is absent too and goes unlisted.

## Task evidence

`finalize-task-evidence.js` → **BLOCK**, correctly:
```
missing: ["signed_approvals:0/2"]
stale:   ["threat_model"]
failed:  ["unit","acceptance","independent_review","integration","sast","dependency_scan","gate_pass"]
```
`unit`, `acceptance` and `integration` all resolve to `specs/reviews/gate-checks.json`, which
is `pass:false` only because of the three registry BLOCKs above (two harness artifacts, one
waived) — **not** because tests fail; 104 backend + 18 frontend pass. `sast` and
`dependency_scan` fail because the tooling is unprovisioned. **`signed_approvals: 0/2` and
the stale threat model are human-owned and cannot be cleared by any agent.**

## next_action

1. **Fix CR-301** — clamp the `method` label to a known-method set with one `<other>`
   bucket (3 lines, `middleware.py`). Closes CR-302 too.
2. **Fix B-4** — bound the digit count before the separator regex in `money.ts:78`
   (1 line). Do not carry it a third round.
3. **Add a test that kills the `_escape_label` identity mutant** (V-0/CR-303), and one that
   kills the non-cumulative-bucket mutant for the p95 test (W-5).
4. Then **re-run `/gate --group A`** — ideally with each re-verification instance in its own
   `git worktree` (GI-005).
5. Consider before group B: normalize-then-match redaction (F-1) *before* E4-S1/E1-S1 log
   applicant data; `slo-check.js` excluding `route="<unmatched>"` (SEC3-003); CR-306's
   unenforced `MoneyField` pattern; and **pin `--http httptools` when E15-S2 writes the
   Dockerfile**, or CR-301 goes live regardless of the app-level fix.

Do **not** build group B on this substrate until CR-301 is closed.
