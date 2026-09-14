# Quality card

Generated: 2026-09-14T06:56:16.487Z
Range: `14e9487..HEAD`

**Overall: FAIL** — 4 pass · 5 fail · 0 missing · 4 skipped

| Check | Status | Detail |
|---|---|---|
| evaluator | ❌ fail | — |
| code_review | ❌ fail | [object Object] |
| security | ❌ fail | [object Object] |
| security_scan | ❓ unknown | — |
| ownership | ❌ fail | — |
| regression | ❌ fail | blocked |
| verification_matrix | ✅ pass | — |
| evidence_integrity | ✅ pass | no sprint contract declares playwright checks — nothing to verify |
| observability | ✅ pass | [object Object] |
| perf_smell | ✅ pass | [object Object] |
| slo | ❓ unknown | unreachable |

## Human navigation

- [`specs/brownfield/wiki/WIKI.md`](../../specs/brownfield/wiki/WIKI.md)
- [`specs/brownfield/symbol-map.md`](../../specs/brownfield/symbol-map.md)
- [`specs/reviews/walkthrough.md`](../../specs/reviews/walkthrough.md)

## How to use this card

1. Confirm **Overall PASS** before opening or merging a PR.
2. Read `specs/reviews/walkthrough.md` for a logical (non-alphabetical) change tour.
3. Read `docs/CODEBASE.md` for system orientation without opening every source file.
4. Drill into failing rows via the matching file under `specs/reviews/`.
