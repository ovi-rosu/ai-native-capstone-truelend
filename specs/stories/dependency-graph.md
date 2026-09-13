# Dependency Graph

## Group A

| Story | Title | Layer | Points | Dependencies |
|---|---|---|---|---|
| E15-S1 | Structured JSON logging, correlation id propagation, PII redaction and health endpoint | Config | 5 | — |
| E9-S1 | Money value type with fixed-point decimal arithmetic | Types | 3 | — |
| E11-S1 | Delinquency bucket ladder over days past due | Types | 3 | — |

## Group B

| Story | Title | Layer | Points | Dependencies |
|---|---|---|---|---|
| E15-S2 | Self-hosted Docker Compose stack and one-way layer dependency test | Config | 3 | E15-S1 (behavior) |
| E1-S1 | Tracer M1: log in, list products, edit a threshold and activate a new policy version | API | 5 | E15-S1 (behavior), E9-S1 (contract) |

## Group C

| Story | Title | Layer | Points | Dependencies |
|---|---|---|---|---|
| E1-S2 | Role boundary enforced at the controller layer with full action audit | API | 5 | E1-S1 (behavior) |
| E3-S1 | Append-only policy version store and destructive migration lint | Repository | 5 | E9-S1 (contract), E1-S1 (behavior) |

## Group D

| Story | Title | Layer | Points | Dependencies |
|---|---|---|---|---|
| E2-S1 | Loan product catalog with three products bound to distinct versioned rule sets | Service | 5 | E3-S1 (data), E1-S1 (behavior) |
| E16-S1 | Architecture invariant test registry and agent provenance evidence | Service | 3 | E15-S2 (behavior), E3-S1 (behavior) |

## Group E

| Story | Title | Layer | Points | Dependencies |
|---|---|---|---|---|
| E3-S2 | Policy Editor activates a new immutable policy version without a restart | UI | 5 | E2-S1 (behavior), E1-S2 (behavior) |
| E4-S1 | Tracer M2: submit an application, score it and return a decision | API | 5 | E2-S1 (behavior), E1-S2 (behavior) |
| E15-S3 | Runtime SLO load harness and ratchet over the read-heavy endpoint registry | API | 2 | E2-S1 (behavior) |

## Group F

| Story | Title | Layer | Points | Dependencies |
|---|---|---|---|---|
| E4-S2 | Application intake with product derived document checklist and submission time policy pinning | Service | 5 | E4-S1 (behavior) |

## Group G

| Story | Title | Layer | Points | Dependencies |
|---|---|---|---|---|
| E4-S3 | Apply screen for product selection, applicant details and checklist display | UI | 3 | E4-S2 (behavior) |
| E4-S4 | Minimum income threshold rejects submission with PolicyViolationException | Service | 3 | E4-S2 (behavior) |
| E5-S1 | Deterministic credit scoring stub over age, income and credit history flags | Service | 3 | E4-S2 (behavior) |
| E6-S1 | Document verification queue with VERIFIED and REJECTED transitions | API | 5 | E4-S2 (behavior), E1-S2 (behavior) |

## Group H

| Story | Title | Layer | Points | Dependencies |
|---|---|---|---|---|
| E5-S2 | Underwriting decision with reason codes from the pinned policy version | Service | 5 | E5-S1 (behavior) |
| E17-S1 | Accessibility harness and WCAG 2.1 AA ratchet over the customer-facing screen registry | UI | 5 | E4-S3 (behavior) |

## Group I

| Story | Title | Layer | Points | Dependencies |
|---|---|---|---|---|
| E6-S2 | Underwriter workbench queue and MANUAL_REVIEW decision review screen | UI | 5 | E5-S2 (behavior), E6-S1 (behavior) |
| E7-S1 | Admin console application list with filters and audited AUTO_REJECT override | UI | 5 | E5-S2 (behavior), E1-S2 (behavior), E15-S3 (contract) |
| E8-S1 | Customer application tracking view | UI | 3 | E5-S2 (behavior), E6-S1 (behavior), E17-S1 (contract) |
| E9-S2 | Tracer M3: approve, disburse and post a first repayment | API | 5 | E5-S2 (behavior) |

## Group J

| Story | Title | Layer | Points | Dependencies |
|---|---|---|---|---|
| E9-S3 | EMI computation and append-only repayment schedule generation | Service | 8 | E9-S2 (behavior), E9-S1 (contract) |

## Group K

| Story | Title | Layer | Points | Dependencies |
|---|---|---|---|---|
| E10-S1 | Disbursement records the released amount and a stub funding source | Service | 5 | E9-S3 (behavior) |
| E12-S1 | Idempotent as-of-date end-of-day delinquency recalculation | Service | 5 | E11-S1 (contract), E9-S3 (data) |

## Group L

| Story | Title | Layer | Points | Dependencies |
|---|---|---|---|---|
| E11-S2 | Repayment posting reduces outstanding principal and recalculates the delinquency bucket | Service | 8 | E10-S1 (behavior), E11-S1 (contract) |

## Group M

| Story | Title | Layer | Points | Dependencies |
|---|---|---|---|---|
| E13-S1 | Customer loan view with schedule, outstanding principal, bucket and repayment posting | UI | 5 | E11-S2 (behavior), E17-S1 (contract), E15-S3 (contract) |
| E14-S1 | Portfolio dashboard by product, delinquency bucket and total overdue | UI | 5 | E11-S2 (data), E1-S2 (behavior), E15-S3 (contract) |

## Ownership Clusters

- C1: E1-S1, E1-S2, E10-S1, E11-S2, E14-S1, E15-S1, E15-S2, E16-S1, E2-S1, E3-S1, E3-S2, E4-S1, E4-S2, E5-S1, E5-S2, E6-S1, E6-S2, E7-S1, E8-S1, E9-S2, E9-S3 (103 pts)
- C2: E11-S1, E12-S1 (8 pts)
- C3: E13-S1, E15-S3 (7 pts)
- C4: E17-S1, E4-S3 (8 pts)
- C5: E4-S4 (3 pts)
- C6: E9-S1 (3 pts)
