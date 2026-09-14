# Quality card

Generated: 2026-09-14T12:16:07.567Z
Range: `14e9487..HEAD`

**Overall: FAIL** — 7 pass · 3 fail · 0 missing · 4 skipped

| Check | Status | Detail |
|---|---|---|
| evaluator | ❌ fail | — |
| code_review | ❌ fail | All three prior code-review BLOCKs (CR-001 error envelope, CR-002 request-scoped PII redaction, CR-003 money-guard exemption) are independently verified CLOSED by executing the code at HEAD, not by reading its comments. Two NEW BLOCKs found, both introduced by the remediation commits themselves: (1) the /metrics RED counter is keyed on the raw request path instead of the matched route template, giving unbounded attacker-controlled counter cardinality (500 unknown paths -> 500 permanent series, 37 KB /metrics body) and destroying per-route aggregation as soon as a path-param route lands; (2) the new global HTTPException handler discards exc.headers, so 405 responses lose the RFC-required Allow header and a future 401 loses its WWW-Authenticate challenge - a regression against the FastAPI default handler it replaced. Four of the six reviewer hypotheses supplied in the spawn prompt were refuted with evidence (contextvar non-unwind, bare asserts under -O, per-request Settings(), and the loggerDict-once gap for the common propagating case). E11-S1 and the Money type are clean; no file exceeds 300 lines and no function exceeds 24. |
| security | ❌ fail | [object Object] |
| security_scan | ❓ unknown | — |
| ownership | ✅ pass | — |
| regression | ✅ pass | pass |
| verification_matrix | ✅ pass | — |
| evidence_integrity | ✅ pass | no sprint contract declares playwright checks — nothing to verify |
| observability | ✅ pass | [object Object] |
| perf_smell | ✅ pass | [object Object] |
| slo | ✅ pass | pass |

## Human navigation

- [`docs/CODEBASE.md`](../../docs/CODEBASE.md)
- [`specs/brownfield/wiki/WIKI.md`](../../specs/brownfield/wiki/WIKI.md)
- [`specs/brownfield/symbol-map.md`](../../specs/brownfield/symbol-map.md)
- [`specs/reviews/walkthrough.md`](../../specs/reviews/walkthrough.md)

## How to use this card

1. Confirm **Overall PASS** before opening or merging a PR.
2. Read `specs/reviews/walkthrough.md` for a logical (non-alphabetical) change tour.
3. Read `docs/CODEBASE.md` for system orientation without opening every source file.
4. Drill into failing rows via the matching file under `specs/reviews/`.
