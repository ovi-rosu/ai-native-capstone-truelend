# Amendment — component-map ownership, group A gate remediation

**Amendment id:** `group-a-gate-remediation`
**Date:** 2026-09-14
**Trigger:** the `/gate --group A` verdict (BLOCK, `code-review` axis: 3 BLOCK /
20 WARN / 8 INFO). Two of the remediations could not be carried out under the
component map as frozen, so `specs/design/component-map.md` is amended here. The
design receipt was re-recorded (`specs/reviews/design-approval.json`, round 3)
and the plan re-sealed.

Only `component-map.md` changes. `api-contracts.md` is deliberately **not**
amended: in both the `/health` and `/metrics` findings it is the authoritative
frozen side, so the code changes to match it, not the reverse.

## Change 1 — E15-S1 owns three further test files

**Before:** E15-S1 owned one test file, `backend/tests/unit/test_log_redaction.py`.

**After:** it also owns `backend/tests/unit/test_correlation_id.py`,
`backend/tests/unit/test_error_envelope.py` and
`backend/tests/unit/test_health_probe.py`.

**Why:** the single file had reached 519 lines — past the 500-line hard limit —
carrying six distinct responsibilities (PII redaction, logger topology,
correlation id, the error envelope, the health probe, and the PII architecture
control). `pre-write-gate` refused further edits and was right to: one file, one
responsibility. The alternative was to trim the rationale out of the test
docstrings to squeeze under the cap, which would have dodged a gate that was
reporting a real SRP violation and left the file to hit the wall again on the
next story touching E15-S1.

The split is by responsibility, not by size. No acceptance criterion changed and
no test assertion was weakened; the blocks moved verbatim.

## Change 2 — E1-S2 may modify E1-S1's policy router

**Before:** the "Modifies (tracer then deepening, same cluster)" table had no row
for the E1-S1 → E1-S2 pair.

**After:** a row authorises E1-S2 to add `require_roles(ADMIN)` and the audit
append to `backend/src/api/policy/routes.py`, owned by E1-S1.

**Why:** E1-S1's Scope Out deliberately ships `POST /products/{code}/policy-versions`
with authentication but no role enforcement, and decision **D-F** makes
`require_roles` the single enforcement point, ruling out a per-route hand-written
check in E1-S1. The enforcement therefore *has* to be retrofitted by E1-S2 onto a
file it does not own — which is precisely the tracer-then-deepening pattern the
Modifies table exists to record. Without the row, `ownership-check` would have
blocked every group C commit, and the story's own authored Operations (step 7)
would have been unimplementable as written.

This was surfaced by reviewing group B/C's Operations before building, not
discovered mid-wave.

## Not amended, deliberately

- **`api-contracts.md`** — frozen and authoritative. `/health` gains `database`
  and `version` in code; `/metrics` gets implemented under E15-S1. The contract
  is the oracle in both cases.
- **The other unowned-route defects** (session 4, defects 2 and 4-6: the
  origination routes attributed to E6-S2/E7-S1/E8-S1, the typed-error subclass
  home, the E3-S1 repository signature, `LoanRepository.set_status`) are left
  open. Each is decided at the group that reaches it, with that group's context,
  rather than pre-emptively widened here.
