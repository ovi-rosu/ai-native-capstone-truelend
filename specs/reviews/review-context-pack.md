# Review Context Pack — /auto group A

Commit under review: `e147f7e` on `feat/harness-scaffold-and-planning`
Base: `14e9487`
Range: `14e9487..e147f7e` (36 files, +1910/-12)

## Stories delivered

| Story | Title | Layer | ACs |
|---|---|---|---|
| E15-S1 | Structured JSON logging, correlation id propagation, PII redaction, health endpoint | Config | E15-S1-AC1..AC5 |
| E9-S1 | Money value type with fixed-point decimal arithmetic | Types | E9-S1-AC1..AC3 |
| E11-S1 | Delinquency bucket ladder over days past due | Types | E11-S1-AC1..AC4 |

Execution contracts: `specs/bundles/E15-S1.json`, `specs/bundles/E9-S1.json`, `specs/bundles/E11-S1.json`.

## Changed production files

backend/src/api/app.py
backend/src/api/errors.py
backend/src/api/middleware.py
backend/src/api/platform/routes.py
backend/src/api/serializers.py
backend/src/config/delinquency.py
backend/src/config/logging.py
backend/src/config/settings.py
backend/src/types/delinquency.py
backend/src/types/errors.py
backend/src/types/money.py
frontend/src/types/money.ts
frontend/src/ui/components/MoneyText.tsx

## Changed test files

backend/tests/architecture/test_no_float_money.py
backend/tests/conftest.py
backend/tests/unit/test_bucket_ladder.py
backend/tests/unit/test_log_redaction.py
frontend/tests/unit/money.test.ts

## Changed config / tooling

frontend/package.json, frontend/tsconfig.json, frontend/vite.config.ts, frontend/eslint.config.js

## Deterministic evidence (re-run by the orchestrator, not self-reported)

| Command | Result |
|---|---|
| `cd backend && uv run pytest -q` | exit 0 — 42 passed |
| `cd backend && uv run mypy src/` | exit 0 — no issues, 12 source files |
| `cd backend && uv run ruff check .` | exit 0 — all checks passed |
| `cd frontend && npm test` | exit 0 — 11 passed |
| `node .claude/scripts/run-gate-checks.js --files <range>` | exit 0 — 25 passed, 0 blocked |
| `validate-generation-contract.js --mode implementable --story <id>` | exit 0 for all 3 group A stories |
| `bundle-check.js --mode implementable --story <id>` | exit 0 for all 3 group A stories |

## Security-relevant surface in this diff

- `backend/src/config/logging.py` — PII redaction in structured log output. A redaction miss leaks PII to logs.
- `backend/src/api/middleware.py` — correlation-id propagation; accepts a caller-supplied `X-Request-ID` header and echoes it in the response. Untrusted input reflected into logs and response headers (log injection / header injection / unbounded length).
- `backend/src/api/errors.py`, `backend/src/types/errors.py` — error surface; check for internal detail or stack-trace leakage in responses.
- `backend/src/api/platform/routes.py` — `GET /health`; check it does not disclose config, versions, or secrets.
- `backend/src/config/settings.py` — configuration loading; check for hardcoded secrets or insecure defaults.
- `backend/src/api/serializers.py` — the single money wire serializer (architecture decision D-G).

No authn/authz, no persistence, no migrations, no outbound network calls, no file uploads, and no payment execution in this diff.

## Architecture constraints the diff must honor

- Strict layered architecture, one-way dependencies: Types -> Config -> Repository -> Service -> API -> UI (`.claude/architecture.md`).
- Decision D-G: money is `NUMERIC(14,2)` in Postgres, `Decimal` in Python, a **quoted 2dp string** in JSON, parsed with a decimal library in TypeScript. No float touches a monetary value at any hop. No integer minor units. The Pydantic serializer exists in exactly one module.
- Decision D-J: the frontend money value is held as a decimal value and never a float; a static check must report 0 float arithmetic operations in that module.
- Functions <= 30 lines, files <= 300 lines, static typing everywhere, zero `any`.
- No pass-through modules: where a story has no business rule, the router uses the repository contract directly.

## Frozen, out-of-scope paths

`specs/design/architecture.md`, `specs/design/api-contracts.md`, `specs/design/data-models.md`, `specs/test_artefacts/**`, `sprint-contracts/**`, `project-manifest.json`. Do not propose edits to these; report a conflict instead.

## Sprint contract (frozen) runtime criteria

`sprint-contracts/A.json` — three api_checks, all `GET /health` -> 200:
- QA-VM-003 / VM-003: sent with `X-Request-ID: req-abc`; 100% of log lines emitted while serving parse as JSON and each carries `request_id == req-abc`.
- QA-VM-004 / VM-004: sent with no `X-Request-ID`; every request-scoped log line carries the same generated non-empty `request_id` and the response echoes that id.
- QA-VM-005 / VM-005: JSON body, measured response time under 1 second.

---

# /gate --group A addendum (on-demand pre-merge entry point)

Re-scoped for `/gate`. Supersedes the range above.

- Range under review: `14e9487..d0b5c94` (HEAD) plus the **uncommitted working tree**.
- Commits: `e147f7e` (implement group A), `d0b5c94` (repair group A contract, remove unratified waivers).
- Branch: `feat/harness-scaffold-and-planning`.

## Runtime target (live during this gate)

`uv run uvicorn src.api.app:app --host 127.0.0.1 --port 8000` from `backend/`.
`GET http://127.0.0.1:8000/health` -> 200 `{"status":"ok"}`, echoes `x-request-id`.
Server log: `.claude/state/uvicorn.log`. `project-manifest.json#verification.mode` is
`local` in the working tree (was `docker`); Docker Desktop is not installed.

## Deterministic gate-lane result (run at gate time, not self-reported)

`node .claude/scripts/run-gate-checks.js --lane gate --files <13 changed src files>`
-> **exit 1: 5 passed, 4 blocked, 0 warn, 0 skipped**

| Check | Verdict | Detail |
|---|---|---|
| canvas-sync | BLOCK | `.claude/state/task-envelope.json` missing from Governs + Operations; `project-manifest.json` missing from Operations. Both are **uncommitted working-tree** edits, not group A product code. |
| ownership-check | BLOCK | 14 checked, 1 unowned: `backend/src/__init__.py` has no owning story row in `specs/design/component-map.md`. |
| regression-suite-full | BLOCK | 54 findings, every one `expected status N, got 0`. Ran with no `--exclude-group`, so it regressed **all 13** sprint contracts A..M (including 12 groups whose endpoints do not exist yet) against a dead server. |
| evidence-integrity | BLOCK | Expected pre-evaluator: reads `specs/reviews/evaluator-evidence.json`, which does not exist yet. Re-run after the evaluator returns. |
| canvas-semantic, observability-gate, perf-smell, sensor-waivers, dead-path | ok | |

Separately: `node .claude/scripts/plan-seal.js check` -> **exit 1**, sealed artifacts changed:
`specs/design/reasons-canvas.md`, `specs/bundles/E11-S1.json`, `specs/bundles/E15-S1.json`,
`specs/bundles/E9-S1.json`. `contract-freeze.js --check` -> **hashes match** (pass).

## Uncommitted working-tree changes (review these too)

| File | Change | Note |
|---|---|---|
| `project-manifest.json` | `verification.mode` docker -> local, plus a `mode_note` key | **Outside** the task envelope's `allowed_paths` and listed as a frozen path in this pack. Also introduces a **duplicate `mode` key risk** — verify the JSON has exactly one `mode`. |
| `.claude/state/task-envelope.json` | `created_at`/`expires_at` rotated ~9h forward, integrity hash rebuilt | Envelope rotation resets the "evidence created after the envelope" window in `finalize-task-evidence.js`. `previous_envelope_hash` is still `null` and `amendments` is still `[]` despite two history files existing. |
| `.claude/state/phase-cost*.json` | telemetry | benign |

## Specific things to judge (do not assume the pack is right)

1. **AC "all log output is structured JSON"** — uvicorn's own lines (`INFO: Application startup complete.`,
   `INFO: 127.0.0.1:... - "GET /health HTTP/1.1" 200 OK`) are plain text, not JSON, and carry no
   `request_id`. Only `truelend.access` emits JSON. Decide whether QA-VM-003's "100% of log lines
   emitted while serving parse as JSON" is met.
2. `backend/src/api/middleware.py` reflects a caller-supplied `X-Request-ID` into logs and into a
   response header with no length cap, charset allow-list, or CRLF filtering.
3. `backend/src/config/logging.py` PII redaction completeness.
4. Layering: `Types -> Config -> Repository -> Service -> API -> UI`, one-way only.
5. Decision D-G / D-J: no float ever touches a monetary value, in Python or TypeScript.

---

# /gate re-entry addendum (gate-time facts, supersedes the block table above)

Re-run at gate time with the runtime target **live** (`uvicorn` on 127.0.0.1:8000,
`GET /health` -> 200 `{"status":"ok"}`, echoes `x-request-id: req-abc`).

## Resolved / re-scoped from the earlier abandoned run

| Earlier BLOCK | Gate-time finding |
|---|---|
| `project-manifest.json` duplicate `mode` key risk | **CLEARED.** `JSON.parse` succeeds; `verification.mode` appears exactly once inside `verification`. The 3 file-wide `"mode"` matches are in distinct objects. |
| `regression-suite-full` — 54 findings | **MISAPPLIED CHECK, not a product regression.** With the server live it is 50 findings, every one a 404 on an endpoint belonging to groups **B..M**, none of which is implemented. `features.json` has **zero** stories with `passes: true` in any group, and `/auto` section-6 step 2 states G15 is skipped "when `features.json` has no prior `passes: true` group". The registry entry (`.claude/config/gate-checks.json`) invokes `regression-gate.js --replay` with a static arg list and no `--exclude-group`, so it cannot know which groups are prior. Group A is the first landed group -> the prior-contract regression set is empty. |
| `evidence-integrity` | Genuinely pre-evaluator. Re-run after the evaluator writes `specs/reviews/evaluator-evidence.json`. |

## Still-open BLOCK candidates (judge these)

1. **`project-manifest.json` is modified in the working tree.** It is outside
   `.claude/state/task-envelope.json#allowed_paths` and is listed as a frozen path
   in this pack. The change itself (`verification.mode` docker -> local + a `mode_note`)
   is defensible (no docker-compose.yml until E15-S2; Docker Desktop absent), but it was
   made without an envelope amendment.
2. **`.claude/state/task-envelope.json` was rotated, not amended.** `created_at`/`expires_at`
   moved ~9h forward and `integrity.hash` was rebuilt, but `previous_envelope_hash` is still
   `null` and `amendments` is still `[]` — even though two files exist under
   `.claude/state/task-envelope-history/`, one of them named for the superseded hash
   `4034db...`. The chain is therefore unauditable, and moving `created_at` forward resets the
   "evidence must be created after the envelope" window that `finalize-task-evidence.js` enforces.
3. **`ownership-check`: `backend/src/__init__.py` has no owning story** in
   `specs/design/component-map.md` (14 files checked, 1 unowned).
4. **`canvas-sync`**: `.claude/state/task-envelope.json` absent from Canvas Governs+Operations,
   `project-manifest.json` absent from Operations. Both are the working-tree edits above, not
   group A product code — so this BLOCK is downstream of finding 1/2, not an independent defect.
5. **`plan-seal.js check` exits 1** — sealed artifacts changed:
   `specs/design/reasons-canvas.md`, `specs/bundles/E{9,11,15}-S1.json`.
   (`contract-freeze.js --check` passes — sprint-contract hashes match.)

## Reviewer scope

Review the committed range `14e9487..d0b5c94` **plus** the uncommitted working tree.
Production source is the 13 backend/frontend files listed earlier in this pack.
Do not read the builder transcript or unrelated repo files.
