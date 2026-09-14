# Component map

Every ready story to the files that implement it. All 29 stories are ready, so
all 29 appear.

**Format matters.** Ownership is parsed per line: a row's story id owns every
backticked path on that row. So the tables below carry one story per row with
all of its owned paths on that row, and the prose sections that follow name
interfaces and story ids **without** backticked paths — a path quoted next to
another story's id would register as shared ownership and report a false
collision.

**Ownership rule.** Each path appears in exactly one row. A story that only reads
or imports a path is named in the Interfaces section instead. Where a tracer
lands a thin version of a file and a later story in the same ownership cluster
deepens it (E1-S1 then E1-S2, E4-S1 then E4-S2, E9-S2 then E9-S3, E9-S2 then
E10-S1), the tracer owns the file and the Modifies notes record the deepening.

Migrations never share a file: one Alembic version file per story.

---

## Story to owned files

### Platform and cross-cutting

| Story | Cluster | Owned files |
|---|---|---|
| E15-S1 | C1 | `backend/src/config/settings.py` `backend/src/config/logging.py` `backend/src/types/errors.py` `backend/src/api/app.py` `backend/src/api/middleware.py` `backend/src/api/errors.py` `backend/src/api/platform/routes.py` `backend/tests/conftest.py` `backend/tests/unit/test_log_redaction.py` `backend/tests/unit/test_correlation_id.py` `backend/tests/unit/test_error_envelope.py` `backend/tests/unit/test_health_probe.py` |
| E15-S2 | C1 | `docker-compose.yml` `Dockerfile.backend` `Dockerfile.frontend` `init.sh` `backend/tests/architecture/test_layer_dependencies.py` `project-manifest.json` |
| E16-S1 | C1 | `backend/tests/architecture/invariant_registry.py` `backend/tests/architecture/test_invariant_registry.py` `backend/tests/architecture/test_agent_provenance.py` |
| E9-S1 | C6 | `backend/src/types/money.py` `backend/src/api/serializers.py` `backend/tests/architecture/test_no_float_money.py` `frontend/src/types/money.ts` `frontend/src/ui/components/MoneyText.tsx` `frontend/tests/unit/money.test.ts` |
| E11-S1 | C2 | `backend/src/types/delinquency.py` `backend/src/config/delinquency.py` `backend/tests/unit/test_bucket_ladder.py` |

### Identity and audit

| Story | Cluster | Owned files |
|---|---|---|
| E1-S1 | C1 | `backend/src/types/enums.py` `backend/src/types/identity.py` `backend/src/repository/models.py` `backend/src/repository/identity/user_repository.py` `backend/src/repository/policy/product_repository.py` `backend/src/service/identity/auth.py` `backend/src/api/deps.py` `backend/src/api/identity/routes.py` `backend/src/api/policy/routes.py` `backend/migrations/versions/0001_identity_catalog_policy.py` `frontend/src/config/env.ts` `frontend/src/config/roles.ts` `frontend/src/types/api.ts` `frontend/src/types/enums.ts` `frontend/src/api/client.ts` `frontend/src/api/auth.ts` `frontend/src/api/products.ts` `frontend/src/ui/App.tsx` `frontend/src/ui/routes.tsx` `frontend/src/ui/pages/Login.tsx` `frontend/src/ui/pages/Catalog.tsx` |
| E1-S2 | C1 | `backend/src/api/authz.py` `backend/src/service/identity/audit.py` `backend/src/repository/identity/audit_repository.py` `backend/src/api/identity/audit_routes.py` `backend/tests/architecture/test_route_authorization.py` `backend/migrations/versions/0002_audit_event.py` |

### Policy and catalog

| Story | Cluster | Owned files |
|---|---|---|
| E3-S1 | C1 | `backend/src/repository/policy/policy_version_repository.py` `backend/tests/architecture/test_policy_version_immutability.py` `backend/tests/architecture/test_migration_lint.py` `backend/migrations/versions/0003_policy_version_constraints.py` |
| E2-S1 | C1 | `backend/src/types/policy.py` `backend/src/service/policy/catalog.py` `backend/src/service/policy/policy_accessor.py` `backend/migrations/versions/0004_seed_catalog.py` `backend/tests/integration/test_catalog_binding.py` |
| E3-S2 | C1 | `backend/src/service/policy/policy_publisher.py` `backend/src/api/policy/policy_version_routes.py` `backend/tests/integration/test_policy_activation.py` `frontend/src/api/policy.ts` `frontend/src/ui/pages/PolicyEditor.tsx` |

### Origination

| Story | Cluster | Owned files |
|---|---|---|
| E4-S1 | C1 | `backend/src/types/origination.py` `backend/src/repository/origination/application_repository.py` `backend/src/service/origination/intake.py` `backend/src/api/origination/routes.py` `backend/migrations/versions/0005_application.py` |
| E4-S2 | C1 | `backend/src/service/origination/checklist.py` `backend/src/repository/origination/checklist_repository.py` `backend/migrations/versions/0006_checklist_item.py` `backend/tests/integration/test_intake_pinning.py` |
| E4-S3 | C4 | `frontend/src/api/applications.ts` `frontend/src/ui/pages/Apply.tsx` `frontend/src/ui/components/ChecklistList.tsx` `frontend/tests/unit/Apply.test.tsx` |
| E4-S4 | C5 | `backend/src/types/policy_violation.py` `backend/src/service/origination/income_guard.py` `backend/tests/integration/test_policy_violation_rollback.py` |
| E5-S1 | C1 | `backend/src/service/origination/scoring.py` `backend/tests/unit/test_scoring_stub.py` |
| E5-S2 | C1 | `backend/src/service/origination/decision.py` `backend/src/repository/origination/decision_repository.py` `backend/migrations/versions/0007_decision_record.py` `backend/tests/unit/test_decision_reason_codes.py` |
| E6-S1 | C1 | `backend/src/service/origination/document_verification.py` `backend/src/api/origination/document_routes.py` `backend/tests/integration/test_document_queue.py` |
| E6-S2 | C1 | `frontend/src/api/workbench.ts` `frontend/src/ui/pages/Workbench.tsx` `frontend/src/ui/pages/DecisionReview.tsx` `frontend/src/ui/components/ReasonCodeList.tsx` |
| E7-S1 | C1 | `backend/src/service/origination/override.py` `backend/src/api/origination/override_routes.py` `frontend/src/api/admin.ts` `frontend/src/ui/pages/AdminApplications.tsx` `backend/tests/integration/test_override_audit.py` |
| E8-S1 | C1 | `frontend/src/ui/pages/Track.tsx` `frontend/src/ui/components/StatusPill.tsx` `frontend/tests/unit/Track.test.tsx` |

### Servicing

| Story | Cluster | Owned files |
|---|---|---|
| E9-S2 | C1 | `backend/src/types/servicing.py` `backend/src/repository/servicing/loan_repository.py` `backend/src/repository/servicing/schedule_repository.py` `backend/src/repository/servicing/disbursement_repository.py` `backend/src/repository/servicing/repayment_repository.py` `backend/src/service/servicing/schedule.py` `backend/src/service/servicing/loan_projection.py` `backend/src/api/servicing/routes.py` `backend/migrations/versions/0008_loan_schedule_disbursement_repayment.py` |
| E9-S3 | C1 | `backend/src/types/loan_terms.py` `backend/src/service/servicing/emi.py` `backend/src/service/servicing/installment_ladder.py` `backend/tests/unit/test_emi_residual.py` `backend/tests/architecture/test_schedule_immutability.py` |
| E10-S1 | C1 | `backend/src/service/servicing/disbursement.py` `backend/src/service/servicing/funding_source.py` `backend/tests/integration/test_disbursement_idempotence.py` |
| E11-S2 | C1 | `backend/src/service/servicing/repayment.py` `backend/src/service/delinquency/recalculation.py` `backend/tests/integration/test_repayment_posting.py` |

### Delinquency, portfolio and customer loan view

| Story | Cluster | Owned files |
|---|---|---|
| E12-S1 | C2 | `backend/src/service/delinquency/end_of_day.py` `backend/src/api/delinquency/end_of_day_routes.py` `backend/tests/integration/test_end_of_day_idempotence.py` |
| E14-S1 | C1 | `backend/src/service/delinquency/portfolio.py` `backend/src/repository/delinquency/portfolio_repository.py` `backend/src/api/delinquency/portfolio_routes.py` `frontend/src/api/dashboard.ts` `frontend/src/ui/pages/Portfolio.tsx` |
| E13-S1 | C3 | `frontend/src/api/loans.ts` `frontend/src/ui/pages/Repay.tsx` `frontend/src/ui/components/BucketBadge.tsx` `frontend/tests/unit/Repay.test.tsx` |

### Harnesses

| Story | Cluster | Owned files |
|---|---|---|
| E15-S3 | C3 | `backend/tests/slo/registry.py` `backend/tests/slo/harness.py` `backend/tests/slo/test_read_slo.py` |
| E17-S1 | C4 | `frontend/tests/a11y/registry.ts` `frontend/tests/a11y/harness.ts` `frontend/tests/a11y/screens.spec.ts` |

---

## Shared registries

Five files are registries that later stories append a single row to. Each has one
owner, named on the same row as the path above. Appenders are listed here by
story id only, deliberately without the path, so an append is not read as
co-ownership.

| Registry | Owner | Appended by | What an append is |
|---|---|---|---|
| app factory router registry | E15-S1 | every story adding a router | one include_router call |
| SQLAlchemy table registry | E1-S1 | every story adding a table | one table class |
| frontend route registry | E1-S1 | every story adding a screen | one route entry |
| read-heavy endpoint registry | E15-S3 | E7-S1, E13-S1, E14-S1 | one endpoint row |
| customer-facing screen registry | E17-S1 | E8-S1, E13-S1 | one screen row |

A registry append is the one legitimate shared-surface edit in this design. No
behavior-bearing file is shared.

---

## Interfaces produced and consumed

Interface names and story ids only; the owning row above carries the path.

### Produces

- **E15-S1** — the create_app factory and router registry, the correlation-id
  middleware, the redaction filter, the single error-mapping table, and the
  log-capture fixture every later story reuses.
- **E15-S2** — the three-service Compose stack, the six-layer one-way dependency
  test, and the manifest architecture block without which that test matches no
  file and passes vacuously.
- **E9-S1** — the Money type, the one Pydantic serializer rendering a quoted 2dp
  string, the one frontend parser over a decimal library, and the money display
  component. Rendered per decision D-G, which rules out integer minor units.
  D-J amends E9-S1-AC3 and FRD-57 to read "held as a decimal value, never a
  float", so the amended AC is the only oracle: no minor-unit conversion may be
  added anywhere in the frontend, including a scale/unscale helper at the
  browser edge. The story bundle and features.json entry for E9-S1 are
  re-rendered from the amended AC by /spec, not here.
- **E11-S1** — the DelinquencyBucket enum and the single classify function over
  the Config-layer boundaries of decision D-B.
- **E1-S1** — the JWT session, the authenticated-user dependency, the table
  registry, the frontend HTTP client and the role-to-landing-surface map. Its
  shallow product list reads the product repository straight from the router:
  there is no business rule yet, so no pass-through service is written.
- **E1-S2** — require_roles, the single enforcement point every non-public router
  takes under decision D-F; the audit append; and the schema-driven 401 and 403
  coverage suite.
- **E3-S1** — a policy-version repository with no update and no delete method,
  plus the migration lint every later migration is held to.
- **E2-S1** — the PolicyRules Pydantic model that validates the JSONB document
  (decision D-A), and the pinned-version accessor that is the only published way
  to read Policy Rules (decision D-D).
- **E3-S2** — append-and-activate in one transaction, with activation as a
  pointer write on the product row. A flag on the policy version would be an
  UPDATE the immutability test forbids.
- **E4-S1** — the application aggregate and the submit endpoint that pins
  policy_version_id at creation.
- **E4-S2** — the Document Checklist generated item-for-item from the pinned
  version, and the pinning guarantee every later reader depends on.
- **E4-S3** — the application API client, plus the first screen registered with
  the accessibility harness.
- **E4-S4** — the PolicyViolationException contract naming the breached threshold
  and the configured value, with a rollback that leaves no application row.
- **E5-S1** — a deterministic score behind its own port, so a real bureau could
  replace it without touching the evaluator. No clock, no randomness, no outbound
  call.
- **E5-S2** — the append-only decision record with latest-record-wins semantics,
  and the approval hand-off servicing consumes.
- **E6-S1** — the verification queue read model and the VERIFIED and REJECTED
  transitions, with the rejection reason enforced by both a validator and a CHECK
  constraint.
- **E7-S1** — the superseding Override, which never edits the row it supersedes.
- **E9-S2** — the Loan aggregate, the four servicing repositories, and the single
  projection write path that both the repayment service and the end-of-day run
  use.
- **E9-S3** — the one EMI and residual implementation (decision D-C), referenced
  by schedule generation and by the FR-07 invariant test; and the installment
  ladder, sole owner of the paid/unpaid derivation and of Days Past Due, published
  for the delinquency context to read.
- **E10-S1** — the disbursement transition and the stubbed funding-source port.
  The UNIQUE constraint on the loan id makes the idempotence guard structural.
- **E11-S2** — the append-only repayment posting and the post-payment bucket
  recalculation.
- **E12-S1** — the As-Of-Date run. It persists no run row of its own, because a
  run row would break the byte-identical second-run assertion.
- **E14-S1** — the portfolio aggregation, served from stored projections only; it
  never invokes the end-of-day run.
- **E15-S3** — the read-heavy endpoint registry, the in-process load driver, and
  the completeness assertion that fails when a GET route is missing.
- **E17-S1** — the axe-core scan, the keyboard-traversal driver, the screen
  registry and its completeness assertion.

### Consumes

| Story | Consumes from |
|---|---|
| E15-S2 | health probe from E15-S1 |
| E16-S1 | layer test from E15-S2, immutability test from E3-S1, EMI invariant test from E9-S3 |
| E1-S1 | Money type from E9-S1, correlation id from E15-S1 |
| E1-S2 | session from E1-S1 |
| E3-S1 | table registry from E1-S1, Money type from E9-S1 |
| E2-S1 | policy-version store from E3-S1 |
| E3-S2 | catalog binding from E2-S1, require_roles from E1-S2 |
| E4-S1 | pinned-version accessor from E2-S1, require_roles from E1-S2 |
| E4-S2 | tracer intake from E4-S1 |
| E4-S3 | intake service from E4-S2, money component from E9-S1 |
| E4-S4 | intake path from E4-S2, error mapping from E15-S1 |
| E5-S1 | pinned application from E4-S2 |
| E5-S2 | score from E5-S1, reason codes from E2-S1 |
| E6-S1 | checklist from E4-S2, require_roles and audit from E1-S2 |
| E6-S2 | decision service from E5-S2, document state from E6-S1, application client from E4-S3 |
| E7-S1 | decision record from E5-S2, require_roles and audit from E1-S2, application client from E4-S3, endpoint registry from E15-S3 |
| E8-S1 | decision service from E5-S2, unverified documents from E6-S1, application client from E4-S3, screen registry from E17-S1 |
| E9-S2 | approving decision from E5-S2 |
| E9-S3 | tracer schedule from E9-S2, Money type from E9-S1 |
| E10-S1 | generated schedule from E9-S3 |
| E11-S2 | disbursed loan from E10-S1, classifier from E11-S1, ladder from E9-S3, projection path from E9-S2 |
| E12-S1 | classifier from E11-S1, ladder and installment rows from E9-S3, projection path from E9-S2 |
| E13-S1 | repayment service from E11-S2, money component from E9-S1, screen registry from E17-S1, endpoint registry from E15-S3 |
| E14-S1 | stored bucket state from E11-S2, require_roles from E1-S2, endpoint registry from E15-S3 |
| E15-S3 | the products read surface from E2-S1 as its first registered endpoint |
| E17-S1 | the Apply screen from E4-S3, which it registers and remediates |

E12-S1 deliberately consumes nothing from E11-S2: decision D-10 keeps the
end-of-day run independent of the repayment path, so both call the classifier and
the ladder rather than each other.

### Modifies (tracer then deepening, same cluster)

| File owner | Deepened by | What changes |
|---|---|---|
| E4-S1 | E4-S2 | the intake service gains checklist generation and the full pinning path |
| E9-S2 | E9-S3 | the schedule service gains the real EMI and residual rules |
| E9-S2 | E10-S1 | the servicing router gains the real disbursement handler |
| E4-S3 | E17-S1 | the Apply screen is remediated for accessibility; no endpoint or contract change |
| E1-S1 | E1-S2 | the policy router gains `require_roles(ADMIN)` and the audit append; E1-S1's Scope Out deliberately left the route unenforced and D-F rules out a per-route hand-written check, so the single enforcement point has to be retrofitted here |

---

## Second-round decisions that touch this map

`design-unresolved.json` is empty; the six items this rendering returned were
settled as D-J through D-O. The three that change what an implementer writes:

- **D-J** — the money module is rendered per D-G, and E9-S1-AC3 and FRD-57 are
  amended to match it. Integer minor units are ruled out everywhere in the
  frontend.
- **D-K** — the repayment service allocates FIFO across whole Installments and,
  within the oldest unpaid Installment, interest before principal. Outstanding
  principal falls by the applied principal portion only.
- **D-L** — ApplicationStatus carries seven states; MANUAL_REVIEW is a status,
  so the workbench filter in the staff surfaces is a plain status filter and the
  two staff mockups' labels already match the schema.
- **D-M** / **D-N** / **D-O** — the JWT TTL is 3600s; disbursement and
  end-of-day are both ADMIN, which E1-S2's generated 401/403 suite encodes; and
  no throttling middleware is written, so no test asserts one.
