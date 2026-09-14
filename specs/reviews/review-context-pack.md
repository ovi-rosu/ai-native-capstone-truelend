# Review Context Pack — /gate --group A (round 3)

**Gate lane:** on-demand pre-merge (`/gate`)
**Generated:** 2026-09-14 (session 6)

## 1. Request / scope

| Field | Value |
|---|---|
| Group | A |
| Stories | E15-S1 (platform logging + health), E9-S1 (Money value type), E11-S1 (delinquency bucket), **E15-S4 (NEW — duration histogram + hostile-input hardening)** |
| Sprint contract | `sprint-contracts/A.json` (re-frozen 2026-09-14T12:43:20Z after E15-S4 was appended; all 13 contract hashes verified against `contract-freeze.json`) |
| Features | F001–F005, F009–F011, F070–F073, **F108, F109** |
| Review range | `14e9487..HEAD` |
| HEAD | `ba457bf` |
| Base | `14e9487` (last commit with no product source) |
| Branch | `feat/harness-scaffold-and-planning` |

**This is round 3.** Round 2 returned **BLOCK** (`.claude/state/handoff/gate-group-A.md`):
security BLOCK 3/3, functional FAIL 2/3, code-review BLOCK. It confirmed the five
*original* BLOCKs (CR-001/002/003, SEC-001/002) genuinely closed, but found **four new
BLOCKs introduced by the remediation commits**.

Six commits landed after round 2's HEAD (`9112495`):

| Commit | Claim |
|---|---|
| `f1367f5` | fix(security): close the /metrics injection and cardinality holes I introduced |
| `3c15089` | docs: record the spec-render landmine / AC-renumbering decision |
| `736d315` | feat(spec): add E15-S4 carrying the two approved observability criteria |
| `004138f` | feat(E15-S4): add the request-duration histogram so the runtime SLO is measurable |
| `a807678` | fix(E9-S1): give MoneyField a JSON-schema hook so money is documented |
| `f5a5ace` | fix(security): scrub numeric and key-borne PII from the error context (SEC-103) |
| `ba457bf` | fix(spec): put the redaction call sites in the Operations that introduce PII |

**Every verdict file in `specs/reviews/` predates these commits and is stale.** They were
committed *by* the fix commits, so their mtimes look current. They are the list of claims to
re-test, not the current verdict.

## 2. Round-2 BLOCK findings — re-verify each by EXECUTION, not by reading the commit message

| ID | Claim | File | Gate-lead pre-read (confirm or refute independently) |
|---|---|---|---|
| **B-1** | `/metrics` Prometheus exposition **injection** — percent-decoded `scope["path"]` f-strung into a label with no escaping; one unauthenticated GET forged a series and drove this project's own `slo-check.js` to 99.90% error rate against a 1% budget | `backend/src/api/platform/routes.py` | `_escape_label` now escapes backslash, double-quote and newline; the route label is the **matched route template**, not the raw path. **Verify:** is carriage return (and other control chars) still unescaped? Is `scope["method"]` attacker-controlled? |
| **B-2** | `/metrics` **unbounded cardinality** → unauthenticated memory DoS; 60,000 label values / +28.2 MB from one keep-alive connection | `backend/src/api/middleware.py` | `route_label()` returns the matched template or the single `<unmatched>` bucket. **Verify by measurement**, and check the NEW `_duration_counts` / `_duration_totals` dicts inherit the same bound — and whether `method` re-opens it |
| **B-3** | `errors.py` discarded `HTTPException.headers` — 405 lost `Allow`, 401 lost `WWW-Authenticate` (RFC 9110 15.5.2/15.5.6) | `backend/src/api/errors.py` | Appears fixed: `headers=exc.headers` (line 136), `headers` param plumbed through `_envelope` (109, 122). **Verify by request**, incl. the 500/422/404 paths |
| **B-4** | `frontend/src/types/money.ts:78` thousands-separator lookahead is **quadratic**: 8-byte `"1e100000"` = 4,152 ms; 9-byte `"1e1000000"` did not finish in 100 s | `frontend/src/types/money.ts` | **UNTOUCHED by every remediation commit — the regex is still verbatim at line 78.** Re-measure and decide severity: is a caller-reachable path bounded upstream (Money constructor / `toWire`)? Round 2 noted evaluator 3 REFUTED this by timing the wrong sink (`toFixed`); security 3 isolated the cost to the regex |

## 3. Round-2 WARNs to re-judge at HEAD (not exhaustive — see `specs/reviews/security-verdict.json`)

- **SEC-003 partial:** `sanitise_context` skipped `scrub_text` for int/bool values and for mapping **KEYS** — a 12-digit Aadhaar egressed whole; absolute filesystem paths egressed. `f5a5ace` claims this. **Re-test.**
- **Redaction bypass by formatting** is far wider than the 5-dash case: dot, underscore, slash, NBSP, soft hyphen, zero-width, homoglyph, fullwidth and NFKC forms all defeat it. Real fix is normalize-then-match. Harmless **only** while there are zero `register_sensitive` call sites; `ba457bf` claims to add call sites to the spec Operations — **if call sites now exist in code, severity rises.**
- `X-Request-ID` unvalidated/unbounded: 5 MB accepted, reflected and logged verbatim; a PAN-format id was logged unredacted.
- Host-header-reflected **open redirect** (`Location: http://evil.example/health`); `/docs` and `/openapi.json` public; no security response headers; `HEAD /health` -> 405.
- PII retained for the process lifetime as `lru_cache` keys on `_redaction_pattern`.
- `Money.multiply` lets bare `decimal.Overflow` escape (`money.py` catches only `InvalidOperation`). Round-2 timing **disputed** (eval-3 9,708 ms vs sec-3 109 ms) — unresolved.
- `/metrics` still has **no authentication**. Deliberate and documented: E15-S4 Scope Out says auth needs an `api-contracts.md` amendment and an auth layer that arrives with E1-S1 (group B). Judge whether the deferral is acceptable, not whether auth is absent.
- Both AC2 "every logger has the filter" tests pass **by construction** — they enumerate the same `loggerDict` the implementation just iterated.
- `uvicorn.access` is disabled and both justifications in `logging.py` were empirically disproven; AC3 passes on its merits but the comment misrepresents why.

## 4. Acceptance criteria in scope

`sprint-contracts/A.json` — three frozen `GET /health` api_checks (deliberately narrow;
`/products` and `POST /applications` were retargeted in session 3 because they belong to
groups B and E). E15-S4's two criteria carry **no `api` or `e2e` layer**, so they add no
frozen check.

| Check | Assertion |
|---|---|
| QA-VM-003 | `GET /health` -> 200 with `X-Request-ID: req-abc`; 100% of log lines emitted while serving parse as JSON and each carries `request_id == req-abc` |
| QA-VM-004 | `GET /health` -> 200 with no `X-Request-ID`; every request-scoped log line carries the same generated non-empty `request_id`, echoed on the response |
| QA-VM-005 | `GET /health` -> 200, JSON body, measured response time < 1 s |

Story ACs remain the authority for unit-level criteria: `specs/stories/E15-S1.md`,
`E9-S1.md`, `E11-S1.md`, `E15-S4.md`. **E15-S4-AC1** (histogram, p95 computable) and
**E15-S4-AC2** (one line per record, no raw control character, no injected series) are new
and have never been evaluated.

## 5. Changed production source (review these)

```
backend/src/__init__.py          backend/src/api/serializers.py
backend/src/api/app.py           backend/src/config/delinquency.py
backend/src/api/errors.py        backend/src/config/logging.py
backend/src/api/middleware.py    backend/src/config/settings.py
backend/src/api/platform/routes.py
backend/src/types/delinquency.py backend/src/types/errors.py
backend/src/types/money.py
frontend/src/types/money.ts      frontend/src/ui/components/MoneyText.tsx
```

Tests added since round 2: `backend/tests/architecture/test_observability_contract.py` (new,
E15-S4), plus additions to `test_no_float_money.py`, `test_error_envelope.py`,
`test_health_probe.py`, `test_log_redaction.py`.

## 6. Deterministic verification at HEAD (run by the gate lead this round)

| Check | Result |
|---|---|
| `backend: uv run pytest -q` | **104 passed** (was 88) |
| `backend: uv run ruff check .` | clean |
| `backend: uv run mypy src/` | clean, 12 source files |
| `frontend: npm test` | **18 passed** |
| `frontend: npm run lint` | clean |
| `frontend: npm run typecheck` | clean |
| `sprint-contracts/*.json` sha256 vs `contract-freeze.json` | **13/13 match** — no contract drift |

### Gate-check registry (`run-gate-checks.js --lane gate`): 6 pass, 3 BLOCK

| Check | Raw | Gate-lead classification |
|---|---|---|
| canvas-semantic, evidence-integrity, observability-gate, perf-smell, sensor-waivers, dead-path | ok | — |
| `canvas-sync` | BLOCK | **GI-003 harness defect, reproduced.** Blocks *only* on `.claude/state/red-phase-presnap.json`, a harness state file; `changedFiles()` has no exclusion filter. Product-scope re-run: 13 files, 0 missing, synchronized (`canvas-sync-check-productscope.md`) |
| `ownership-check` | BLOCK | **WAIVED, not open.** `backend/src/__init__.py` (0 bytes, package marker) has no owning story in `component-map.md`, but `specs/reviews/sensor-waivers.json` carries a ratified `ownership-check` waiver naming this exact file (approved_by `ovi-rosu`, expires 2026-10-15). The waiver itself records that `run-gate-checks.js` has **no waiver-application path** — waivers apply at pre-commit only — so the runner will always re-report this as blocked. Waiver set re-validated this round: `sensor-waivers: pass`, 5 waivers, none expired |
| `regression-suite-full` | BLOCK | **GI-002 harness defect, reproduced.** Registry passes only `--replay`, never `--exclude-group`, so `discoverPriorContracts()` grades the **unbuilt** groups B–M as prior baselines and reports 404s. Re-run with B–M excluded (no group is completed, so the true baseline is empty): **`regression-gate: pass`** |

### Computational security scan (gap G3)

Run with **explicit `--files`** per round 2's GI-001 (`--all --staged --boundary-only` scanned
ZERO files and self-reported a clean pass). Result: `no findings at or above "high"`, but
**gitleaks, semgrep and pip-audit are all unprovisioned and loudly skipped** — treat the
SAST and secrets tiers as **unscanned**, not as passed.

Dependency tier, now genuinely auditable because `.gitignore` was fixed to track lockfiles
(`frontend/package-lock.json` and `backend/uv.lock` are both committed as of round 3 —
closing a round-2 WARN): `npm audit` reports **1 critical (vitest) + 1 high (vite) + 3
moderate**, all `devDependency`-only and absent from any production image.

## 7. Risk triggers -> security review REQUIRED

The changed set crosses these boundaries, so `security-reviewer` and the computational scan
both run:

- **user input handling** — `X-Request-ID` header, request paths, `sanitise_context`
- **API routes / middleware** — `api/middleware.py`, `api/platform/routes.py`, `api/errors.py`
- **secrets / PII** — `config/logging.py` redaction, error-context egress
- **network-adjacent** — host-header reflection, public `/docs` and `/metrics`

## 8. Reviewer instructions

Read **this pack, the diff, and the files it touches** — not the build transcript, and not the
prior verdict files as authority. Round 2's own record shows why: a single instance filed
B-4 as *refuted* by timing the wrong sink. Re-derive each verdict by execution.
