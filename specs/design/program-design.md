# Program design

Types, signatures, call stacks and file layout the implementer is bound by.
The human approves this file — not an implied architecture in the stories.

Greenfield: every path below is new, so the diff markers are `+` throughout.
Money is `Decimal` in Python and a quoted 2dp string on the wire (D-G); no
signature below takes or returns a `float`.

## Types

```
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
ApplicationStatus          = SUBMITTED | AWAITING_DOCUMENTS | UNDER_REVIEW | MANUAL_REVIEW | APPROVED | REJECTED | DISBURSED   # 7 states, D-L
DecisionOutcome            = AUTO_APPROVE | AUTO_REJECT | MANUAL_REVIEW
DocumentVerificationStatus = PENDING | VERIFIED | REJECTED
DelinquencyBucket          = CURRENT | DPD_30 | DPD_60 | DPD_90 | NPA      # wire values CURRENT, DPD-30, ...

# backend/src/types/policy.py  (D-A: the whole configurability surface, one Pydantic model)
PolicyRules     { min_income: Money, min_age: int, max_age: int, min_credit_score: int,
                  min_tenure_months: int, max_tenure_months: int, annual_rate_pct: Decimal,
                  reason_codes: list[ReasonCode], required_documents: list[RequiredDocument] }
ReasonCode      { code: str, text: str }
RequiredDocument{ document_type: str, label: str }
Threshold       { kind: str, value: str }        # read-only projection for the Policy Editor form

# backend/src/types/origination.py
Applicant       { full_name: str, date_of_birth: date, declared_income: Money,
                  pan: str, aadhaar: str, credit_history_flags: list[str] }
ApplicationSubmission { product_code: str, requested_amount: Money, requested_tenure_months: int,
                        applicant: Applicant }
LoanApplication { id, product_code, policy_version_id, status: ApplicationStatus,
                  requested_amount: Money, requested_tenure_months, applicant: Applicant,
                  credit_score: int | None, submitted_at }
ApplicationDocument { id, application_id, document_type, status: DocumentVerificationStatus,
                      rejection_reason: str | None, actioned_by, actioned_at }
UnderwritingDecision { id, application_id, policy_version_id, outcome: DecisionOutcome,
                       reason_codes: list[ReasonCode], comment: str | None,
                       supersedes_id: UUID | None, decided_by, decided_at }

# backend/src/types/servicing.py
Loan            { id, application_id, product_code, principal: Money, annual_rate_pct,
                  tenure_months, status, outstanding_principal: Money,
                  delinquency_bucket: DelinquencyBucket, disbursed_at: datetime | None }
RepaymentSchedule { id, loan_id, emi: Money, total_payable: Money, rounding_residual: Money,
                    installments: list[Installment] }
Installment     { id, schedule_id, sequence: int, due_date: date,
                  principal_component: Money, interest_component: Money, emi: Money }
Disbursement    { id, loan_id, released_amount: Money, funding_source: str, disbursed_at }
Repayment       { id, loan_id, amount: Money, applied_principal: Money, applied_interest: Money,
                  posted_at, posted_by }

# backend/src/types/identity.py
User            { id, username, role: Role }
AuditEntry      { id, actor_user_id, action, entity_type, entity_id, comment, reason_code, occurred_at }

# backend/src/types/errors.py            (mapped once, at the API boundary)
PolicyViolation(threshold_kind, configured_value, submitted_value)   -> 422 PolicyViolationException
ReasonCodeNotDeclared(code, policy_version_id)                       -> 409
AlreadyDisbursed(loan_id)                                            -> 409
InvalidTransition(entity, from_state, to_state)                      -> 409
EntityNotFound(entity, id)                                           -> 404

# frontend/src/types/money.ts     (D-G: decimal library, never integer minor units)
Money           = Decimal        # from a decimal library; parsed from the quoted 2dp wire string
parseMoney(wire: string) -> Money
formatMoney(value: Money) -> string
```

## Signatures

```
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
PolicyVersionRepository.activate(policy_version_id) -> None      # writes product.active_policy_version_id
ProductRepository.list() -> list[LoanProduct]
ProductRepository.get(product_code) -> LoanProduct
# origination
ApplicationRepository.insert(submission, policy_version_id, applicant_user_id) -> LoanApplication
ApplicationRepository.get(application_id) -> LoanApplication
ApplicationRepository.list(status=None, product_code=None, applicant_user_id=None) -> list[LoanApplication]
ApplicationRepository.set_status(application_id, status) -> None          # mutable projection (D-E)
ApplicationRepository.set_credit_score(application_id, score) -> None
ChecklistRepository.insert_many(application_id, required_documents) -> list[ApplicationDocument]
ChecklistRepository.list_for_application(application_id) -> list[ApplicationDocument]
ChecklistRepository.list_pending() -> list[ApplicationDocument]
ChecklistRepository.set_verification(document_id, status, rejection_reason, actor) -> ApplicationDocument
DecisionRepository.insert(decision) -> UnderwritingDecision                # no update, no delete
DecisionRepository.latest_for_application(application_id) -> UnderwritingDecision | None
# servicing
LoanRepository.insert(application, terms: LoanTerms) -> Loan
LoanRepository.get(loan_id) -> Loan
LoanRepository.list(applicant_user_id=None) -> list[Loan]
LoanRepository.list_active() -> list[Loan]
LoanRepository.set_outstanding_principal(loan_id, amount: Money) -> None   # projection
LoanRepository.set_delinquency_bucket(loan_id, bucket) -> None             # projection
ScheduleRepository.insert(loan_id, schedule: RepaymentSchedule) -> RepaymentSchedule   # no update/delete
ScheduleRepository.get_for_loan(loan_id) -> RepaymentSchedule
DisbursementRepository.insert(loan_id, released_amount, funding_source) -> Disbursement
DisbursementRepository.get_for_loan(loan_id) -> Disbursement | None
RepaymentRepository.insert(repayment) -> Repayment                         # no update, no delete
RepaymentRepository.list_for_loan(loan_id) -> list[Repayment]
# delinquency / identity
PortfolioRepository.summary() -> PortfolioSummary
UserRepository.get_by_username(username) -> User | None
AuditRepository.insert(entry) -> AuditEntry                                # no update, no delete
AuditRepository.list(entity_type=None, entity_id=None) -> list[AuditEntry]

# ---------- Service (layer 4) ------------------------------------------------
# policy — the only published way to read rules (D-A, D-D)
rules_for_version(policy_version_id) -> PolicyRules
reason_codes_for_version(policy_version_id) -> list[ReasonCode]
active_policy_version(product_code) -> PolicyVersion          # callable ONLY from intake (D-D)
publish_policy_version(product_code, rules: PolicyRules, actor) -> PolicyVersion   # append + activate
list_catalog() -> list[LoanProduct]
# origination
submit(submission: ApplicationSubmission, actor: User) -> LoanApplication
  raises PolicyViolation                                       # E4-S4, transaction rolls back
generate_checklist(application_id, rules: PolicyRules) -> list[ApplicationDocument]
score(applicant: Applicant) -> int                             # deterministic stub, no I/O, no clock
evaluate(application_id, actor: User | None) -> UnderwritingDecision
record_manual_decision(application_id, outcome, reason_code, comment, actor) -> UnderwritingDecision
override_decision(application_id, reason_code, comment, actor) -> UnderwritingDecision  # supersedes_id set
verify_document(application_id, document_id, status, rejection_reason, actor) -> ApplicationDocument
verification_queue() -> list[ApplicationDocument]
# servicing
compute_schedule(terms: LoanTerms, first_due_date: date) -> RepaymentSchedule   # pure, D-C residual
on_approved(application_id) -> Loan                            # creates loan + schedule
disburse(loan_id, actor) -> Disbursement                       # idempotence guard, E10-S1-AC4
ladder_state(loan_id, as_of_date) -> LadderState               # single owner of paid/unpaid derivation
post_repayment(loan_id, amount: Money, actor) -> Repayment     # FIFO; interest-before-principal, D-K
loan_view(loan_id, actor) -> tuple[Loan, RepaymentSchedule]
set_projections(loan_id, outstanding_principal, bucket) -> None # single write path for both projections
# delinquency
recalculate(loan_id, as_of_date) -> LoanAgeing                 # calls config.classify, never its own floors
run_end_of_day(as_of_date) -> EndOfDayRun                      # idempotent per As-Of Date
portfolio_summary() -> PortfolioSummary                         # stored bucket state only (E14-S1-AC4)
# identity
authenticate(username, password) -> str                        # signed JWT: sub, role, exp
current_user(token) -> User
audit(actor, action, entity_type, entity_id, comment=None, reason_code=None) -> AuditEntry

# ---------- API (layer 5) ----------------------------------------------------
require_roles(*roles: Role) -> Callable[..., User]             # the ONE enforcement point (D-F)
money_field_serializer(value: Decimal) -> str                  # the ONE money serializer (D-G)
correlation_id_middleware(request, call_next)
create_app() -> FastAPI                                        # registers middleware + every router
```

## Call stack

```
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
+       servicing.on_approved                       # only when the outcome approves
+         servicing.compute_schedule                # pure: EMI + D-C residual
+         LoanRepository.insert
+         ScheduleRepository.insert
+
+ POST /loans/{loan_id}/repayments                  [CUSTOMER]
+   require_roles(CUSTOMER)
+   servicing.post_repayment
+     servicing.ladder_state                        # FIFO derivation, oldest unpaid installment
+     RepaymentRepository.insert
+     delinquency.recalculate
+       config.classify                             # single owner of the D-B boundaries
+     servicing.set_projections                     # outstanding_principal + delinquency_bucket
+
+ POST /operations/end-of-day                       [ADMIN]
+   require_roles(ADMIN)
+   delinquency.run_end_of_day
+     LoanRepository.list_active
+     servicing.ladder_state                        # same derivation as the repayment path
+     config.classify
+     LoanRepository.set_delinquency_bucket
+     identity.audit
+
+ POST /products/{product_code}/policy-versions     [ADMIN]
+   require_roles(ADMIN)
+   policy.publish_policy_version
+     PolicyRules.model_validate                    # D-A: schema-validated JSONB, no DSL
+     PolicyVersionRepository.insert                 # append, never update
+     PolicyVersionRepository.activate               # hot, no restart (E3-S2-AC3)
+     identity.audit
```

## File tree

```
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
+       policy/         catalog.py policy_accessor.py policy_publisher.py
+       origination/    intake.py scoring.py decision.py override.py document_verification.py
+       servicing/      emi.py schedule.py loan_projection.py installment_ladder.py
+                       disbursement.py repayment.py
+       delinquency/    recalculation.py end_of_day.py portfolio.py
+       identity/       auth.py audit.py
+     api/
+       app.py deps.py middleware.py errors.py serializers.py
+       identity/routes.py policy/routes.py origination/routes.py servicing/routes.py
+       delinquency/routes.py platform/routes.py        # /health and /metrics
+   migrations/     versions/*.py env.py               # Alembic, append-only (E3-S1-AC3)
+   tests/          architecture/ slo/ unit/ integration/ conftest.py
+ frontend/
+   src/
+     types/        money.ts api.ts enums.ts
+     config/       env.ts roles.ts
+     api/          client.ts products.ts applications.ts loans.ts dashboard.ts auth.ts
+     ui/
+       App.tsx  routes.tsx
+       components/  MoneyText.tsx BucketBadge.tsx ReasonCodeList.tsx StatusPill.tsx
+       pages/       Login.tsx Apply.tsx Track.tsx Repay.tsx Workbench.tsx
+                    DecisionReview.tsx AdminApplications.tsx PolicyEditor.tsx Portfolio.tsx
+   tests/          a11y/ unit/
+ docker-compose.yml   Dockerfile.backend   Dockerfile.frontend   init.sh
```

Shared surfaces and their owning story are listed in `component-map.md`; the app
factory (`backend/src/api/app.py`) and the frontend router (`frontend/src/ui/routes.tsx`)
are route registries that later stories append to, not rewrite.
