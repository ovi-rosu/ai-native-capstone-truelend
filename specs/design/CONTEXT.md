# Context

Domain glossary for TrueLend — a configurable loan-origination and servicing
platform. These are the ubiquitous-language terms: every entity in
`data-models.schema.json`, every key under `components.schemas` in
`api-contracts.schema.json`, and every name in the REASONS Canvas `Entities`
section must resolve to a term below.

A new domain concept goes in this file **first**, then into the schema. Never
invent a name in a schema alone — `vocabulary-check.js` treats an undocumented
candidate as a hard block.

Grouping lines below are bounded contexts, written bold rather than as
headings: the sensor parses every `###` under `## Terms` as a glossary term, so
only real terms use that level.

## Terms

**Policy & Catalog** — core, high volatility. The configurability surface.

### Loan Product
A lendable offering in the catalog — Personal, Vehicle or Education. Identified by a stable product code. Carries no thresholds itself; its rules live in its Policy Versions.

### Policy Version
An immutable, numbered rule set for exactly one Loan Product. Never updated or deleted; a change produces a new version.

### Active Policy Version
The single Policy Version currently in force for a Loan Product. Activation takes effect without a restart and never retargets an application already submitted.

### Policy Rules
The validated threshold document carried by a Policy Version — minimum income, age band, minimum credit score, tenure band, interest rate, and the version's Reason Codes.

### Threshold
One configurable bound inside Policy Rules. Changing a Threshold means publishing a new Policy Version, not editing code.

### Reason Code
A stable code plus human-readable text, declared by a Policy Version, explaining why an Underwriting Decision came out the way it did. A decision may only cite Reason Codes declared by the Policy Version named on its application.

### Required Document
A document type a Loan Product demands of an applicant, declared by the Policy Version.

### Document Checklist
The set of Required Documents generated for one Loan Application at submission, from the Policy Version pinned to it.

**Origination** — core, medium volatility. Application intake through decision.

### Applicant
The person applying. Exactly one per Loan Application; co-applicants and guarantors are out of scope.

### Loan Application
An Applicant's request for a specific Loan Product. Pins its Policy Version at submission and carries an Application Status.

### Application Status
The lifecycle state of a Loan Application — submitted, awaiting documents, under review, manual review, approved, rejected, disbursed. A mutable projection of the append-only facts recorded against the application. Per D-L, MANUAL_REVIEW is both a Decision Outcome and the Application Status that mirrors it: an application whose latest Underwriting Decision outcome is MANUAL_REVIEW carries MANUAL_REVIEW as its status, and the workbench filters on it as a plain status.

### Application Submission
The inbound payload that creates a Loan Application: applicant details, product code, requested amount and tenure, declared income.

### Credit Score
A deterministic score derived from age, income and credit-history flags by the Credit Score Stub. Not a bureau score.

### Credit Score Stub
The in-process stand-in for a credit bureau. Deterministic for identical inputs; no external call and no provider credentials.

### Application Document
One uploaded document attached to a Loan Application, carrying a Document Verification Status.

### Document Verification Status
An Underwriter ruling on one Application Document — pending, verified, or rejected with a reason.

### Document Verification Queue
The Underwriter work list of Loan Applications with Application Documents still awaiting verification.

### Underwriting Decision
An append-only record of a Decision Outcome plus its Reason Codes, evaluated against the Policy Version pinned to the Loan Application. An Override supersedes rather than edits it.

### Decision Outcome
One of AUTO_APPROVE, AUTO_REJECT or MANUAL_REVIEW.

### Override
An Admin reversal of an AUTO_REJECT, recorded as a new Underwriting Decision that supersedes the prior one and carries a comment, a Reason Code and an Audit Entry.

### Policy Violation
The rejection of an Application Submission that breaches a Threshold outright — declared income below the product minimum. Surfaces as PolicyViolationException.

**Servicing** — core, low-to-medium volatility. Disbursement through repayment.

### Loan
A disbursed Loan Application. Carries Outstanding Principal and a Delinquency Bucket as maintained projections.

### Disbursement
The append-only record that released a Loan principal — the released amount, the Funding Source and the disbursement date.

### Funding Source
The stubbed origin of disbursed money. Recorded for audit; no payment rail is called.

### Repayment Schedule
The immutable set of Installments generated for a Loan at approval from the EMI formula. Never updated or deleted.

### Installment
One dated row of a Repayment Schedule — its due date, principal component, interest component and EMI.

### EMI
Equated Monthly Installment: the level payment computed from principal, periodic interest rate and tenure.

### Total Payable
The sum of every Installment principal and interest across a Repayment Schedule. The per-installment components sum to it exactly.

### Rounding Residual
The difference between the unrounded EMI stream and its 2-decimal representation, absorbed wholly by the final Installment so the Repayment Schedule sums exactly to Total Payable.

### Repayment
An append-only posted payment against a Loan. Reduces Outstanding Principal and triggers recalculation of the Delinquency Bucket.

### Outstanding Principal
The principal not yet repaid on a Loan. A stored projection of Disbursement minus the principal components of its Repayments, reconcilable by replay.

**Delinquency & Portfolio** — core, medium volatility. Ageing and reporting.

### Days Past Due
Whole days between the As-Of Date and the due date of the Loan oldest unpaid Installment. Zero when no Installment is overdue.

### Delinquency Bucket
The ageing band derived from Days Past Due — CURRENT, DPD-30, DPD-60, DPD-90 or NPA. Status only; nothing is charged for lateness.

### As-Of Date
The date an End-Of-Day Run evaluates against. Makes the run replayable and its result independent of wall-clock time.

### End-Of-Day Run
The idempotent, As-Of-Date-parameterised operation that recalculates the Delinquency Bucket of every active Loan. Running it twice for one As-Of Date yields the same result.

### Portfolio Summary
The Admin reporting view: loan count and value by Loan Product, count and value per Delinquency Bucket, and total overdue.

**Identity & Audit** — supporting, low volatility. Cross-cutting enforcement.

### User
An authenticated actor holding exactly one Role.

### Role
Exactly one of CUSTOMER, UNDERWRITER or ADMIN. Determines which surfaces a User may reach; enforced at the controller layer.

### Audit Entry
An append-only record of a privileged action — the acting User id, the action, the affected entity and a timestamp. Every Underwriter and Admin action writes one.

### Correlation Id
The request-scoped identifier carried by every structured log line emitted while handling one request.

## Invariants

- A Policy Version, once activated, is never mutated: no update and no delete, in code or in migration.
- A Repayment Schedule and its Installments are never mutated after generation.
- An Underwriting Decision is never edited; an Override is a new superseding record.
- An Underwriting Decision cites only Reason Codes declared by the Policy Version pinned to its Loan Application.
- A Loan Application Policy Version is pinned at submission and never retargeted by a later activation.
- Money is fixed-point decimal at 2 decimal places end to end, never floating-point.
- Per-Installment principal plus interest sums exactly to Total Payable, with the Rounding Residual in the final Installment.
- An End-Of-Day Run is idempotent for a given As-Of Date.
- Synthetic identifiers (PAN, Aadhaar) and salary-document content never appear in a log line.

## Out of Scope Terms

- **Late Fee, Penal Interest, Collections, Write-Off** — delinquency is status only; nothing is charged for lateness and no recovery process exists.
- **Co-Applicant, Guarantor** — one Applicant per Loan Application.
- **Top-Up, Restructuring, Foreclosure, Prepayment Quote, Early Settlement** — no mid-life modification of a disbursed Loan.
- **KYC Check, AML Screening, Credit Bureau** — synthetic PAN and Aadhaar values are captured as application data only and are never verified.
- **Notification, Email, SMS** — no customer notifications of any kind.
- **Electronic Signature, Loan Agreement** — no signed artifact is produced.
- **Currency, Exchange Rate** — single currency only.
