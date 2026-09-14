# Security Review — TrueLend Group A, round 4, security instance 1 of 3 — 2026-09-14

Target commit f3c25eb. Scope: the two remediation commits since round 3 (ab0fd6e bound the method label and made grouping linear; f3c25eb stopped the metrics scrape diluting its own error rate) plus immediate data-flow neighbours. Both HTTP parsers present (h11 0.16.0, httptools 0.8.0). Baseline suite: 108 passed. Every claim is backed by an executed request or command.

## Summary
- BLOCK findings: 0
- WARN findings: 3
- INFO findings: 5
- Overall verdict: PASS (0 BLOCK-level vulnerability)

## Remediation verified closed (by attack)

### CR-301 method-label cardinality bound — CLOSED under BOTH parsers
Output domain of method_label() is provably the 9 ASCII constants + <other>; no attacker string is ever returned (Unicode .upper() expansions map to a known bucket or <other>).
- In-process: 22,003 distinct method tokens via the shipped record_request path -> 1 counter series, 1 duration series, 1,348 bytes retained (round 3: 25.3 MB). Known methods keep their own labels.
- Live h11 (port 8021): 3,000 distinct tchar method tokens over one keep-alive connection -> all collapsed to method="<other>"; /metrics body 3.6 KB.
- Live httptools (port 8022): BOGUSMETHOD /health -> 400 below the ASGI layer; 20 distinct bogus methods produced zero counter series.

### B-1 /metrics exposition injection — CLOSED
Labels are the bucketed method (a constant) and the matched route template or <unmatched>; the raw path never reaches a label. Live h11 attacks with percent-encoded quote/newline/CRLF payloads all returned 404 and collapsed to route="<unmatched>"; post-attack body had no forged/injected/admin token, no raw CR (0x0d), no NUL. Could neither forge a series nor mask an outage.

### B-4 money.ts ReDoS — CLOSED
f3c25eb replaced the quadratic lookahead with a linear forward walk. No dangerouslySetInnerHTML/innerHTML in changed frontend; MoneyText.tsx uses JSX text interpolation (React auto-escaping). No XSS.

## WARN Findings

### [SEC3-003] Unauthenticated caller can still mask a real SLO breach
File: backend/src/api/middleware.py:95-115; root cause .claude/hooks/lib/prom-parse.js:37-90. Severity: medium (WARN).
f3c25eb excludes only /metrics from its own counters. errorRate() and histogramP95() still sum globally across every route, and /health is unauthenticated with no rate limit. Proven with the real sensor code: a true 50% outage (errorRate 50.0000%, p95 500 ms, both BREACH the 1%/500ms budgets) drops to 0.9804% and 4.8 ms (both under budget) after 5,000 fast /health 200s an anonymous caller can trivially generate — outage and latency fully MASKED. Residual severity medium. Not a BLOCK for this diff: the diff strictly improved matters, the true fix (per-route aggregation) is in the untouched harness file, and auth/rate-limiting are documented deferrals to group B.
Fix: aggregate the SLI per business route; add rate limiting with the auth layer.

### [CR-308] DB credentials egress verbatim through error detail
File: backend/src/api/errors.py:104-123 (_envelope), :45 (_CREDENTIAL_URI). Severity: medium (WARN).
A credential URI in a context value is dropped by _CREDENTIAL_URI ({"db":"postgresql://admin:S3cr3tPass@..."} -> context {}), but the identical URI in detail egresses verbatim — detail passes only through the inert scrub_text, never the guard. Proven: _envelope(400,"BadRequest","connect failed to postgresql://admin:S3cr3tPass@dbhost:5432",{...}) returned detail with creds intact. Asymmetric protection in a changed file. Latent at HEAD (no AppError is raised; handle_unexpected returns a static string) -> WARN.
Fix: run detail through the same credential-URI guard and length cap in _envelope.

### [F-1] PII redaction is inert
File: backend/src/config/logging.py:74-142; backend/src/api/errors.py:66-101. Severity: medium (WARN).
register_sensitive/redact_values have zero production call sites, so scrub_text/RedactionFilter never redact. With an empty scope, sanitise_context egressed a 12-digit Aadhaar int (234512345612), a PAN in a context key (pan-ABCDE1234F), and a PAN in a value — all verbatim. Dead subsystem giving false coverage. Latent (no business PII flows in the change set; those arrive group B/E) -> WARN; rises to BLOCK once business code handles PAN/Aadhaar and relies on this without calling register_sensitive.
Fix: wire register_sensitive(...) at the PII-introducing operations; normalise-then-match in the sanitiser.

## INFO Findings

### [CR-302] _escape_label passes raw CR/TAB/NUL/BEL/ESC/DEL
File: backend/src/api/platform/routes.py:78-83. Severity: low (INFO). Confirmed UNREACHABLE at HEAD: no attacker string reaches a label (method -> constant, route -> template/<unmatched>). Live CRLF-path attack produced no raw CR in the body. Defense-in-depth gap only. Fix: escape all control characters.

### [SEC-OBS] observe_duration unbounded on method dimension if called directly
File: backend/src/api/middleware.py:107-128. Severity: low (INFO). record_request bounds method first; called directly with raw methods, observe_duration produced 22,003 series / 12.3 MB. Not reachable over HTTP. Fix: bound inside observe_duration so the invariant is not caller-dependent.

### [AUTHZ] /health and /metrics unauthenticated
File: backend/src/api/platform/routes.py:63-129. Severity: low (INFO). Documented, ratified deferral (E15-S4 Scope Out; auth arrives E1-S1 group B). Anonymous disclosure at HEAD: /health -> version 0.1.0, DB liveness, status; /metrics -> route templates (API surface), per-route/status counts, latency histogram (traffic volume/timing). Low sensitivity given the minimal surface today.

### [REQID] X-Request-ID reflected and logged verbatim
File: backend/src/api/middleware.py:171-176, 203-204. Severity: low (INFO). PAN-format id echoed verbatim and logged unredacted (redaction inert); it is the callers own data. Oversized bounded — 100 KB id -> 400 at the server header limit (round-2 5 MB accepted no longer reproduces). Fix: validate id charset/length.

### [PRE-EXISTING] Unchanged network-adjacent WARNs
Not touched by these commits, out of scope, noted for continuity: public /docs and /openapi.json, missing security headers (CSP/X-Frame-Options/X-Content-Type-Options), host-header-reflected open redirect. No regression introduced.

## Classes NOT covered — UNSCANNED, not clean
- Secrets scan (gitleaks): unprovisioned — UNSCANNED.
- SAST (semgrep): unprovisioned — UNSCANNED.
- Python dependency CVEs (pip-audit): unprovisioned — UNSCANNED. (npm audit: 1 critical + 1 high, all devDependency-only, absent from prod images.)
The clean security-scan.json is not evidence for these tiers.

## Verdict rationale
Every round-2/3 BLOCK is closed by execution; the two new commits add only bounded, constant-domain labels and a linear formatter. The three WARNs are latent or architectural (root causes in untouched harness code or deferred to group B), and the diff strictly improved matters. No finding survives adversarial refutation as a reachable, unmitigated attacker path at HEAD. Security axis: PASS.
