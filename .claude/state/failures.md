# Failure Log
<!-- Append-only. Used for pattern detection → learned rules extraction. -->
<!-- When 2+ entries share the same Category, extract a Learned Rule to .claude/state/learned-rules.md -->

<!-- ENTRY FORMAT (copy this for each new failure):

## Group {ID} — Failure #{N}
- **Date:** {ISO 8601}
- **Category:** {lint_format | type_error | test_failure | import_error | coverage_drop | api_check_fail | playwright_fail | design_score_low | docker_fail | architecture_drift}
- **Story:** {story ID}
- **Attempt 1:**
  - Error: {error message with file:line if available}
  - Fix: {what was tried}
  - Result: FAIL — {why it failed}
- **Attempt 2:**
  - Error: {error message}
  - Fix: {what was tried}
  - Result: FAIL — {why it failed}
- **Attempt 3:**
  - Error: {error message}
  - Fix: {what was tried}
  - Result: FAIL — 3 attempts exhausted
- **Escalation:** User notified. Marked BLOCKED. Skipped to next group.
- **Pattern:** {describe the recurring pattern if visible}

-->

## 2026-09-13 — Group A (wave 1) BLOCKED before any code: task-envelope scope
- **Group:** A (E15-S1, E9-S1, E11-S1) · mode full · sequential lane
- **Category:** authorization / infrastructure (not a code failure — self-heal attempts do not apply)
- **What failed:** `/implement` Step 0.2 must persist the Generation Contract "Operations"
  section into specs/stories/{id}.md (all 29 stories currently read "- pending") before any
  teammate may spawn. `.claude/state/task-envelope.json` (task `truelend-build`, tier R3)
  lists allowed_paths WITHOUT `specs/stories/**`, so pre-write-gate.js and
  pre-bash-gate.js both refuse the write.
- **Evidence:**
  - `node .claude/scripts/validate-generation-contract.js --mode implementable --story E15-S1` -> exit 1, "Operations is still pending"
  - `node .claude/scripts/bundle-check.js --mode implementable` -> exit 1, 29/29 stories "Operations is still pending"
  - direct probe: a zero-byte bash append to specs/stories/E1-S1.md -> BLOCKED by pre-bash-gate ("outside task truelend-build's allowed_paths")
  - `node .claude/state/scope-audit.js` -> 0 story-owned product files blocked; only harness-record paths blocked
- **Also blocked downstream by the same envelope (will bite later, same fix):**
  specs/design/reasons-canvas.md (spdd-sync.js --write / canvas-sync-check, SECTION 5 every group),
  specs/design/amendments/** (SECTION 8), docker-compose.yml + .env.example (E15-S2, group B),
  README.md (SECTION 11 success step).
- **Correctly blocked, leave as is:** specs/test_artefacts/** and sprint-contracts/** are frozen
  (`contract-freeze.js --check` reports hashes match).
- **Not attempted:** no gate bypass, no forged authority receipt, no envelope self-amendment.
  `task-envelope.js amend` needs a signed `amend_task` capability receipt with 2 distinct human
  approvals and `.claude/authority/` does not exist. Envelope scope is a human authorization decision.
- **Second, independent blocker:** `docker` is not installed on this machine while
  project-manifest.json#verification.mode is `docker`. Blocks E15-S2 (compose stack) and the
  end-of-run evaluator boot. `uv` was also missing and HAS been fixed this session (uv 0.12.13 on PATH).
