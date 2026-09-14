# Canvas Sync Check

Changed files checked: 4
Missing from Governs: 1
- .claude/state/red-phase-presnap.json

Missing from Operations: 1
- .claude/state/red-phase-presnap.json

## Proposed Canvas patch (deterministic)

Add to `## Governs`:

- `.claude/state/red-phase-presnap.json`

Add to `## Operations`:

- TODO(canvas-sync): document the operation that lands in `.claude/state/red-phase-presnap.json`

Run `npm run canvas-sync -- --write` to apply this patch, then review. Or edit the Canvas by hand.

Update `specs\design\reasons-canvas.md` before treating the design as synchronized.
