# Test Plan

Scope: 29 stories, 107 acceptance criteria.
Machine spine: `verification-matrix.json` (one row per AC). Behavior scenarios are that list in Given/When/Then — not extra cases, not Cucumber, not AT source.

## Named Seams (Ports-and-Adapters)

| Story | Seam (port) | Real adapter | Test-double adapter |
| --- | --- | --- | --- |
| E15-S1 | app factory + router registry; observability port (log sink, correlation id, error-mapping table) | structlog JSON handler + correlation-id middleware over `create_app` | in-memory log-capture fixture (reused by every later story) |
| E15-S2 | six-layer one-way dependency rule; container boundary | Docker Compose three-service stack (Postgres, FastAPI, React-Vite) | import-graph walker over manifest `layer_roots` — no containers needed |
| E9-S1 | Money port: one Pydantic serializer out, one decimal-library parser in | Decimal quantized to 2dp, on the wire as a quoted string | static float-arithmetic scanner over the money code paths |
| E1-S1 | session/identity port; SQLAlchemy table registry; frontend HTTP client | JWT issuer (60-min TTL, D-3) + product repository read straight from the router | seeded one-user-per-role fixtures through the in-process TestClient |
| E1-S2 | `require_roles` — the single enforcement point every non-public router takes (D-F) | FastAPI dependency over the app factory router registry | OpenAPI-derived route enumerator + one token per role |
| E3-S1 | policy_version repository port exposing no update and no delete method | SQLAlchemy append-only repository + the migration lint every later migration inherits | AST/SQL scanner over `src/` and `migrations/` |
| E2-S1 | pinned-version accessor — the only published way to read Policy Rules (D-D) | PolicyRules Pydantic model validating the JSONB document (D-A) | seeded three-product catalog, one distinct policy version each |
| E3-S2 | append-and-activate port — one transaction, activation as a pointer write on the product row | policy version append + product pointer write; no flag UPDATE | in-process TestClient; the pre-save version re-read as the immutability oracle |
| E16-S1 | invariant registry port with a fail-closed completeness assertion | architecture suite + git provenance check + `/gate` attestation reader | registry seeded with a deliberately orphaned invariant |
| E4-S1 | application intake port pinning `policy_version_id` at creation | submit endpoint over the application aggregate | deterministic scoring stub + seeded product |
| E4-S2 | Document Checklist generation port + the pinning guarantee later readers depend on | generator reading the pinned version required-document list item for item | pinned-version fixture plus a newer version activated after submission |
| E4-S3 | application API client port; first screen registered with the accessibility harness | Apply screen over the E4-S2 intake service | HTTP double for the intake endpoint (no backend process) |
| E4-S4 | policy-evaluation error port — PolicyViolationException naming threshold and configured value | 422 mapping through the E15-S1 error table, with a rollback leaving no application row | sub-threshold declared-income fixture |
| E5-S1 | credit-scoring port, replaceable by a real bureau without touching the evaluator | deterministic in-process scoring stub — no clock, no randomness, no outbound call | collaborator inspection asserting no bureau call and no live credential |
| E5-S2 | decision-record append port with latest-record-wins semantics | append-only decision repository + the approval hand-off servicing consumes | pinned reason-code set; a newer policy version activated after submission |
| E6-S1 | document-verification transition port (VERIFIED / REJECTED) | transition guarded by both a validator and a CHECK constraint on the reason | queue fixture holding both pending and already-actioned documents |
| E6-S2 | workbench queue read model port | queue filtered to SUBMITTED and MANUAL_REVIEW + the review screen | applications seeded across every lifecycle state |
| E7-S1 | superseding Override port — never edits the row it supersedes (D-E) | decision_record append with `supersedes_id` + one audit_event | AUTO_REJECT application fixture; a reason code outside the pinned version |
| E8-S1 | customer tracking read port over the role-scoped application read | tracking view rendering status, unverified documents and decision | undecided and decided application fixtures; notification dispatch spy |
| E11-S1 | delinquency classification port — the single classify function | DelinquencyBucket enum over the Config-layer floors of D-B | days-past-due values sampled across 0-400 |
| E9-S2 | Loan aggregate + the single projection write path shared with the end-of-day run | the four servicing repositories | approved-application fixture |
| E9-S3 | EMI/residual port (the one implementation, D-C) + the installment ladder publishing Days Past Due | schedule generation and the FR-07 invariant test over that one implementation | generated principal/rate/tenure triples; a residual-bearing schedule |
| E10-S1 | funding-source port | stubbed funding source + DISBURSED transition; idempotence structural via UNIQUE on loan id | stub rail asserting no outbound call and no signed artifact |
| E11-S2 | repayment posting port — append-only, FIFO across installments, interest-first within the oldest (D-K) | repayment_posting append + bucket recalculation through the published ladder | disbursed loan with a known outstanding principal and a 35-day-overdue installment |
| E12-S1 | As-Of-Date run port, persisting no run row of its own | end-of-day operation writing bucket state only | seeded loans with differing DPD; a fixed injected as-of date |
| E13-S1 | customer loan view port over `GET /loans/{loan_id}` | loan view rendering the installment ladder, outstanding principal and bucket | disbursed-loan and delinquent-loan fixtures |
| E14-S1 | portfolio aggregation port, served from stored projections only | aggregation over stored loan bucket state | end-of-day spy asserting the run is never invoked |
| E17-S1 | customer-facing screen registry + accessibility driver port | axe-core scan + keyboard-traversal driver over every registered screen | registry plus an unregistered customer-facing route |
| E15-S3 | read-heavy endpoint registry + load driver port | in-process load driver measuring p95 and error rate per registered endpoint | registry plus an unregistered GET route |

## Behavior scenarios (Given / When / Then)

Human-reviewed behavior spec. Implement-time ATs match this wording. Do not write `.feature` or AT source here.

| AC | Matrix | Given | When | Then |
| --- | --- | --- | --- | --- |
| E15-S1-AC1 | VM-001 | an application payload carrying synthetic PAN, Aadhaar and salary-document content | the request is served and every emitted log record is captured | the captured buffer contains 0 occurrences of each of those three values |
| E15-S1-AC2 | VM-002 | the application's logging configuration | every configured logger is enumerated | the redaction filter is installed on 100% of them and a logger registered without it fails the assertion |
| E15-S1-AC3 | VM-003 | a request carrying the header X-Request-ID with value req-abc | every log line emitted while serving that request is parsed | 100% of the lines parse as JSON and each carries request_id equal to req-abc |
| E15-S1-AC4 | VM-004 | a request with no X-Request-ID header | the response is returned | every request-scoped log line carries the same generated non-empty request_id and the response echoes that id |
| E15-S1-AC5 | VM-005 | the backend reporting a successful startup | GET /health is called | the response is 200 with a JSON body and the measured response time is under 1 second |
| E15-S2-AC1 | VM-006 | a clean checkout with no prior containers | docker compose up runs to completion | exactly one Postgres service, the Python 3.12 FastAPI backend and the TypeScript React-Vite frontend are running and all three report healthy |
| E15-S2-AC2 | VM-007 | the running stack | the layer-dependency architecture test executes | it reports 0 violations of the one-way rule across Types, Config, Repository, Service, API and UI |
| E15-S2-AC3 | VM-008 | the compose service inventory | it is asserted against the declared stack | no second database engine and no external provider endpoint is configured |
| E9-S1-AC1 | VM-009 | randomly generated principal, rate and tenure triples | a schedule is computed from each triple | every money field on the result is a Decimal quantized to exactly 2 decimal places |
| E9-S1-AC2 | VM-010 | the backend money code paths | the static arithmetic check runs over them | it reports 0 float arithmetic operations in those paths |
| E9-S1-AC3 | VM-011 | the frontend money module | a monetary amount is carried and formatted | the value is held as a decimal value and never a float, and the static check reports 0 float arithmetic operations in that module |
| E1-S1-AC1 | VM-012 | seeded users for CUSTOMER, UNDERWRITER and ADMIN | each logs in with valid credentials | a session is issued naming exactly one role and that role's landing surface loads |
| E1-S1-AC2 | VM-013 | the seeded product catalog | a CUSTOMER requests the product list | at least one product is returned and it carries a policy version id |
| E1-S1-AC3 | VM-014 | an ADMIN session and a product with a minimum-income threshold | that threshold is saved with a new value | a new policy version id is returned in the response |
| E1-S1-AC4 | VM-015 | the newly saved policy version | the product is read again inside the same running process | the read cites the new policy version id with no process restart |
| E1-S2-AC1 | VM-016 | any underwriter or admin route | it is called with no session | the response is 401 and no handler body executes |
| E1-S2-AC2 | VM-017 | a CUSTOMER session | an underwriter or admin route is called with it | the response is 403, while each role reaches its own surfaces with 200 |
| E1-S2-AC3 | VM-018 | the underwriter and admin routes enumerated from the OpenAPI schema | the generated authorization suite runs | it reports 100% of those routes covered by both the no-session and wrong-role cases and fails when a new route is unguarded |
| E1-S2-AC4 | VM-019 | an authenticated underwriter or admin action | the action completes | an audit_event row exists carrying the acting user id and a timestamp |
| E3-S1-AC1 | VM-020 | the policy_version repository interface | its public methods are enumerated | no update method and no delete method is exposed |
| E3-S1-AC2 | VM-021 | the contents of src/ and migrations/ | the immutability architecture test scans them | it reports 0 UPDATE statements, 0 DELETE statements and 0 ORM mutations targeting policy_version |
| E3-S1-AC3 | VM-022 | every file under migrations/ | the migration lint parses them | it reports 0 DROP TABLE, 0 DROP COLUMN and 0 destructive ALTER statements |
| E3-S1-AC4 | VM-023 | a policy migration file | it is parsed by that same lint | it is held to the identical zero-destructive-statement assertion as a schema migration |
| E2-S1-AC1 | VM-024 | the seeded catalog | GET /products is called | at least 3 products are returned and Personal, Vehicle and Education are among them |
| E2-S1-AC2 | VM-025 | the returned product list | each entry is inspected | each carries its own policy version id and no two products reference the same one |
| E2-S1-AC3 | VM-026 | the three referenced policy versions | their stored threshold values are compared | the minimum income, age, score, tenure and rate values differ between the three versions |
| E3-S2-AC1 | VM-027 | an authorised user editing a product's income, age, score, tenure and rate thresholds | the editor form is saved | a new policy version row is appended and becomes the product's active version |
| E3-S2-AC2 | VM-028 | the policy version that was active before the save | it is re-read afterwards | its stored values are byte-identical to their pre-save state |
| E3-S2-AC3 | VM-029 | the newly activated policy version | a subsequent application is decided in the same running process | the decision cites the new policy version id with no process restart |
| E3-S2-AC4 | VM-030 | a CUSTOMER session | the Policy Editor save endpoint is called with it | the response is 403 and no policy version row is appended |
| E16-S1-AC1 | VM-031 | a registry naming policy-version immutability, the EMI principal/rate/tenure invariant and the six-layer one-way dependency rule | the architecture suite runs | at least one test exists and executes for every registered invariant |
| E16-S1-AC2 | VM-032 | a registered invariant with no corresponding test | the architecture suite runs | the suite fails and names the orphaned invariant |
| E16-S1-AC3 | VM-033 | every production commit on the branch | the provenance check inspects them | each carries agent co-authorship and a passing record from the standard pre-commit gate set |
| E16-S1-AC4 | VM-034 | the /gate attestation record | it is read for the head commit | it is present and records 0 hand-written production lines as the NFR-11 evidence |
| E4-S1-AC1 | VM-035 | a chosen product and a CUSTOMER session | an application is submitted | a persisted application in SUBMITTED state is returned carrying the product's current policy version id |
| E4-S1-AC2 | VM-036 | that application's age, income and credit-history flags | the scoring stub is called for it | a numeric credit score is returned and stored against the application |
| E4-S1-AC3 | VM-037 | the scored application | it is decided | the response carries one of AUTO_APPROVE, AUTO_REJECT or MANUAL_REVIEW together with at least one reason code |
| E4-S2-AC1 | VM-038 | a selected product with a required-document list on its policy version | an application is submitted against it | the generated checklist matches that policy version's list item for item |
| E4-S2-AC2 | VM-039 | a submitted application | it is read back from storage | it is in SUBMITTED state and stores the policy_version_id resolved at submission |
| E4-S2-AC3 | VM-040 | a policy version activated after that submission | the application is re-read | its stored policy_version_id and checklist are unchanged |
| E4-S2-AC4 | VM-041 | a generated checklist item | it is inspected | it carries its document type and an unverified status |
| E4-S3-AC1 | VM-042 | the Apply screen with a product selected | the applicant submits valid details | the confirmation shows the newly created application in SUBMITTED state |
| E4-S3-AC2 | VM-043 | the submitted application | the Apply screen renders its confirmation | every required-document checklist item for the chosen product is listed |
| E4-S3-AC3 | VM-044 | the Apply form | it is rendered | no co-applicant or guarantor field is present |
| E4-S4-AC1 | VM-045 | declared income below the selected product's minimum income threshold | the application is submitted | the error response identifies PolicyViolationException |
| E4-S4-AC2 | VM-046 | that refused submission | the error body is inspected | it names the breached threshold and the configured value it was checked against |
| E4-S4-AC3 | VM-047 | that refused submission | the application table is queried afterwards | no application row was persisted for it |
| E5-S1-AC1 | VM-048 | one set of age, income and credit-history-flag values | the scoring stub is called repeatedly with it | every call returns the identical score |
| E5-S1-AC2 | VM-049 | two inputs differing only in their credit-history flags | both are scored | the two returned scores differ |
| E5-S1-AC3 | VM-050 | the scoring stub under test | its outbound collaborators are inspected | no external credit-bureau call and no live provider credential is used |
| E5-S2-AC1 | VM-051 | a scored application | it is decided | the response carries AUTO_APPROVE, AUTO_REJECT or MANUAL_REVIEW plus at least one reason code |
| E5-S2-AC2 | VM-052 | the reason codes on that decision | each is looked up | it exists in the policy version pinned on the application |
| E5-S2-AC3 | VM-053 | a decided application | the decision is recorded | a new decision_record row is appended and the application's current decision is its latest record |
| E5-S2-AC4 | VM-054 | a MANUAL_REVIEW application re-decided after a newer policy version was activated | its decision is read | the re-decision still cites the policy version pinned at submission |
| E6-S1-AC1 | VM-055 | a checklist document in the verification queue | an underwriter marks it VERIFIED | its stored status reads VERIFIED |
| E6-S1-AC2 | VM-056 | a checklist document in the verification queue | an underwriter marks it REJECTED with a reason | the stored row reads REJECTED and carries that non-empty reason |
| E6-S1-AC3 | VM-057 | a document being rejected with an empty reason | the transition is attempted | it is refused and the document's stored status is unchanged |
| E6-S1-AC4 | VM-058 | documents that have already been actioned | the verification queue is listed | those documents are absent from the returned queue |
| E6-S2-AC1 | VM-059 | applications spread across every lifecycle state | the workbench queue is listed | it contains exactly those applications in SUBMITTED or MANUAL_REVIEW state |
| E6-S2-AC2 | VM-060 | a MANUAL_REVIEW application | its review screen is opened | the screen shows its credit score, its decision reason codes and the verification state of each checklist document |
| E6-S2-AC3 | VM-061 | an underwriter deciding a MANUAL_REVIEW case from the review screen | the decision is saved | the application's latest decision record reflects that decision and the case leaves the queue |
| E7-S1-AC1 | VM-062 | applications across several statuses and products | the list is filtered to one status and one product | only the matching rows are returned |
| E7-S1-AC2 | VM-063 | an application decided AUTO_REJECT | an admin overrides it with a comment and a reason code | a new decision_record is appended and the application's current decision is the override |
| E7-S1-AC3 | VM-064 | that override | the audit trail is read | it contains an entry carrying the comment, the reason code, the acting user id and a timestamp |
| E7-S1-AC4 | VM-065 | the reason code supplied with the override | it is looked up | it exists in the policy version pinned on the application |
| E8-S1-AC1 | VM-066 | a submitted application belonging to the signed-in customer | its tracking view is opened | the view shows the application's current status |
| E8-S1-AC2 | VM-067 | an application with documents still unverified | the tracking view renders | every unverified required document is listed |
| E8-S1-AC3 | VM-068 | a decided application | the tracking view renders | the decision and each of its reason codes are shown |
| E8-S1-AC4 | VM-069 | an application that has not been decided yet | the tracking view renders | no decision section is shown and no notification was dispatched to the customer |
| E11-S1-AC1 | VM-070 | the floors CURRENT 0-29, DPD-30 30-59, DPD-60 60-89, DPD-90 90-179 and NPA at 180 or more days past due | a loan whose oldest unpaid installment is 35 days past due is classified | the returned bucket is DPD-30 |
| E11-S1-AC2 | VM-071 | days-past-due values sampled across 0 through 400 | each value is classified | exactly one of the five buckets is returned for every value, with no gap and no overlap |
| E11-S1-AC3 | VM-072 | a loan with no installment past its due date as of a given date | it is classified as of that date | the returned bucket is CURRENT |
| E11-S1-AC4 | VM-073 | any classification result | it is inspected | it carries a bucket only, with no fee, penal interest or charge of any kind |
| E9-S2-AC1 | VM-074 | an application with an approved decision | its loan is created | a repayment schedule exists with one installment row per month of the product tenure |
| E9-S2-AC2 | VM-075 | that loan | it is disbursed | it is in DISBURSED state holding the released amount and a funding-source identifier |
| E9-S2-AC3 | VM-076 | the disbursed loan | a repayment is posted against it | the loan's outstanding principal is lower than it was before the posting |
| E9-S3-AC1 | VM-077 | a generated repayment schedule | the principal column across its rows is summed | the sum equals the disbursed amount exactly, with no residual |
| E9-S3-AC2 | VM-078 | that same schedule | total payable is read and the installments are counted | total payable equals the sum of principal plus interest over the stored rows and the installment count equals the product tenure |
| E9-S3-AC3 | VM-079 | a schedule whose rounded EMI leaves a residual | the final installment row is inspected | its principal equals the balance remaining after all preceding rows |
| E9-S3-AC4 | VM-080 | each period of the schedule | that period's interest is computed | it is derived from the period's opening balance at the rate on the application's pinned policy version |
| E9-S3-AC5 | VM-081 | the schedule_installment repository together with src/ and migrations/ | they are scanned by the immutability architecture test | no update or delete method is exposed and 0 UPDATE or DELETE statements target schedule_installment |
| E10-S1-AC1 | VM-082 | an approved loan with a generated schedule | it is disbursed | the loan record holds the released amount |
| E10-S1-AC2 | VM-083 | that disbursement | the loan is read back | it holds a funding-source identifier and is in DISBURSED state with its schedule attached |
| E10-S1-AC3 | VM-084 | the stub funding source | the disbursement executes | no external payment rail is called and no signed agreement artifact is produced |
| E10-S1-AC4 | VM-085 | a loan already in DISBURSED state | disbursement is attempted a second time | the attempt is refused and the recorded released amount is unchanged |
| E11-S2-AC1 | VM-086 | a disbursed loan with a known outstanding principal | a repayment is posted against it | outstanding principal falls by exactly the applied principal portion of that payment |
| E11-S2-AC2 | VM-087 | a posted repayment | the repayment_posting table is read | a new immutable row records the payment and no pre-existing row was updated |
| E11-S2-AC3 | VM-088 | a loan whose oldest unpaid installment is 35 days past due | its bucket is recalculated after the posting | the stored delinquency bucket reads DPD-30 |
| E11-S2-AC4 | VM-089 | a posting that clears every overdue installment | the bucket is recalculated | the stored bucket reads CURRENT and no late fee or penal interest was charged |
| E12-S1-AC1 | VM-090 | seeded active loans with differing days past due | the end-of-day operation runs for a given as-of date | each loan's stored bucket matches its days past due at that date |
| E12-S1-AC2 | VM-091 | a completed end-of-day run | the operation runs a second time for the same as-of date | every bucket and every stored row is byte-identical to the first run's result |
| E12-S1-AC3 | VM-092 | an as-of date earlier than a loan's first installment due date | the operation runs for that date | that loan's stored bucket reads CURRENT |
| E12-S1-AC4 | VM-093 | the completed run | the loan records are compared against their pre-run state | no fee, penal interest or collections record was created |
| E13-S1-AC1 | VM-094 | a disbursed loan belonging to the signed-in customer | its loan view is opened | every installment is listed with its due date and amount |
| E13-S1-AC2 | VM-095 | that same loan view | it renders | the current outstanding principal and the current delinquency bucket are both shown |
| E13-S1-AC3 | VM-096 | a repayment posted from the loan view | the page is reloaded | the displayed outstanding principal reflects that posting |
| E13-S1-AC4 | VM-097 | the loan view for a delinquent loan | it renders | it offers no early settlement, foreclosure or prepayment quote |
| E14-S1-AC1 | VM-098 | loans spread across products and delinquency buckets | an admin opens the dashboard | the loan count and value are reported for every product and bucket combination |
| E14-S1-AC2 | VM-099 | those same loans | the total overdue figure is read | it equals the sum of overdue installment amounts across all active loans |
| E14-S1-AC3 | VM-100 | a CUSTOMER session | the dashboard endpoint is called with it | the response is 403 and no portfolio figures are returned |
| E14-S1-AC4 | VM-101 | the dashboard request | its data source is traced | the figures are served from stored loan bucket state without invoking the end-of-day job |
| E17-S1-AC1 | VM-102 | the customer-facing screen registry | the automated axe-core scan runs against every registered screen | it reports 0 WCAG 2.1 AA violations with no rule suppressed, and asserts it covered 100% of registered screens |
| E17-S1-AC2 | VM-103 | each registered screen | its primary flow is traversed using the keyboard only | the flow completes, no focus trap is encountered, and every interactive control exposes an accessible name and a visible focus indicator |
| E17-S1-AC3 | VM-104 | a route that renders a customer-facing screen and is absent from the registry | the accessibility suite runs | the suite fails, so Apply, Track and Repay are each held to WCAG 2.1 AA by the story that lands them |
| E15-S3-AC1 | VM-105 | the read-heavy endpoint registry, which contains GET /products, GET /applications, GET /loans/{id} and GET /dashboard | the load run executes against every registered endpoint | the measured p95 latency is under 500 ms and the error rate is under 1% across all of them |
| E15-S3-AC2 | VM-106 | the completed load run | the evaluation report is written | it records the measured p95 and error-rate figures for each registered endpoint |
| E15-S3-AC3 | VM-107 | a read-heavy endpoint absent from the registry | the SLO suite runs | the suite fails, so a read surface added later is measured by the story that adds it |

## Proposed sprint-contract checks

Evaluator QA procedure (`api` / `playwright`). Fill Observe (method/path or UI steps). Do not write `sprint-contracts/*.json` or Playwright files in this phase.

| Group | Check id | Kind | Matrix ids | Observe |
| --- | --- | --- | --- | --- |
| A | QA-VM-003 | api | VM-003 | GET /health → 200 — sent with header X-Request-ID: req-abc; 100% of the log lines emitted while serving parse as JSON and each carries request_id equal to req-abc |
| A | QA-VM-004 | api | VM-004 | GET /health → 200 — sent with no X-Request-ID header; every request-scoped log line carries the same generated non-empty request_id and the response echoes that id |
| A | QA-VM-005 | api | VM-005 | GET /health → 200 — JSON body, and the measured response time is under 1 second |
| B | QA-VM-012 | api | VM-012 | POST /auth/login → 200 — for each seeded CUSTOMER, UNDERWRITER and ADMIN; GET /auth/session then names exactly one role and that role's landing surface |
| B | QA-VM-013 | api | VM-013 | GET /products → 200 — as CUSTOMER; at least one product and every entry carries a policy_version_id |
| B | QA-VM-014 | api | VM-014 | POST /products/{product_code}/policy-versions → 201 — as ADMIN saving a new minimum-income threshold; the body carries a new policy_version_id |
| B | QA-VM-015 | api | VM-015 | GET /products/{product_code} → 200 — in the same running process; cites the policy_version_id from QA-VM-014 with no restart |
| C | QA-VM-016 | api | VM-016 | GET /documents/queue → 401 — no Authorization header; no handler body executes |
| C | QA-VM-017 | api | VM-017 | GET /documents/queue → 403 — with a CUSTOMER token, while GET /products with that same token is 200 |
| C | QA-VM-018 | api | VM-018 | GET /openapi.json → 200 — enumerate every UNDERWRITER/ADMIN route; the generated suite reports 100% covered by both a no-session and a wrong-role case |
| C | QA-VM-019 | api | VM-019 | GET /audit-entries → 200 — as ADMIN after an UNDERWRITER decision; an entry carries the acting user id and a timestamp |
| D | QA-VM-024 | api | VM-024 | GET /products → 200 — at least 3 products, with PERSONAL, VEHICLE and EDUCATION among them |
| D | QA-VM-025 | api | VM-025 | GET /products → 200 — each entry carries its own policy_version_id and no two are equal |
| D | QA-VM-026 | api | VM-026 | GET /products/{product_code} → 200 — for all three; minimum income, age, score, tenure and rate differ across the three pinned versions |
| E | QA-VM-027 | playwright | VM-027 | Sign in as ADMIN, open the Policy Editor for PERSONAL, change income, age, score, tenure and rate, save — a new policy version is appended and shown as the product's active version |
| E | QA-VM-028 | playwright | VM-028 | With the previously active version reopened after that save — its income, age, score, tenure and rate read identical to their pre-save values |
| E | QA-VM-029 | playwright | VM-029 | Submit an application against that product in the same running process — the decision shown cites the newly activated policy version id |
| E | QA-VM-030 | playwright | VM-030 | Signed in as CUSTOMER, attempt the Policy Editor save — the request is refused 403 and the version list gains no row |
| E | QA-VM-035 | api | VM-035 | POST /applications → 201 — as CUSTOMER for a chosen product; the application is SUBMITTED and carries the product's current policy_version_id |
| E | QA-VM-036 | api | VM-036 | POST /applications → 201 — the body carries a numeric credit_score stored against the application |
| E | QA-VM-037 | api | VM-037 | POST /applications → 201 — decision.outcome is one of AUTO_APPROVE, AUTO_REJECT or MANUAL_REVIEW with at least one reason code |
| F | QA-VM-038 | api | VM-038 | POST /applications → 201 — document_checklist matches the pinned version's required-document list item for item |
| F | QA-VM-039 | api | VM-039 | GET /applications/{application_id} → 200 — SUBMITTED, storing the policy_version_id resolved at submission |
| F | QA-VM-040 | api | VM-040 | GET /applications/{application_id} → 200 — after a newer policy version is activated; stored policy_version_id and checklist are unchanged |
| F | QA-VM-041 | api | VM-041 | GET /applications/{application_id} → 200 — every checklist item carries its document type and status PENDING |
| G | QA-VM-042 | playwright | VM-042 | Sign in as CUSTOMER, open Apply, select a product, enter valid details and submit — the confirmation shows the new application in SUBMITTED state |
| G | QA-VM-043 | playwright | VM-043 | On that confirmation screen — every required-document checklist item for the chosen product is listed |
| G | QA-VM-044 | playwright | VM-044 | Render the Apply form — no co-applicant field and no guarantor field is present |
| G | QA-VM-045 | api | VM-045 | POST /applications → 422 — declared income below the product minimum; error reads PolicyViolationException |
| G | QA-VM-046 | api | VM-046 | POST /applications → 422 — context names threshold_kind min_income and the configured_value it was checked against |
| G | QA-VM-047 | api | VM-047 | GET /applications → 200 — after that refusal; no application row was persisted for it |
| G | QA-VM-048 | api | VM-048 | POST /applications → 201 — repeated with one identical age/income/credit-flag set; credit_score is identical on every call |
| G | QA-VM-049 | api | VM-049 | POST /applications → 201 — two submissions differing only in credit-history flags return different credit_score values |
| H | QA-VM-051 | api | VM-051 | POST /applications/{application_id}/decision → 200 — outcome is AUTO_APPROVE, AUTO_REJECT or MANUAL_REVIEW with at least one reason code |
| H | QA-VM-052 | api | VM-052 | POST /applications/{application_id}/decision → 409 — a reason code absent from the pinned version is refused ReasonCodeNotDeclared |
| H | QA-VM-053 | api | VM-053 | GET /applications/{application_id} → 200 — a new decision_record is appended and the current decision is the latest record |
| H | QA-VM-054 | api | VM-054 | POST /applications/{application_id}/decision → 200 — re-deciding a MANUAL_REVIEW case after a newer version is activated still cites the version pinned at submission |
| G | QA-VM-055 | api | VM-055 | POST /applications/{application_id}/documents/{document_id}/verification → 200 — {"status":"VERIFIED"}; the stored status reads VERIFIED |
| G | QA-VM-056 | api | VM-056 | POST /applications/{application_id}/documents/{document_id}/verification → 200 — REJECTED with a reason; the row reads REJECTED and carries that non-empty reason |
| G | QA-VM-057 | api | VM-057 | POST /applications/{application_id}/documents/{document_id}/verification → 422 — REJECTED with an empty reason; the stored status is unchanged |
| G | QA-VM-058 | api | VM-058 | GET /documents/queue → 200 — already-actioned documents are absent from the returned queue |
| I | QA-VM-059 | playwright | VM-059 | Sign in as UNDERWRITER and open the workbench — the queue lists exactly the applications in SUBMITTED or MANUAL_REVIEW state |
| I | QA-VM-060 | playwright | VM-060 | Open a MANUAL_REVIEW case review screen — it shows the credit score, the decision reason codes and each checklist document's verification state |
| I | QA-VM-061 | playwright | VM-061 | Decide that case from the review screen and save — the latest decision record reflects it and the case leaves the queue |
| I | QA-VM-062 | playwright | VM-062 | As ADMIN, filter the application list to one status and one product — only the matching rows are shown |
| I | QA-VM-063 | playwright | VM-063 | Override an AUTO_REJECT application with a comment and a reason code — a new decision record is appended and shown as the current decision |
| I | QA-VM-064 | playwright | VM-064 | Open the audit trail for that override — an entry shows the comment, the reason code, the acting user id and a timestamp |
| I | QA-VM-065 | playwright | VM-065 | Submit the override with a reason code absent from the pinned version — it is refused and no decision record is appended |
| I | QA-VM-066 | playwright | VM-066 | Sign in as CUSTOMER and open a submitted application's tracking view — the current status is shown |
| I | QA-VM-067 | playwright | VM-067 | On the tracking view for an application with unverified documents — every unverified required document is listed |
| I | QA-VM-068 | playwright | VM-068 | On the tracking view for a decided application — the decision and each of its reason codes are shown |
| I | QA-VM-069 | playwright | VM-069 | On the tracking view for an undecided application — no decision section is shown and no notification was dispatched |
| I | QA-VM-074 | api | VM-074 | GET /loans/{loan_id} → 200 — an approved application's loan carries one installment row per month of the product tenure |
| I | QA-VM-075 | api | VM-075 | POST /loans/{loan_id}/disbursement → 201 — the loan reads DISBURSED holding the released amount and a funding_source |
| I | QA-VM-076 | api | VM-076 | POST /loans/{loan_id}/repayments → 201 — outstanding_principal on the refreshed loan is lower than before the posting |
| J | QA-VM-077 | api | VM-077 | GET /loans/{loan_id} → 200 — the schedule principal column sums to the disbursed amount exactly, with no residual |
| J | QA-VM-078 | api | VM-078 | GET /loans/{loan_id} → 200 — total payable equals principal plus interest over the stored rows and the installment count equals the product tenure |
| J | QA-VM-079 | api | VM-079 | GET /loans/{loan_id} → 200 — for a schedule with a rounding residual, the final row principal equals the balance left after all preceding rows |
| J | QA-VM-080 | api | VM-080 | GET /loans/{loan_id} → 200 — each period interest derives from that period's opening balance at the pinned policy version's rate |
| K | QA-VM-082 | api | VM-082 | POST /loans/{loan_id}/disbursement → 201 — the loan record holds the released amount |
| K | QA-VM-083 | api | VM-083 | GET /loans/{loan_id} → 200 — holds a funding_source and reads DISBURSED with its schedule attached |
| K | QA-VM-084 | api | VM-084 | POST /loans/{loan_id}/disbursement → 201 — with the stub funding source; no external payment rail is called and no signed agreement artifact is produced |
| K | QA-VM-085 | api | VM-085 | POST /loans/{loan_id}/disbursement → 409 — AlreadyDisbursed on the second attempt; the recorded released amount is unchanged |
| L | QA-VM-086 | api | VM-086 | POST /loans/{loan_id}/repayments → 201 — outstanding principal falls by exactly applied_principal |
| L | QA-VM-087 | api | VM-087 | GET /loans/{loan_id} → 200 — a new immutable repayment_posting row records the payment and no pre-existing row was updated |
| L | QA-VM-088 | api | VM-088 | POST /loans/{loan_id}/repayments → 201 — for a loan 35 days past due, the stored delinquency_bucket reads DPD-30 after the posting |
| L | QA-VM-089 | api | VM-089 | POST /loans/{loan_id}/repayments → 201 — a posting clearing every overdue installment leaves the bucket CURRENT with no late fee or penal interest charged |
| K | QA-VM-090 | api | VM-090 | POST /operations/end-of-day → 200 — for a given as_of_date; each seeded loan's stored bucket matches its days past due at that date |
| K | QA-VM-091 | api | VM-091 | POST /operations/end-of-day → 200 — a second run for the same as_of_date leaves every bucket and stored row byte-identical |
| K | QA-VM-092 | api | VM-092 | POST /operations/end-of-day → 200 — for an as_of_date before a loan's first due date, that loan's bucket reads CURRENT |
| K | QA-VM-093 | api | VM-093 | POST /operations/end-of-day → 200 — no fee, penal interest or collections record was created by the run |
| M | QA-VM-094 | playwright | VM-094 | Sign in as CUSTOMER and open a disbursed loan's view — every installment is listed with its due date and amount |
| M | QA-VM-095 | playwright | VM-095 | On that loan view — the current outstanding principal and the current delinquency bucket are both shown |
| M | QA-VM-096 | playwright | VM-096 | Post a repayment from the loan view and reload — the displayed outstanding principal reflects that posting |
| M | QA-VM-097 | playwright | VM-097 | On the loan view for a delinquent loan — no early settlement, foreclosure or prepayment quote is offered |
| M | QA-VM-098 | playwright | VM-098 | Sign in as ADMIN and open the portfolio dashboard — loan count and value are shown for every product and bucket combination |
| M | QA-VM-099 | playwright | VM-099 | On the dashboard — total_overdue equals the sum of overdue installment amounts across all active loans |
| M | QA-VM-100 | playwright | VM-100 | Call the dashboard with a CUSTOMER session — 403 and no portfolio figures are rendered |
| M | QA-VM-101 | playwright | VM-101 | Load the dashboard with the end-of-day operation spied — the figures come from stored bucket state and the run is never invoked |
| H | QA-VM-102 | playwright | VM-102 | Run the axe-core scan over every screen in the customer-facing registry — 0 WCAG 2.1 AA violations, no rule suppressed, and 100% of registered screens covered |
| H | QA-VM-103 | playwright | VM-103 | Traverse each registered screen's primary flow with the keyboard only — the flow completes, no focus trap is hit, and every interactive control exposes an accessible name and a visible focus indicator |
| H | QA-VM-104 | playwright | VM-104 | Add a customer-facing route absent from the screen registry and run the accessibility suite — the suite fails and names the unregistered route |
| E | QA-VM-105 | api | VM-105 | GET /products → 200 — load run across the registered read-heavy set (GET /products, GET /applications, GET /loans/{loan_id}, GET /dashboard); p95 under 500 ms and error rate under 1% on each |

## What Is Explicitly Untested (and why)

| Area | Reason |
| --- | --- |
| Late fees, penal interest, collections records | Out of scope by SG-1. Not merely untested — asserted *absent* by VM-073, VM-089 and VM-093, so adding one fails the suite. |
| Live credit bureau integration | E5-S1 scores behind a port with a deterministic stub. No live provider credential exists in any environment; VM-050 asserts no outbound call. |
| Real payment rail / bank disbursement | Stubbed funding source per SG-2. VM-084 asserts no external rail is called. |
| Signed loan agreement artifacts | Out of scope for v1; VM-084 asserts none is produced. |
| Co-applicant and guarantor flows | Out of scope for v1; VM-044 asserts the Apply form exposes no such field. |
| Early settlement, foreclosure, prepayment quotes | Out of scope for v1; VM-097 asserts the loan view offers none. |
| Customer notifications (email / SMS / push) | No dispatch channel in v1; VM-069 asserts nothing is dispatched for an undecided application. |
| Rate limiting and login attempt throttling | Confirmed out of scope for v1 at the design gate (U-5). The throttle gap is a knowingly accepted risk, not an oversight — no test asserts either presence or absence. |
| Second database engine / external provider endpoints | VM-008 asserts the compose inventory configures neither. |
| Browsers other than Chromium | Playwright runs Chromium only. Cross-browser rendering is unmeasured; the a11y and keyboard suites are Chromium-scoped. |
| Write-path and end-of-day performance | The SLO harness registers only the four read-heavy GETs (E15-S3-AC1). POST latency and end-of-day run duration carry no p95 budget in v1. |
| Concurrency and race conditions | No concurrent-writer test. Disbursement idempotence is structural (UNIQUE on loan id) rather than proven under parallel load, and repayment allocation is never exercised concurrently. |
| Data migration from a legacy system | Greenfield. Migrations are forward-only from empty and lint-checked for destructive statements, never replayed against production-shaped data. |
| Token revocation / logout invalidation | JWT TTL is 60 minutes (D-3) with no revocation list in v1; an early-revocation path does not exist to test. |

## Environment Assumptions

- `docker compose up` from a clean checkout brings up exactly three services — Postgres, the Python 3.12 FastAPI backend, the TypeScript React-Vite frontend — and all three report healthy; `GET /health` answers 200 within 1 s of startup.
- **Seed data is a fixture, not a migration:** at least three products (PERSONAL, VEHICLE, EDUCATION), each pinned to its own distinct policy version with differing income, age, score, tenure and rate thresholds, plus one user per role (CUSTOMER, UNDERWRITER, ADMIN).
- **Time is injected, never read from the wall clock.** Every delinquency and end-of-day row is driven by an explicit `as_of_date`; no test depends on the day it runs. That is what makes VM-091's byte-identical second run assertable at all.
- **Money** crosses every boundary as a Decimal quantized to 2dp, serialized as a quoted string (D-G). No minor-unit integer conversion exists anywhere, including at the browser edge (D-J).
- **Sessions** are JWTs with a 60-minute TTL (D-3). `api` checks attach a role token directly; `playwright` checks sign in through the UI.
- **No network egress.** The credit bureau and the funding rail are in-process stubs; a test that reaches the network is a failing test.
- Playwright drives **Chromium** only. Accessibility uses axe-core against the screen registry; the SLO run uses the in-process load driver, not an external load tool.

## Sprint Pass / Fail

The sprint passes when **all** of the following hold:

1. Every one of the 107 matrix rows is green at each of its `required_layers` — no row passing at a layer below the one the matrix assigns it.
2. The architecture suite reports **0** violations: six-layer one-way dependencies, policy_version and schedule_installment immutability, the EMI principal/rate/tenure invariant, and **0** float arithmetic operations in money code paths.
3. The invariant registry completeness assertion passes — every registered invariant has an executing test, and an orphaned invariant fails the suite by name.
4. p95 **< 500 ms** and error rate **< 1%** on each of the four registered read-heavy endpoints, with the measured figures recorded in the evaluation report.
5. **0** WCAG 2.1 AA violations across every registered customer-facing screen, no rule suppressed, and keyboard-only traversal completes each primary flow.
6. Coverage at or above the **80%** floor, tracked against the 100% meaningful-coverage target.
7. Every production commit carries agent co-authorship and a passing pre-commit gate record, with a `/gate` attestation recording **0** hand-written production lines (NFR-11).

Any red row in 1-7 fails the sprint. The registry completeness assertions in 3, 4 and 5 are why a later story cannot quietly escape the gate: a new screen or read endpoint that is never registered fails the suite rather than going unmeasured.


### Layer decisions taken at the test gate

- **Static assertions are `unit`, not `api`.** 12 rows — the policy_version and schedule_installment immutability scans, the migration lint, the invariant-registry suite, git provenance, the `/gate` attestation, the scoring-stub collaborator check and the SLO report/registry assertions — assert over source, migrations, git history or a written report, not over a served request. They are enforced by the architecture suite and the pre-commit gate set, and are deliberately **not** sprint-contract checks. This matches VM-010, where the backend float scanner was already `unit`.
- **Three observability NFR rows carry `api` evidence as well as `unit`.** VM-003 and VM-004 (correlation id with and without an inbound header) and VM-005 (`GET /health` under 1 s) are observable over a served request, so proving them only at the log-capture fixture would leave the real request path unexercised. All three observe `GET /health`, the only endpoint E15-S1 builds in its own group — an evaluator check may only name an endpoint that exists by the end of the group it is frozen into.
- **VM-001 (no PII in logs) stays `unit`.** Its api evidence would need an endpoint that *accepts* PAN, Aadhaar and salary content, and the only one is `POST /applications`, which E4-S1 builds five groups later. It is proven at the log-capture fixture E15-S1 produces, and incidentally re-exercised by every later api check, since the redaction filter is asserted installed on 100% of loggers (VM-002).
- **Concurrency stays untested for v1**, with idempotence resting on the UNIQUE constraint on loan id and repayment allocation on FIFO plus the `applied_principal + applied_interest = amount` CHECK constraint — both structural, so a concurrent writer corrupts nothing even unproven.

## Test Levels

- **unit** / **api** / **e2e** as tagged on each matrix row. Unit rows stay on the seam; they are not evaluator checks.

