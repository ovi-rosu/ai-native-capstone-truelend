# BRD: TrueLend — Configurable Loan Origination & Servicing

Mode: `--prd` adopt-only. Source: `prd/truelend.md` (copied to `specs/brd/source-frd.md`).
Spine: `specs/brd/brd-requirements.json` — **29 requirements**, adopted verbatim. Do not restate them here.

## In scope

29 adopted requirements. Machine spine + acceptance: `brd-requirements.json`, `brd-acceptance.json`.

## Out of scope

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

## Open questions

- none

## Clarifications

- none — lean adopt does not invent decisions the PRD did not ask

## Risks

- **R-1 EMI rounding residual.** Fixed-point money at 2 decimal places (NFR-01) and the requirement that per-installment principal plus interest equal total payable (FR-07) are in tension: rounded equal installments rarely sum to the unrounded total. Design must state where the residual is absorbed, or the FR-07 invariant test will be loosened to hide it.
- **R-2 Append-only versus correction.** Policy versions and schedules admit no update or delete (NFR-02, NFR-05), while an override changes a decision (FR-10) and a posted repayment changes outstanding principal and bucket (FR-09). Design must draw the boundary between the immutable artifacts and the mutable loan state explicitly, or the architecture test and the features will collide.
- **R-3 Policy activation with in-flight applications.** A new version becomes active without restart (FR-13), yet every reason code must exist in the policy version named on the application (FR-04). An application decided across an activation must keep citing its own version rather than the newly active one.
- **R-4 Undefined bucket boundaries.** The delinquency buckets are named (FR-09) but no requirement fixes the day ranges, nor where NPA begins. Left unstated, the first agent to write that code picks the thresholds by accident. Design must fix the boundaries against the capstone's intent before FR-09 or FR-14 is implemented.

## Gates

- Grounding and taxonomy are the scripts in Step 4.4 / 4.45 — not a restated analysis pack.
- No `brd-analysis.json`. Domain/risk seed: `analysis-seed.json`. SPDD Canvas is a `/design` artifact.
