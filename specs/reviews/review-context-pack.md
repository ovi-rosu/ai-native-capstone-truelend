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
