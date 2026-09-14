# Review Context Pack — /gate --group A (round 2)

/ **Gate lane:** on-demand pre-merge (`/gate`)
/ **Generated:** 2026-09-14 (session 5)

## 1. Request / scope

| Field | Value |
|---|---|
| Group | A |
| Stories | E15-S1 (platform logging + health), E9-S1 (Money value type), E11-S1 (delinquency bucket) |
| Sprint contract | `sprint-contracts/A.json` (FROZEN — do not edit) |
| Features | F001–F005, F009–F011, F070–F073 |
| Review range | `14e9487..HEAD` |
| HEAD | `9112495` |
| Base | `14e9487` (planning-artefacts commit, last commit with no product source) |
| Branch | `feat/harness-scaffold-and-planning` |

**This is a re-run, not a first pass.** A previous `/gate` reviewed `f4abd41` and
returned **BLOCK** on 5 findings (3 code-review, 2 security). Two remediation
commits then landed:

- `9558cc5` — "fix(security): bound the redaction pattern and make PII redaction request-scoped" (targets SEC-001, SEC-002 / CR-002)
- `9112495` — "fix: complete the frozen error envelope, sanitise context, ship /health and /metrics" (targets CR-001, SEC-003)

Every verdict file in `specs/reviews/` older than `9112495` describes the
**pre-fix** tree and is stale. They were committed *by* the fix commits, which is
why their mtimes look current. Do not treat them as the current verdict; they are
included below only as the list of claims to re-test.

## 2. Prior BLOCK findings to re-verify

Each must be independently re-tested against HEAD. Do not accept the commit
message as evidence.

| ID | Axis | Claim | File |
|---|---|---|---|
| CR-001 | code-review | Frozen non-2xx error envelope applied only to `AppError`; framework 401/403/404/409, 422 and unhandled 500 bypassed it | `backend/src/api/errors.py` |
| CR-002 | code-review | Registered PII leaks unredacted, with an empty `request_id`, when the exception carrying it escapes the `redact_values` scope | `backend/src/config/logging.py` |
| CR-003 | code-review | Per-line money-guard exemption silenced *every* float category, not just division | `backend/tests/architecture/test_no_float_money.py` |
| SEC-001 | security (high) | Catastrophic regex backtracking (ReDoS) in the PII redaction pattern — measured 199,326 ms at haystack length 40 | `backend/src/config/logging.py` |
| SEC-002 | security (high) | PII in an exception message bypasses redaction and is logged at ERROR | `backend/src/config/logging.py`, `backend/src/api/middleware.py` |

Open non-BLOCK findings carried forward (SEC-003…SEC-020) are in
`specs/reviews/security-verdict.json`; re-judge severity against HEAD rather than
re-deriving them from scratch.

## 3. Acceptance criteria in scope

From `sprint-contracts/A.json` — the frozen contract is **three `GET /health`
api_checks**. It is deliberately narrow: contracts referencing `/products` and
`POST /applications` were retargeted in session 3 because those endpoints belong
to groups B and E and group A could otherwise never pass.

| Check | Matrix | Assertion |
|---|---|---|
| QA-VM-003 | VM-003 | `GET /health` → 200 with header `X-Request-ID: req-abc`; 100% of log lines emitted while serving parse as JSON and each carries `request_id == req-abc` |
| QA-VM-004 | VM-004 | `GET /health` → 200 with no `X-Request-ID`; every request-scoped log line carries the same generated non-empty `request_id`, and the response echoes it |
| QA-VM-005 | VM-005 | `GET /health` → 200, JSON body, measured response time < 1 s |

Story ACs (`specs/stories/E15-S1.md`, `E9-S1.md`, `E11-S1.md`) remain the
authority for unit-level criteria; E15-S1-AC3/AC4 (JSON logs, correlated 500)
and E9-S1-AC1/AC2 (2dp quantization, zero float arithmetic) are the ones the
prior BLOCKs touched.

## 4. Changed files

### Production source (review these)
```
backend/src/__init__.py
backend/src/api/app.py                     # app factory; CorrelationIdMiddleware mounted outside ServerErrorMiddleware
backend/src/api/errors.py                  # CR-001 + SEC-003 fix: 4 handlers, sanitise_context()
backend/src/api/middleware.py              # SEC-002 fix: pure-ASGI, owns redaction scope lifetime
backend/src/api/platform/routes.py         # /health {status,database,version}; /metrics RED counters
backend/src/api/serializers.py
backend/src/config/delinquency.py
backend/src/config/logging.py              # SEC-001 fix: bounded separator run; register_sensitive()
backend/src/config/settings.py
backend/src/types/delinquency.py
backend/src/types/errors.py                # AppError carries error name + context mapping
backend/src/types/money.py
frontend/src/types/money.ts
frontend/src/ui/components/MoneyText.tsx
```

### Tests
```
backend/tests/conftest.py
backend/tests/architecture/test_no_float_money.py   # CR-003 fix + regression test
backend/tests/unit/test_bucket_ladder.py
backend/tests/unit/test_correlation_id.py
backend/tests/unit/test_error_envelope.py
backend/tests/unit/test_health_probe.py
backend/tests/unit/test_log_redaction.py
frontend/tests/unit/money.test.ts
```

### Config / non-source
```
frontend/package.json  frontend/tsconfig.json  frontend/vite.config.ts  frontend/eslint.config.js
specs/design/amendments/group-a-gate-remediation.md
specs/design/component-map.md   (1 line)
specs/stories/E1-S1.md          (group B story, Operations detail)
```

## 5. Deterministic results at HEAD (`9112495`)

All run fresh for this gate. **All green.**

| Check | Command | Result |
|---|---|---|
| Backend tests | `cd backend && uv run pytest -q` | **88 passed**, 2 warnings, 0.15 s |
| Backend lint | `uv run ruff check .` | All checks passed |
| Backend types | `uv run mypy src/` | Success: no issues in 12 source files |
| Frontend tests | `cd frontend && npm test` | **18 passed** (1 file) |
| Frontend lint | `npm run lint` | clean |
| Frontend types | `npm run typecheck` | clean |

Test count moved 73 → 88 across the two fix commits (new files
`test_correlation_id.py`, `test_error_envelope.py`, `test_health_probe.py`).

### Registry gate checks (`run-gate-checks.js --lane gate`)

`7 passed, 2 blocked, 0 warn, 0 skipped` → `specs/reviews/gate-checks.json`

Passing: canvas-semantic, ownership-check, evidence-integrity, observability-gate,
perf-smell, sensor-waivers, dead-path.

Two BLOCKs, both under orchestrator investigation as **invocation artefacts, not
product defects** — reviewers should not spend effort on them:

1. **canvas-sync** — sole missing entry is `.claude/state/red-phase-presnap.json`,
   a harness state file in the working tree. No product file is unsynced.
2. **regression-suite-full** — 54 findings, all `expected status N, got 0`,
   across contracts `A.json`…`M.json`. `discoverPriorContracts()` treats *every*
   file in `sprint-contracts/` as a prior baseline unless `--exclude-group` is
   passed; the registry passes none. Group A is the **first** group
   (`groups_completed: []`), so groups B–M describe unbuilt endpoints, and `got 0`
   means no server was listening. The sibling
   `regression-gate-verdict-nobaseline.json` records the semantically correct
   reading: *"sprint-contracts/ exists but has no prior contracts to re-validate"*.

### Orchestrator measurement of SEC-001 at HEAD

Direct timing of `backend/src/config/logging.py::_scrub`, same probe shape the
prior gate used to confirm the BLOCK (value `'-'*n + 'Z'` against an all-hyphen
haystack):

| value length | 13 | 17 | 21 | 25 | 27 | 31 | 41 | 61 |
|---|---|---|---|---|---|---|---|---|
| pre-fix (prior gate) | 0.58 ms @16 | — | 7.74 ms @20 | 100.66 ms @24 | 314.66 ms @26 | — | 199,326 ms @40 | — |
| **at HEAD** | 0.037 | 0.027 | 0.025 | 0.026 | 0.026 | 0.028 | 0.034 | 0.044 |

Growth is flat/linear, not exponential. Two further adversarial shapes
(non-separator value against a separator-heavy 200-char haystack; value of
alternating `A-` against a 200-char all-dash haystack) stay under 0.2 ms.
Redaction still fires for spaced PAN, lowercase PAN, dashed document ids and
grouped Aadhaar. One deliberate behaviour narrowing: a gap of **5+** separators
between characters no longer matches (`_SEPARATOR_RUN = [ \t\-]{0,4}`).

Treat SEC-001 as **independently confirmed fixed**. Re-test if you can find a
different backtracking shape; do not re-litigate this one from the description.

## 6. Risk triggers → security review IS required

The diff crosses these boundaries, so `security-reviewer` and
`security-scan.js` both run, and the 3-instance bounded re-verification applies:

- **User input handling** — `X-Request-ID` read from an inbound header and
  reflected into the response and every log line (`middleware.py`).
- **PII / data handling** — the entire PII redaction subsystem (`logging.py`):
  PAN, Aadhaar, salary-document content.
- **API routes / middleware** — `api/app.py`, `api/middleware.py`,
  `api/platform/routes.py`, `api/errors.py`.
- **Outbound error channel** — `AppError.context` and `detail` are serialised to
  clients (`errors.py::sanitise_context`); prior SEC-003 said this was unfiltered.
- **Dependency manifest** — `frontend/package.json` is new; prior SEC-010/SEC-011
  flagged advisories and a missing committed lockfile.
- **Observability surface** — `GET /metrics` is newly exposed and unauthenticated.

`security_review: required` (not `skipped_no_boundary`).

## 7. Architecture constraints

`Types → Config → Repository → Service → API → UI`, one-way only
(`.claude/architecture.md`). Group A has no Repository or Service layer.

Relevant invariants:
- No float in any money path (E9-S1-AC2) — enforced by the AST guard in
  `backend/tests/architecture/test_no_float_money.py`.
- Errors are typed in Types and mapped **once** at the API boundary.
- `api/errors.py` importing `src.config.logging.scrub_text` is API → Config,
  which is allowed.
- File ownership is `specs/design/component-map.md`; ownership-check passes.

## 8. Reviewer instructions

Read **only**: this pack, the diff (`git diff 14e9487..HEAD -- backend frontend`),
and the files it touches. Do **not** read the build transcript, the prior verdict
files as authority, `.claude/state/uvicorn.log` (36 MB), or unrelated repo source.

Evaluator instances: `verification.mode` is `local` (Docker Desktop is not
installed; `docker-compose.yml` does not exist until E15-S2 in group B). Boot with
`cd backend && uv run uvicorn src.api.app:app --port <8000|8001|8002>` and use a
distinct port per instance. Serve `src.api.app:app` (or `create_app()`) — never
`build_fastapi_app()`, which omits the correlation middleware.
