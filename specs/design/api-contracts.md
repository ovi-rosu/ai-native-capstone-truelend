# API contracts

Base URL `http://localhost:8000`. JSON only; REST only (constitution invariant).
The machine-readable form is `api-contracts.schema.json` (OpenAPI 3.0.3) and is
the contract of record for the evaluator.

## Conventions

- **Money** — every monetary field is a **quoted 2-decimal string** matching
  `^-?[0-9]{1,12}\.[0-9]{2}$` (D-G). Never a JSON number. A client parses it with
  a decimal library; native-number arithmetic on these fields is a contract
  violation, not a style preference.
- **Auth** — `Authorization: Bearer <jwt>`. The token carries `sub`, `role`, `exp`
  (D-F). Enforcement is a single `require_roles(...)` dependency at the router;
  no route hand-rolls a role check and no service-layer code authorizes.
  Ownership *scoping* (a CUSTOMER sees only their own applications and loans) is
  data filtering performed by the service from the authenticated actor — it is
  not authorization and does not move the D-F enforcement point.
- **Correlation id** — every request may carry `X-Request-ID`; the response always
  echoes one back in the same header (`E15-S1-AC3`, `E15-S1-AC4`).
- **Rate limits** — **none**, per **D-O**. v1 ships no throttling middleware in
  the app factory and no per-endpoint quota, so no test asserts one. This
  includes `POST /auth/login`, which therefore has no attempt throttle; paired
  with the absent lockout policy that is a credential-stuffing gap D-O records
  as accepted rather than overlooked.
- **Errors** — one shape for every non-2xx response:
  `{ "error": "<ErrorName>", "detail": "<message>", "context": { ... } }`.
  `401` no or invalid token; `403` wrong role; `404` unknown id; `409` illegal
  transition; `422` validation or `PolicyViolationException`.

## Endpoint index

| Method | Path | Auth | Story |
|---|---|---|---|
| POST | `/auth/login` | public | E1-S1 |
| GET | `/auth/session` | any role | E1-S1 |
| GET | `/health` | public | E15-S1 |
| GET | `/metrics` | public | E15-S1 |
| GET | `/products` | any role | E1-S1, E2-S1 |
| GET | `/products/{product_code}` | any role | E2-S1, E3-S2 |
| POST | `/products/{product_code}/policy-versions` | ADMIN | E1-S1, E3-S2 |
| POST | `/applications` | CUSTOMER | E4-S1, E4-S2, E4-S4, E5-S1, E5-S2 |
| GET | `/applications` | any role (scoped) | E6-S2, E7-S1, E8-S1 |
| GET | `/applications/{application_id}` | any role (scoped) | E8-S1, E6-S2 |
| POST | `/applications/{application_id}/decision` | UNDERWRITER | E6-S2 |
| POST | `/applications/{application_id}/override` | ADMIN | E7-S1 |
| GET | `/documents/queue` | UNDERWRITER | E6-S1 |
| POST | `/applications/{application_id}/documents/{document_id}/verification` | UNDERWRITER | E6-S1 |
| POST | `/loans/{loan_id}/disbursement` | ADMIN | E9-S2, E10-S1 |
| GET | `/loans` | CUSTOMER, ADMIN (scoped) | E13-S1 |
| GET | `/loans/{loan_id}` | CUSTOMER, ADMIN (scoped) | E9-S2, E13-S1 |
| POST | `/loans/{loan_id}/repayments` | CUSTOMER | E9-S2, E11-S2, E13-S1 |
| POST | `/operations/end-of-day` | ADMIN | E12-S1 |
| GET | `/dashboard` | ADMIN | E14-S1 |
| GET | `/audit-entries` | ADMIN | E1-S2, E7-S1 |

Read-heavy endpoints registered with the SLO harness (`E15-S3-AC1`):
`GET /products`, `GET /applications`, `GET /loans/{loan_id}`, `GET /dashboard`.

---

## Identity

### POST /auth/login — public

Request `{ "username": "priya.customer", "password": "<secret>" }`
(inline body schema; there is no CONTEXT.md term for a credential pair, so per
D-H no `components.schemas` key is minted for it).

`200` → `{ "access_token": "<jwt>", "token_type": "bearer", "user": User }`
`401` → invalid credentials. No lockout or attempt counter is specified; none is
recorded in the decisions file.

The token lifetime is `Settings.jwt_ttl_seconds = 3600` (60 minutes), per
**D-M**. With no refresh token issued (D-F) that is the whole session length;
D-M rules out an 8-hour token, a 30-minute token, and adding a refresh token to
compensate.

### GET /auth/session — any authenticated role

`200` → `User` `{ id, username, role }`. Drives the role landing surface
(`E1-S1-AC1`). `401` when the token is absent or invalid.

---

## Policy & Catalog

### GET /products — any authenticated role

`200` → `LoanProduct[]`. Each entry carries `product_code`, `name`,
`active_policy_version_id`, and the active version's rate and tenure band for
display. At least 3 products, Personal / Vehicle / Education among them, and no
two share a policy version (`E2-S1-AC1`, `E2-S1-AC2`).

### GET /products/{product_code} — any authenticated role

`200` → `LoanProduct` with `active_policy_version` (`PolicyVersion`, rules
inlined) so the Policy Editor can populate its form and `E1-S1-AC4` can assert
the read cites the new version id. `404` unknown product code.

### POST /products/{product_code}/policy-versions — ADMIN

Request: `PolicyRules` (`$ref`; all five threshold families plus the version's
reason codes and required documents).

`201` → `PolicyVersion` `{ id, product_code, version_number, rules, created_by, created_at, is_active: true }`
Appends a row and activates it in the same transaction, with no process restart
(`E3-S2-AC1`, `E3-S2-AC3`). The prior version is left byte-identical
(`E3-S2-AC2`) — there is no update path to it at all (D-E). Writes one
`audit_event`.

`403` CUSTOMER session, and no row is appended (`E3-S2-AC4`).
`422` rules failing `PolicyRules` validation (D-A: schema-validated JSONB, no DSL).

---

## Origination

### POST /applications — CUSTOMER

Request: `ApplicationSubmission` (`$ref`) — `product_code`, `requested_amount`
(money string), `requested_tenure_months`, `applicant` (`Applicant`: name, DOB,
declared income, synthetic PAN and Aadhaar, credit-history flags).

`201` →
```json
{
  "application": { "...": "LoanApplication" },
  "credit_score": 712,
  "decision": { "...": "UnderwritingDecision" },
  "document_checklist": [ { "...": "ApplicationDocument" } ]
}
```
The application is persisted in `SUBMITTED` state carrying the `policy_version_id`
resolved at submission (`E4-S1-AC1`, `E4-S2-AC2`) — pinned there and never
retargeted (D-D, `E4-S2-AC3`). The checklist matches the pinned version's
required-document list item for item (`E4-S2-AC1`) and every item carries its
document type with `status: "PENDING"` (`E4-S2-AC4`). The decision carries one of
the three outcomes plus at least one reason code drawn from the pinned version
(`E4-S1-AC3`, `E5-S2-AC1`, `E5-S2-AC2`).

`422` → `PolicyViolation`:
```json
{ "error": "PolicyViolationException",
  "detail": "declared income 18000.00 is below the minimum income for PERSONAL",
  "context": { "threshold_kind": "min_income", "configured_value": "25000.00",
               "submitted_value": "18000.00", "policy_version_id": "..." } }
```
The transaction rolls back; no application row survives (`E4-S4-AC3`). PAN,
Aadhaar and salary content never reach a log line (`E15-S1-AC1`).

### GET /applications — any authenticated role, results scoped

Query: `status` (`ApplicationStatus`, repeatable), `product_code`.

`MANUAL_REVIEW` is a plain `ApplicationStatus` value, per **D-L**: CONTEXT.md's
Application Status term and the `ApplicationStatus` enum both carry it, so the
enum holds seven states and this filter needs no alias. An application whose
latest Underwriting Decision outcome is `MANUAL_REVIEW` carries `MANUAL_REVIEW`
as its status. D-L rules out the filter-alias reading.

- CUSTOMER → only their own applications (`E8-S1` scope-out: never another
  customer's).
- UNDERWRITER → the workbench queue; `?status=SUBMITTED&status=MANUAL_REVIEW`
  returns exactly those (`E6-S2-AC1`).
- ADMIN → all, filterable to one status and one product (`E7-S1-AC1`).

`200` → `LoanApplication[]`. Registered read-heavy endpoint: p95 < 500 ms.

### GET /applications/{application_id} — any authenticated role, scoped

`200` →
```json
{ "application": { "...": "LoanApplication" },
  "document_checklist": [ { "...": "ApplicationDocument" } ],
  "decision": { "...": "UnderwritingDecision" },
  "decision_history": [ { "...": "UnderwritingDecision" } ] }
```
`decision` is the latest record; `decision_history` is every appended record
newest-first, so an Override shows the superseded decision as structured data
rather than audit prose (D-E). `decision` is `null` while the application is
undecided, which is how the Track screen suppresses its decision section
(`E8-S1-AC4`). `403` when a CUSTOMER requests another customer's application.

### POST /applications/{application_id}/decision — UNDERWRITER

Request `{ "outcome": "AUTO_APPROVE" | "AUTO_REJECT", "reason_code": "RC-07", "comment": "..." }`
Records an underwriter's ruling on a `MANUAL_REVIEW` case: appends a new
`decision_record`, so the latest record wins and the case leaves the queue
(`E6-S2-AC3`). Approval triggers Loan and Repayment Schedule creation (D-9).

`200` → `UnderwritingDecision`. `409` `ReasonCodeNotDeclared` when the code is
absent from the pinned version. Writes one `audit_event`.

### POST /applications/{application_id}/override — ADMIN

Request `{ "reason_code": "RC-12", "comment": "verified employer letter offline" }`

`200` → `UnderwritingDecision` with `supersedes_id` set to the overridden record
(`E7-S1-AC2`). The overridden row is untouched (D-E). Writes one `audit_event`
carrying the comment, the reason code, the acting user id and a timestamp
(`E7-S1-AC3`). `409` when the reason code is not declared by the pinned version
(`E7-S1-AC4`) or when the latest decision is not `AUTO_REJECT`.

### GET /documents/queue — UNDERWRITER

`200` → `DocumentVerificationQueue` — `ApplicationDocument[]` still in `PENDING`,
with the application id and product code for context. Already-actioned documents
are absent (`E6-S1-AC4`).

### POST /applications/{application_id}/documents/{document_id}/verification — UNDERWRITER

Request `{ "status": "VERIFIED" }` or `{ "status": "REJECTED", "rejection_reason": "illegible payslip" }`

`200` → `ApplicationDocument` with the stored status (`E6-S1-AC1`, `E6-S1-AC2`).
`422` when `REJECTED` arrives with an empty or missing reason; the stored status
is unchanged (`E6-S1-AC3`). Writes one `audit_event`. Verification never gates
schedule generation (D-9).

---

## Servicing

### POST /loans/{loan_id}/disbursement — ADMIN

Request `{}` — the funding source is the configured stub, not client input
(`SG-2`). The role is `ADMIN` per **D-N**, which rules out `UNDERWRITER`
disbursement so that approving an application and moving the money stay separate
privileges. `E1-S2`'s generated 401/403 suite asserts `UNDERWRITER` and
`APPLICANT` are rejected here.

`201` → `Disbursement` `{ id, loan_id, released_amount, funding_source, disbursed_at }`;
the loan reads `DISBURSED` with its schedule attached (`E10-S1-AC1`,
`E10-S1-AC2`). No payment rail is called and no signed artifact is produced
(`E10-S1-AC3`). `409` `AlreadyDisbursed` on a repeat attempt, with the recorded
released amount unchanged (`E10-S1-AC4`); `409` when no schedule is attached.

### GET /loans — CUSTOMER (own), ADMIN (all)

`200` → `Loan[]` with `outstanding_principal` and `delinquency_bucket`.

### GET /loans/{loan_id} — CUSTOMER (own), ADMIN

`200` →
```json
{ "loan": { "...": "Loan" },
  "repayment_schedule": { "...": "RepaymentSchedule" },
  "repayments": [ { "...": "Repayment" } ] }
```
Every installment carries due date, principal component, interest component and
EMI (`E13-S1-AC1`); the loan carries the current outstanding principal and bucket
(`E13-S1-AC2`). Registered read-heavy endpoint. `403` for another customer's loan.

### POST /loans/{loan_id}/repayments — CUSTOMER

Request `{ "amount": "18450.00" }`

`201` → `Repayment` `{ id, loan_id, amount, applied_principal, applied_interest, posted_at }`
plus the refreshed `loan`. Appends one immutable `repayment_posting` row with no
pre-existing row updated (`E11-S2-AC2`); outstanding principal falls by exactly
`applied_principal` (`E11-S2-AC1`); the bucket is recalculated through the
published ladder (`E11-S2-AC3`, `E11-S2-AC4`). No late fee, penal interest or
charge of any kind is computed anywhere on this path (`SG-1`).

Allocation is FIFO across whole Installments (forced by D-E, see
`architecture.md`), and within the oldest unpaid Installment a partial Repayment
applies to **interest first, then principal**, per **D-K**. `applied_principal +
applied_interest = amount` is a CHECK constraint. D-K rules out pro-rata
splitting by that Installment's stored components and rules out refusing a
non-whole-installment payment with a `422` — an underpayment is accepted and
posted.

---

## Delinquency & Portfolio

### POST /operations/end-of-day — ADMIN

Request `{ "as_of_date": "2026-03-31" }`

`200` → `EndOfDayRun` `{ as_of_date, loans_evaluated, buckets: { CURRENT: 41, "DPD-30": 6, ... }, completed_at }`
Idempotent for a given As-Of Date: a second run leaves every bucket and stored
row byte-identical (`E12-S1-AC2`). Creates no fee, penal interest or collections
record (`E12-S1-AC4`) and does not depend on the repayment endpoint (D-10).
The role is `ADMIN` per **D-N**, the same shape as disbursement so the
`require_roles` matrix and its 403 coverage stay single-shaped.

### GET /dashboard — ADMIN

`200` → `PortfolioSummary`
```json
{ "by_product": [ { "product_code": "PERSONAL", "loan_count": 24, "loan_value": "48250000.00",
                    "by_bucket": [ { "delinquency_bucket": "DPD-30", "loan_count": 3,
                                     "loan_value": "5400000.00" } ] } ],
  "total_overdue": "812340.00", "as_of": "2026-03-31T18:30:00Z" }
```
Served from stored loan bucket state; the End-Of-Day Run is never invoked
(`E14-S1-AC4`). `total_overdue` equals the sum of overdue installment amounts
across active loans (`E14-S1-AC2`). `403` for a CUSTOMER session with no figures
returned (`E14-S1-AC3`). Registered read-heavy endpoint.

### GET /audit-entries — ADMIN

Query `entity_type`, `entity_id`. `200` → `AuditEntry[]` newest-first, each with
actor user id, action, entity, timestamp and — for an Override — comment and
reason code (`E1-S2-AC4`, `E7-S1-AC3`).

---

## Operational endpoints

| Method | Path | Response |
|---|---|---|
| GET | `/health` | `200` `{ "status": "ok", "database": "ok", "version": "..." }` within 1 s of startup (`E15-S1-AC5`) |
| GET | `/metrics` | `200` `text/plain` RED metrics labelled `method`, `route`, `status`. Path from `project-manifest.json#observability.metrics_path`, not from a story. |

Neither carries a `components.schemas` entry: no CONTEXT.md term describes a
health or metrics payload, and D-H forbids minting one in the schema alone.
