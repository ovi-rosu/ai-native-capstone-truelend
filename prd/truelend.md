# PRD: TrueLend — Configurable Loan Origination & Servicing

## 1. Problem & Goal

Horizon Bank cannot launch a loan product without an engineering release. Every
new product — a different tenure band, rate, income floor, or required-document
set — and every change to credit policy is expressed in code, so the business
cannot test a product idea without engineering capacity, and a policy change
that should take an afternoon takes a release cycle.

TrueLend makes the product and its credit policy configuration rather than code.
Success is observable in one sentence: a business user changes a product's
thresholds in the Policy Editor, that change becomes the active policy version
with no code change and no restart, and a customer can then apply against it,
receive a decision with reason codes traceable to that policy version, be
disbursed, and repay on a generated schedule.

## 2. Users & Jobs-to-be-done

| User | Job |
|---|---|
| Customer | Apply for a loan, see what is missing, track the decision and its reasons, view the schedule and repay |
| Underwriter | Work the application queue, verify documents, review MANUAL_REVIEW cases and decide |
| Admin | Configure products and policy versions, list and filter applications, override an AUTO_REJECT with reason, disburse, run end-of-day, watch the portfolio |

## 3. Functional Requirements

Ids FR-01…FR-10 correspond one-for-one to capstone acceptance criteria
AC-01…AC-10; the `AC-NN` label is retained in each so every test can reference
its criterion identifier as required by NFR-08. FR-11…FR-17 cover functional
scope named in capstone section 6 that carries no AC of its own.

- **FR-01** (AC-01) The loan product catalog offers at least 3 products — Personal, Vehicle and Education — each bound to its own distinct rule set sourced from a versioned policy record.
- **FR-02** (AC-02) A customer can submit a loan application against a chosen product, and the system generates that product's required-document checklist.
- **FR-03** (AC-03) A credit-scoring stub returns a deterministic score computed from age, income and credit-history flags.
- **FR-04** (AC-04) An underwriting decision returns AUTO_APPROVE, AUTO_REJECT or MANUAL_REVIEW together with reason codes referenced from the active policy version.
- **FR-05** (AC-05) Application submission fails with PolicyViolationException when declared income is below the minimum income threshold for the selected product.
- **FR-06** (AC-06) An underwriter can mark each document in the document-verification queue VERIFIED or REJECTED with a reason.
- **FR-07** (AC-07) On approval, a repayment schedule is generated using the EMI formula, with per-installment principal and interest summing to total payable.
- **FR-08** (AC-08) Disbursement records the released amount and the funding source, the funding source being a stub.
- **FR-09** (AC-09) Posting a repayment reduces outstanding principal and recalculates the loan's delinquency bucket across CURRENT, DPD-30, DPD-60, DPD-90 and NPA.
- **FR-10** (AC-10) An admin can list applications, filter them by status and by product, and override an AUTO_REJECT with a comment and a reason code, with the override written to the audit trail.
- **FR-11** A customer can track a submitted application: its status, outstanding required documents, the decision, and the decision's reason codes.
- **FR-12** A customer can view a disbursed loan's repayment schedule, outstanding principal and current delinquency bucket, and post a repayment against it.
- **FR-13** The Policy Editor lets an authorised user change a product's income, age, score, tenure and rate thresholds without a code change, producing a new immutable policy version that becomes the active version without a restart.
- **FR-14** An idempotent, as-of-date-parameterised end-of-day operation recalculates delinquency buckets across all active loans, and produces the same result when run twice for the same date.
- **FR-15** An admin dashboard reports the portfolio by product, the count and value of loans in each delinquency bucket, and total overdue.
- **FR-16** Users authenticate and act under exactly one of the roles CUSTOMER, UNDERWRITER or ADMIN, and each surface is reachable only by its permitted roles.
- **FR-17** The underwriter workbench presents the queue of applications awaiting action and a decision-review screen for MANUAL_REVIEW cases.

## 4. Non-Functional Requirements

- **NFR-01** Money — principal, interest and EMI — is computed in fixed-point decimal and never in floating-point; monetary amounts carry 2 decimal places.
- **NFR-02** Approved policy versions and generated repayment schedules are append-only: 0 update and 0 delete operations against either, in code or in migration.
- **NFR-03** Synthetic identifiers (PAN, Aadhaar) and salary-document content are never written to logs: 0 occurrences in any emitted log line.
- **NFR-04** The authentication boundary is enforced at the controller layer, and 100% of underwriter and admin actions are audited with the acting user id and a timestamp.
- **NFR-05** Database migrations and policy migrations are append-only: 0 destructive migrations.
- **NFR-06** Logs are structured JSON, and 100% of request-scoped log lines carry a request correlation id.
- **NFR-07** The health endpoint returns 200 within 1 second of a successful startup.
- **NFR-08** Architecture rules are enforced as automated tests, at least 1 test per invariant — including that a policy version cannot be mutated and that the EMI principal-rate-tenure invariant holds.
- **NFR-09** API responses meet the project runtime SLO: p95 under 500 ms and an error rate under 1%.
- **NFR-10** Customer-facing screens — Apply, Track and Repay — meet WCAG 2.1 AA.
- **NFR-11** 100% of production code is generated by Claude Code agents under human supervision, with 0 hand-written production lines; the capstone permits no manual coding.
- **NFR-12** The system is self-hosted via Docker Compose over a single Postgres database, with a Python 3.12 FastAPI backend and a TypeScript React-Vite frontend, and respects one-way dependencies across its 6 layers (Types, Config, Repository, Service, API, UI).

## 5. Out of Scope

Every line here is a Forbidden Action the autonomous gate enforces.

- Late fees, penal interest, collections workflow and write-off. Delinquency is status only: buckets are computed, nothing is charged for lateness and no recovery process exists.
- Real money movement and real credit-bureau calls. The funding source (FR-08) and the credit score (FR-03) are stubs; no payment rail, no external bureau, no live provider credentials.
- Native or responsive mobile clients.
- Customer notifications of any kind — no email or SMS on decision, disbursement or due date.
- Electronic signature or a signed loan agreement artifact.
- Multi-currency support. Single currency only.
- Co-applicants, guarantors and joint applications. One applicant per application.
- Loan top-ups, restructuring and any mid-life modification of a disbursed loan.
- KYC/AML identity verification against external registries. Synthetic PAN and Aadhaar values are captured as application data only and are never verified.
- Early settlement, foreclosure and prepayment quotes.

## 6. Acceptance / Done

- **FR-01** → `GET /products` returns at least 3 products (Personal, Vehicle, Education); each carries a policy version id, and the three policy versions hold different threshold values.
- **FR-02** → Submitting an application returns a persisted application in SUBMITTED state whose required-document checklist matches the selected product's policy version, item for item.
- **FR-03** → The same age, income and credit-history-flag input returns the identical score on repeated calls, and two inputs differing only in credit-history flags return different scores.
- **FR-04** → The decision response carries a decision of AUTO_APPROVE, AUTO_REJECT or MANUAL_REVIEW plus at least one reason code, and every returned reason code exists in the policy version named on the application.
- **FR-05** → Submitting with income below the product's minimum threshold returns an error identifying PolicyViolationException and the breached threshold, and persists no application row.
- **FR-06** → Each checklist document can be transitioned to VERIFIED or REJECTED; a REJECTED document stores a non-empty reason, and the queue no longer lists documents already actioned.
- **FR-07** → For a generated schedule, the sum of all installment principal equals the disbursed amount, the sum of principal plus interest across installments equals total payable, and installment count equals the product tenure.
- **FR-08** → After disbursement the loan record holds the released amount and a funding-source identifier, and the loan is in a DISBURSED state with a schedule attached.
- **FR-09** → Posting a repayment lowers outstanding principal by the applied principal portion, and a loan whose oldest unpaid installment is 35 days past due reads as DPD-30 after recalculation.
- **FR-10** → The application list can be filtered to a given status and product and returns only matching rows; overriding an AUTO_REJECT changes the decision and writes an audit entry containing the comment, reason code, acting user id and timestamp.
- **FR-11** → The tracking view for an application shows its current status, every unverified checklist item, and — once decided — the decision with its reason codes.
- **FR-12** → The customer loan view lists every installment with due date and amount, the current outstanding principal and the current bucket; a repayment posted from this view is reflected in the outstanding figure on reload.
- **FR-13** → Saving an edited threshold in the Policy Editor creates a new policy version, leaves the prior version's stored values byte-identical, and a subsequent application decision cites the new version id without any process restart.
- **FR-14** → Running the end-of-day operation for a given as-of date sets each active loan's bucket according to its days past due, and a second run for the same date leaves every bucket and every stored row unchanged.
- **FR-15** → The dashboard returns, per product, the loan count and value per bucket and a total overdue figure that equals the sum of overdue installment amounts across active loans.
- **FR-16** → A request to an underwriter or admin route with a CUSTOMER session is rejected with 403; a request with no session is rejected with 401; each role can reach its own surfaces.
- **FR-17** → The workbench queue lists exactly the applications in SUBMITTED or MANUAL_REVIEW state, and opening a MANUAL_REVIEW case shows its score, reason codes and document verification state.
- **NFR-01** → A property test over (principal, rate, tenure) asserts every money field on a generated schedule is a Decimal quantized to exactly 2 decimal places, and a static check reports 0 float arithmetic operations in money code paths (backend `decimal.Decimal`; frontend integer minor units).
- **NFR-02** → The policy_version and schedule_installment repositories expose no update or delete method (asserted by interface test), and an architecture test reports 0 UPDATE or DELETE statements and 0 ORM mutations against those two tables across `src/` and `migrations/`.
- **NFR-03** → A test submits an application carrying synthetic PAN, Aadhaar and salary-document content, captures every emitted log record, and asserts 0 occurrences of each value; a second assertion confirms the redaction filter is installed on every configured logger.
- **NFR-04** → For every underwriter and admin route enumerated from the OpenAPI schema, a generated test issues the request with no session (expect 401) and with a CUSTOMER session (expect 403); the test asserts it covered 100% of those routes, so a newly added unguarded route fails the suite.
- **NFR-05** → A migration-lint test parses every file under `migrations/` and asserts 0 DROP TABLE, 0 DROP COLUMN and 0 destructive ALTER statements; policy migrations are checked by the same parser.
- **NFR-06** → Every log line emitted while serving a request parses as JSON and carries a non-empty request_id equal to the inbound X-Request-ID header, or to a generated id when the header is absent; the assertion covers 100% of request-scoped lines in the captured buffer.
- **NFR-07** → In the deploy smoke test, after `docker compose up` reports the backend healthy, `GET /health` returns 200 with a JSON body and the measured response time is under 1 second.
- **NFR-08** → An architecture test module holds at least one test per named invariant — policy-version immutability, the EMI principal/rate/tenure invariant, and the one-way dependency rule across Types, Config, Repository, Service, API, UI — and the suite fails if any registered invariant has no corresponding test.
- **NFR-09** → A load run against the read-heavy endpoints (`GET /products`, `GET /applications`, `GET /loans/{id}`, `GET /dashboard`) reports p95 under 500 ms and an error rate under 1%; the measured figures are recorded in the evaluation report.
- **NFR-10** → An automated axe-core scan of the Apply, Track and Repay screens reports 0 WCAG 2.1 AA violations, and keyboard-only traversal of each screen's primary flow completes without a focus trap.
- **NFR-11** → Every production commit on the branch carries agent co-authorship and passes the standard pre-commit gate set, and the `/gate` attestation record is the evidence for 0 hand-written production lines.
- **NFR-12** → `docker compose up` from a clean checkout brings up exactly one Postgres service, the Python 3.12 FastAPI backend and the TypeScript React-Vite frontend, all reporting healthy; the layer-dependency architecture test reports 0 violations of the six-layer one-way rule.

## 7. Milestones

- **M1 — Policy & Catalog** — FR-01, FR-02, FR-13, FR-16. Done when: an ADMIN edits a product threshold in the Policy Editor, a new policy version becomes active with no restart, and the catalog and a generated document checklist reflect it.
- **M2 — Apply & Decide** — FR-03, FR-04, FR-05, FR-06, FR-10, FR-11, FR-17. Done when: a customer submits against each of the 3 products and receives AUTO_APPROVE, AUTO_REJECT or MANUAL_REVIEW with reason codes tied to the active policy version, and an admin override of an AUTO_REJECT appears in the audit trail.
- **M3 — Disburse & Repay** — FR-07, FR-08, FR-09, FR-12, FR-14, FR-15. Done when: an approved application disburses, its schedule's principal plus interest equals total payable, a posted repayment reduces outstanding principal, and the end-of-day operation moves a 35-day-overdue loan to DPD-30 on the portfolio dashboard.

## 8. Traceability

| Capstone criterion | Requirement |
|---|---|
| AC-01 | FR-01 |
| AC-02 | FR-02 |
| AC-03 | FR-03 |
| AC-04 | FR-04 |
| AC-05 | FR-05 |
| AC-06 | FR-06 |
| AC-07 | FR-07 |
| AC-08 | FR-08 |
| AC-09 | FR-09 |
| AC-10 | FR-10 |
| capstone section 6.1 Track | FR-11 |
| capstone section 6.1 Repay | FR-12 |
| capstone section 6.2 Policy Editor | FR-13 |
| capstone section 6.2 Repayment Scheduler | FR-14 |
| capstone section 6.2 Admin Dashboard | FR-15 |
| capstone NFR-04 boundary | FR-16 |
| capstone section 6.2 Underwriter Workbench | FR-17 |

## 9. Stated Assumptions

Decisions taken to write this document. Each is a decision, not a finding — correct any that is wrong before the pipeline consumes this PRD.

- **Source coverage.** Capstone sections 5 and 6 were supplied verbatim and are adopted as the requirement spine. Sections 1–4 and 7 of the capstone document were not supplied; section 1 (Problem & Goal) above and the Out of Scope deny-list are therefore authored here, not adopted.
- **Locale and currency.** Single currency INR, with Indian synthetic identifiers (PAN, Aadhaar) and Indian delinquency vocabulary (DPD, NPA), inferred from capstone NFR-03 and AC-09.
- **Money scale.** 2 decimal places for monetary amounts, following INR's smallest unit.
- **Policy version storage.** Policy versions are immutable records with an active-version pointer, exportable and importable as JSON, with the three seed products' policies committed as JSON. Chosen over runtime-written files so NFR-02 and NFR-05 are provable as architecture tests.
- **End-of-day trigger.** Admin-triggered and command-runnable, as-of-date parameterised, with no background scheduler — so FR-14 and AC-09 are verifiable without wall-clock dependence.
- **Documents.** Document records are metadata only — declared filename, size, checksum, verification status and reason. No binary content is stored, which is what makes NFR-03 structurally true rather than merely observed.
- **Roles.** Exactly three: CUSTOMER, UNDERWRITER, ADMIN. Disbursement (FR-08) sits with ADMIN; there is no separate operations role.
- **Added requirements.** Four NFRs are not present in capstone sections 5–6. NFR-09 adopts the SLO already declared in `project-manifest.json` (`observability.slo`). NFR-11 and NFR-12 adopt the delivery and platform constraints stated in `CLAUDE.md` and `project-manifest.json`, added so the constraint reaches the grounding spine the evaluator checks rather than living only in hook configuration. NFR-10 is the only one of the four that is a new decision.
- **Retention.** No data-retention window is specified, by decision: every identifier in the system is synthetic test data and no real PAN or Aadhaar is ever stored, so a retention period is a production concern outside v1. Recorded as a taxonomy waiver rather than left silent.
- **Inferred deny-list entries.** KYC/AML verification and early settlement/foreclosure were not named as non-goals by the capstone document; they are listed in Out of Scope because no criterion covers them and an unstated non-goal is read as permitted.

## 10. Risks

Recorded so design must answer them. These are risks, not requirements: they add no scope to the spine.

- **R-1 EMI rounding residual.** Fixed-point money at 2 decimal places (NFR-01) and the requirement that per-installment principal plus interest equal total payable (FR-07) are in tension: rounded equal installments rarely sum to the unrounded total. Design must state where the residual is absorbed, or the FR-07 invariant test will be loosened to hide it.
- **R-2 Append-only versus correction.** Policy versions and schedules admit no update or delete (NFR-02, NFR-05), while an override changes a decision (FR-10) and a posted repayment changes outstanding principal and bucket (FR-09). Design must draw the boundary between the immutable artifacts and the mutable loan state explicitly, or the architecture test and the features will collide.
- **R-3 Policy activation with in-flight applications.** A new version becomes active without restart (FR-13), yet every reason code must exist in the policy version named on the application (FR-04). An application decided across an activation must keep citing its own version rather than the newly active one.
- **R-4 Undefined bucket boundaries.** The delinquency buckets are named (FR-09) but no requirement fixes the day ranges, nor where NPA begins. Left unstated, the first agent to write that code picks the thresholds by accident. Design must fix the boundaries against the capstone's intent before FR-09 or FR-14 is implemented.
