# Security Review — ai-native-capstone-truelend — /gate --group A round 3

**Date:** 2026-09-14 · **HEAD:** `ba457bf` · **Range:** `14e9487..HEAD` · **Reviewer:** security-reviewer instance 1/3 (canonical)

## Summary

- BLOCK findings: **0**
- WARN findings: **6**
- INFO findings: **4** (+2 fixed items retained as INFO for the record)
- **Overall verdict: PASS** (no critical/high finding on a reachable path)

Both round-2 security BLOCKs (`B-1` metrics injection, `B-2` unbounded cardinality) are
**genuinely closed by execution**, and the SEC-103 partial (`SEC-003`) is closed. The
remaining findings are WARN-latent or INFO. Nothing in the group-A change set is exploitable
today, so the security gate does not block the merge. Two WARNs (`SEC-201`, `SEC-202`) are
timed to become BLOCKs the instant the E4-S1 / E1-S1 handlers land, and must be fixed first.

**Coverage caveat:** the computational tier is unprovisioned — gitleaks, semgrep and
pip-audit are absent and skipped, so the SAST and secrets tiers are **UNSCANNED, not passed**.
This inferential review is the only real coverage for the injection/authz/PII classes this
round. `npm audit`: 1 critical (vitest) + 1 high (vite), both devDependency-only, absent from
any production image — out of scope for a runtime finding.

## Priority 1 — round-2 remediation BLOCKs, re-tested at HEAD

### B-1 `/metrics` exposition injection — FIXED (INFO residual)

Reproduction attempt against a live server on port 8034 (raw sockets):
- Round-2 vector `GET /%22%7D%201%0Ahttp_requests_total%7B...%7D%209999%0A` → **404**, folded
  into the bounded `route="<unmatched>"` series. No forged `http_requests_total{...status="500"}`
  series appeared in `/metrics`.
- `slo-check.js --url http://127.0.0.1:8034` → `{"verdict":"pass","error_rate_pct":0}` against
  the 1% budget (round 2 drove this to 99.90%).
- Label channels enumerated: **route** is the matched template (`/health`, `/metrics`) or the
  constant `<unmatched>` — never attacker data. **status** is an int. **method** is filtered by
  the httptools/llhttp parser: a method containing CR (`GET\r`), a double-quote (`GE"T`), a
  backslash, or an unknown token (`FOOBAR`, `GET_PARAMETER`) all return **400** before the
  counter runs. Only parser-known method tokens (`M-SEARCH`, `PROPFIND`, `QUERY`, `ACL`,
  `PURGE`, …) reach the counter, and those contain no control characters.

**Residual (INFO, defence-in-depth):** `_LABEL_ESCAPES` still omits carriage return and the
other C0 control characters the pack flagged. This is unreachable given the parser filter above,
but the control is one parser-swap away from mattering. Escape/reject all C0 controls.

### B-2 `/metrics` unbounded cardinality — FIXED

Measured: 1500 GETs to distinct unmatched paths (`/nope-N-<rand>`) → the counter series count
stayed at **8** and the `http_request_duration_seconds_count` series count stayed at **8**; all
1500 collapsed into `route="<unmatched>"` (count 1501). `route_label()` returns the matched
template or the single `<unmatched>` bucket, and the new histogram dicts `_duration_counts` /
`_duration_totals` key on `(method, route_label(scope))`, inheriting that bound. The **method**
component does not re-open growth: unknown method tokens are rejected 400 by the parser, so
method is confined to llhttp's fixed method table.

## Priority 2 — carried findings re-judged at HEAD

| Finding | Disposition | Evidence |
|---|---|---|
| **SEC-003** sanitise_context int/key PII (SEC-103) | **FIXED (INFO)** | int Aadhaar → `[REDACTED]`; Aadhaar as key → `[REDACTED]`; `pan-ABCDE1234F` key → `pan-[REDACTED]`; str PAN → `[REDACTED]`; bool passes through harmlessly |
| **Redaction bypass by formatting** (SEC-201) | **WARN (latent)** | Live `scrub_text` LEAKS dot/underscore/slash-separated, NBSP, zero-width and fullwidth variants. **Zero production call sites** of `register_sensitive`/`redact_values` in `backend/src` (ba457bf added them only to the E4-S1/E1-S1 *specs*), so no real PII flows yet. Becomes BLOCK when those handlers are built. |
| **X-Request-ID** unvalidated/unbounded (SEC-203) | **WARN** | 16 KB id accepted, reflected verbatim, logged verbatim in the `request_id` field. No CRLF/log injection (parser rejects CR/LF; `json.dumps` escapes controls). |
| **Host-header open redirect** (SEC-204) | **WARN** | `GET /health/` + `Host: evil.example` → `307 Location: http://evil.example/health` (Starlette `redirect_slashes`) |
| **Public `/docs` `/openapi.json` `/redoc`** (SEC-207) | **INFO** | all 200; minimal surface in group A |
| **Missing security headers** (SEC-205) | **WARN** | `/health` has no CSP / X-Frame-Options / X-Content-Type-Options / HSTS |
| **PII retained as lru_cache keys** (SEC-202) | **WARN (latent)** | `_redaction_pattern` `@lru_cache(maxsize=256)` keyed on the raw sensitive value; retains up to 256 PII strings for process lifetime once call sites exist |
| **`/metrics` no auth** (SEC-208) | **INFO — deferral defensible** | Content is bounded RED counters + latency histogram, no PII/secrets/injectable series; E15-S4 Scope Out defers auth to E1-S1 (group B) |
| **`Money.multiply` bare `decimal.Overflow`** | not re-filed | Backend correctness/perf; no attacker-reachable path in group A (no route constructs Money from request input yet). Track with E9. |
| **money.ts thousands-separator regex** (SEC-206) | **WARN** | Quadratic: 20k digits 157 ms, 50k digits 1008 ms; unbounded magnitude reaches `format()` → client-side DoS |

## BLOCK Findings

None.

## WARN Findings

- **SEC-201** — redaction defeated by formatting (`backend/src/config/logging.py:102`). Latent
  (no call sites); escalates to BLOCK with E4-S1/E1-S1. Fix: NFKC-normalize + strip zero-width/
  formatting chars before matching.
- **SEC-202** — PII retained as `lru_cache` keys (`backend/src/config/logging.py:102`). Cache on
  a non-sensitive derived key or drop the cache.
- **SEC-203** — `X-Request-ID` unvalidated/unbounded (`backend/src/api/middleware.py:151`).
  Enforce a bounded charset/length; regenerate on failure.
- **SEC-204** — host-header-reflected open redirect (`backend/src/api/app.py:36`). Disable
  `redirect_slashes` or build Location from a configured canonical host.
- **SEC-205** — missing security response headers (`backend/src/api/app.py:42`). Add nosniff,
  frame protection, HSTS.
- **SEC-206** — quadratic `Money.format()` regex (`frontend/src/types/money.ts:78`). Bound
  integer length or use a linear formatter.

## INFO Findings

- **B-1 residual** — `_escape_label` omits `\r`/C0 controls (unreachable today).
- **SEC-207** — public `/docs` `/redoc` `/openapi.json`.
- **SEC-208** — `/metrics` unauthenticated (documented, defensible deferral).
- **SEC-209** — `HEAD /health` → 405 (compatibility, not security).

## Method notes / what I could not test

- Live testing used a throwaway uvicorn on **port 8034** (httptools/llhttp protocol, confirmed
  via `Config.load()`); server killed and port confirmed free; all scratch removed.
- **Two sibling instances mutated production files mid-review** (`routes.py:83` `_escape_label`
  neutralised to `return value`, `middleware.py:63` `route_label` changed to the raw path,
  each tagged `# MUTANT`). These are concurrent mutation-test artifacts, **not part of HEAD**. I
  restored both from `git checkout` and re-derived every verdict against the true HEAD code;
  `git status` for both files is clean. Untracked `backend/.eval-i3/`, `backend/sec3_probe.py`,
  `frontend/.eval-i3/`, `frontend/tests/unit/_eval_i2_b4.test.ts` belong to siblings and were
  left untouched.
- **UNSCANNED:** SAST (semgrep) and secrets (gitleaks) tiers — tools unprovisioned. Python
  dependency CVEs (pip-audit) — unprovisioned. These classes have only inferential coverage.
- The `X-Request-ID` "5 MB accepted" round-2 claim did not reproduce here — httptools rejects a
  200 KB header; 16 KB was the largest I confirmed accepted. The finding stands on the 16 KB
  reproduction.
