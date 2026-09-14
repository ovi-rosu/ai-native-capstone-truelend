# PR walkthrough

Generated: 2026-09-14T13:37:37.677Z
Files changed: **225**

## Intent

# Review Context Pack — /gate --group A (round 3) **Gate lane:** on-demand pre-merge (`/gate`) **Generated:** 2026-09-14 (session 6) ## 1. Request / scope | Field | Value | |---|---| | Group | A | | Stories | E15-S1 (platform logging + health), E9-S1 (Money value type), E11-S1 (delinquency bucket), **E15-S4 (NEW — duration histogram + hostile-input hardening)** | | Sprint contract | `sprint-contra

Stories: `E15-S1`, `E9-S1`, `E11-S1`, `E15-S4`, `E1-S1`

## Story / slice groups

_Grouped from `component-map.md`. Each slice sits next to the matching `program-design.md` section._

### Slice `E15-S3`

- `.claude/state/eval-i1/harness.py`

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

### Slice `E15-S1`

- `backend/src/api/app.py`
- `backend/src/api/errors.py`
  - 🟠 **WARN** (high): CR-307
  - 🟠 **WARN** (medium): CR-308
- `backend/src/api/middleware.py`
  - 🔴 **BLOCK** (high): CR-301
  - ⚪ **INFO** (high): CR-314
  - ⚪ **INFO** (medium): CR-315
  - ⚪ **INFO** (high): CR-316
  - ⚪ **INFO** (medium): CR-318
- `backend/src/api/platform/routes.py`
  - 🟠 **WARN** (high): CR-302
  - 🟠 **WARN** (high): CR-309
  - ⚪ **INFO** (high): CR-317
- `backend/src/config/logging.py`
  - 🟠 **WARN** (high): CR-305
  - 🟠 **WARN** (high): CR-310
- `backend/src/config/settings.py`
- `backend/src/types/errors.py`
- `backend/tests/conftest.py`
  - 🟠 **WARN** (medium): CR-313
- `backend/tests/unit/test_correlation_id.py`
- `backend/tests/unit/test_error_envelope.py`
- `backend/tests/unit/test_health_probe.py`
- `backend/tests/unit/test_log_redaction.py`
  - 🟠 **WARN** (high): CR-311

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
  - 🟠 **WARN** (high): CR-306
- `backend/src/types/money.py`
- `backend/tests/architecture/test_no_float_money.py`
- `frontend/src/types/money.ts`
  - 🟠 **WARN** (high): CR-304
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

### Slice `E15-S4`

- `backend/tests/architecture/test_observability_contract.py`
  - 🟠 **WARN** (high): CR-303
  - 🟠 **WARN** (high): CR-312

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

### Slice `E15-S2`

- `project-manifest.json`

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

### Slice `unmapped`

- `.claude/state/budget-start`
- `.claude/state/current-risk-tier`
- `.claude/state/current-task`
- `.claude/state/eval-i1/attack.log`
- `.claude/state/eval-i1/f003.body`
- `.claude/state/eval-i1/f003.hdr`
- `.claude/state/eval-i1/f003.lines`
- `.claude/state/eval-i1/f004.body`
- `.claude/state/eval-i1/f004.hdr`
- `.claude/state/eval-i1/f004.lines`
- `.claude/state/eval-i1/f005.timings`
- `.claude/state/eval-i1/features.json.bak`
- `.claude/state/eval-i1/harness.log`
- `.claude/state/eval-i1/logcheck.js`
- `.claude/state/eval-i1/metrics-forged.txt`
- `.claude/state/eval-i1/metrics-poisoned.txt`
- `.claude/state/eval-i1/metrics.txt`
- `.claude/state/eval-i1/money.py.bak`
- `.claude/state/eval-i1/pii-window.log`
- `.claude/state/eval-i1/promcheck.js`
- `.claude/state/eval-i1/update-features.js`
- `.claude/state/eval-i1/vm003.lines`
- `.claude/state/eval-i1/vm004.body`
- `.claude/state/eval-i1/vm004.hdr`
- `.claude/state/failures.md`
- `.claude/state/g3eval2-500.txt`
- `.claude/state/g3eval2-body005.json`
- `.claude/state/g3eval2-chatty.txt`
- `.claude/state/g3eval2-conc.txt`
- `.claude/state/g3eval2-h003.txt`
- `.claude/state/g3eval2-h004.txt`
- `.claude/state/g3eval2-injlines.txt`
- `.claude/state/g3eval2-lines003.txt`
- `.claude/state/g3eval2-lines004.txt`
- `.claude/state/g3eval2-perf.txt`
- `.claude/state/g3eval2-piiboom.txt`
- `.claude/state/g3eval2_probe.py`
- `.claude/state/g3eval3-expected-ids.json`
- `.claude/state/gate-receipt.json`
- `.claude/state/handoff/gate-group-A.md`
- `.claude/state/iteration-log.md`
- `.claude/state/navigation-status.json`
- `.claude/state/phase-cost-cursor.json`
- `.claude/state/phase-cost.json`
- `.claude/state/red-phase-presnap.json`
- `.claude/state/risk-envelope.json`
- `.claude/state/task-completion-receipt.json`
- `.claude/state/task-envelope-history/267760e13e6cda739f0835ffdff9140b7b2ddd3eb3bf1ce64c0dd7adeecbf13d.json`
- `.claude/state/task-envelope-history/4034d3db61bdff6b223fd631480932d03510d6d52a32870b4bf0c2ee702e05da.json`
- `.claude/state/task-envelope-history/62e4d6055406f528dbaf106b4c2490ab209a6769c21f981f45bcead78a5a94ed.json`
- `.claude/state/task-envelope-history/7ae6bff4fdcfe4e5e350b8cc6b4823a2f49a8a7805e97359a800301b681b5394.json`
- `.claude/state/task-envelope-history/8914ad672f478b7a255bfa5bae84a4f42f262d43034b9944be6525ac67b9e330.json`
- `.claude/state/task-envelope-history/9a1142eaa81a33a48bcc68d2252eefe06fb3db52e50f19947aa449da5d909a0d.json`
- `.claude/state/task-envelope-history/b0a253ab010f74d11bb8d478187ee07dbd6f37f63b7637cbfd40acc8e8eff5bc.json`
- `.claude/state/task-envelope-history/b24a95b810c8614edc100467573c4435f8ec62962945fb944182f44df8a260f8.json`
- `.claude/state/task-envelope-history/ebce3b61ee635eb8cc8f12d7b9694b33b719a76c5e05eeaa634f09bc416b8f7e.json`
- `.claude/state/task-envelope-history/eda892d10c64151b32bbc2480478f10210ff8346da6a9d222f34b97ad71a715d.json`
- `.claude/state/task-envelope-history/fb41b097c331594e1807274e9ee9b47320e6a57f83ca3cd62ba155ba90598404.json`
- `.claude/state/task-envelope.json`
- `.claude/state/work-claims/group__A.json`
- `.gitignore`
- `backend/src/__init__.py`
- `backend/tests/__init__.py`
- `backend/uv.lock`
- `claude-progress.txt`
- `docs/CODEBASE.md`
- `features.json`
- `frontend/eslint.config.js`
- `frontend/package-lock.json`
- `frontend/package.json`
- `frontend/tsconfig.json`
- `frontend/vite.config.ts`
- `specs/brownfield/code-graph.json`
- `specs/brownfield/code-graph.meta.json`
- `specs/bundles/E1-S1.json`
- `specs/bundles/E1-S2.json`
- `specs/bundles/E10-S1.json`
- `specs/bundles/E11-S1.json`
- `specs/bundles/E11-S2.json`
- `specs/bundles/E12-S1.json`
- `specs/bundles/E13-S1.json`
- `specs/bundles/E14-S1.json`
- `specs/bundles/E15-S1.json`
- `specs/bundles/E15-S2.json`
- `specs/bundles/E15-S3.json`
- `specs/bundles/E15-S4.json`
- `specs/bundles/E16-S1.json`
- `specs/bundles/E17-S1.json`
- `specs/bundles/E2-S1.json`
- `specs/bundles/E3-S1.json`
- `specs/bundles/E3-S2.json`
- `specs/bundles/E4-S1.json`
- `specs/bundles/E4-S2.json`
- `specs/bundles/E4-S3.json`
- `specs/bundles/E4-S4.json`
- `specs/bundles/E5-S1.json`
- `specs/bundles/E5-S2.json`
- `specs/bundles/E6-S1.json`
- `specs/bundles/E6-S2.json`
- `specs/bundles/E7-S1.json`
- `specs/bundles/E8-S1.json`
- `specs/bundles/E9-S1.json`
- `specs/bundles/E9-S2.json`
- `specs/bundles/E9-S3.json`
- `specs/design/amendments/e15-s4-observability-contract.md`
- `specs/design/amendments/group-a-gate-remediation.md`
- `specs/design/amendments/group-a-implementation-sync.md`
- `specs/design/component-map.md`
- `specs/design/reasons-canvas.md`
- `specs/reviews/canvas-semantic-review.md`
- `specs/reviews/canvas-sync-check-productscope.md`
- `specs/reviews/canvas-sync-check.md`
- `specs/reviews/code-review-groupA.md`
- `specs/reviews/code-review-verdict.json`
- `specs/reviews/code-review.md`
- `specs/reviews/contract-freeze.json`
- `specs/reviews/design-approval.json`
- `specs/reviews/eval-failures-001.json`
- `specs/reviews/eval-failures-002.json`
- `specs/reviews/evaluator-evidence-instance2.json`
- `specs/reviews/evaluator-evidence-instance3.json`
- `specs/reviews/evaluator-evidence.json`
- `specs/reviews/evaluator-report-instance2.md`
- `specs/reviews/evaluator-report-instance3.md`
- `specs/reviews/evaluator-report.md`
- `specs/reviews/evidence-integrity-verdict.json`
- `specs/reviews/gate-checks.json`
- `specs/reviews/local-regression-gate-verdict.json`
- `specs/reviews/metrics-forgery-evidence.txt`
- `specs/reviews/observability-gate.md`
- `specs/reviews/observability-verdict.json`
- `specs/reviews/ownership-check.json`
- `specs/reviews/perf-smell-gate.md`
- `specs/reviews/perf-smell-verdict.json`
- `specs/reviews/plan-seal.json`
- `specs/reviews/quality-card.json`
- `specs/reviews/quality-card.md`
- `specs/reviews/regression-gate-verdict-groupA-live.json`
- `specs/reviews/regression-gate-verdict-nobaseline.json`
- `specs/reviews/regression-gate-verdict-registryinvocation.json`
- `specs/reviews/regression-gate-verdict.json`
- `specs/reviews/reverify-votes.json`
- `specs/reviews/review-context-pack.md`
- `specs/reviews/security-review-instance2.md`
- `specs/reviews/security-review-instance3.md`
- `specs/reviews/security-review.md`
- `specs/reviews/security-scan.json`
- `specs/reviews/security-verdict-instance2.json`
- `specs/reviews/security-verdict-instance3.json`
- `specs/reviews/security-verdict.json`
- `specs/reviews/sensor-checks.json`
- `specs/reviews/sensor-waivers-verdict.json`
- `specs/reviews/sensor-waivers.json`
- `specs/reviews/slo-verdict-poisoned-evidence.json`
- `specs/reviews/slo-verdict.json`
- `specs/reviews/spdd-sync.json`
- `specs/reviews/spec-approval.json`
- `specs/reviews/test-approval.json`
- `specs/reviews/test-grounding.json`
- `specs/reviews/verification-matrix-verdict.json`
- `specs/reviews/walkthrough.json`
- `specs/reviews/walkthrough.md`
- `specs/stories/E1-S1.md`
- `specs/stories/E1-S2.md`
- `specs/stories/E10-S1.md`
- `specs/stories/E11-S1.md`
- `specs/stories/E11-S2.md`
- `specs/stories/E12-S1.md`
- `specs/stories/E13-S1.md`
- `specs/stories/E14-S1.md`
- `specs/stories/E15-S1.md`
- `specs/stories/E15-S2.md`
- `specs/stories/E15-S3.md`
- `specs/stories/E15-S4.md`
- `specs/stories/E16-S1.md`
- `specs/stories/E17-S1.md`
- `specs/stories/E2-S1.md`
- `specs/stories/E3-S1.md`
- `specs/stories/E3-S2.md`
- `specs/stories/E4-S1.md`
- `specs/stories/E4-S2.md`
- `specs/stories/E4-S3.md`
- `specs/stories/E4-S4.md`
- `specs/stories/E5-S1.md`
- `specs/stories/E5-S2.md`
- `specs/stories/E6-S1.md`
- `specs/stories/E6-S2.md`
- `specs/stories/E7-S1.md`
- `specs/stories/E8-S1.md`
- `specs/stories/E9-S1.md`
- `specs/stories/E9-S2.md`
- `specs/stories/E9-S3.md`
- `specs/stories/acceptance-criteria.json`
- `specs/stories/stories.json`
- `specs/stories/story-traces.json`
- `specs/test_artefacts/ac-index.json`
- `specs/test_artefacts/test-plan.md`
- `specs/test_artefacts/test-traces.json`
- `specs/test_artefacts/verification-matrix.json`
- `sprint-contracts/A.json`
- `uv.lock`

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
  - 🟠 **WARN** (high): CR-307
  - 🟠 **WARN** (medium): CR-308
- `backend/src/api/middleware.py`
  - 🔴 **BLOCK** (high): CR-301
  - ⚪ **INFO** (high): CR-314
  - ⚪ **INFO** (medium): CR-315
  - ⚪ **INFO** (high): CR-316
  - ⚪ **INFO** (medium): CR-318
- `backend/src/api/platform/routes.py`
  - 🟠 **WARN** (high): CR-302
  - 🟠 **WARN** (high): CR-309
  - ⚪ **INFO** (high): CR-317
- `backend/src/api/serializers.py`
  - 🟠 **WARN** (high): CR-306

### 6. Config & infrastructure

- `backend/src/config/delinquency.py`
- `backend/src/config/logging.py`
  - 🟠 **WARN** (high): CR-305
  - 🟠 **WARN** (high): CR-310
- `backend/src/config/settings.py`
- `frontend/eslint.config.js`
- `frontend/package.json`
- `frontend/tsconfig.json`
- `frontend/vite.config.ts`

### 7. Tests

- `frontend/tests/unit/money.test.ts`

### 8. Docs & specs

- `.claude/state/failures.md`
- `.claude/state/handoff/gate-group-A.md`
- `.claude/state/iteration-log.md`
- `docs/CODEBASE.md`
- `specs/brownfield/code-graph.json`
- `specs/brownfield/code-graph.meta.json`
- `specs/bundles/E1-S1.json`
- `specs/bundles/E1-S2.json`
- `specs/bundles/E10-S1.json`
- `specs/bundles/E11-S1.json`
- `specs/bundles/E11-S2.json`
- `specs/bundles/E12-S1.json`
- `specs/bundles/E13-S1.json`
- `specs/bundles/E14-S1.json`
- `specs/bundles/E15-S1.json`
- `specs/bundles/E15-S2.json`
- `specs/bundles/E15-S3.json`
- `specs/bundles/E15-S4.json`
- `specs/bundles/E16-S1.json`
- `specs/bundles/E17-S1.json`
- `specs/bundles/E2-S1.json`
- `specs/bundles/E3-S1.json`
- `specs/bundles/E3-S2.json`
- `specs/bundles/E4-S1.json`
- `specs/bundles/E4-S2.json`
- `specs/bundles/E4-S3.json`
- `specs/bundles/E4-S4.json`
- `specs/bundles/E5-S1.json`
- `specs/bundles/E5-S2.json`
- `specs/bundles/E6-S1.json`
- `specs/bundles/E6-S2.json`
- `specs/bundles/E7-S1.json`
- `specs/bundles/E8-S1.json`
- `specs/bundles/E9-S1.json`
- `specs/bundles/E9-S2.json`
- `specs/bundles/E9-S3.json`
- `specs/design/amendments/e15-s4-observability-contract.md`
- `specs/design/amendments/group-a-gate-remediation.md`
- `specs/design/amendments/group-a-implementation-sync.md`
- `specs/design/component-map.md`
- `specs/design/reasons-canvas.md`
- `specs/reviews/canvas-semantic-review.md`
- `specs/reviews/canvas-sync-check-productscope.md`
- `specs/reviews/canvas-sync-check.md`
- `specs/reviews/code-review-groupA.md`
- `specs/reviews/code-review-verdict.json`
- `specs/reviews/code-review.md`
- `specs/reviews/contract-freeze.json`
- `specs/reviews/design-approval.json`
- `specs/reviews/eval-failures-001.json`
- `specs/reviews/eval-failures-002.json`
- `specs/reviews/evaluator-evidence-instance2.json`
- `specs/reviews/evaluator-evidence-instance3.json`
- `specs/reviews/evaluator-evidence.json`
- `specs/reviews/evaluator-report-instance2.md`
- `specs/reviews/evaluator-report-instance3.md`
- `specs/reviews/evaluator-report.md`
- `specs/reviews/evidence-integrity-verdict.json`
- `specs/reviews/gate-checks.json`
- `specs/reviews/local-regression-gate-verdict.json`
- `specs/reviews/metrics-forgery-evidence.txt`
- `specs/reviews/observability-gate.md`
- `specs/reviews/observability-verdict.json`
- `specs/reviews/ownership-check.json`
- `specs/reviews/perf-smell-gate.md`
- `specs/reviews/perf-smell-verdict.json`
- `specs/reviews/plan-seal.json`
- `specs/reviews/quality-card.json`
- `specs/reviews/quality-card.md`
- `specs/reviews/regression-gate-verdict-groupA-live.json`
- `specs/reviews/regression-gate-verdict-nobaseline.json`
- `specs/reviews/regression-gate-verdict-registryinvocation.json`
- `specs/reviews/regression-gate-verdict.json`
- `specs/reviews/reverify-votes.json`
- `specs/reviews/review-context-pack.md`
- `specs/reviews/security-review-instance2.md`
- `specs/reviews/security-review-instance3.md`
- `specs/reviews/security-review.md`
- `specs/reviews/security-scan.json`
- `specs/reviews/security-verdict-instance2.json`
- `specs/reviews/security-verdict-instance3.json`
- `specs/reviews/security-verdict.json`
- `specs/reviews/sensor-checks.json`
- `specs/reviews/sensor-waivers-verdict.json`
- `specs/reviews/sensor-waivers.json`
- `specs/reviews/slo-verdict-poisoned-evidence.json`
- `specs/reviews/slo-verdict.json`
- `specs/reviews/spdd-sync.json`
- `specs/reviews/spec-approval.json`
- `specs/reviews/test-approval.json`
- `specs/reviews/test-grounding.json`
- `specs/reviews/verification-matrix-verdict.json`
- `specs/reviews/walkthrough.json`
- `specs/reviews/walkthrough.md`
- `specs/stories/E1-S1.md`
- `specs/stories/E1-S2.md`
- `specs/stories/E10-S1.md`
- `specs/stories/E11-S1.md`
- `specs/stories/E11-S2.md`
- `specs/stories/E12-S1.md`
- `specs/stories/E13-S1.md`
- `specs/stories/E14-S1.md`
- `specs/stories/E15-S1.md`
- `specs/stories/E15-S2.md`
- `specs/stories/E15-S3.md`
- `specs/stories/E15-S4.md`
- `specs/stories/E16-S1.md`
- `specs/stories/E17-S1.md`
- `specs/stories/E2-S1.md`
- `specs/stories/E3-S1.md`
- `specs/stories/E3-S2.md`
- `specs/stories/E4-S1.md`
- `specs/stories/E4-S2.md`
- `specs/stories/E4-S3.md`
- `specs/stories/E4-S4.md`
- `specs/stories/E5-S1.md`
- `specs/stories/E5-S2.md`
- `specs/stories/E6-S1.md`
- `specs/stories/E6-S2.md`
- `specs/stories/E7-S1.md`
- `specs/stories/E8-S1.md`
- `specs/stories/E9-S1.md`
- `specs/stories/E9-S2.md`
- `specs/stories/E9-S3.md`
- `specs/stories/acceptance-criteria.json`
- `specs/stories/stories.json`
- `specs/stories/story-traces.json`
- `specs/test_artefacts/ac-index.json`
- `specs/test_artefacts/test-plan.md`
- `specs/test_artefacts/test-traces.json`
- `specs/test_artefacts/verification-matrix.json`

### 9. Other

- `.claude/state/budget-start`
- `.claude/state/current-risk-tier`
- `.claude/state/current-task`
- `.claude/state/eval-i1/attack.log`
- `.claude/state/eval-i1/f003.body`
- `.claude/state/eval-i1/f003.hdr`
- `.claude/state/eval-i1/f003.lines`
- `.claude/state/eval-i1/f004.body`
- `.claude/state/eval-i1/f004.hdr`
- `.claude/state/eval-i1/f004.lines`
- `.claude/state/eval-i1/f005.timings`
- `.claude/state/eval-i1/features.json.bak`
- `.claude/state/eval-i1/harness.log`
- `.claude/state/eval-i1/harness.py`
- `.claude/state/eval-i1/logcheck.js`
- `.claude/state/eval-i1/metrics-forged.txt`
- `.claude/state/eval-i1/metrics-poisoned.txt`
- `.claude/state/eval-i1/metrics.txt`
- `.claude/state/eval-i1/money.py.bak`
- `.claude/state/eval-i1/pii-window.log`
- `.claude/state/eval-i1/promcheck.js`
- `.claude/state/eval-i1/update-features.js`
- `.claude/state/eval-i1/vm003.lines`
- `.claude/state/eval-i1/vm004.body`
- `.claude/state/eval-i1/vm004.hdr`
- `.claude/state/g3eval2-500.txt`
- `.claude/state/g3eval2-body005.json`
- `.claude/state/g3eval2-chatty.txt`
- `.claude/state/g3eval2-conc.txt`
- `.claude/state/g3eval2-h003.txt`
- `.claude/state/g3eval2-h004.txt`
- `.claude/state/g3eval2-injlines.txt`
- `.claude/state/g3eval2-lines003.txt`
- `.claude/state/g3eval2-lines004.txt`
- `.claude/state/g3eval2-perf.txt`
- `.claude/state/g3eval2-piiboom.txt`
- `.claude/state/g3eval2_probe.py`
- `.claude/state/g3eval3-expected-ids.json`
- `.claude/state/gate-receipt.json`
- `.claude/state/navigation-status.json`
- `.claude/state/phase-cost-cursor.json`
- `.claude/state/phase-cost.json`
- `.claude/state/red-phase-presnap.json`
- `.claude/state/risk-envelope.json`
- `.claude/state/task-completion-receipt.json`
- `.claude/state/task-envelope-history/267760e13e6cda739f0835ffdff9140b7b2ddd3eb3bf1ce64c0dd7adeecbf13d.json`
- `.claude/state/task-envelope-history/4034d3db61bdff6b223fd631480932d03510d6d52a32870b4bf0c2ee702e05da.json`
- `.claude/state/task-envelope-history/62e4d6055406f528dbaf106b4c2490ab209a6769c21f981f45bcead78a5a94ed.json`
- `.claude/state/task-envelope-history/7ae6bff4fdcfe4e5e350b8cc6b4823a2f49a8a7805e97359a800301b681b5394.json`
- `.claude/state/task-envelope-history/8914ad672f478b7a255bfa5bae84a4f42f262d43034b9944be6525ac67b9e330.json`
- `.claude/state/task-envelope-history/9a1142eaa81a33a48bcc68d2252eefe06fb3db52e50f19947aa449da5d909a0d.json`
- `.claude/state/task-envelope-history/b0a253ab010f74d11bb8d478187ee07dbd6f37f63b7637cbfd40acc8e8eff5bc.json`
- `.claude/state/task-envelope-history/b24a95b810c8614edc100467573c4435f8ec62962945fb944182f44df8a260f8.json`
- `.claude/state/task-envelope-history/ebce3b61ee635eb8cc8f12d7b9694b33b719a76c5e05eeaa634f09bc416b8f7e.json`
- `.claude/state/task-envelope-history/eda892d10c64151b32bbc2480478f10210ff8346da6a9d222f34b97ad71a715d.json`
- `.claude/state/task-envelope-history/fb41b097c331594e1807274e9ee9b47320e6a57f83ca3cd62ba155ba90598404.json`
- `.claude/state/task-envelope.json`
- `.claude/state/work-claims/group__A.json`
- `.gitignore`
- `backend/src/__init__.py`
- `backend/src/types/delinquency.py`
- `backend/src/types/errors.py`
- `backend/src/types/money.py`
- `backend/tests/__init__.py`
- `backend/tests/architecture/test_no_float_money.py`
- `backend/tests/architecture/test_observability_contract.py`
  - 🟠 **WARN** (high): CR-303
  - 🟠 **WARN** (high): CR-312
- `backend/tests/conftest.py`
  - 🟠 **WARN** (medium): CR-313
- `backend/tests/unit/test_bucket_ladder.py`
- `backend/tests/unit/test_correlation_id.py`
- `backend/tests/unit/test_error_envelope.py`
- `backend/tests/unit/test_health_probe.py`
- `backend/tests/unit/test_log_redaction.py`
  - 🟠 **WARN** (high): CR-311
- `backend/uv.lock`
- `claude-progress.txt`
- `features.json`
- `frontend/package-lock.json`
- `frontend/src/types/money.ts`
  - 🟠 **WARN** (high): CR-304
- `frontend/src/ui/components/MoneyText.tsx`
- `project-manifest.json`
- `sprint-contracts/A.json`
- `uv.lock`

## High-signal findings

- 🔴 **BLOCK** `backend/src/api/middleware.py`: CR-301
- 🟠 **WARN** `backend/src/api/platform/routes.py`: CR-302
- 🟠 **WARN** `backend/tests/architecture/test_observability_contract.py`: CR-303
- 🟠 **WARN** `frontend/src/types/money.ts`: CR-304
- 🟠 **WARN** `backend/src/config/logging.py`: CR-305
- 🟠 **WARN** `backend/src/api/serializers.py`: CR-306
- 🟠 **WARN** `backend/src/api/errors.py`: CR-307
- 🟠 **WARN** `backend/src/api/errors.py`: CR-308
- 🟠 **WARN** `backend/src/api/platform/routes.py`: CR-309
- 🟠 **WARN** `backend/src/config/logging.py`: CR-310
- 🟠 **WARN** `backend/tests/unit/test_log_redaction.py`: CR-311
- 🟠 **WARN** `backend/tests/architecture/test_observability_contract.py`: CR-312
- 🟠 **WARN** `backend/tests/conftest.py`: CR-313

## Blast radius (from code-graph)

_No graph neighbors (missing graph or isolated files)._

## 5-minute human review script

1. Read **Intent** and confirm the PR matches the story/AC.
2. Walk **Logical change groups** top to bottom — skip alphabetical GitHub view.
3. Open every 🔴 BLOCK and 🟠 WARN; dismiss only with evidence.
4. Spot-check one happy path and one failure path in tests (group 7).
5. Confirm `specs/reviews/quality-card.md` is PASS and wiki links are fresh.
6. A human merges. The agent pre-read never approves or merges.
