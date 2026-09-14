# Amendment — REASONS Canvas sync for E1-S1's Types layer

**Amendment id:** `e1-s1-types-canvas-sync`
**Date:** 2026-09-14
**Trigger:** `node .claude/scripts/spdd-sync.js --write` after E1-S1's Types
layer landed. `canvas-sync-check` blocked on two changed paths with no canvas
entry, and the sync appended `Governs` / `Source paths` rows for them. This
amendment exists to satisfy `amendment-provenance`, which requires a matching
file here for any commit touching `specs/design/`.

No design decision changed. `specs/design/reasons-canvas.md` is the only
design file touched, and only its bookkeeping section.

## What landed

E1-S1 Operations steps 1-2, the first slice of group B:

- `backend/src/types/enums.py` — `Role`, `ApplicationStatus`,
  `DecisionOutcome`, `DocumentVerificationStatus`. The registry
  `component-map.md` names, so every later story imports these rather than
  repeating a string literal.
- `backend/src/types/identity.py` — `User` and `AuditEntry`, both frozen.

Implemented as designed, with three choices worth recording:

1. **`ApplicationStatus` has seven members, not six.** Decision **D-L**
   added `MANUAL_REVIEW` to the CONTEXT.md term after the design review
   (U-6). A six-member enum would be the pre-amendment shape, so the test
   asserts the count explicitly rather than only membership.
2. **`StrEnum` rather than `(str, Enum)`.** The project targets 3.12 and ruff
   `UP042` flags the older pair; both serialise a member as its own value
   through Pydantic and SQLAlchemy without a custom encoder.
3. **`AuditEntry.occurred_at` must be timezone-aware**, enforced by a
   validator. A naive timestamp cannot be ordered across deployments, and
   E1-S2's audit criterion reads a timestamp off this entry as evidence of
   when a privileged action happened.

## Notes for whoever continues E1-S1

- **The story owns no pytest file.** Its Operations say the acceptance
  criteria are verified by evaluator-run `QA-VM-012`..`QA-VM-015`. The unit
  tests added here (`backend/tests/unit/test_identity_types.py`) pin the
  shared vocabulary every later story imports, and they pass
  `ownership-check` only because the ratified `ownership-check` waiver is
  broader than its scope text describes. That is worth tightening rather than
  relying on.
- **Password hashing WAS specified and I missed it.** I raised it seven times
  as an open decision and defaulted to stdlib `hashlib.scrypt`. That was
  wrong: `architecture.md:107` names **`passlib[bcrypt]`** for credential
  hashing in its rendering-level library list, and `data-models.md:103`
  specifies `password_hash` as "NOT NULL, bcrypt; no plaintext column exists".
  I had read the story Operations and CONTEXT.md but never the architecture's
  dependency paragraph. Corrected to `passlib[bcrypt]`.

  One real constraint came with it. `passlib` 1.7.4 has been unmaintained
  since 2020 and breaks against `bcrypt` 4.1 and newer: its backend detection
  probes with a password longer than 72 bytes, which current bcrypt refuses
  rather than truncating, so `CryptContext.hash` raises on any input at all.
  `bcrypt` is therefore pinned below 4.1 (resolving to 4.0.1), which restores
  correct hash, verify and reject. That pin is the cost of honouring the named
  library rather than substituting the maintained `bcrypt` package directly.
  If the pin is unacceptable, using `bcrypt` directly is the alternative, and
  this is where that decision should be revisited.
- **Dependencies added** per the Operations: `sqlalchemy`, `alembic`, `pyjwt`
  and `psycopg[binary]`. `uv.lock` is now tracked, so these are pinned.
