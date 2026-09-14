# Security Review — /gate --group A, round 4, instance 3 of 3

- **Axis:** security · **Emphasis:** availability, resource exhaustion, and the integrity of the SLO signal itself
- **HEAD under test:** `f3c25eb`
- **Worktree:** `C:/Users/rosuo/WORK/ai-native-capstone-truelend/.claude/worktrees/agent-ad8db03a77477db48`

## SECURITY VERDICT: PASS

**BLOCK 0 · WARN 6 · INFO 5**

> **Transcription note.** This instance could not write its own artifacts: `pre-write-gate.js`
> normalises `.claude/worktrees/<id>/specs/reviews/...` and fails to match its own
> `specs/reviews/**` allow-entry (**GI-011**). It declined to route around a security gate via a
> program-side write and reported inline instead. This file was transcribed by the gate lead from
> its final report; every measurement below is the instance's own. Machine-readable form:
> `specs/reviews/security-verdict-instance3.json`.

## Environment repair (disclosed)

The worktree was provisioned from `c4189ec` — an unrelated 2-commit lineage containing only a
README, with no review-context pack and no product source (**GI-010**). The instance reset its own
branch to `f3c25eb` and reviewed from there. Tree verified pristine afterwards: `git diff --stat
f3c25eb` empty, `git status` clean. No in-tree mutation — all probes ran against an esbuild bundle
and in-process app instances.

## Headline finding

**`f3c25eb` fixed the wrong half of its own problem.** `record_request` excludes `/metrics` from
`_request_counts` but still calls `observe_duration` unconditionally, so an anonymous scraper no
longer appears in the counters *but still dilutes the latency histogram*. The practical effect is
that the masking now leaves **no trace at all** in `http_requests_total`:

| Condition | Real | Reported |
|---|---|---|
| 40 × `/slow` at ~900 ms | p95 **975.0 ms** — BREACH vs 500 ms budget | p95 975 ms |
| \+ 2,000 anonymous `GET /metrics` in 2.3 s | p95 still 975 ms — still BREACH | p95 **4.8 ms** — PASS |

`errorRate` read 0.0000% in both states. Honest answer to the emphasis question: excluding
`/metrics` from its own counters made the signal *harder to reason about*, not safer.

## Findings

| ID | Level | File:line | Summary |
|---|---|---|---|
| **SEC4-001** | WARN | `middleware.py:113` | Real p95 breach masked by anonymous scrapes; `/metrics` excluded from the counter but not the histogram |
| **SEC4-002** | WARN | `middleware.py:104` | SEC3-003 residual: 50 errors + 50 successes = 50.0000% breach; + 20,000 anonymous `/health` = 0.2488% PASS. Only ~4,900 extra requests needed |
| **SEC4-003** | WARN | `money.ts:24` | Frontend `Money` unbounded: `1e20000000` → 1,888 ms / 26.7 MB string; `1e400000000` → V8 OOM, exit 134, from an 11-byte input |
| **SEC4-004** | WARN | `middleware.py:203` | `X-Request-ID` unvalidated/unbounded and structurally un-scrubbable — the formatter injects `request_id` *after* `RedactionFilter` runs |
| **SEC4-005** | WARN | `money.py:91` | `decimal.Overflow` escapes `multiply` in 0.00 ms — contract break (500 not 422), not a DoS |
| **SEC4-006** | WARN | `app.py:31` | Host-header-reflected redirect: `Host: evil.example` → 307 to `http://evil.example/health` |
| **SEC4-007** | INFO | `app.py:31` | No security response headers; `/docs` and `/openapi.json` anonymous 200 |
| **SEC4-008** | INFO | `logging.py:74` | PII redaction inert — zero production call sites; `ba457bf` touched specs only |
| **SEC4-009** | INFO | `serializers.py:24` | Declared wire pattern unenforced. Parse-cost DoS **refuted**: 4,000,000 chars rejected in 31.3 ms, linear |
| **SEC4-010** | INFO | `money.py:71` | The magnitude bound is an artifact of ambient `decimal` context, not an invariant (`prec=200` admits `1e100`) |
| **SEC4-011** | INFO | `middleware.py:165` | `seen` growth is app-driven only; **the `500` default is refuted as an attacker vector** |

## Sub-claims refuted by measurement

- **`X-Request-ID` log amplification is 1.00x**, not an amplification DoS (1,000,040 B in → 1,000,147 B logged). CRLF header-splitting fails (parser drops the injected header). JSON line integrity holds against quote/backslash/JSON-ish ids.
- **The `500` default is not client-reachable.** 5 × `curl --max-time 1` aborts against a 5 s handler recorded `6 × /slow status=200` and zero 5xx — uvicorn does not cancel the handler on client disconnect. Injected directly at the ASGI layer, `CancelledError` *does* record 500, but no client-reachable path produces it. Verified for httptools only.
- **Round 2's `Money.multiply` timing dispute is resolved — both instances were right about different scalars.** `multiply(Decimal)` = 0.00 ms; `multiply(10**1000000)` = 9,538 ms, of which **9,531 ms is CPython's int→Decimal coercion**, not the multiplication (94.81 ms at `10**100000` → 9,530.95 ms at `10**1000000`, quadratic).

## Remediation verified closed

- **B-4 / CR-304 `format()` is genuinely linear.** Old regex 59 / 254 / 1,015 / 4,102 ms at 12.5k/25k/50k/100k digits — a clean 4× per doubling, reproducing round 3's 4,091 ms. New walk 1.0 / 0.6 / 1.6 / 3.6 ms — **1,149× faster at 100k**. Real `Money.format()` over five doublings (12.5k→400k): 1.6 / 1.8 / 3.8 / 8.9 / 16.4 / 51.5 ms, flat at 0.07–0.13 µs per 1k digits. Output **byte-identical** to the old regex for n=1..60.
- **CR-301 bounded.** `PROPFIND` → `method="<other>"`; `FROBNICATE`, `GET1`, lowercase `get` → 400 *below* the ASGI layer.
- **B-2 bounded.** 300 unique random paths → one `route="<unmatched>"` series, count 302; whole exposition 78 lines.
- **B-1 closed — but by label bounding, not by the escaping.** Quote/brace and CRLF path payloads → 404, zero forged series. `\r` remains absent from `_LABEL_ESCAPES` (`routes.py:78`), harmless only while both label dimensions stay closed sets.

## Classes NOT covered — unscanned, not clean

- **Secrets** — gitleaks unprovisioned. `settings.py` manually confirmed env-sourced (`TRUELEND_` prefix, no hardcoded credentials, no debug flag), but not machine-scanned.
- **SAST / injection** — semgrep unprovisioned; coverage is manual and dynamic only. No SQL/ORM/template/shell sink exists in the changed set, so residual risk is low but unscanned.
- **Python dependency CVEs** — pip-audit unprovisioned; `backend/uv.lock` unaudited.
- **JS dependency CVEs** — carried forward unverified by this instance (1 critical vitest, 1 high vite, devDependency-only).

The clean `security-scan.json` was not treated as evidence at any point.
