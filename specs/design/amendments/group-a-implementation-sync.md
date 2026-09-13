# Amendment — Group A implementation sync

**Amendment id:** `group-a`
**Trigger:** `node .claude/scripts/spdd-sync.js --write` (SECTION 5 of the ratchet gate,
run after Group A — E15-S1, E9-S1, E11-S1 — landed) rewrote `specs/design/reasons-canvas.md`
to append `Governs`/`Source paths` bookkeeping entries for files that changed in the working
tree but had no canvas entry yet. This amendment exists solely to satisfy the
`amendment-provenance` sensor, which requires a matching file under
`specs/design/amendments/` for any commit touching `specs/design/`.

## Per-story impact

- **E15-S1** (Structured JSON logging, correlation id propagation, PII redaction and health
  endpoint) — implemented exactly as designed: `JSONLogFormatter` + `RedactionFilter` in
  `backend/src/config/logging.py`, `CorrelationIdMiddleware` in `backend/src/api/middleware.py`,
  `GET /health` in `backend/src/api/platform/routes.py`, wired by `create_app()` in
  `backend/src/api/app.py`. No new entity, no new endpoint beyond `/health`. Seam: the
  Cross-cutting "Correlation Id" / "Redaction" / "Observability" entries in
  `specs/design/architecture.md` (SG-9).
- **E9-S1** (Money value type) — implemented exactly as designed under D-G/D-J:
  `backend/src/types/money.py` (`Decimal`, 2dp quantized), `backend/src/api/serializers.py`
  (the single quoted-2dp-string Pydantic serializer), `frontend/src/types/money.ts` (decimal.js
  wrapper, never a float, no minor-unit conversion). No new entity beyond `Money`, which the
  architecture and story bundle already named. Seam: D-G, D-J, SG-6.
- **E11-S1** (Delinquency bucket ladder) — implemented exactly as designed under D-B/D3:
  `DelinquencyBucket` enum in `backend/src/types/delinquency.py` (Types layer, zero imports);
  the DPD floor boundaries and the canonical `classify_by_days_past_due`/`classify` functions in
  `backend/src/config/delinquency.py` (Config layer), matching the architecture's stated
  mitigation for the "DPD boundaries re-derived" coupling risk verbatim ("one Config-layer
  mapping function"). No sixth bucket, no orthogonal NPA flag, no fee/charge field. Seam: D-B,
  SG-1, and the coupling-risk table in `specs/design/architecture.md`.

## Seam citations

- `specs/design/architecture.md` — decisions D-B, D-G, D-J; Cross-cutting section
  (Correlation Id, Redaction, Errors, Observability); Coupling-risk table (DPD boundary
  duplication, shared mutable money model); Components table (Types/Config/API layer
  responsibilities).
- `specs/design/reasons-canvas.md` — Safeguards SG-1, SG-6, SG-9.
- `specs/design/component-map.md` — rows for E15-S1, E9-S1, E11-S1 (owned files, Produces
  edges consumed by Group B+ stories).

## Breaking changes

None. No API contract, schema, or existing-consumer behavior changed — this is the first
group to land production code in a greenfield build (`backend/` and `frontend/` had no source
beyond scaffolding before this group). The `Governs`/`Source paths` entries `spdd-sync.js`
appended to `reasons-canvas.md` for non-design bookkeeping artifacts (state logs, bundle JSON,
sprint-contract/review snapshots already dirty in the working tree from a prior partial run)
are sync noise, not an architectural change; they are recorded here only to satisfy the
provenance sensor's literal requirement, not because any of those files represent a design
decision.
