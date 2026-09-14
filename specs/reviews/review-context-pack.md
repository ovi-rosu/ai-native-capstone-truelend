# Review Context Pack — /gate --group A (round 4)

- **Generated:** 2026-09-14 (round 4)
- **Group:** A · **Stories:** E15-S1, E9-S1, E11-S1, E15-S4
- **Range:** `14e9487..f3c25eb` (full group-A diff) — remediation since round 3 is `ba457bf..f3c25eb`
- **Sprint contract:** `sprint-contracts/A.json` (frozen; all 13 contract hashes re-verified byte-identical this round)
- **Security trigger:** **FIRES** — ASGI middleware, API error envelope/PII redaction, an unauthenticated `/metrics` exposition endpoint, config/settings.
- **Re-verification:** 3 instances each of evaluator and security-reviewer (2-of-3 majority per axis), 1 code-reviewer outside the vote.
- **Isolation (GI-005 fix):** every instance runs in **its own git worktree** this round. Round 3 ran them in one shared tree and 3 of 7 agents observed a sibling's live `# MUTANT` edit; no instance could vouch for another's in-tree measurements.

## What round 4 must decide

Round 3 was **BLOCK** on exactly one finding, **CR-301** (unbounded `method` label). Two commits then landed:

| Commit | Claim |
|---|---|
| `ab0fd6e` | bound the method label (CR-301), protect the escaping with a direct test (CR-303/V-0), make `format()` grouping linear (CR-304/B-4) |
| `f3c25eb` | stop the metrics scrape diluting its own error rate (SEC3-003, **partially** — self-observation only) |

The question for this round: **are those three claims true, and did they introduce anything new?**

`ab0fd6e` is not a 3-line change. It restructured request accounting: the RED counter moved
out of `_stamping_send` (at `http.response.start`) into a new single-entry-point
`record_request()` called from `_observe()` after the app returns, with the status carried
across in a new mutable `seen: list[int]` and **defaulting to 500** when the app raised
before sending a response start. That is a behaviour change to the SLO signal on both the
success and the failure path, and it silently also changes CR-314. Review it as new code,
not as a bounded fix.

## Acceptance criteria in scope

Authoritative sources: `specs/stories/story-traces.json` (`.acs`) and the embedded
`acceptance_criteria` in `specs/stories/stories.json`. Story markdown for the four stories
is in `specs/stories/{E15-S1,E9-S1,E11-S1,E15-S4}.md`.

Frozen API checks (the entire machine-checkable contract for group A — three `GET /health`
calls, deliberately narrow; two round-3 evaluator instances noted it is too narrow to carry
a merge decision alone):

- **QA-VM-003** `GET /health` → 200 with `X-Request-ID: req-abc`; 100% of log lines emitted while serving parse as JSON and carry `request_id == req-abc`
- **QA-VM-004** `GET /health` → 200 with no inbound id; every request-scoped line carries the same generated non-empty `request_id`, echoed on the response
- **QA-VM-005** `GET /health` → 200 JSON body, measured response time < 1 s

## Deterministic results at HEAD (this round, re-run)

| Check | Result |
|---|---|
| `backend: uv run pytest -q` | **108 passed** (round 3: 104) |
| `frontend: npm test` | **20 passed** (round 3: 18) |
| `backend: ruff check .` | All checks passed |
| `backend: mypy src/` | Success, no issues, 12 source files |
| `frontend: npm run lint` (eslint) | clean |
| `frontend: npm run typecheck` (tsc --noEmit) | clean |
| `contract-freeze` hashes | 13/13 byte-identical to the frozen receipt |

### Registry sweep — `run-gate-checks.js --lane gate --files <14 prod files>`

`6 passed, 3 blocked, 0 warn, 0 skipped`. **All three BLOCKs were independently
re-verified this round and are harness artifacts, not product defects:**

- `canvas-sync` — BLOCK only on `.claude/state/red-phase-presnap.json` and
  `specs/reviews/local-regression-gate-verdict.json`; the script has no harness-state
  exclusion (GI-003). Re-run scoped to the 14 production source files:
  **0 issues, 14/14 synchronized** (`specs/reviews/canvas-sync-check-productscope.md`).
- `ownership-check` — `unowned: ["backend/src/__init__.py"]`, one 0-byte package marker
  named *exactly* by a ratified waiver (`approved_by: ovi-rosu`, not expired;
  `validate-sensor-waivers.js` → **pass**). `run-gate-checks.js` has no waiver-application
  path (GI-006), so it will keep reporting blocked.
- `regression-suite-full` — the registry passes only `--replay`, never `--exclude-group`,
  so it grades the unbuilt groups B–M as prior baselines (GI-002). Re-run with B–M
  excluded: **regression-gate: pass** (`specs/reviews/local-regression-gate-verdict.json`).

`evidence-integrity`, `observability-gate`, `perf-smell`, `canvas-semantic`,
`sensor-waivers`, `dead-path` all pass. Note `evidence-integrity` passes with
`applicable:false` — honest but **vacuous**; no sprint contract declares a Playwright
check, so do not read it as browser-backed verification (GI-007).

### Computational security scan — UNSCANNED TIERS, NOT PASSED

`security-scan.js --files <13 prod files>` (explicit `--files`, per GI-001) →
`no findings at or above "high"`, but **three of four tiers did not run**:

- **gitleaks (secrets) — UNSCANNED**, not installed
- **semgrep (SAST) — UNSCANNED**, not installed
- **pip-audit (Python CVE) — UNSCANNED**, not installed
- `npm audit` run explicitly against `frontend/` (the scanner's `runDeps()` only probes the
  repo root, GI-001): **1 critical + 1 high + 3 moderate, all devDependency-only** —
  `vitest`/`@vitest/mocker`/`vite`/`vite-node`/`esbuild`. `prod: 5` dependencies, none
  affected. Not blocking; absent from any production image.

The three inferential security instances are therefore **the only real coverage** for the
injection / authz / PII classes again this round.

## Carried-over open findings — confirm or refute, do not re-litigate from scratch

Round 3 left these open at WARN. State for each whether HEAD closes it, and flag any that
should now *escalate*:

| ID | File | Claim |
|---|---|---|
| **F-1 / V-1** (major) | `backend/src` | Redaction is **INERT** — zero `register_sensitive` call sites in production code. Live raw PAN + Aadhaar were logged from a request path and from `X-Request-ID`. `ba457bf` put the call sites in `specs/bundles/*.json` — the **specs**, not the code. E15-S1-AC1 passes only as a surrogate. Also: with values registered, dotted/underscored/slashed/NBSP/soft-hyphen/zero-width/fullwidth forms all still bypass; normalize-then-match is still required. |
| **SEC3-003** | `middleware.py` + `.claude/hooks/lib/prom-parse.js` | Unauthenticated volume dilution masks an SLO breach: `errorRate()` sums 5xx over lifetime counters that never reset, and `/metrics` is anonymous. A real 50% outage read 0.0100% and passed the 1% budget. `f3c25eb` excludes `/metrics` from its own counters — the **self-observation** component only. Any public route still dilutes. Does the residual still warrant WARN or more? |
| **CR-302 / F-3** | `platform/routes.py:78` | `_escape_label` passes raw CR, TAB, NUL, BEL, ESC, DEL; `_histogram_lines()` emitted 14 lines carrying a raw CR, contradicting E15-S4-AC2's own "no raw control character". Was unreachable *only* under httptools. **CR-301's fix was supposed to close this — verify it actually did.** |
| **CR-306** | `serializers.py:75` | `MoneyField`'s declared JSON-schema pattern is **unenforced**: `POST principal "12.3"` returns 200 `"12.30"` although the schema and `test_no_float_money.py:342` both call 1dp invalid. |
| **CR-307** | `errors.py:85` | `sanitise_context` drops values silently with no marker — over-long strings discarded not truncated; floats, `None`, lists, nested mappings vanish. A caller cannot distinguish "not set" from "removed", and `types/errors.py:20` records that E4-S4-AC2 reads `threshold_kind`/`configured_value` out of `context`. |
| **CR-308** | `errors.py:115` | `detail` bypasses the `_CREDENTIAL_URI` and length guards that `context` values get — a DB URI with inline `user:password` egresses verbatim. |
| **CR-309** | `platform/routes.py:57` | `_database_status` swallows the probe failure reason: bare `except Exception: return "down"`, no log. |
| **CR-310** | `config/logging.py:84` | Avoidable `# type: ignore[arg-type]`; CLAUDE.md requires static typing everywhere. Fix verified clean in round 3 (typing both as `Token[set[str] | None]`). |
| **CR-311** | `tests/unit/test_log_redaction.py:43` | Both AC2 "every logger has the filter" tests enumerate `logging.root.manager.loggerDict` — the same collection the installer just iterated — so a logger created after `configure_logging` is invisible to the assertion by construction. |
| **CR-312** | `tests/architecture/test_observability_contract.py:87` | `assert p95_bound == "+Inf" or float(p95_bound) <= 0.5` accepts the unbounded bucket, so it passes when p95 exceeds every declared bound — the opposite of its own comment. |
| **CR-313** | `tests/conftest.py:28` | Process-global metric state has no enforced test isolation; it holds only because every count-asserting test remembers `reset_request_counters()`. |
| **CR-305** | `config/logging.py:217` | Two of the three stated reasons for silencing `uvicorn.access` are false at HEAD (uvicorn emits the access line *inside* the wrapped `send`, so `request_id_var` is still bound). |
| **CR-314** | `middleware.py` | Counter incremented before `await send(message)`, so a response failing mid-send was still recorded as served. **`ab0fd6e` moved this — re-derive it rather than reusing the round-3 text.** |
| **CR-316** | `middleware.py:159` | `_observe` called on both the success and exception branches rather than once in a `finally`. Still true at HEAD. |
| **SEC3-011 / F-6** | `types/money.py` | `Money.multiply` leaks bare `decimal.Overflow` in 0.0 ms — settled as a **contract break** (500 instead of 422), not a DoS. `money.py` catches only `InvalidOperation`. |

**Settled — do not reopen:** B-4's cost is the regex, not `toFixed()` (round 2's refutation
timed a linear sink 1,260–7,000x cheaper). "E15-S1-AC2 passes by construction" is
*partially* refuted — the root-only mutant kills both AC2 tests, so "vacuous" overstated it.
B-1, B-3 closed. The method-label magnitude split was parser-dependent, not a contradiction.

## Reading list (do not read the build transcript or unrelated files)

- Diff: `git diff 14e9487..f3c25eb -- backend/src backend/tests frontend/src frontend/tests`
- Remediation only: `git diff ba457bf..f3c25eb -- backend/src backend/tests frontend/src frontend/tests`
- Touched production: the 14 files listed above, `backend/src/**`, `frontend/src/**`
- Contract: `sprint-contracts/A.json` · ACs: `specs/stories/story-traces.json`
- Design: `specs/design/program-design.md`, `specs/design/component-map.md`,
  `specs/design/amendments/e15-s4-observability-contract.md`,
  `specs/design/amendments/group-a-gate-remediation.md`
- Prior rounds: `.claude/state/handoff/gate-group-A.md`, `specs/reviews/reverify-votes.json`
