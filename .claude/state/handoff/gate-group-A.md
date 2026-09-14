# Handoff — /gate --group A (round 2)

**Verdict: BLOCK.** Not merged, no PR opened. `.claude/state/gate-receipt.json` `pass:false`;
quality-card 7 pass / 3 fail. Task lifecycle deliberately left `active` —
`finalize-task-evidence.js` correctly refused (gate_pass / security_review / sast /
dependency_scan failed, signed_approvals 0/2, threat_model stale).

**ACTION FOR THE LEAD: paste the "Session 5 block" below into `claude-progress.txt`
above `=== Session 0 ===`.** I hit the 200K context ceiling before I could write it;
every other gate artifact is already on disk. (I did already correct the two
misleading lines in the old top block, which claimed a fresh verdict was "in flight".)

## Axis results

| Axis | Verdict | Detail |
|---|---|---|
| security | **BLOCK** | unanimous 3/3 |
| functional | **FAIL** | 2/3 (instance 2 passed but scoped itself functional-only and declined to clear security) |
| code-review | **BLOCK** | single-instance axis, outside the vote, sufficient alone |

Full vote record + independent confirmations: `specs/reviews/reverify-votes.json`.

## All five prior BLOCKs are genuinely CLOSED

CR-001, CR-002, CR-003, SEC-001, SEC-002 — verified by **execution** at HEAD by seven
reviewers plus my own probes, not by reading the code comments. SEC-001's original
199,326 ms probe now runs in 0.03 ms with flat growth. Evaluator 1 mutation-tested the
float guard (appended `float(x) * 1.5` to production `money.py`, 2 tests fired, reverted
via git — I verified the tree is pristine), so E9-S1-AC2 is a measured result.

The frozen contract is fine: QA-VM-003/004/005 pass live in all three evaluator
instances and in my own live regression run. All 12 story ACs pass.

## The two remediation commits introduced four new BLOCKs

**1. `/metrics` Prometheus exposition INJECTION — the worst one.**
`backend/src/api/platform/routes.py:77-81` f-strings the percent-DECODED `scope["path"]`
into a Prometheus label with no escaping of quote/backslash/newline. One unauthenticated
GET forged a whole sample. I reproduced it directly:
```
http_requests_total{method="GET",route="/hx",status="500"} 424242
#",status="404"} 1
```
Then ran **this project's own sensor** against the poisoned endpoint:
`slo-check.js` → `{"verdict":"fail","error_rate_pct":99.90,"breaches":["error_rate"]}`
against a budget of 1. Evaluator 1 measured 99.995% and also proved the inverse —
inflate the 200 counter to **mask** a real outage. The observability data plane is
attacker-writable. Evidence: `specs/reviews/metrics-forgery-evidence.txt`,
`specs/reviews/slo-verdict-poisoned-evidence.json`.

**2. `/metrics` unbounded cardinality → unauthenticated memory DoS.**
`backend/src/api/middleware.py:49,75,91`. `_request_counts` is a process-global `Counter`
keyed on the RAW path, never evicted, incremented for 404s too. Measured independently
six times; worst: 60,000 paths from ONE keep-alive connection in 11.9 s → +28.2 MB
permanently retained (~142 MB/min), `/metrics` body 45.6 MB / 124,012 series.

*One fix closes both:* key on the matched route template (verified viable — `scope["route"]`
IS populated at `http.response.start`), escape label values, bound cardinality,
authenticate `/metrics`.

**3. `errors.py:107` discards `HTTPException.headers`.**
I reproduced: a 401 with `headers={"WWW-Authenticate":"Bearer"}` returns it ABSENT;
`POST /health` → 405 has no `Allow`. RFC 9110 §15.5.2/§15.5.6. A regression against the
FastAPI default handler this replaced. One line: `headers=getattr(exc, "headers", None)`.
Worse at group C: D-F makes `require_roles` the single 401 point and every current error
test asserts only on the body, so a missing challenge header would pass unnoticed.

**4. (latent, frontend) `frontend/src/types/money.ts:78`.**
The thousands-separator lookahead `/\B(?=(\d{3})+(?!\d))/g` is QUADRATIC: `"1e100000"`
(8 bytes) = 4,152 ms; `"1e1000000"` (9 bytes) did not finish in 100 s. Not reachable at
HEAD (no frontend entry point). **Note:** evaluator 3 REFUTED this by timing `toFixed()`
(40 ms) — wrong sink. Security 3 isolated the cost to the regex. Clearest case where
running 3 instances changed the outcome; a single-instance run would have filed it refuted.

## Top WARNs to fold in (not exhaustive — see `specs/reviews/security-verdict.json`)

- `sanitise_context`: int/bool values and mapping **KEYS** skip `scrub_text` entirely, so
  a registered 12-digit Aadhaar egresses whole; absolute filesystem paths still egress.
  **SEC-003 is only PARTIALLY fixed.**
- Redaction bypass by formatting is far wider than the 5-dash case: dot, underscore,
  slash, NBSP, soft hyphen, zero-width, homoglyph, fullwidth, NFKC forms all defeat it.
  Real fix is normalize-then-match, not a wider run. Harmless **only** because there are
  zero `register_sensitive` call sites at HEAD. MUST close before group B/E logs applicant data.
- `X-Request-ID` unvalidated/unbounded: 5 MB accepted, reflected, logged verbatim. A
  PAN-format id was logged unredacted.
- Host-header-reflected **open redirect** (`Location: http://evil.example/health`);
  `/docs` and `/openapi.json` public; no security response headers. `HEAD /health` → 405.
- PII retained for the process lifetime as `lru_cache` keys on `_redaction_pattern`.
- `Money.multiply` lets bare `decimal.Overflow` escape (`money.py:101` catches only
  `InvalidOperation`). Timing **disputed**: eval-3 9,708 ms vs sec-3 109 ms — recorded as
  disputed, not resolved either way.
- `/metrics` has **no duration metric**, so `slo.p95_ms:500` is permanently unmeasurable
  (`p95_ms` null every run).
- `uvicorn.access` is DISABLED and **both** justifications in `logging.py:217-223` are
  FALSE (disproven empirically and against uvicorn source `httptools_impl.py:484`).
  Routing through the JSON root handler works and preserves client address, HTTP version
  and query string. AC3 passes on its merits; the comment misrepresents why.
- **No dependency lockfile is under version control at all**: `.gitignore:48-49` ignore
  `*.lock` and `package-lock.json` repo-wide, so neither `frontend/package-lock.json` nor
  `backend/uv.lock` is tracked. Manual npm audit: 1 critical (vitest, CVSS 9.8) + 1 high
  (vite, CVSS 7.5, Windows-specific), both devDependency-only.
- Both AC2 "every logger has the filter" tests pass **by construction** — they enumerate
  the same `loggerDict` the implementation just iterated.

## Harness / gate-integrity defects (details in `reverify-votes.json`)

- **GI-001 BLOCK** — `security-scan.js` reported a clean pass having scanned **ZERO files**.
  The skill's documented `--all --staged --boundary-only` yields `files=[]` when nothing is
  staged, and `runSastDetail` then returns `{ran:true,hadTargets:false}` with **no** skip
  warning. Also `runDeps()` probes only the repo ROOT for `package.json`, so with the only
  manifest at `frontend/package.json` **npm audit never ran**. gitleaks, semgrep and
  pip-audit are all absent here. → Always pass explicit `--files`; treat
  `security-scan.json` as unprovisioned.
- **GI-002** — `regression-suite-full` BLOCKed with 54 bogus `got 0` findings because
  `discoverPriorContracts()` grades EVERY sprint-contract as a prior baseline unless
  `--exclude-group` is passed, and the registry passes none. Re-ran correctly against a
  live server: group A passes, true baseline is no-baseline. Canonical verdict
  regenerated; bad run preserved as `regression-gate-verdict-registryinvocation.json`.
- **GI-003** — `canvas-sync` BLOCKed only on `.claude/state/red-phase-presnap.json`, a
  harness state file; `changedFiles()` has no exclusion filter. Product-scope re-run:
  13/13 synchronized, 0 issues (`canvas-sync-check-productscope.md`).
- **GI-004** — `slo-check.js` **ignores `--out`** and always writes
  `specs/reviews/slo-verdict.json`. My poisoned probe overwrote the canonical artifact;
  detected and repaired (regenerated clean: pass, error_rate 0). Same family as the known
  "harness scripts ignore unknown flags" rule.
- **GI-006** — a reviewer left 17 untracked `backend/_probe_*` files (one 29 MB) mid-gate,
  making `ruff check .` report 41-92 errors. Evaluators 1 and 2 both caught that the
  pack's "lint clean" claim didn't reproduce and localised it correctly. Cleaned; all
  checks re-verified green (88 tests, ruff/mypy clean); product tree pristine.

## Also note

- `docs/CODEBASE.md` renders but indexes **0 files / 0 edges / 0 concepts** — the code
  graph has never been built against the now-existing source. Run `/code-map` so the human
  homepage isn't vacuous.
- Docker Desktop still not installed; `verification.mode` stays `local`. E15-S2-AC1 is in
  group B and remains unverifiable. Related: `/health` reports `status:"ok"` while
  `database:"unconfigured"`, so "all three healthy" will be **vacuous** until E1-S1
  registers a real probe.
- Session 4 open item 2 (E1-S2 modifying E1-S1's policy router) is RESOLVED by
  `specs/design/amendments/group-a-gate-remediation.md` with the design receipt
  re-recorded. Design defects 2 and 4-6 remain deliberately open, each deferred to the
  group that reaches it.

## next_action

Return group A to the generator for the four new BLOCKs. Fix 1+2 together (one change
across `middleware.py` + `platform/routes.py`) and fold in the `sanitise_context`
int/bool/key gap — all of it is outbound-channel sanitisation in group A's own owned
files. Fix 3 is one line. Fix 4 is frontend, cheap now and free of consumers.

**Three items need a HUMAN SPEC DECISION first**, because `/metrics` has **no acceptance
criterion** and `api-contracts.md` is frozen and authoritative:
- (a) may `/metrics` require auth, or must it stay public for scraping?
- (b) add an AC for a duration metric so `slo.p95_ms` is measurable at all?
- (c) add an AC for log-input sanitisation (`X-Request-ID` / raw path), which redaction's
  registration-based design cannot cover?

Then re-run `/gate --group A`. **Do NOT build group B on this substrate** — every later
story inherits the logging, error-envelope and metrics surfaces.

---

# Session 5 block — paste into `claude-progress.txt` above `=== Session 0 ===`

```
=== Session 5 ===
date: 2026-09-14T12:20:00.000Z
mode: /gate --group A (round 2, on-demand pre-merge)
groups_completed: []
groups_remaining: [A (GATE = BLOCK), B, C, D, E, F, G, H, I, J, K, L, M]
current_group: A (gated, not merged)
current_stories: [E15-S1, E9-S1, E11-S1]
sprint_contract: sprint-contracts/A.json (frozen, untouched)
last_commit: 9112495 "fix: complete the frozen error envelope, sanitise context, ship /health and /metrics"
features_passing: 12 / 107 (last_evaluated refreshed by evaluator 1; no status field changed)
coverage: backend 88 tests pass, frontend 18 tests pass, ruff/mypy/eslint/tsc clean
learned_rules: 0
blocked_stories: none

GATE VERDICT: BLOCK. See .claude/state/handoff/gate-group-A.md for the full
record, and specs/reviews/reverify-votes.json for the vote trail.

All five prior BLOCKs (CR-001/002/003, SEC-001/002) are genuinely CLOSED,
verified by execution. The frozen contract passes: QA-VM-003/004/005 live in
3/3 evaluator instances, all 12 story ACs pass.

But the two remediation commits introduced FOUR new BLOCKs:
  1. /metrics Prometheus exposition INJECTION — one unauthenticated GET forges
     counters and flips this project's own SLO sensor to 99.9% error rate
     (budget 1%). Also works in reverse to mask a real outage.
  2. /metrics unbounded cardinality — process-global Counter keyed on the raw
     path, never evicted: 60k paths from one connection = +28.2 MB retained.
  3. errors.py:107 discards HTTPException.headers — 405 loses Allow, 401 loses
     WWW-Authenticate (RFC 9110). One-line fix.
  4. frontend money.ts:78 quadratic separator regex — 9 bytes freezes the thread
     for >100 s. Latent (no frontend entry point yet).

Axes: security BLOCK (unanimous 3/3), functional FAIL (2/3), code-review BLOCK
(out-of-vote, sufficient alone). Task lifecycle left `active`;
finalize-task-evidence.js correctly refused completion.

HARNESS DEFECT worth remembering: security-scan.js reported a clean pass having
scanned ZERO files (`--staged` with an empty index → no SAST targets, self-reports
ran:true, no skip warning; and runDeps() only looks for package.json in the repo
ROOT so npm audit never ran against frontend/). Always pass explicit --files.
Also: no dependency lockfile is tracked at all (.gitignore:48-49).

next_action: Return group A to the generator for the four new BLOCKs (fix 1+2
  together, plus the sanitise_context int/bool/key gap). THREE SPEC DECISIONS
  NEEDED FIRST because /metrics has no AC and api-contracts.md is frozen:
  (a) may /metrics require auth? (b) add an AC for a duration metric so
  slo.p95_ms is measurable? (c) add an AC for log-input sanitisation?
  Then re-run /gate --group A. Do NOT build group B on this substrate.
```
