# Canvas Sync Check

Changed files checked: 4
Missing from Governs: 2
- .claude/state/red-phase-presnap.json
- specs/reviews/local-regression-gate-verdict.json

Missing from Operations: 2
- .claude/state/red-phase-presnap.json
- specs/reviews/local-regression-gate-verdict.json

## Proposed Canvas patch (deterministic)

Add to `## Governs`:

- `.claude/state/red-phase-presnap.json`
- `specs/reviews/local-regression-gate-verdict.json`

Add to `## Operations`:

- TODO(canvas-sync): document the operation that lands in `.claude/state/red-phase-presnap.json`
- TODO(canvas-sync): document the operation that lands in `specs/reviews/local-regression-gate-verdict.json`

Run `npm run canvas-sync -- --write` to apply this patch, then review. Or edit the Canvas by hand.

Update `specs\design\reasons-canvas.md` before treating the design as synchronized.
