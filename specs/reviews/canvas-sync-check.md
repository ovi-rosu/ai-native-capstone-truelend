# Canvas Sync Check

Changed files checked: 7
Missing from Governs: 4
- .claude/state/red-phase-presnap.json
- .claude/state/task-envelope.json
- features.json
- specs/reviews/review-context-pack.md

Missing from Operations: 5
- .claude/state/red-phase-presnap.json
- .claude/state/task-envelope.json
- features.json
- project-manifest.json
- specs/reviews/review-context-pack.md

## Proposed Canvas patch (deterministic)

Add to `## Governs`:

- `.claude/state/red-phase-presnap.json`
- `.claude/state/task-envelope.json`
- `features.json`
- `specs/reviews/review-context-pack.md`

Add to `## Operations`:

- TODO(canvas-sync): document the operation that lands in `.claude/state/red-phase-presnap.json`
- TODO(canvas-sync): document the operation that lands in `.claude/state/task-envelope.json`
- TODO(canvas-sync): document the operation that lands in `features.json`
- TODO(canvas-sync): document the operation that lands in `project-manifest.json`
- TODO(canvas-sync): document the operation that lands in `specs/reviews/review-context-pack.md`

Run `npm run canvas-sync -- --write` to apply this patch, then review. Or edit the Canvas by hand.

Update `specs\design\reasons-canvas.md` before treating the design as synchronized.
