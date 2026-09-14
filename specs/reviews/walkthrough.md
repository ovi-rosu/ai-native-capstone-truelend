# PR walkthrough

Generated: 2026-09-14T06:56:16.378Z
Files changed: **61**

## Intent

# Review Context Pack — /auto group A Commit under review: `e147f7e` on `feat/harness-scaffold-and-planning` Base: `14e9487` Range: `14e9487..e147f7e` (36 files, +1910/-12) ## Stories delivered | Story | Title | Layer | ACs | |---|---|---|---| | E15-S1 | Structured JSON logging, correlation id propagation, PII redaction, health endpoint | Config | E15-S1-AC1..AC5 | | E9-S1 | Money value type with 

Stories: `E15-S1`, `E9-S1`, `E11-S1`, `E15-S2`

## Story / slice groups

_Grouped from `component-map.md`. Each slice sits next to the matching `program-design.md` section._

### Slice `E15-S1`

- `backend/src/api/app.py`
- `backend/src/api/errors.py`
- `backend/src/api/middleware.py`
  - 🔴 **BLOCK** (high): CR-003
  - 🟠 **WARN** (medium): CR-011
- `backend/src/api/platform/routes.py`
- `backend/src/config/logging.py`
  - 🔴 **BLOCK** (high): CR-004
  - 🟠 **WARN** (high): CR-005
  - 🟠 **WARN** (high): CR-006
  - 🟠 **WARN** (medium): CR-007
  - 🟠 **WARN** (high): CR-016
- `backend/src/config/settings.py`
- `backend/src/types/errors.py`
- `backend/tests/conftest.py`
- `backend/tests/unit/test_log_redaction.py`
  - 🟠 **WARN** (medium): CR-017

**Program design (this slice)**

#### Types

# backend/src/types/money.py
Money                      = Decimal            # always quantized to 2dp when stored or serialized
MONEY_SCALE                = 2

# backend/src/types/loan_terms.py  (argument-clump value objects)
LoanTerms       { principal: Money, annual_rate_pct: Decimal, tenure_months: int }
LadderState     { loan_id: UUID, as_of_date: date, oldest_unpaid_due_date: date | None,
                  cumulative_due: Money, cumulative_paid: Money, days_past_due: int }
LoanAgeing      { loan_id: UUID, as_of_date: date, days_past_due: int, bucket: DelinquencyBucket }

# backend/src/types/enums.py
Role                       = CUSTOMER | UNDERWRITER | ADMIN
ApplicationStatus          = SUBMITTED | AWAITING_DOCUMENTS | UNDER_REVIEW | MANUAL_REVIEW | APPROVED | REJECTED | DISBURSE

#### Signatures

# ---------- Config (layer 2) -------------------------------------------------
# backend/src/config/delinquency.py            (D-B, single owner of the mapping)
DPD_BUCKET_FLOORS: tuple[tuple[int, DelinquencyBucket], ...]   # 0, 30, 60, 90, 180
classify(days_past_due: int) -> DelinquencyBucket
# backend/src/config/settings.py
Settings { database_url, jwt_secret, jwt_ttl_seconds = 3600, log_level, funding_source_id }   # TTL per D-M

# ---------- Repository (layer 3, insert-only where D-E says so) --------------
# policy
PolicyVersionRepository.insert(product_code, rules: PolicyRules, created_by) -> PolicyVersion
PolicyVersionRepository.get(policy_version_id) -> PolicyVersion
PolicyVersionRepository.get_active(product_code) -> PolicyVersion
PolicyVersionRepository.activate(policy_versi

#### File tree

+ backend/
+   src/
+     types/        money.py loan_terms.py enums.py policy.py origination.py servicing.py
+                   identity.py delinquency.py errors.py
+     config/       settings.py delinquency.py logging.py database.py
+     repository/
+       policy/         product_repository.py policy_version_repository.py
+       origination/    application_repository.py checklist_repository.py decision_repository.py
+       servicing/      loan_repository.py schedule_repository.py disbursement_repository.py
+                       repayment_repository.py
+       delinquency/    portfolio_repository.py
+       identity/       user_repository.py audit_repository.py
+       models.py       # SQLAlchemy tables (Repository layer only)
+     service/
+       policy/         catalog.py

### Slice `E9-S1`

- `backend/src/api/serializers.py`
- `backend/src/types/money.py`
  - 🔴 **BLOCK** (high): CR-001
  - 🟠 **WARN** (medium): CR-012
  - 🟠 **WARN** (medium): CR-013
  - ⚪ **INFO** (medium): CR-014
  - ⚪ **INFO** (low): CR-015
- `backend/tests/architecture/test_no_float_money.py`
  - 🔴 **BLOCK** (high): CR-002
  - 🟠 **WARN** (medium): CR-018
- `frontend/src/types/money.ts`
  - 🟠 **WARN** (medium): CR-020
  - ⚪ **INFO** (low): CR-022
- `frontend/src/ui/components/MoneyText.tsx`
- `frontend/tests/unit/money.test.ts`

**Program design (this slice)**

#### Types

# backend/src/types/money.py
Money                      = Decimal            # always quantized to 2dp when stored or serialized
MONEY_SCALE                = 2

# backend/src/types/loan_terms.py  (argument-clump value objects)
LoanTerms       { principal: Money, annual_rate_pct: Decimal, tenure_months: int }
LadderState     { loan_id: UUID, as_of_date: date, oldest_unpaid_due_date: date | None,
                  cumulative_due: Money, cumulative_paid: Money, days_past_due: int }
LoanAgeing      { loan_id: UUID, as_of_date: date, days_past_due: int, bucket: DelinquencyBucket }

# backend/src/types/enums.py
Role                       = CUSTOMER | UNDERWRITER | ADMIN
ApplicationStatus          = SUBMITTED | AWAITING_DOCUMENTS | UNDER_REVIEW | MANUAL_REVIEW | APPROVED | REJECTED | DISBURSE

### Slice `E11-S1`

- `backend/src/config/delinquency.py`
  - 🟠 **WARN** (high): CR-009
  - ⚪ **INFO** (medium): CR-019
- `backend/src/types/delinquency.py`
- `backend/tests/unit/test_bucket_ladder.py`

**Program design (this slice)**

#### Signatures

# ---------- Config (layer 2) -------------------------------------------------
# backend/src/config/delinquency.py            (D-B, single owner of the mapping)
DPD_BUCKET_FLOORS: tuple[tuple[int, DelinquencyBucket], ...]   # 0, 30, 60, 90, 180
classify(days_past_due: int) -> DelinquencyBucket
# backend/src/config/settings.py
Settings { database_url, jwt_secret, jwt_ttl_seconds = 3600, log_level, funding_source_id }   # TTL per D-M

# ---------- Repository (layer 3, insert-only where D-E says so) --------------
# policy
PolicyVersionRepository.insert(product_code, rules: PolicyRules, created_by) -> PolicyVersion
PolicyVersionRepository.get(policy_version_id) -> PolicyVersion
PolicyVersionRepository.get_active(product_code) -> PolicyVersion
PolicyVersionRepository.activate(policy_versi

### Slice `unmapped`

- `.claude/state/budget-start`
- `.claude/state/current-risk-tier`
- `.claude/state/current-task`
- `.claude/state/failures.md`
- `.claude/state/iteration-log.md`
- `.claude/state/navigation-status.json`
- `.claude/state/phase-cost-cursor.json`
- `.claude/state/phase-cost.json`
- `.claude/state/red-phase-presnap.json`
- `.claude/state/risk-envelope.json`
- `.claude/state/task-envelope-history/8914ad672f478b7a255bfa5bae84a4f42f262d43034b9944be6525ac67b9e330.json`
- `.claude/state/task-envelope-history/b24a95b810c8614edc100467573c4435f8ec62962945fb944182f44df8a260f8.json`
- `.claude/state/task-envelope-history/ebce3b61ee635eb8cc8f12d7b9694b33b719a76c5e05eeaa634f09bc416b8f7e.json`
- `.claude/state/task-envelope.json`
  - 🟠 **WARN** (high): CR-025
- `.claude/state/work-claims/group__A.json`
- `backend/src/__init__.py`
- `backend/tests/__init__.py`
- `claude-progress.txt`
- `frontend/eslint.config.js`
  - ⚪ **INFO** (low): CR-023
- `frontend/package.json`
- `frontend/tsconfig.json`
  - ⚪ **INFO** (low): CR-021
- `frontend/vite.config.ts`
- `specs/brownfield/code-graph.json`
- `specs/brownfield/code-graph.meta.json`
- `specs/bundles/E11-S1.json`
- `specs/bundles/E15-S1.json`
- `specs/bundles/E9-S1.json`
- `specs/design/amendments/group-a-implementation-sync.md`
  - ⚪ **INFO** (medium): CR-027
- `specs/design/reasons-canvas.md`
- `specs/reviews/contract-freeze.json`
- `specs/reviews/plan-seal.json`
- `specs/reviews/review-context-pack.md`
- `specs/reviews/sensor-checks.json`
- `specs/reviews/sensor-waivers-verdict.json`
- `specs/reviews/sensor-waivers.json`
- `specs/reviews/spdd-sync.json`
- `specs/reviews/test-approval.json`
- `specs/stories/E11-S1.md`
  - 🟠 **WARN** (high): CR-008
  - ⚪ **INFO** (high): CR-010
- `specs/stories/E15-S1.md`
- `specs/stories/E9-S1.md`
- `specs/test_artefacts/test-plan.md`
- `specs/test_artefacts/verification-matrix.json`
- `sprint-contracts/A.json`

**Program design (this slice)**

#### Types

# backend/src/types/money.py
Money                      = Decimal            # always quantized to 2dp when stored or serialized
MONEY_SCALE                = 2

# backend/src/types/loan_terms.py  (argument-clump value objects)
LoanTerms       { principal: Money, annual_rate_pct: Decimal, tenure_months: int }
LadderState     { loan_id: UUID, as_of_date: date, oldest_unpaid_due_date: date | None,
                  cumulative_due: Money, cumulative_paid: Money, days_past_due: int }
LoanAgeing      { loan_id: UUID, as_of_date: date, days_past_due: int, bucket: DelinquencyBucket }

# backend/src/types/enums.py
Role                       = CUSTOMER | UNDERWRITER | ADMIN
ApplicationStatus          = SUBMITTED | AWAITING_DOCUMENTS | UNDER_REVIEW | MANUAL_REVIEW | APPROVED | REJECTED | DISBURSE

#### Signatures

# ---------- Config (layer 2) -------------------------------------------------
# backend/src/config/delinquency.py            (D-B, single owner of the mapping)
DPD_BUCKET_FLOORS: tuple[tuple[int, DelinquencyBucket], ...]   # 0, 30, 60, 90, 180
classify(days_past_due: int) -> DelinquencyBucket
# backend/src/config/settings.py
Settings { database_url, jwt_secret, jwt_ttl_seconds = 3600, log_level, funding_source_id }   # TTL per D-M

# ---------- Repository (layer 3, insert-only where D-E says so) --------------
# policy
PolicyVersionRepository.insert(product_code, rules: PolicyRules, created_by) -> PolicyVersion
PolicyVersionRepository.get(policy_version_id) -> PolicyVersion
PolicyVersionRepository.get_active(product_code) -> PolicyVersion
PolicyVersionRepository.activate(policy_versi

#### Call stack

+ POST /applications                               [CUSTOMER]
+   require_roles(CUSTOMER)
+   origination.submit
+     policy.active_policy_version                 # only call site permitted by D-D
+     guard_minimum_income                         # raises PolicyViolation -> 422, rollback
+     ApplicationRepository.insert                 # pins policy_version_id
+     origination.generate_checklist
+       ChecklistRepository.insert_many
+     origination.score                            # deterministic stub
+       ApplicationRepository.set_credit_score
+     origination.evaluate
+       policy.rules_for_version(pinned)
+       policy.reason_codes_for_version(pinned)
+       DecisionRepository.insert
+       servicing.on_approved                       # only when the outcome approve

#### File tree

+ backend/
+   src/
+     types/        money.py loan_terms.py enums.py policy.py origination.py servicing.py
+                   identity.py delinquency.py errors.py
+     config/       settings.py delinquency.py logging.py database.py
+     repository/
+       policy/         product_repository.py policy_version_repository.py
+       origination/    application_repository.py checklist_repository.py decision_repository.py
+       servicing/      loan_repository.py schedule_repository.py disbursement_repository.py
+                       repayment_repository.py
+       delinquency/    portfolio_repository.py
+       identity/       user_repository.py audit_repository.py
+       models.py       # SQLAlchemy tables (Repository layer only)
+     service/
+       policy/         catalog.py

## Logical change groups

_Ordered for review top-to-bottom (entry → domain → services → data → adapters → tests). Not alphabetical._

### 1. Entry points (routes / handlers / CLI)

- `backend/src/api/app.py`
- `backend/src/api/errors.py`
- `backend/src/api/middleware.py`
  - 🔴 **BLOCK** (high): CR-003
  - 🟠 **WARN** (medium): CR-011
- `backend/src/api/platform/routes.py`
- `backend/src/api/serializers.py`

### 6. Config & infrastructure

- `backend/src/config/delinquency.py`
  - 🟠 **WARN** (high): CR-009
  - ⚪ **INFO** (medium): CR-019
- `backend/src/config/logging.py`
  - 🔴 **BLOCK** (high): CR-004
  - 🟠 **WARN** (high): CR-005
  - 🟠 **WARN** (high): CR-006
  - 🟠 **WARN** (medium): CR-007
  - 🟠 **WARN** (high): CR-016
- `backend/src/config/settings.py`
- `frontend/eslint.config.js`
  - ⚪ **INFO** (low): CR-023
- `frontend/package.json`
- `frontend/tsconfig.json`
  - ⚪ **INFO** (low): CR-021
- `frontend/vite.config.ts`

### 7. Tests

- `frontend/tests/unit/money.test.ts`

### 8. Docs & specs

- `.claude/state/failures.md`
- `.claude/state/iteration-log.md`
- `specs/brownfield/code-graph.json`
- `specs/brownfield/code-graph.meta.json`
- `specs/bundles/E11-S1.json`
- `specs/bundles/E15-S1.json`
- `specs/bundles/E9-S1.json`
- `specs/design/amendments/group-a-implementation-sync.md`
  - ⚪ **INFO** (medium): CR-027
- `specs/design/reasons-canvas.md`
- `specs/reviews/contract-freeze.json`
- `specs/reviews/plan-seal.json`
- `specs/reviews/review-context-pack.md`
- `specs/reviews/sensor-checks.json`
- `specs/reviews/sensor-waivers-verdict.json`
- `specs/reviews/sensor-waivers.json`
- `specs/reviews/spdd-sync.json`
- `specs/reviews/test-approval.json`
- `specs/stories/E11-S1.md`
  - 🟠 **WARN** (high): CR-008
  - ⚪ **INFO** (high): CR-010
- `specs/stories/E15-S1.md`
- `specs/stories/E9-S1.md`
- `specs/test_artefacts/test-plan.md`
- `specs/test_artefacts/verification-matrix.json`

### 9. Other

- `.claude/state/budget-start`
- `.claude/state/current-risk-tier`
- `.claude/state/current-task`
- `.claude/state/navigation-status.json`
- `.claude/state/phase-cost-cursor.json`
- `.claude/state/phase-cost.json`
- `.claude/state/red-phase-presnap.json`
- `.claude/state/risk-envelope.json`
- `.claude/state/task-envelope-history/8914ad672f478b7a255bfa5bae84a4f42f262d43034b9944be6525ac67b9e330.json`
- `.claude/state/task-envelope-history/b24a95b810c8614edc100467573c4435f8ec62962945fb944182f44df8a260f8.json`
- `.claude/state/task-envelope-history/ebce3b61ee635eb8cc8f12d7b9694b33b719a76c5e05eeaa634f09bc416b8f7e.json`
- `.claude/state/task-envelope.json`
  - 🟠 **WARN** (high): CR-025
- `.claude/state/work-claims/group__A.json`
- `backend/src/__init__.py`
- `backend/src/types/delinquency.py`
- `backend/src/types/errors.py`
- `backend/src/types/money.py`
  - 🔴 **BLOCK** (high): CR-001
  - 🟠 **WARN** (medium): CR-012
  - 🟠 **WARN** (medium): CR-013
  - ⚪ **INFO** (medium): CR-014
  - ⚪ **INFO** (low): CR-015
- `backend/tests/__init__.py`
- `backend/tests/architecture/test_no_float_money.py`
  - 🔴 **BLOCK** (high): CR-002
  - 🟠 **WARN** (medium): CR-018
- `backend/tests/conftest.py`
- `backend/tests/unit/test_bucket_ladder.py`
- `backend/tests/unit/test_log_redaction.py`
  - 🟠 **WARN** (medium): CR-017
- `claude-progress.txt`
- `frontend/src/types/money.ts`
  - 🟠 **WARN** (medium): CR-020
  - ⚪ **INFO** (low): CR-022
- `frontend/src/ui/components/MoneyText.tsx`
- `sprint-contracts/A.json`

## High-signal findings

- 🔴 **BLOCK** `backend/src/types/money.py`: CR-001
- 🔴 **BLOCK** `backend/tests/architecture/test_no_float_money.py`: CR-002
- 🔴 **BLOCK** `backend/src/api/middleware.py`: CR-003
- 🔴 **BLOCK** `backend/src/config/logging.py`: CR-004
- 🟠 **WARN** `backend/src/config/logging.py`: CR-005
- 🟠 **WARN** `backend/src/config/logging.py`: CR-006
- 🟠 **WARN** `backend/src/config/logging.py`: CR-007
- 🟠 **WARN** `specs/stories/E11-S1.md`: CR-008
- 🟠 **WARN** `backend/src/config/delinquency.py`: CR-009
- 🟠 **WARN** `backend/src/api/middleware.py`: CR-011
- 🟠 **WARN** `backend/src/types/money.py`: CR-012
- 🟠 **WARN** `backend/src/types/money.py`: CR-013
- 🟠 **WARN** `backend/src/config/logging.py`: CR-016
- 🟠 **WARN** `backend/tests/unit/test_log_redaction.py`: CR-017
- 🟠 **WARN** `backend/tests/architecture/test_no_float_money.py`: CR-018
- 🟠 **WARN** `frontend/src/types/money.ts`: CR-020
- 🟠 **WARN** `project-manifest.json`: CR-024
- 🟠 **WARN** `.claude/state/task-envelope.json`: CR-025

## Blast radius (from code-graph)

_No graph neighbors (missing graph or isolated files)._

## 5-minute human review script

1. Read **Intent** and confirm the PR matches the story/AC.
2. Walk **Logical change groups** top to bottom — skip alphabetical GitHub view.
3. Open every 🔴 BLOCK and 🟠 WARN; dismiss only with evidence.
4. Spot-check one happy path and one failure path in tests (group 7).
5. Confirm `specs/reviews/quality-card.md` is PASS and wiki links are fresh.
6. A human merges. The agent pre-read never approves or merges.
