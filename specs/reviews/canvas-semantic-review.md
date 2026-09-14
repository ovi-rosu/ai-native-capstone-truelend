# Canvas Semantic Review

Changed governed files:

- backend/src/api/app.py

For each claim below, judge against the diff of those files whether it STILL holds.
If a claim no longer describes the code, fix the Canvas prose in `specs\design\reasons-canvas.md` first (fix-the-prompt-first), then the code.

## Claim — Approach

**Chosen.** Rules are data, decisions are pinned, facts are append-only and reads
are cheap. Concretely: one JSONB threshold document per Policy Version validated
by one Pydantic model and read by one threshold-driven evaluator (D-A); the
version pinned on the application at submission and read by checklist, score,
decision and override alike (D-D); insert-only fact tables with three stored
projections rather than derive-on-read (D-E); fixed-point money as a quoted
string at every hop (D-G); one `require_roles` dependency at the controller
boundary (D-F); DPD boundaries as Config constants with the residual confined to
the final installment (D-B, D-C).

**Rejected, and what decided it.**

| Alternative | Rejected because |
|---|---|
| Expression DSL for policy rules | FRD-13 names a fixed threshold set. A DSL buys rule shapes nobody asked for and adds a parser plus an injection surface (D-A). |
| Typed columns per threshold | Every new threshold becomes an ALTER TABLE, which NFR-22's append-only migration rule constrains (D-A). |
| NPA at 90 days (RBI convention) | It overlaps DPD-90 and leaves one of FR-09's five named buckets unreachable (D-B). |
| Per-product configurable ageing | Would drag the End-Of-Day Run into resolving a Policy Version per loan (D-B). |
| Spread the rounding residual across early installments | The schedule stops being recomputable from principal, rate and tenure plus one adjustment; the residual smears instead of sitting in one auditable place (D-C). |
| Store unrounded money, round at the edge | NFR-01's 2dp would describe presentation rather than stored money (D-C, D-G). |
| Pin the policy version at decision time | The FR-02 checklist and the FR-04 decision could then disagree about required documents (D-D). |
| Full event sourcing | The Portfolio Summary would replay every loan's history on each read, against NFR-26 (D-E). |
| Server-side session behind an HttpOnly cookie | Adds a session store to the Compose stack and a CSRF surface (D-F). |
| Integer minor units on the wire | Scale/unscale conversions at both edges, for no gain over a quoted decimal string (D-G). The FRD-57 / E9-S1-AC3 conflict was closed by amending the AC (D-J), so minor units are ruled out on the frontend too. |
| Pro-rata splitting of a partial repayment | Interest-before-principal within the oldest unpaid Installment is standard practice and the least surprising split to audit (D-K). |
| A MANUAL_REVIEW query alias over an UNDER_REVIEW status | The workbench filter and the two staff mockups would read differently from the schema; the enum carries the seventh state instead (D-L). |
| An 8-hour token, or a refresh token to soften a short one | A working-day theft window with no refresh path to revoke it; D-F already forecloses refresh in v1 (D-M). |
| UNDERWRITER disbursement | Approving an application and moving the money would collapse into one privilege (D-N). |
| Throttling middleware in the app factory | No requirement or NFR defines request volume, so any figure would be invented; the login attempt-throttle gap is recorded as accepted (D-O). |
| One flat service package | Every story edits the same files, which is exactly what makes the 21-story C1 cluster serialize (D-I). |

---

## Claim — Structure

Six layers, strictly one-way: Types → Config → Repository → Service → API → UI.
Five bounded contexts cut vertically through Repository, Service and API (D-I):
**Policy & Catalog** (core, high volatility — the configurability surface),
**Origination** (core, medium), **Servicing** (core, low), **Delinquency &
Portfolio** (core, medium), **Identity & Audit** (supporting, low).

Integration contracts, one per context, are the only cross-context surfaces:

| Context | Published contract |
|---|---|
| Policy & Catalog | a read-only accessor returning validated Policy Rules for a pinned version id, plus that version's Reason Code set; activation writes here and nowhere else |
| Origination | submit a submission, verify a document, evaluate or override a decision; emits an approved application |
| Servicing | disburse, read a schedule, post a repayment; publishes the Installment ladder |
| Delinquency & Portfolio | recalculate buckets for an As-Of Date, read a Portfolio Summary; consumes the published ladder, never Servicing's tables |
| Identity & Audit | require_roles at the API layer, append an Audit Entry, bind a Correlation Id |

Balanced coupling: the high-volatility Policy context is held at a distance
behind a narrow versioned accessor and nobody reads its JSONB directly; the
low-volatility Servicing-to-Delinquency pair is genuinely sequential so a
stronger integration is acceptable; Identity & Audit is generic enough to be used
directly everywhere, which is why it must stay free of domain meaning.

Layer placement detail that matters: the DelinquencyBucket enum is in Types while
`classify` and its boundaries are in Config, because Types may import nothing and
D-B puts the boundaries in Config. Both live in one file pair owned by one story,
so the mapping has exactly one owner.

Agreement check: this section matches `architecture.md`, `folder-structure.md`
and the six-layer config in `.claude/architecture.md`.

---

## Claim — Norms

- **Static typing everywhere.** Full annotations in Python, mypy over `src/`; zero
  `any` in TypeScript — `unknown` plus narrowing.
- **TDD.** Test first, then implementation. Architecture invariants are tests in
  `backend/tests/architecture/`, registered so an unregistered invariant fails the
  suite.
- **Size limits.** Functions at most 30 lines, files at most 300 — enforced by the
  pre-write gate. The context split in D-I is what keeps modules under it.
- **Naming.** Domain vocabulary from CONTEXT.md, verbatim, in schemas, types and
  code. A new concept goes into CONTEXT.md first (D-H). No DTO suffixes.
- **Layering.** Imports flow one way only; a Service never imports from API, a
  Repository never from Service. Cross-context access goes through the target
  context's service, never its repository.
- **No pass-through modules.** Where a story has no business rule the router uses
  the repository contract directly.
- **Dependency injection.** FastAPI `Depends` for the session, the current user
  and repositories; no module-level singletons holding state.
- **Logging — SG-9.** Structured JSON only, one Correlation Id per request on
  every line, and the redaction filter installed on every configured logger.
  Applicant PAN, Aadhaar and salary-document content never reach a sink.
- **Errors.** Typed error classes in Types, raised in Service, mapped exactly once
  at the API boundary. Nothing is swallowed; no bare `except`.
- **Money.** `Decimal` in Python, `NUMERIC(14,2)` in Postgres, a quoted 2dp string
  on the wire, a decimal library in TypeScript. No float in a money code path.
- **Commits.** Conventional format, branch `<type>/<description>`, agent
  co-authorship on every production commit.

---

## Claim — Safeguards

Non-negotiable boundaries. A reviewer checks the diff against these.

**Business prohibitions from `specs/brd/brd-safeguards.json`** — all ten are
`forbidden_action`, so all ten are filed here:

- **SG-1** — no late fee, penal interest, collections workflow or write-off. No
  monetary field anywhere on the delinquency path: `classify` returns a bucket and
  nothing else, and no schema in this design has a fee, penalty or charge
  property.
- **SG-2** — no real money movement and no credit-bureau call. `funding_source.py`
  is a stub returning a configured identifier; `scoring.py` has no outbound
  collaborator and no credential; the Compose stack configures no provider
  endpoint.
- **SG-3** — no native or responsive mobile client. Desktop-and-tablet web only.
- **SG-4** — no customer notification of any kind. No email, SMS or notification
  module, and the Track screen shows state without dispatching anything.
- **SG-5** — no electronic signature and no signed loan-agreement artifact. The
  disbursement writes a row and produces no document.
- **SG-6** — single currency. No currency field and no exchange-rate path.
- **SG-7** — one Applicant per Loan Application. Enforced structurally: the
  applicant is inlined on the application row, so no second applicant can exist.
- **SG-8** — no top-up, restructuring or mid-life modification of a disbursed
  loan. No endpoint mutates loan principal, rate or tenure after disbursement.
- **SG-9** — no KYC or AML verification against an external registry. PAN and
  Aadhaar are captured as application data, never verified, and redacted from
  every log line.
- **SG-10** — no early settlement, foreclosure or prepayment quote. The loan view
  offers posting a repayment and nothing else.

**Design invariants.**

- A Policy Version is never mutated: the repository exposes no update or delete,
  and an architecture test reports 0 UPDATE, 0 DELETE and 0 ORM mutations against
  `policy_version` across `src/` and `migrations/`.
- A Repayment Schedule and its Installments are never mutated after generation;
  the same scan covers `schedule_installment`.
- An Underwriting Decision is never edited; an Override appends with
  `supersedes_id` set.
- A decision cites only Reason Codes declared by the Policy Version pinned to its
  application.
- An application's `policy_version_id` is written at submission and never
  retargeted by a later activation.
- Money is fixed-point 2dp end to end; no float touches a monetary value.
- Per-Installment principal plus interest equals Total Payable **exactly** — no
  epsilon, no tolerance. The residual sits in the final Installment.
- An End-Of-Day Run is idempotent for a given As-Of Date.
- Every non-public route carries `require_roles`; the generated suite asserts 100%
  coverage of the 401 and 403 cases, so a new unguarded route fails the build.
- Every underwriter and admin action appends exactly one Audit Entry.

**Limits and budgets.**

- Runtime SLO: p95 under 500 ms and error rate under 1% on the four registered
  read-heavy endpoints (`GET /products`, `GET /applications`, `GET /loans/{id}`,
  `GET /dashboard`).
- `GET /health` returns 200 within 1 second of a successful startup.
- WCAG 2.1 AA with zero axe violations and no suppressed rule on Apply, Track and
  Repay.
- Functions at most 30 lines, files at most 300.
- **Token lifetime is 3600 seconds** (`Settings.jwt_ttl_seconds`), per **D-M** —
  the whole session length, since D-F issues no refresh token.
- **No rate limit, quota or throttle anywhere**, per **D-O**: v1 ships no
  throttling middleware, so no test asserts one and `POST /auth/login` has no
  attempt throttle. Combined with the absent lockout policy that is an accepted
  credential-stuffing gap, not an oversight.
- **No backup retention window is asserted here.** None is recorded in the
  decisions file, and a number nobody chose reads as decided once written down.

**Coupling-risk safeguards** (from the Step 0.7 assessment):

- one money serializer module; one DPD boundary mapping; one EMI and residual
  implementation; one paid/unpaid derivation; one projection write path.
- projection drift is caught by replay reconciliation against `disbursement` and
  `repayment_posting`.
- `(principal, rate, tenure)` and `(as_of_date, loan_id, bucket)` are value
  objects in Types before the clump spreads.

---

## Claim — Operations

`backend/src/api/app.py`, `backend/src/api/middleware.py`,

