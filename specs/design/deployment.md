# Deployment

Self-hosted Docker Compose over a single PostgreSQL database (FRD-29). Exactly
three services — no cache, no broker, no second database engine, and no external
provider endpoint (`E15-S2-AC1`, `E15-S2-AC3`). D-F's no-session-store choice is
what keeps Redis out of this file.

## Environments

| Environment | How it runs | Data | Notes |
|---|---|---|---|
| `local` | `./init.sh` then `docker compose up` | ephemeral volume, seeded catalog and three role users | the environment every AC is verified in |
| `ci` | GitHub Actions service container for Postgres, backend under pytest | throwaway | no frontend container; Vitest and the a11y harness run on the runner |
| `production` | same Compose stack on the self-hosted host | persistent named volume | declared in `project-manifest.json` under `github.environments` with `protected_branches: true` and a required reviewer, so a deploy pauses for approval |

There is no staging environment; none is recorded in the manifest or any
requirement, so none is invented here.

## Compose topology

```yaml
services:
  postgres:   # postgres:16-alpine, healthcheck pg_isready, named volume, no host port in production
  backend:    # Dockerfile.backend, depends_on postgres condition service_healthy,
              # healthcheck GET /health, runs alembic upgrade head then uvicorn
  frontend:   # Dockerfile.frontend, depends_on backend condition service_healthy,
              # vite build served by a static server, healthcheck on /
```

`E15-S2-AC1` asserts exactly one Postgres, one Python 3.12 FastAPI backend and one
TypeScript React-Vite frontend, all reporting healthy from a clean checkout.
The backend healthcheck is the same `/health` endpoint `E15-S1-AC5` times at
under one second, so the compose readiness gate and the AC share one probe.

## Images

- `Dockerfile.backend` — `python:3.12-slim`, `uv sync --frozen`, non-root user,
  `CMD alembic upgrade head && uvicorn src.api.app:create_app --factory`.
- `Dockerfile.frontend` — `node:22-alpine` build stage running `npm ci` and
  `npm run build`, then a minimal static-serve stage. `VITE_API_BASE_URL` is a
  build argument.

Migrations run on backend start, not in a separate job: they are append-only and
non-destructive by construction (`E3-S1-AC3`), so there is no destructive step
that needs a human in the loop.

## Bootstrap — `init.sh`

1. Verify `docker` and `docker compose` are present.
2. Copy `.env.example` to `.env` when absent and generate a local `JWT_SECRET`.
3. `docker compose up -d --build`.
4. Poll `GET /health` until 200 or a bounded timeout, then print the frontend URL
   and the three seeded usernames.
5. Exit non-zero if any service never reports healthy — the smoke test in
   `E15-S2-AC1` depends on that exit code.

## CI/CD

Pipeline order, fail-fast:

1. `gitleaks` and `sast` (semgrep) — both are required checks in
   `project-manifest.json` under `github.required_checks`, so they block merge.
2. Backend: `uv run ruff check .`, `uv run mypy src/`, `uv run pytest -x -q`,
   including `backend/tests/architecture/` (layer rule, policy-version and
   schedule immutability, migration lint, route-authorization coverage, the
   invariant registry from `E16-S1`).
3. Frontend: `npm run lint`, `npm run typecheck`, `npm test`, plus the axe-core
   and keyboard-traversal harness from `E17-S1`.
4. `docker compose up` smoke test asserting the three services healthy and
   `GET /health` under one second (`E15-S2-AC1`, FRD-63).
5. The SLO load run from `E15-S3` against the four registered read-heavy
   endpoints, recording measured p95 and error rate in the evaluation report.
6. Provenance: every production commit carries agent co-authorship and a passing
   pre-commit record; the `/gate` attestation is the evidence for zero
   hand-written production lines (`E16-S1-AC3`, `E16-S1-AC4`).

Branch protection: 1 required approval, code-owner review required, admins
included — all as already declared in the manifest. Merge to `main` is the only
deploy trigger; `production` then waits on its required reviewer.

## IaC approach

`docker-compose.yml` plus the two Dockerfiles *are* the infrastructure
definition. There is no Terraform, Helm chart or cloud provider module: the
target is a self-hosted single host, and adding a provisioning layer would
introduce credentials `SG-2` forbids the system to hold.

## Secrets handling

| Secret | Source | Never |
|---|---|---|
| `DATABASE_URL` | Compose environment, from `.env` (git-ignored) | committed, logged |
| `JWT_SECRET` | `.env` locally; GitHub environment secret for `production` | defaulted to a literal in code |
| `POSTGRES_PASSWORD` | same | echoed by `init.sh` |

`JWT_TTL_SECONDS` is **not** a secret: it is non-sensitive config with the
default `3600` fixed by **D-M**, so it ships in `.env.example` at its real value
rather than as a placeholder.

`.env.example` carries placeholder values only. `gitleaks` runs as a required
check, and `.gitleaks.toml` is already in the repo. There are no third-party
provider credentials at all: the credit bureau and the funding source are stubs
(`SG-2`), and D-F's tokenless-storage choice removes a session store. Applicant
PAN, Aadhaar and salary content are not secrets in the credential sense but are
redacted from every log sink by the `E15-S1` filter.

## Rollback

1. **Application rollback** — redeploy the previous image tag. Safe without a
   data step because every schema change is expand-only; no migration removes a
   column or table in the same sprint it stops being used (constitution
   invariant, enforced by the `E3-S1` migration lint).
2. **Data rollback is not a code path.** The append-only tables (policy version,
   schedule, installment, decision, repayment, disbursement, audit) have no
   delete path by design (D-E), so a bad write is corrected by appending a
   superseding fact — a new policy version, a superseding decision — never by an
   UPDATE or a DELETE.
3. **Projection repair** — `loan.outstanding_principal` and
   `loan.delinquency_bucket` are recomputable from the facts, so a drifted
   projection is repaired by replay: re-derive from `disbursement` and
   `repayment_posting`, and re-run the End-Of-Day Run for the affected As-Of
   Date, which is idempotent (`E12-S1-AC2`).
4. **Restore** — a volume snapshot restore is the last resort. No backup
   schedule or retention window is specified here: no requirement or recorded
   decision fixes one, and inventing a retention period would read as decided.
