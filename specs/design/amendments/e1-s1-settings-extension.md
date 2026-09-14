# Amendment — E1-S1 may extend E15-S1's Settings

**Amendment id:** `e1-s1-settings-extension`
**Date:** 2026-09-14
**Trigger:** E1-S1 step 3 reads a database URL and step 8 reads a JWT secret
and TTL, but `backend/src/config/settings.py` is owned by E15-S1 and the
"Modifies" table had no row for this pair. Only `component-map.md` changes.

## Why a row rather than the waiver

E1-S1's settings additions would have passed `ownership-check` anyway, because
the ratified `ownership-check` waiver is broader than its scope text describes
— it was written for two frontend config files and two package markers. Using
it here would have been the second time in two commits that a real ownership
question was absorbed by a waiver meant for something else, which is how a
waiver quietly becomes a blanket exemption.

E15-S1's own module docstring anticipates the extension in as many words:
*"Later stories may extend this same `Settings` class with DB URL / JWT
settings per the Config layer's responsibilities."* The Config layer is meant
to hold one settings class, not one per story, so the row records what the
design already intended.

## The change

`component-map.md` gains a Modifies row **E15-S1 → E1-S1** covering
`config/settings.py`.

## What landed behind it

`Settings` gains `database_url`, `jwt_secret`, `jwt_ttl_seconds` and
`jwt_algorithm`. `jwt_ttl_seconds` is 3600, fixing the 60-minute session
lifetime decision **D-M** states.

**Neither `database_url` nor `jwt_secret` has a default**, and that is the
substantive choice here. The first version of this commit defaulted
`database_url` to a working development DSN; `pre-write-gate`'s secret scan
rejected it and was right to — a committed default DSN carries credentials,
and a default signing key is the standard route by which a development secret
reaches production. Empty means the process fails fast at startup instead.

The development values now live in a new `.env.example`, which also documents
how to generate a real `jwt_secret` rather than shipping a placeholder anyone
could reuse.

## Not changed

No decision, contract or component ownership beyond the single row.
`data-models.md` already specifies `password_hash` as bcrypt and
`architecture.md:107` already names `passlib[bcrypt]`; both are followed, and
the correction to my earlier claim that hashing was unspecified is recorded in
`e1-s1-types-canvas-sync.md`.
