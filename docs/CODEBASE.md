# Codebase map (human homepage)

> Living orientation document. Deterministically rendered from the code-graph + CONTEXT.
> Prefer this page + concept wiki over opening the whole tree.

## What this system is

Mode: `--prd` adopt-only. Source: `prd/truelend.md` (copied to `specs/brd/source-frd.md`). Spine: `specs/brd/brd-requirements.json` — **29 requirements**, adopted verbatim. Do not restate them here.

_Source: `specs/brd/BRD.md`_

## At a glance

| Metric | Value |
|---|---|
| Indexed files | 0 |
| Graph edges | 0 |
| Concept pages | 0 |
| Wiki cluster pages | 0 |

## How to run / test / gate

```bash
# project-specific — see README / init.sh
./init.sh                 # or docker compose up
npm test                 # or pytest / vitest
/gate                    # pre-merge quality gate
npm run quality-card     # trust receipt
npm run ask -- "..."     # ask the codebase
```

## Architecture (hub modules)

_No hubs yet — run `/code-map` or wait for graph-refresh._

## Entry points

_No route/main entrypoints detected in the graph._

## Concept pages (clusters)

_Run `node .claude/scripts/nav-concepts.js` or `nav-query.js refresh`._

## DeepWiki cluster pages

_Run `/code-map` to render `specs/brownfield/wiki/`._

## Critical paths & debugging

- Metrics path: `/metrics`
- SLO: error_rate_pct≤1 · p95_ms≤500
- Prefer structured logs with `request_id` / `X-Request-ID` correlation.
- Quality receipt after changes: `specs/reviews/quality-card.md`.
- Ask navigation: `npm run ask -- "where is auth validated?"`.

## If X breaks, start here

| Symptom | Start |
|---|---|
| Auth / session failures | concept or entry modules matching `auth` / `session` |
| Slow API | quality-card perf + `/metrics` + N+1 smells (`npm run perf-smell`) |
| Silent failures | structured logs + `request_id`; observability gate |
| Merge confidence | `specs/reviews/quality-card.md` + `walkthrough.md` |
| "Where is X?" | `npm run ask -- "X"` |

## Machine-readable companions

- `specs/brownfield/code-graph.json` — dependency DAG (agents + tools)
- `specs/brownfield/symbol-map.md` — symbols with line ranges
- `specs/brownfield/wiki/WIKI.md` — deterministic DeepWiki index
- `.harness/wiki.json` — steer wiki priorities (Devin `.devin/wiki.json` analogue)
