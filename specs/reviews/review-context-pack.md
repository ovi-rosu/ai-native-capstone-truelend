# Review Context Pack — /gate --group A (fresh re-run)

**This pack supersedes the 2026-09-14T09:37 pack.** That pack described commit
`e147f7e`. Every BLOCK it produced has since been fixed in three commits, and the
stored verdicts (`code-review-verdict.json`, `security-verdict.json`,
`evaluator-report.md`, `quality-card.json`, `.claude/state/gate-receipt.json`) all
predate those fixes and read `pass: false`. They are snapshots of a superseded tree —
do **not** read a verdict from them. Review the tree at HEAD.

## Request

| Field | Value |
|---|---|
| Request | `/gate --group A` — fresh pre-merge verdict for story group A |
| Branch | `feat/harness-scaffold-and-planning` |
| HEAD | `f4abd41` "fix: close CR-003 and align the error envelope with the frozen contract" |
| Base | `14e9487` (scaffold + approved planning artefacts; no source existed) |
| Range | `14e9487..HEAD` — production/test scope: 24 files, +1835/-0 net of the base |
| Sprint contract | `sprint-contracts/A.json` (frozen — 3 api_checks, all `GET /health`) |
| Stories | E15-S1, E9-S1, E11-S1 |

## Stories and acceptance criteria

| Story | Title | Layer | ACs |
|---|---|---|---|
| E15-S1 | Structured JSON logging, correlation-id propagation, PII redaction, health endpoint | Config / API | E15-S1-AC1..AC5 |
| E9-S1 | Money value type with fixed-point decimal arithmetic | Types | E9-S1-AC1..AC3 |
| E11-S1 | Delinquency bucket ladder over days past due | Types | E11-S1-AC1..AC4 |

Full AC text: `specs/stories/E15-S1.md`, `specs/stories/E9-S1.md`, `specs/stories/E11-S1.md`.
Per-story execution contracts (owned files + Generation Contract Operations):
`specs/bundles/E15-S1.json`, `specs/bundles/E9-S1.json`, `specs/bundles/E11-S1.json`.

## What changed since the superseded review (read these diffs closely)

| Commit | Closes | Change |
|---|---|---|
| `d0b5c94` | — | repaired the group A sprint contract; removed unratified gate waivers |
| `5c13f54` | CR-001, CR-002 | `Money` rejects non-finite input (`is_finite` guard); the no-float architecture test now also walks `Div`/`FloorDiv` and `math.*` calls, with a per-line exemption mechanism |
| `f4abd41` | CR-003, CR-004, design defect 1 | correlation id survives the 500 path (pure-ASGI middleware installed **outside** `ServerErrorMiddleware`); uvicorn own loggers are routed through the root JSON formatter; `AppError` carries a `context` mapping and reports its class name, and the handler emits `{error, detail, context}` per `specs/design/api-contracts.md` |

The four closed BLOCKs were CR-001 (Money accepted NaN), CR-002 (the float guard
ignored arithmetic), CR-003 (the 500 path lost `X-Request-ID`) and CR-004 (uvicorn
loggers bypassed the JSON formatter). **Verify each fix on its merits rather than
trusting this table** — a claimed fix is not a verified fix, and the WARN/INFO
findings from the prior round were not all addressed.

## Changed production files (13)

```
backend/src/__init__.py            (empty package marker)
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
```

## Changed test files (5) and tooling (4)

```
backend/tests/__init__.py  backend/tests/conftest.py
backend/tests/architecture/test_no_float_money.py
backend/tests/unit/test_bucket_ladder.py
backend/tests/unit/test_log_redaction.py
frontend/tests/unit/money.test.ts
frontend/package.json  frontend/tsconfig.json  frontend/vite.config.ts  frontend/eslint.config.js
```

## Deterministic evidence — re-run by the gate orchestrator at HEAD, not self-reported

| Command | Result |
|---|---|
| `cd backend && uv run pytest -q` | exit 0 — **73 passed**, 2 warnings, 0.10s |
| `cd backend && uv run ruff check .` | exit 0 — all checks passed |
| `cd backend && uv run mypy src/` | exit 0 — no issues in 12 source files (`strict = true`) |
| `cd frontend && npm test` | exit 0 — **18 passed** (1 file) |
| `cd frontend && npm run lint` | exit 0 — eslint clean |
| `cd frontend && npm run typecheck` | exit 0 — `tsc --noEmit` clean |

Test counts rose 42 to 73 (backend) and 11 to 18 (frontend) across the three fix
commits. Coverage is not yet instrumented in this project; judge test *adequacy* from
the suites themselves, not from a coverage number.

## Runtime evidence the evaluator must produce (not reuse)

`verification.mode` is `local` (not `docker` — Docker Desktop is not installed on this
machine, and `docker-compose.yml` does not exist until E15-S2 in group B). Boot the
backend yourself with uvicorn and drive the three frozen api_checks live.

**Port assignment — instances must not collide.** Each evaluator instance boots its own
uvicorn on its own port and uses that port as the api base url:

| Instance | Port | Base URL |
|---|---|---|
| 1 | 8000 | `http://localhost:8000` |
| 2 | 8001 | `http://localhost:8001` |
| 3 | 8002 | `http://localhost:8002` |

The contract criteria are path- and header-based, so a non-default port does not
weaken them. Capture the process stdout/stderr: two of the three checks are
assertions about the *log stream*, not about the response body.

`sprint-contracts/A.json` (frozen, read-only):
- **QA-VM-003 / VM-003** — `GET /health` with header `X-Request-ID: req-abc` to 200; 100% of the log lines emitted while serving parse as JSON and each carries `request_id == "req-abc"`.
- **QA-VM-004 / VM-004** — `GET /health` with no `X-Request-ID` to 200; every request-scoped log line carries the same generated non-empty `request_id`, and the response echoes that id.
- **QA-VM-005 / VM-005** — `GET /health` to 200, JSON body, measured response time under 1 second.

Runtime SLO for the project: `{"error_rate_pct": 1, "p95_ms": 500}`.

No sprint contract in this repo declares Playwright checks, and `e2e/` is empty — there
is no browser evidence to produce for group A, and none may be claimed.

## Security-relevant surface in this diff (the security trigger fires)

- `backend/src/api/middleware.py` — accepts a **caller-supplied** `X-Request-ID` header, echoes it in the response header and threads it into every log line. Untrusted input reflected into both logs and headers: log injection (CR/LF, ANSI, JSON-breaking), header injection / response splitting, unbounded length, and control characters. Now a pure-ASGI middleware installed outside `ServerErrorMiddleware` — re-check the ordering claim and the 500 path.
- `backend/src/config/logging.py` — PII redaction over structured log output. A redaction miss leaks PII; check nesting depth, key-name matching, non-dict payloads, `extra=` fields, exception messages/tracebacks, and the uvicorn access logger now routed through the root formatter.
- `backend/src/api/errors.py`, `backend/src/types/errors.py` — the error envelope. `AppError` now carries a `context` mapping that reaches the client as `{error, detail, context}`. **That mapping is a new outbound channel: confirm nothing internal (paths, SQL, stack frames, config, PII) can ride out in it, and that the class name it reports is not an information leak.**
- `backend/src/api/platform/routes.py` — `GET /health`; must not disclose config, versions, or secrets, and must remain safe unauthenticated.
- `backend/src/config/settings.py` — configuration loading; hardcoded secrets, insecure defaults, secrets reachable from a log line or the new error `context`.
- `backend/src/api/serializers.py` — the single money wire serializer (decision D-G).

Not in this diff: authn/authz, persistence/migrations, outbound network calls, file
uploads, payment execution. Do not review for them; do not pad the report with their absence.

## Architecture constraints the diff must honor

- Strict layered architecture, one-way dependencies: Types to Config to Repository to Service to API to UI (`.claude/architecture.md`).
- **Decision D-G:** money is `NUMERIC(14,2)` in Postgres, `Decimal` in Python, a **quoted 2dp string** in JSON, parsed with a decimal library in TypeScript. No float touches a monetary value at any hop. No integer minor units. The Pydantic serializer lives in exactly one module.
- **Decision D-J:** the frontend money value is held as a decimal value, never a float; a static check must report 0 float arithmetic operations in that module.
- Functions <= 30 lines, files <= 300 lines, static typing everywhere, zero `any`.
- No pass-through modules: where a story has no business rule, the router uses the repository contract directly.
- Domain vocabulary is enforced from `specs/design/CONTEXT.md`.

## Frozen / out-of-scope paths

`specs/design/architecture.md`, `specs/design/api-contracts.md`, `specs/design/data-models.md`,
`specs/design/component-map.md`, `specs/test_artefacts/**`, `sprint-contracts/**`,
`project-manifest.json`. Do not propose edits to these — report the conflict instead.
`specs/design/component-map.md` in particular is covered by a design-approval receipt;
amending it invalidates that receipt and needs a human re-record.

## Known open items — in scope to judge, not to re-discover

1. **`ownership-check` blocks:** `backend/src/__init__.py` (0 bytes, package marker) has no row in `component-map.md`. The map is frozen, so this needs a human decision (amend the map and re-record the design receipt, vs. ratify a waiver, vs. delete the file if it is unnecessary). Judge whether the file is needed at all.
2. **`canvas-sync` blocks:** harness state files and `features.json` are missing from the REASONS Canvas Governs/Operations sections. `specs/reviews/canvas-sync-check.md` carries the deterministic patch.
3. **`regression-suite-full` blocks:** it treats *every* non-current `sprint-contracts/*.json` as a "prior" contract that must still pass. All 13 contracts (A..M) were authored up-front at plan time, so B..M are re-validated against an app that has not implemented them yet and return 404. Nothing regressed — group A is the first group, so there is no baseline. Flagged for the orchestrator; not a code defect in this diff.
4. Design defects 2 and 4-7 recorded in `claude-progress.txt` session 4 are still open and are **not** group A code defects.

## Review scope discipline

Read this pack, the range diff, and the files it touches. Do **not** read the builder
conversation, the full build transcript, raw test logs, or unrelated repo files. Do not
re-litigate the planning artefacts.
