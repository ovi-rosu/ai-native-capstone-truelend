# Security Review — ai-native-capstone-truelend — story group A — 2026-09-14

**Instance:** 1 of 3 (independent). **Tree reviewed:** HEAD `f4abd41`.
**Range:** `git diff 14e9487..HEAD -- backend frontend` (24 files, all additions).
**Scope:** the changed files, the review context pack, and their immediate
data-flow neighbours. Judged fresh at HEAD; no prior-round verdict was read.

All findings below were reached by reading the code and then **testing it against a
live server**, not by pattern matching. Where a candidate finding was refuted by a
real mitigation, it is recorded as refuted rather than dropped silently.

## Summary

- BLOCK findings: **2**
- WARN findings: **9**
- INFO findings: **9**
- Overall verdict: **BLOCK**

### Honest framing of the two BLOCKs

Neither BLOCK is reachable over HTTP at HEAD, because no production code calls
`redact_values()` yet (verified: the only call sites are in
`backend/tests/unit/test_log_redaction.py`). Both are defects **inside
`backend/src/config/logging.py`**, on the path that the repo's own control test
`test_modules_handling_applicant_pii_enter_a_redaction_scope` *obliges* the next
story (`POST /applications`, E4-S1) to take. A reviewer who scopes the gate strictly
to "exploitable through a live route today" would read both as WARN, and that reading
is defensible — this report does not hide that.

They are nonetheless recorded as BLOCK, for one reason: E15-S1 exists specifically so
this substrate is correct *before* anything depends on it (the story's own rationale:
"D12 places this first in M1 because NFR-03 and NFR-06 are retrofit-hostile"). Both
defects are unfixable by the future caller — SEC-002 leaks PII even when the caller
uses the API exactly as the project's enforced control test mandates — and both fixes
are local to this diff. Merging them turns a 20-line fix into the retrofit the story
was written to prevent.

---

## BLOCK Findings

### [SEC-001] Catastrophic regex backtracking (ReDoS) in the PII redaction pattern
**File:** `backend/src/config/logging.py` line 58 (`_redaction_pattern`), consumed at
line 67 (`_scrub`)
**Severity:** high → BLOCK · **Category:** dos / redos

**Description.** `_redaction_pattern` builds a matcher by joining the escaped
characters of the sensitive value with the separator class `[\s\-]*`
(`_SEPARATORS`, line 46). When the value itself contains characters that the
separator class also matches (space, tab, hyphen), every literal in the pattern
becomes ambiguous with its neighbouring quantifier, and matching degenerates to
exponential backtracking.

Measured against the real production `_scrub`, imported from
`src.config.logging` (single-threaded CPU, no I/O):

| sensitive value | text scanned | time |
|---|---|---|
| `"-"*12 + "Z"` (13 chars) | 20 hyphens | 8 ms |
| `"-"*12 + "Z"` (13 chars) | 30 hyphens | 3,125 ms |
| `"-"*12 + "Z"` (13 chars) | **40 hyphens** | **199,326 ms** |
| `"-"*18 + "Z"` (19 chars) | 30 hyphens | 11,404 ms |
| `" "*18 + "Z"` (19 chars) | 30 spaces | 10,304 ms |

A 13-character value and a 40-character log line cost **over three minutes** of one
worker's CPU. `_scrub` runs this loop for every registered value against every log
line emitted in the scope, so the cost multiplies.

The value is attacker-supplied **by the module's own documented contract** (lines
9-13): "Business code (a future story's origination endpoint) marks the values that
must never reach a log sink ... it redacts whatever values the caller marks as
sensitive, which is the only sound approach given those are per-applicant,
per-request data." An applicant submitting a PAN/Aadhaar/salary-document field of
`"------------Z"` therefore chooses the regex. `_MIN_REDACTABLE_LENGTH = 6` does not
help (13 > 6); there is no length cap, no character-class restriction and no timeout.

**Adversarial check.** The only refutation found is that `redact_values` has no
production caller at HEAD. That is sprint sequencing, not a mitigation. The exploit
path I could not refute: attacker-submitted applicant field → `redact_values(field)`
(mandated by the repo's own control test) → any log line in that scope → `_scrub` →
exponential match → worker pinned for minutes against a `p95_ms: 500` SLO, with no
authentication and no rate limiting (D-O ships none).

**Fix.** Normalise instead of tolerating separators inside the pattern: strip
`[\s\-]` from both the sensitive value and a normalised copy of the text, match on
the normalised form, and map the match back — or, minimally, build the separator
class only *between* characters that are not themselves separator characters, cap the
registered value length, and reject values that are predominantly separator
characters. Add a regression test asserting `_scrub` over `"-"*12 + "Z"` against 40
hyphens completes in under a millisecond.

---

### [SEC-002] PII in an exception message bypasses redaction and is logged at ERROR
**File:** `backend/src/config/logging.py` lines 34-42 (`redact_values` scope),
100-118 (`JSONLogFormatter`, the new `payload["exception"]`), 141
(`_JSON_ROUTED_LOGGERS`)
**Severity:** high → BLOCK · **Category:** sensitive-data-exposure

**Description.** `redact_values` is a lexical context manager whose `finally` resets
the sensitive-value set. An exception raised inside the scope unwinds that scope
first, then propagates past `ServerErrorMiddleware`, which re-raises it; uvicorn then
formats the traceback and logs it on `uvicorn.error`. By then
`_sensitive_values` is empty, so the `RedactionFilter` installed on that logger
no-ops, and the raw exception message is written into the JSON `exception` field at
ERROR level.

Demonstrated end-to-end against a live uvicorn process with the unmodified
application (probe handler standing in for E4-S1, doing exactly what the project's
control test requires — entering the redaction scope before touching PII):

```
handler:  with redact_values(PAN, AADHAAR):
              raise RuntimeError(f"could not score applicant pan={PAN} aadhaar={AADHAAR}")

log line: {"level":"ERROR","logger":"uvicorn.error","request_id":"",
           "exception":"... RuntimeError: could not score applicant
                        pan=ABCDE1234F aadhaar=234123412346"}
```

The PAN and Aadhaar appear verbatim. For comparison, the same values logged
*inside* the scope were correctly redacted to `[REDACTED]` in the same run, so the
mechanism works — it simply does not cover the error path, which is the single most
likely place an identifier ends up in a log.

This diff created the sink: commit `f4abd41` deliberately routed `uvicorn.error`
through the root JSON handler (line 141) and added `payload["exception"]` to the
formatter (lines 111-117). Before those two changes the traceback was dropped.

Violates the project threat model rule "NEVER log secrets, tokens, passwords, or
full PII (email, SSN, card numbers) at INFO level or above"
(`.claude/claude-security-guidance.md`), the story's E15-S1-AC1 ("the captured buffer
contains 0 occurrences of each of those three values") and its scope_out ("must not
write applicant PAN, Aadhaar or salary-document content to any log sink").

**Adversarial check.** Refutations attempted and rejected: (a) the
`RedactionFilter` *is* attached to `uvicorn.error`, but has nothing registered to
scrub by then; (b) the caller cannot hold the scope open across the uvicorn boundary,
because uvicorn logs after the ASGI callable has already raised; (c) the caller
cannot guarantee no exception message ever embeds PII — a DB driver, pydantic, or any
library raise site is outside the caller's control. Same latency caveat as SEC-001
(no PII endpoint exists yet), but unlike a normal "future misuse" risk, the leak
occurs when the caller does everything right.

**Fix.** Make the sensitive-value set request-scoped rather than handler-lexical:
bind it in `CorrelationIdMiddleware` (which sits outside `ServerErrorMiddleware`) and
have handlers register into that request-scoped store, so it outlives handler
unwinding; and/or catch the exception in the middleware, log it scrubbed while the
scope is live, then re-raise. Add a test that drives a raising handler through the
real ASGI stack and asserts the PAN is absent from the traceback line.

---

## WARN Findings

### [SEC-003] `AppError.context` and `detail` are echoed to the client unfiltered
**File:** `backend/src/api/errors.py` lines 25-31; `backend/src/types/errors.py` lines 23-37
**Severity:** medium → WARN · **Category:** information-disclosure

The handler serialises `exc.context` (typed `Mapping[str, object]`, i.e. anything)
and `exc.message` straight into the response body. Demonstrated against the live app
— a 422 returned, in full:

```
{"error":"AppError","detail":"rejected applicant pan=ABCDE1234F",
 "context":{"pan":"ABCDE1234F","aadhaar":"234123412346",
            "db_url":"<a Postgres DSN carrying user, password, host, port, db>",
            "sql":"SELECT * FROM applications WHERE pan = 'ABCDE1234F'",
            "config_path":"/app/backend/src/config/settings.py"}}
```

PII, a DSN with credentials, a SQL string and a filesystem path all egressed. Note
the probe held an **active `redact_values` scope** and it made no difference:
redaction covers log records only, never response bodies, so this new outbound
channel sits entirely outside the story's PII control. Separately,
`AppError.__init__` defaults `status_code=500`, so a bare
`AppError("internal detail")` echoes an internal message on a 5xx.

Nothing in the diff raises `AppError` with a populated context yet, and the envelope
itself matches the frozen contract (`specs/design/api-contracts.md:27`, whose own
example legitimately returns the caller's `submitted_value`) — hence WARN, not BLOCK.
The gap is that no discipline constrains what may ride out.

**Fix.** Give each subclass a declared, typed, disclosure-safe context model (or an
explicit `public_context` allowlist); never place applicant PII, DSNs, SQL or paths
in it; for 5xx suppress `detail`/`context` and return a generic message plus the
correlation id. Add a test asserting a 5xx body carries no `detail`.

### [SEC-004] `X-Request-ID` is accepted unvalidated and unbounded
**File:** `backend/src/api/middleware.py` lines 50-51, 58, 61
**Severity:** medium → WARN · **Category:** dos / input-validation

`inbound = Headers(scope=scope).get("x-request-id")` is used verbatim with no length
cap and no character-class restriction. Verified live: a **64 KB** `X-Request-ID` was
accepted, echoed in full in the response header (65,692-byte response) and written in
full into the `request_id` field of the access log line. Unauthenticated and
unthrottled — `/health` needs no credentials and D-O ships no rate limiting — so this
is a cheap log-volume and response-size amplifier.

**Fix.** Cap the accepted value (e.g. 128 characters) and restrict it to
`[A-Za-z0-9_.:-]`; on violation generate a fresh id rather than echoing the
caller's.

### [SEC-005] The correlation id is fully caller-controlled, so it can be forged or collided
**File:** `backend/src/api/middleware.py` lines 50-51
**Severity:** medium → WARN · **Category:** audit-integrity

Any caller can set `X-Request-ID` to any value, including one identical to another
request's id, and every log line for that request then carries it. An attacker can
therefore stamp their own traffic with a chosen or copied correlation id, merge their
requests into someone else's trace, or fragment their own — degrading incident
forensics and repudiation for a lending platform. Honouring the inbound header is
mandated by the frozen contract (`api-contracts.md:19-20`, E15-S1-AC3), so the header
cannot simply be ignored. Generated ids themselves are sound (`uuid4().hex`, CSPRNG —
not guessable).

**Fix.** Always emit a server-generated `request_id` on every log line and record the
caller's value separately as `client_request_id`, echoing the caller's value in the
response header to satisfy the contract. Validate per SEC-004.

### [SEC-006] The 500 path loses the correlation id on the traceback line
**File:** `backend/src/api/middleware.py` lines 56-67; `backend/src/config/logging.py` line 141
**Severity:** medium → WARN · **Category:** audit-integrity

`f4abd41` is credited with making the correlation id survive the 500 path. It does
for the response header and the access line — but not for the traceback. Measured in
one live failing request:

```
{"logger":"truelend.access","message":"GET /probe/raise-inside-scope -> 500",
 "request_id":"probe-raise-inside-scope"}
{"logger":"uvicorn.error","message":"Exception in ASGI application\n",
 "request_id":""}            <-- the line an operator actually needs
```

uvicorn logs the traceback after the ASGI callable raised, by which point the
middleware's `finally` has already reset `request_id_var`. E15-S1-AC3 ("100% of the
lines ... each carries request_id equal to req-abc") is therefore **not** met on the
error path. The repo's own test asserts only the access line, so it passes with the
hole open. Primarily a correctness/observability defect — flagged here because it is
the forensic half of SEC-002 and contradicts the pack's claimed CR-003 fix.

**Fix.** Log the exception from inside `CorrelationIdMiddleware` while the contextvar
is still set, then re-raise; or attach a filter to `uvicorn.error` that reads a
request-scoped store rather than the contextvar.

### [SEC-007] Money wire format is unvalidated, silently coerced, and parsed differently on each side
**File:** `backend/src/api/serializers.py` lines 20-26; `backend/src/types/money.py`
lines 59-69; `frontend/src/types/money.ts` lines 24-35
**Severity:** medium → WARN · **Category:** financial-integrity

D-G specifies "a quoted 2dp string", but `_validate_money` accepts anything
`Decimal()` can parse and then silently rounds. Measured on the real types:

| wire value | backend `Money` | frontend `Money.fromWire` |
|---|---|---|
| `"1.005"` | `1.01` (silently rounded up) | `1.01` |
| `"0.001"` | `0.00` (silently zeroed) | `0.00` |
| `"-0.001"` | **`-0.00`** (negative zero on the wire) | `0.00` |
| `"1E5"` | `100000.00` | `100000.00` |
| `"1_000.00"` | `1000.00` | `1000.00` |
| `"  1.00  "` | `1.00` | **throws** |
| `"0x10"` | **rejected** | **`16.00`** |
| `".5"` / `"5."` | `0.50` / `5.00` | `0.50` / — |

Three distinct problems. (1) A hostile input produces a monetary value different
from the one submitted, with no error: `"0.001"` → `0.00`, `"0.005"` → `0.01`.
(2) Exponent, underscore and hex notations are accepted, so any upstream length or
format check that assumes plain decimal notation is bypassable — `"1E5"` is three
characters and means one hundred thousand. (3) The two ends of the wire **disagree**:
`"0x10"` is 16.00 in the browser and a rejection on the server; `"  1.00  "` is
1.00 on the server and a render-time throw in the browser. The frontend module's own
docstring promises "the same amount rounds identically on both sides of the wire".
`-0.00` also reaches the wire as `"-0.00"` while comparing equal to `0.00`.

Not exploitable today (no money-carrying endpoint exists), but this is the single
canonical money wire module for the whole platform.

**Fix.** Validate against a strict grammar such as `^-?(0|[1-9]\d{0,11})(\.\d{1,2})?$`
in `_validate_money` **before** calling `Decimal()`; reject rather than round
anything with more than 2 decimal places; normalise `-0.00` to `0.00`; apply the
identical grammar in `toQuantizedDecimal`; drive both with one shared fixture set.

### [SEC-008] `Money.multiply` lets `decimal.Overflow` escape after ~10 s of CPU
**File:** `backend/src/types/money.py` lines 71-76, 91-101
**Severity:** medium → WARN · **Category:** dos / error-handling

`_quantize` catches only `InvalidOperation`, and `multiply` wraps nothing around
`self._amount * scalar`. Python's default decimal context traps `Overflow`, which is
**not** an `InvalidOperation` subclass, so it escapes `Money`'s documented error
contract. Measured:

| call | result |
|---|---|
| `Money("1.00").multiply(10**30)` | `InvalidMoneyAmountError` (correct) |
| `Money("1.00").multiply(10**1000)` | `InvalidMoneyAmountError` (correct) |
| `Money("1.00").multiply(10**1000000)` | **`decimal.Overflow` after 9,690 ms** |

So an oversized scalar both burns ten seconds of CPU and surfaces as an unhandled
500 rather than a typed validation error. `multiply`'s scalar is an interest rate or
term, which on a platform whose premise is business-configurable loan products
without code changes is operator-supplied input.

**Fix.** Bound the scalar's magnitude/digit count before multiplying, and catch
`decimal.DecimalException` (not just `InvalidOperation`) in `_quantize` and
`multiply`, re-raising `InvalidMoneyAmountError`.

### [SEC-009] Frontend money rendering hangs on a pathological exponent
**File:** `frontend/src/types/money.ts` lines 24-35, 74-80;
`frontend/src/ui/components/MoneyText.tsx` lines 13-16
**Severity:** medium → WARN · **Category:** dos

`toQuantizedDecimal` applies no magnitude bound, and `MoneyText` accepts an arbitrary
`string`. Measured in node with the project's `decimal.js@10.6.0`:

| wire value | `toWire()` output | time |
|---|---|---|
| `"1e+1000000"` | 1,000,004 chars | 41 ms |
| `"1e+100000000"` | **100,000,004 chars (~100 MB)** | 4,825 ms |
| `"1e+200000"` via `format()` | 266,667 chars | **16,482 ms** |

An 11-byte field value allocates hundreds of megabytes and hangs the tab for
seconds — roughly 20,000x amplification, worst in `format()`, whose thousands-
separator regex is super-linear. The backend serializer would not currently emit such
a value (it always renders 2dp via `str(value.amount)`), so this needs a compromised
or spoofed API response — hence WARN.

**Fix.** Apply the SEC-007 grammar in `toQuantizedDecimal`, which bounds magnitude,
and cap integer-digit count before `toFixed`/`format`.

### [SEC-010] Known advisories in the newly added `frontend/package.json`
**File:** `frontend/package.json` (dependency manifest, added by this diff)
**Severity:** medium → WARN · **Category:** dependency

`npm audit` at HEAD reports 5 advisories — **1 critical, 1 high, 3 moderate**:

| package | installed | severity | advisory |
|---|---|---|---|
| `vitest` | 2.1.9 | critical | GHSA-5xrq-8626-4rwp — Vitest UI server arbitrary file read/exec (`<3.2.6`) |
| `vite` | 5.4.21 | high | GHSA-fx2h-pf6j-xcff — `server.fs.deny` bypass on Windows alternate paths |
| `vite` | 5.4.21 | moderate | GHSA-4w7w-66w2-5vf9 path traversal; GHSA-v6wh-96g9-6wx3 NTLMv2 disclosure |
| `esbuild` | 0.21.5 | moderate | GHSA-67mh-4wv8-2f99 — any site can query the dev server |
| `@vitest/mocker` | 2.1.9 | moderate | GHSA-82fw-gwwq-j7x9 path traversal |

Deliberately recorded as WARN rather than BLOCK despite the raw critical/high
labels, because: all five are **devDependencies**, no production artifact ships
them, group A deploys no frontend, and the *critical* requires the Vitest **UI**
server — `@vitest/ui` is not a dependency of this manifest, so that code path cannot
even be started here. The `vite` high **is** genuinely reachable in this project's
documented workflow (`npm run dev` on Windows, which is the host platform): a
malicious page visited while the dev server runs can read files outside the project
root. The exposure is the developer's workstation, not the service. A mechanical
CVE gate elsewhere in the pipeline will report critical/high — that difference is
this judgement, stated openly.

Backend `pip-audit`: **clean**, no known vulnerabilities.

**Fix.** Bump `vite` and `vitest` to patched lines (`npm audit fix --force` proposes
vite 8 / vitest 5 as breaking majors); re-audit before group B ships a deployable
frontend.

### [SEC-011] No lockfile is under version control
**File:** `frontend/package.json`, `backend/pyproject.toml` (manifests added by this
diff); `.gitignore` lines 48-49 (pre-existing, outside the diff)
**Severity:** medium → WARN · **Category:** supply-chain

`git ls-files` shows **no** lockfile of any kind. Both lockfiles exist locally but
are ignored:

```
.gitignore:48:*.lock              -> backend/uv.lock
.gitignore:49:package-lock.json   -> frontend/package-lock.json
```

This diff introduces the project's first dependency manifests, every entry a `^` or
`>=` range. Without a committed lockfile, each clone and CI run re-resolves
transitive dependencies, so a compromised release inside a permitted semver range is
installed silently, the set audited in SEC-010 is not reproducible, and no build
attestation is possible. For a lending platform that is a real integrity gap. The
`.gitignore` rules are pre-existing base state, so the fix touches a file this diff
does not own — reporting the conflict rather than proposing the edit.

**Fix.** Commit `frontend/package-lock.json` and `backend/uv.lock`, remove those two
`.gitignore` lines, and use `npm ci` / `uv sync --frozen` in CI.

---

## INFO Findings

### [SEC-012] `extra=` fields are silently discarded by the formatter
`backend/src/config/logging.py` lines 103-118 — `JSONLogFormatter` emits six fixed
keys and never reads `record.__dict__`. Verified: `log.info("extra-test",
extra={"pan": ..., "aadhaar": ...})` produced a line containing neither key. Safe
today (nothing leaks), but `extra` is *dropped*, not *redacted* — `RedactionFilter`
only scrubs `getMessage()` and `exc_text`. Any future change that starts emitting
extras would emit them unscrubbed. Redact at the formatter, or explicitly document
that `extra` is unsupported.

### [SEC-013] Sensitive values shorter than 6 characters are never redacted
`backend/src/config/logging.py` lines 45, 63-66 — `_MIN_REDACTABLE_LENGTH = 6`
silently skips shorter values. The rationale (a 3-character value with separators
tolerated between every character matches far too much) is sound, but an OTP, PIN,
CVV or short account suffix registered through `redact_values` would pass through
unredacted with no warning. Log or raise on a skipped registration so the caller
knows.

### [SEC-014] Applicant identifiers persist in a process-global cache beyond request scope
`backend/src/config/logging.py` lines 49-58 — `_redaction_pattern` is
`@lru_cache(maxsize=256)` keyed on the sensitive value, so up to 256 PAN/Aadhaar
values (and their compiled patterns' `.pattern` attributes) stay resident in process
memory long after the request, visible in any heap or core dump. Prefer a
request-scoped cache, or `cache_clear()` when the scope exits.

### [SEC-015] URL path segments are logged verbatim, outside any redaction scope
`backend/src/api/middleware.py` line 61 — verified: `GET /health/ABCDE1234F -> 404`
was logged with the path intact. The access line is emitted on
`http.response.start`, i.e. after the handler's `redact_values` scope has closed, so
PII in a path can never be redacted. No current violation (the frozen contract uses
opaque ids), but applicant identifiers must never become path segments. Query strings
are safe: `scope["path"]` excludes them and `uvicorn.access` — which would have
logged them — is disabled (line 150). Verified: `?pan=...&aadhaar=...` appeared
nowhere in the log.

### [SEC-016] Redaction coverage is a one-shot enumeration at configure time
`backend/src/config/logging.py` lines 167-177 — `_install_redaction_filter_everywhere`
walks `loggerDict` once. A logger created later has no filter of its own and is
scrubbed only by the root `StreamHandler`'s filter (confirmed working: a logger
created after `configure_logging` was still redacted). Adding a second handler
(file/syslog) without a `RedactionFilter` would emit unscrubbed records from
late-created loggers. Putting redaction in the formatter, or on handlers only, would
be structurally safer than enumerating loggers.

### [SEC-017] CR/LF and ANSI injection are blocked only by controls outside this diff
`backend/src/api/middleware.py` lines 50-58, 61 — the application performs no
validation, but the attack is refuted in the shipped configuration at two layers.
Verified live: `httptools`/llhttp rejects CR, bare LF, NUL, ESC and obs-fold in a
header value at parse time (all four hostile variants returned
`400 Invalid HTTP request received.` without reaching the app), and uvicorn
re-validates outgoing header values against `[\x00-\x08\n-\x1f\x7f]`. Log injection is
independently blocked by `json.dumps`: `é"},{"request_id":"spoof\` came back as one
valid, fully escaped JSON line (`"Ã©\"},{\"request_id\":\"spoof\\"`), and
`ensure_ascii` escapes non-ASCII too. **No response splitting and no log injection is
possible as deployed.** Recorded only because the guarantee lives in the server, not
the code: a different ASGI server, an HTTP/2 path, or a proxy that normalises
obs-folds differently could re-open it. Fixing SEC-004 closes it structurally.

### [SEC-018] `GET /health` discloses nothing — verified clean
`backend/src/api/platform/routes.py` lines 10-13 — returns `{"status": "ok"}` and
nothing else: no version, no config, no dependency state, no secret, no I/O.
Unauthenticated access is appropriate for a liveness probe. No finding.

### [SEC-019] `Settings` holds no secrets and cannot enable debug mode — verified clean
`backend/src/config/settings.py` lines 18-24 — two non-sensitive fields
(`service_name`, `log_level`), `env_prefix="TRUELEND_"`, `extra="ignore"`, and no
`env_file`, so no stray env var can inject a field and nothing can turn on FastAPI
debug (`build_fastapi_app` never passes `debug`). Confirmed on the live 500 path: the
client received the plain-text `Internal Server Error` (21 bytes) with **no stack
trace, no exception type and no internal detail** — the `f4abd41` middleware
reordering leaks nothing. The reviewer's question "can any secret reach a log line or
the error context" resolves to no, because no secret exists yet; re-check when a DB
URL or JWT key is added. Minor: `log_level` is an unvalidated free string, so a bad
value raises at `root.setLevel` on startup (operator-controlled, availability only).

### [SEC-020] Framework errors bypass the frozen envelope, and error messages echo unbounded input
`backend/src/api/errors.py` registers a handler for `AppError` only. Verified: a 404
returns FastAPI's `{"detail":"Not Found"}`, not the contract's
`{error, detail, context}` shape (`api-contracts.md:27` says "one shape for every
non-2xx response"), and pydantic validation errors use `{"detail":[...]}`. No
information leakage in itself, but pydantic reflects the submitted value back in
`detail`, and `Money`'s messages embed `{amount!r}` — measured: `Money("9"*100000)`
raises with a **100,024-character** message. A 100 KB numeric field therefore yields
a ~100 KB error body and a ~100 KB log line, the same amplification family as
SEC-004. Contract conformance is the code reviewer's call; truncate values embedded
in error messages.

---

## Candidate findings tested and refuted

Recorded so a later reviewer does not re-litigate them:

| Candidate | Verdict | Evidence |
|---|---|---|
| CR/LF response splitting via `X-Request-ID` | **refuted** | parser returns 400 before the app; uvicorn re-validates outgoing values (SEC-017) |
| ANSI escape / control-char injection into the log stream | **refuted** | ESC and NUL rejected at parse; `json.dumps` escapes all `< 0x20` |
| JSON-breaking log injection (quote/brace/backslash) | **refuted** | one valid escaped JSON line produced (SEC-017) |
| Non-ASCII breaking the log line | **refuted** | `ensure_ascii` default escapes to `\uXXXX` |
| Stack trace leaked to the client on the 500 path | **refuted** | body is 21-byte plain `Internal Server Error`; debug unreachable (SEC-019) |
| PII missed in nested structures beyond a walk depth | **refuted** | there is no walk — `_scrub` runs over the fully formatted message, so a nested dict/list was redacted correctly |
| PII leaking via `extra=` | **refuted** as a leak | extras are dropped entirely (SEC-012) |
| Query-string PII reaching the access log | **refuted** | `scope["path"]` excludes the query string and `uvicorn.access` is disabled |
| Predictable generated correlation ids | **refuted** | `uuid4().hex`, CSPRNG-backed |
| Cross-request leakage of the correlation id or sensitive set | **refuted** | both are `ContextVar`s reset in `finally`; per-task context copies isolate them |
| Money accepting NaN / Infinity / float / bool | **refuted** (CR-001 verified) | all rejected as `InvalidMoneyAmountError` |
| Money DoS via a huge positive exponent | **refuted** | `quantize` raises `InvalidOperation` at the 28-digit context limit; `1E+999999999` rejected in under a millisecond |
| XSS in `MoneyText` | **refuted** | renders a text child only; no `dangerouslySetInnerHTML`/`innerHTML` anywhere in the diff; React escapes |
| Hardcoded secrets in the diff | **refuted** | scoped grep found only `token = ...contextvar.set(...)` false positives |
| SQL / command / template injection, unsafe deserialization, dynamic execution | **not present** | no DB, subprocess, template, pickle or eval code exists in the diff |

Out of scope per the context pack and not reviewed: authn/authz, persistence and
migrations, outbound network calls / SSRF, file upload/download, payment execution.

## Method notes

- Booted the unmodified app with `uv run uvicorn src.api.app:app` on an isolated port
  (8010; port 8000 was already held by another process) and captured stdout.
- Drove 14 raw-socket requests for the header/log-injection matrix, so malformed
  bytes reached the parser exactly as sent rather than being normalised by a client.
- Timed the redaction regex and the `Money` type by importing the real production
  functions (`src.config.logging._scrub`, `src.types.money.Money`).
- For SEC-002/SEC-003 a throwaway probe app imported the real `create_app`/
  `build_fastapi_app` and added handlers standing in for a future PII endpoint.
  **No production source was modified**; all scratch files were deleted.
