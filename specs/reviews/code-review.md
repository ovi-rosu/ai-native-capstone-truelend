# Code Review — group A (fresh context)

**Range:** `14e9487..d0b5c94` plus the uncommitted working tree
**Branch:** `feat/harness-scaffold-and-planning`
**Scope:** the 13 production source files and 5 test files named in `specs/reviews/review-context-pack.md`
**Verdict:** **BLOCK** — 4 BLOCK, 14 WARN, 9 INFO

Reviewed cold against `.claude/architecture.md`, the sealed stories `E9-S1` / `E11-S1` / `E15-S1`,
and `specs/design/architecture.md` decisions D-B / D-G / D-J. Builder transcript and progress
files not read.

---

## What is genuinely good

Worth stating, because the BLOCK list below is about four specific things and not about the
overall shape of the change:

- **Layering is clean.** Every import in the diff was checked by hand. `backend/src/types/*`
  imports stdlib only (`enum`, `decimal`, `typing`) — zero cross-layer imports, so the Types
  floor holds. `config/delinquency.py` imports `src.types.delinquency` (Config→Types, correct
  direction). `config/logging.py` imports `config/settings.py` (intra-layer, allowed). `api/*`
  imports only `src.config.*` and `src.types.*`. `frontend/src/ui/components/MoneyText.tsx`
  imports `../../types/money` (UI→Types). **No layering violation anywhere in the diff.**
- **Size and typing limits met.** Largest file 149 lines (test), largest production file 105
  (`types/money.py`) — all well under 300. Longest function 14 lines
  (`classify_by_days_past_due`, `CorrelationIdMiddleware.dispatch`) — all well under 30. Zero
  `any`, zero `# type: ignore` and zero `@ts-ignore` in `backend/src` and `frontend/src`; the two
  `# type: ignore[arg-type]` are in tests and legitimately exist to test rejection paths.
- **The delinquency ladder is correct at every edge.** I traced
  `classify_by_days_past_due` by hand at 0, 29, 30, 59, 60, 89, 90, 179, 180 and 400: all
  correct, inclusive-floor semantics, no off-by-one. Zero DPD → `CURRENT`. Negative DPD raises
  `ValueError` rather than silently bucketing. `classify()` clamps a future due date with
  `max(0, ...)` → `CURRENT`. The tests use an *independent* oracle (`_expected_bucket_for`,
  written from the AC's literal ranges rather than from the production tuple), which is the
  right way to test a lookup table.
- **`MoneyText.tsx` is clean** — no `Number()`, no `parseFloat`, no coercion; it delegates to
  `Money.fromWire` / `format()` and renders a string. D-J is honoured in the component.
- **Float and JSON-number money are genuinely rejected at the wire boundary.** I confirmed
  empirically that `MoneyField` rejects `12.34` (float), `1234` (int) and `True` with a
  `ValidationError` — only quoted strings and `Decimal` get through. `Money.__init__` rejects
  `float` and `bool` before anything else. Serialization emits a quoted string via
  `plain_serializer_function_ser_schema(..., return_schema=str_schema())`.
- **`errors.py` leaks nothing** — no traceback, no internal detail, just
  `{"error": exc.message}`. Starlette walks the MRO so future `AppError` subclasses are covered
  by the one registration, matching "mapped once at the API boundary".
- **`types/errors.py` and `settings.py` correctly refuse to speculate** — `AppError` with no
  subclasses, `Settings` with two fields, both with a docstring saying "when a story needs one".
  That is the right call and the opposite of the usual failure mode.
- **All reported evidence reproduces.** I re-ran everything: `pytest -q` → 42 passed;
  `mypy src/` → clean, 12 files; `ruff check .` → clean; `npm test` → 11 passed;
  `npm run typecheck` and `npm run lint` → clean. The pack's evidence table is accurate.

The BLOCK findings are all cases where a gate is **green but not load-bearing**. That is the
theme of this review: the code that exists is tidy, and four of the mechanisms meant to
*guarantee* the story's invariants do not actually constrain anything.

---

## BLOCK findings

### CR-001 — `Money` accepts NaN, and the wire serializer emits `{"amount":"NaN"}`
`backend/src/types/money.py:59` · `backend/src/api/serializers.py:31` · axis: spec · confidence: high

`Money._quantize` relies on `Decimal.quantize` raising `InvalidOperation` for anything it cannot
represent at 2dp. That works for infinities and signalling NaN, but a **quiet NaN propagates
through `quantize` without raising**. Confirmed by execution:

```
Money('NaN')          -> Money(NaN)     amount = Decimal('NaN')
Money('nan')          -> Money(NaN)
Money(Decimal('NaN')) -> Money(NaN)
Money('Infinity')     -> InvalidMoneyAmountError   (correct)
Money('sNaN')         -> InvalidMoneyAmountError   (correct)
```

Because `_validate_money` accepts any `str`, this is reachable straight through the D-G wire
boundary:

```
class M(BaseModel): amount: MoneyField
M(amount='NaN').model_dump_json()   ->   {"amount":"NaN"}
```

That violates D-G's "quoted **2dp string**" contract. It is also a cross-hop divergence: the
TypeScript side *does* guard (`money.ts:31` `if (!parsed.isFinite()) throw ...`), so Python
produces a payload the frontend rejects at render time rather than at the API boundary.
Secondary damage: `Money('NaN') == Money('NaN')` is `False` while `hash()` succeeds, so a NaN
`Money` placed in a `dict` or `set` can never be looked up again.

**Fix:** reject non-finite values before quantizing, mirroring the TS guard — in `__init__`
after the `Decimal` conversion, `if not decimal_amount.is_finite(): raise
InvalidMoneyAmountError(...)`. One line, plus a `Money('NaN')` rejection test.

### CR-002 — the E9-S1-AC2 / AC3 "static float-arithmetic check" does not detect float arithmetic
`backend/tests/architecture/test_no_float_money.py:29` · `frontend/tests/unit/money.test.ts:76` · axis: spec · confidence: high

Both ACs require a check that "reports **0 float arithmetic operations**". Neither check looks at
arithmetic. `_count_float_usages` counts only `float(...)` `Name` calls and float `Constant`
nodes. I ran the project's own function against realistic leaks:

```
MISSED  true division int/int      ->  def f(): return 3 / 2
MISSED  division chain             ->  return a / 100 * (7/3)
MISSED  round on division          ->  return round(x / 12, 2)
MISSED  pow with negative exponent ->  return (1 + r) ** -12
MISSED  math.fsum
MISSED  numpy float64
MISSED  aliased float constructor  ->  from builtins import float as F
caught  CONTROL: x = 1.5
```

7 of 7 realistic leaks missed. The first one matters most: `/` on two ints is *the* way float
silently enters Python money code, and it is invisible to this check. The frontend regex list is
weaker still:

```
MISSED  Decimal.toNumber()            <- decimal.js's one float escape hatch
MISSED  unary plus coercion  (+x)
MISSED  Math.round(x * 100) / 100
MISSED  .valueOf() * 2
MISSED  float literal arithmetic      <- `const r = 0.1 + 0.2` passes
caught  parseFloat / Number.parseFloat
```

So `this.amount.toNumber() * 1.05` inside `money.ts` would pass the D-J check cleanly. Both
checks also hardcode their target paths (two literal backend files), so "the backend money code
paths" will not grow as the schedule and repayment stories add money code — the check will
silently stop covering what it claims to cover.

**Fix:** backend — walk `ast.BinOp` for `Div`/`Pow`, flag any float `Constant`, flag calls to
`float`/`round`/`math.*`, and glob the money paths instead of listing two. Frontend — move
enforcement into eslint (`no-restricted-properties` on `toNumber`/`valueOf`, `no-restricted-syntax`
on `UnaryExpression[operator="+"]` and float literals) scoped to `src/types/money.ts`; a lint rule
is the right tool here and a regex over source text is not.

### CR-003 — unhandled exceptions lose the correlation id from both the response and the logs
`backend/src/api/middleware.py:34` · axis: spec · confidence: high

`response.headers[_REQUEST_ID_HEADER] = request_id` (line 36) and `_access_logger.info(...)`
(line 37) both sit *after* `await call_next(request)` inside the same `try`. When a handler raises
an unhandled exception, `call_next` propagates and neither statement runs. Only
`request_id_var.reset(token)` is in the `finally`. Confirmed by execution against the real app:

```
GET /_boom  with  X-Request-ID: req-trace-me
  -> status 500
  -> echoed X-Request-ID: None
  -> truelend.access log lines emitted for this request: 0
```

E15-S1-AC4 requires the response to echo the id. The story's business value is "so that I can
diagnose the origination flow" — and the 500 path, the one case where an operator actually needs
the correlation id, is the single path that emits neither a correlated log line nor the header.
`AppError` is unaffected (FastAPI's exception middleware runs inside `call_next`, so the mapped
response does get the header), so this is scoped to genuinely-unhandled errors — which is exactly
the diagnosis-critical case.

**Fix:** emit the access line in a `finally` (or an `except BaseException:` branch that logs with
status 500 and re-raises), and stamp the header on the error response too — either by catching and
building the 500 response inside the middleware, or by moving the header write into a
`ServerErrorMiddleware`-level hook. Add a test that asserts a 500 carries `X-Request-ID`.

### CR-004 — "all log output is structured JSON" is false in the real runtime, and the tests cannot see it
`backend/src/config/logging.py:71` · axis: spec · confidence: high

`configure_logging` clears and replaces the handlers of the **root** logger only (lines 77-79).
Uvicorn configures `uvicorn`, `uvicorn.error` and `uvicorn.access` from its own `LOGGING_CONFIG`
with their own handlers and `propagate = False`, so those loggers never reach `JSONLogFormatter`
and keep their plain-text format. The project's own server log proves it —
`.claude/state/uvicorn.log` interleaves:

```
INFO:     127.0.0.1:50224 - "GET /health HTTP/1.1" 200 OK
{"timestamp": "...", "level": "INFO", "logger": "truelend.access", "message": "GET /health -> 200", "request_id": "req-abc"}
```

plus plain-text `INFO:     Application startup complete.` and an `ERROR:    [Errno 10048] ...`
bind-failure line. Roughly half the lines at the actual process log sink are not JSON and carry no
`request_id`. E15-S1-AC3 and sprint-contract QA-VM-003/VM-003 require "**100%** of the lines parse
as JSON and each carries `request_id`". Measured at the real sink, that criterion is not met.

The test suite cannot detect this: `TestClient` never starts uvicorn's loggers, and
`conftest.log_capture` attaches to the root logger only — and additionally silences the one
non-conforming logger it *would* have seen (`conftest.py:51-53`, `httpx_logger.setLevel(WARNING)`).
That silencing is defensible on its own terms (it is client-side instrumentation, and the docstring
says so), but the net effect is that no non-JSON line can reach the AC3/AC4 assertions, in test or
in production.

**Fix:** in `configure_logging`, take ownership of uvicorn's loggers — for each of
`("uvicorn", "uvicorn.error", "uvicorn.access")` clear `.handlers` and set `propagate = True` so
they render through the root JSON handler. Then add a test that reads a live-server log capture and
asserts every non-blank line is `json.loads`-able, so the AC is measured where it is claimed.

---

## WARN findings

### CR-005 — PII redaction is opt-in value-marking with zero production call sites
`backend/src/config/logging.py:32` · axis: spec · confidence: high

`RedactionFilter` replaces only exact strings a caller registered via `redact_values(...)`. Grep
confirms `redact_values` has **zero** call sites in `backend/src` or `frontend/src` — only its own
definition and its mention in the module docstring. There is no key-based redaction (nothing keyed
on `pan` / `aadhaar` / `salary_doc`) and no format-based redaction, so any future handler that logs
a PAN without wrapping itself in `redact_values` leaks it verbatim. E15-S1's stated business value
is "Removes the retrofit pass that would otherwise have to revisit every handler written before
observability existed" — this design *requires* precisely that per-handler retrofit, inverting the
story's purpose. The docstring at lines 9-13 asserts "This module does not know PAN/Aadhaar formats
in advance ... which is the only sound approach"; that premise is incorrect — PAN is
`[A-Z]{5}[0-9]{4}[A-Z]` and Aadhaar is 12 digits, both fixed, both named in the story. WARN and not
BLOCK only because no business endpoint exists yet, so nothing leaks today. This should be treated
as must-fix before the first origination endpoint lands.

**Fix:** add defence in depth inside `RedactionFilter` — a key allow-list applied to `record.__dict__`
extras plus PAN/Aadhaar regex substitution over the rendered message — and keep `redact_values` as
the explicit channel for salary-document blobs, which genuinely cannot be pattern-matched.

### CR-006 — exception payloads and `extra` fields are silently dropped from every log line
`backend/src/config/logging.py:60` · axis: standards · confidence: high

`JSONLogFormatter.format` builds a fixed five-key payload and never reads `record.exc_info`,
`record.stack_info`, or any `extra=` field. `logger.exception("failed")` emits
`{"message": "failed"}` with the traceback discarded — silently, on the error path where the caller
most needs it. Combined with CR-003 (no log line at all for an unhandled 500), an unhandled error is
completely invisible in the log stream this story exists to install.

**Fix:** add an `"exception"` key rendered from `self.formatException(record.exc_info)` when present,
and copy whitelisted `extra` keys — and route both through redaction (see CR-007) in the same change,
not after it.

### CR-007 — redaction coverage is formatter-dependent, so CR-006's fix would open a leak
`backend/src/config/logging.py:45` · axis: standards · confidence: medium

`RedactionFilter.filter` rewrites `record.msg` from `record.getMessage()` and clears `record.args`.
It does not touch `record.exc_info`, `record.stack_info` or `extra` attributes. Nothing leaks today
only because `JSONLogFormatter` happens to emit nothing but the message. That makes redaction
correctness a property of the *formatter*, not of the filter — so the moment anyone adds exc_info or
extras (CR-006), or attaches a second handler with a different formatter (`conftest.py:47` already
does, and a file handler is the obvious next step), unredacted values reach that sink. The ordering
hazard is the finding.

**Fix:** scrub in the filter, not the formatter — rewrite `record.exc_text` / stringified
`exc_info` and iterate the whitelisted `extra` keys inside `RedactionFilter.filter`, so any
formatter downstream is safe by construction.

### CR-008 — the sealed generation contract for all three stories was authored inside the range under review
`specs/stories/E9-S1.md` · `E11-S1.md` · `E15-S1.md` · axis: spec · confidence: high

In `14e9487..d0b5c94` each of the three story files had `### Operations` change from `- pending` to
a concrete numbered operation list, with matching `Entities` additions, and
`specs/bundles/E{9,11,15}-S1.json` changed alongside. The pack independently reports
`plan-seal.js check` exit 1 naming exactly these artifacts. Reviewing an implementation against a
contract written in the same commit range cannot detect a spec divergence — the oracle is not
independent. Concretely it did not work: the contract text as written still contradicts the shipped
code (CR-009) and the project's own architecture rules (CR-010). Governance finding, no code defect.

**Fix:** no source change. Either revert the story-file edits and carry the operation lists in the
bundles only, or re-seal deliberately with a ratified amendment that records the operation text as
*post-hoc*, and regenerate Operations from the ACs via `/spec` before group B so the next group has
a real oracle.

### CR-009 — `classify`'s shipped signature diverges from the contract; named downstream consumers would break
`backend/src/config/delinquency.py:31,47` · axis: spec · confidence: high

E11-S1 Operation 2 specifies `classify(days_past_due: int) -> DelinquencyBucket` in
`backend/src/types/delinquency.py`. What shipped is `classify(oldest_unpaid_due_date: date,
as_of_date: date)` plus `classify_by_days_past_due(days_past_due: int)`, both in
`backend/src/config/delinquency.py`. The name `classify` is reused with an *incompatible* signature,
so a consumer generated against the contract — `component-map.md:209-210` names E11-S2 and E12-S1 as
consuming "classifier from E11-S1" — calling `classify(35)` gets a `TypeError`. Not a live break,
since neither consumer exists yet. The two-function split itself is good design: the int-based
classifier is independently testable and the date-based one is a thin adapter.

**Fix:** rename to remove the collision — `classify_by_days_past_due` and `classify_as_of` — and
correct the bundle/contract text to the shipped names and location, so E11-S2 and E12-S1 are
generated against the real surface.

### CR-011 — no length cap or charset constraint on the reflected `X-Request-ID`
`backend/src/api/middleware.py:32` · axis: spec · confidence: medium

`request.headers.get(_REQUEST_ID_HEADER) or uuid4().hex` accepts the caller's value unvalidated.
Confirmed: a 4000-character `X-Request-ID` is echoed verbatim on the response *and* embedded in
every JSON log line for that request (`len echoed: 4000`). A whitespace-only `"  "` header is
accepted as the correlation id, because the `or` fallback triggers only on empty/absent — E15-S1-AC4
requires a "non-empty" id and `"  "` satisfies that only in the most literal reading.

On the robustness/correctness angle I was asked to judge: log injection and header injection are
already largely mitigated and not the issue here. `json.dumps` escapes CR/LF and quotes, so the log
line stays one parseable JSON object; the ASGI server rejects CR/LF in raw header values at parse
time; and Starlette decodes inbound headers as latin-1 so the echo round-trips without a
`UnicodeEncodeError`. What remains is unbounded log-volume amplification and a useless-but-accepted
id.

**Fix:** validate before binding — take the header, `strip()` it, accept it only if it matches
`[A-Za-z0-9._-]{1,128}`, else generate. Put the length bound and pattern in `Settings` rather than
inline.

### CR-012 — lenient wire parsing diverges between Python and TypeScript
`backend/src/types/money.py:56` · `frontend/src/types/money.ts:27` · axis: spec · confidence: medium

Python's `Decimal()` accepts underscore digit separators, surrounding whitespace and scientific
notation. Confirmed round-trips through the serializer:

```
M(amount='1_000.50')   -> {"amount":"1000.50"}
M(amount='  12.34  ')  -> {"amount":"12.34"}
M(amount='1e3')        -> {"amount":"1000.00"}
M(amount='12.345')     -> {"amount":"12.35"}     (3dp silently rounded, not rejected)
```

`new Decimal("1_000.50")` throws, so the frontend rejects inputs the backend accepted and re-emitted.
The accepted-input set for a single wire contract is therefore defined by two different parsers,
and the inbound side accepts values D-G does not describe.

**Fix:** constrain the Python side to the wire grammar — validate the string against
`^-?\d+(\.\d{1,2})?$` in `_validate_money` before constructing `Money`, so the boundary accepts
exactly what D-G specifies and over-precise values are rejected rather than rounded.

### CR-013 — `Money` does not enforce D-G's `NUMERIC(14,2)` bound
`backend/src/types/money.py:53` · axis: spec · confidence: medium

D-G fixes storage at `NUMERIC(14,2)` — 14 total digits, so a maximum of `999999999999.99`. `Money`
accepts anything the default 28-digit decimal context can quantize, so `Money(Decimal("9" * 20))`
constructs happily and will fail only at the database insert in a later story, far from the input
boundary and with a driver-level error rather than a typed one. No persistence in this diff, so not
reachable yet.

**Fix:** add `_MAX_AMOUNT: Final[Decimal] = Decimal("999999999999.99")` beside `_TWO_PLACES` and
range-check in `_quantize`, raising `InvalidMoneyAmountError` outside the bound.

### CR-016 — `_install_redaction_filter_everywhere` is dead weight shaped by the AC's wording
`backend/src/config/logging.py:82,85` · axis: standards · confidence: high

The `RedactionFilter` attached to the handler at line 75 already sees every record routed through
that handler — that is the effective enforcement point. Logger-level filters are *not* consulted for
records propagated up from descendant loggers (`Logger.callHandlers` walks ancestors' handlers, not
their filters), so the extra copies this function pins to root and to every entry of
`logging.root.manager.loggerDict` do nothing for the normal propagation path. Their only real effect
is to make `test_redaction_filter_installed_on_every_configured_logger` (E15-S1-AC2) pass by
enumerating `loggerDict` and finding a filter on each object. The production shape is driven by the
AC's literal phrasing rather than by redaction need. It is also a one-shot snapshot: any logger
created *after* `configure_logging` runs — i.e. every `logging.getLogger(...)` at import time in a
future module — gets no filter, so AC2's "100%" property decays silently the moment group B lands.
(The `already_installed` guard at line 93 does correctly prevent duplicate accumulation across
repeated `create_app()` calls.)

**Fix:** delete the function and keep the single handler-level filter as the enforcement point.
Satisfy AC2 behaviourally instead — log a marked value through several differently-named loggers
inside `redact_values` and assert it is absent from the captured sink.

### CR-017 — the AC2 redaction test asserts structure, and its anti-vacuity proof is itself vacuous
`backend/tests/unit/test_log_redaction.py:45` · axis: standards · confidence: medium

The test asserts `isinstance(f, RedactionFilter)` over each logger's `.filters` — implementation
structure, not redaction behaviour. It would still pass with `RedactionFilter.filter` reduced to
`return True` and its body deleted, which is the exact bug it needs to catch. Its self-declared
not-vacuous check (lines 65-67) constructs a bare `logging.Logger(...)`, which trivially has an
empty `.filters` list, and asserts the helper returns False for it — that proves the helper reads a
list, not that redaction works. Separately the test calls `create_app()` with no teardown, and
`configure_logging` does `root.handlers.clear()`, so it mutates global logging state for the rest of
the session.

**Fix:** make the primary assertion behavioural (marked value in, `[REDACTED]` out, raw value
absent) and keep the structural check as a secondary assertion; wrap the `create_app()` call in a
fixture that saves and restores root handlers.

### CR-018 — the AC1 money test cannot fail for any input
`backend/tests/architecture/test_no_float_money.py:128` · axis: standards · confidence: medium

E9-S1-AC1 reads "when a **schedule is computed** from each triple, then every money field on the
result is a Decimal quantized to exactly 2 decimal places". The test computes three ad-hoc
expressions — `principal.multiply(rate)`, `principal.subtract(interest)`,
`principal.add(interest).multiply(tenure)` — which are not a schedule, and then asserts the results
are `Decimal` with exponent `-2`. That is true by construction: `Money.__init__` quantizes
unconditionally and every helper returns a `Money`. The assertion cannot fail for any input, so the
200 seeded iterations add no discriminating power. The file docstring (lines 8-11) fairly
acknowledges that the schedule generator is a later story.

**Fix:** give it something that can fail — assert the *values* against an independently computed
`Decimal` oracle rather than only the exponent — and record AC1's schedule half as explicitly
deferred to E9-S2/E9-S3 so it is not counted satisfied by this file.

### CR-020 — `Money.multiply` breaks the module's own typed-error contract
`frontend/src/types/money.ts:64` · axis: standards · confidence: medium

`fromWire`, `add` and `subtract` all route through `toQuantizedDecimal`, which wraps decimal.js
failures in `InvalidMoneyAmountError`. `multiply` constructs `new Decimal(scalar)` directly at line
65, *outside* that wrapper, so an invalid scalar string throws decimal.js's raw
`Error: [DecimalError] Invalid argument`. A caller catching `InvalidMoneyAmountError` — which
`money.test.ts:54` establishes as the module's contract — misses it. The path is untested: the tests
pass only `"3"` and a valid `Decimal`.

**Fix:** extract a `toDecimal(value)` helper that does the try/rethrow *without* quantizing, and
have both `toQuantizedDecimal` and `multiply` use it. Note that routing the scalar through
`toQuantizedDecimal` directly would be wrong — it would round the `0.105` rate to `0.11`.

### CR-024 — `project-manifest.json` is modified in the working tree, outside the envelope and inside a frozen path
`project-manifest.json:92` · axis: standards · confidence: high

The pack lists `project-manifest.json` under "Frozen, out-of-scope paths", and I confirmed it is
absent from `.claude/state/task-envelope.json#allowed_paths` (which lists `backend/**`,
`frontend/**`, `specs/**` subsets, `.claude/state/**` and a handful of root files — not this one).
The working tree nonetheless changes `verification.mode` docker→local and adds a `mode_note` key.

The change itself is defensible and honestly annotated — there is no `docker-compose.yml` until
E15-S2 and Docker Desktop is absent — and I can clear the pack's duplicate-key worry: `JSON.parse`
succeeds and `mode` appears exactly once inside `verification`. But it was made without an envelope
amendment, it is traceable to no group A acceptance criterion, and it is the direct cause of the
`canvas-sync` BLOCK. `mode_note` is also a non-schema key added to a file other harness scripts
parse. It does not belong in this change.

**Fix:** revert it out of the group A change and land it as its own `chore:` commit with an envelope
amendment covering the frozen path; carry the rationale in the amendment rather than an ad-hoc
`mode_note` key.

### CR-025 — the task envelope was rotated, not amended, breaking the audit chain
`.claude/state/task-envelope.json:64,69` · axis: standards · confidence: high

Confirmed from the working-tree diff: `created_at` / `expires_at` moved ~9h forward
(`2026-09-13T19:30:08.588Z` → `2026-09-14T04:37:07.592Z`) and `integrity.hash` was rebuilt
(`4034d3db61bdff6b223fd631480932d03510d6d52a32870b4bf0c2ee702e05da` →
`fb41b097c331594e1807274e9ee9b47320e6a57f83ca3cd62ba155ba90598404`), while `previous_envelope_hash`
remains `null` and `amendments` remains `[]` — even though `.claude/state/task-envelope-history/`
holds five files, one named for exactly the superseded hash `4034d3db…`. The chain is therefore
unauditable. Moving `created_at` forward also resets the "evidence must be created after the
envelope" window that `finalize-task-evidence.js` enforces, which is the mechanism that stops stale
evidence being accepted. Note the file path itself *is* inside `allowed_paths` (`.claude/state/**`),
so this is about chaining, not about path legality.

**Fix:** set `previous_envelope_hash` to `4034d3db61bdff6b223fd631480932d03510d6d52a32870b4bf0c2ee702e05da`
and append an `amendments` entry recording the rotation and its reason, instead of rebuilding the
hash in place.

---

## INFO findings

### CR-010 — the contract text for E11-S1 mandates a layering violation; the code correctly refused it
`specs/stories/E11-S1.md` (Operation 2) · axis: spec · confidence: high

Operation 2 places the `classify` function in `backend/src/types/delinquency.py` "reading the floors
from `backend/src/config/delinquency.py`" — a Types→Config import, explicitly FORBIDDEN by
`.claude/architecture.md` ("A `Types` importing from any other layer — FORBIDDEN"). The
implementation resolved this correctly: the classifier sits in Config, `types/delinquency.py` keeps
zero cross-layer imports, and `config/delinquency.py:3-11` documents the reasoning against the
architecture's own coupling-risk mitigation. Recorded as INFO because the *code* is right — but the
sealed text should be corrected so a later story does not implement it literally.

### CR-014 — `Money` has no division and no ordering, which is correct now and load-bearing next
`backend/src/types/money.py` · axis: spec · confidence: medium

No `divide`, no `__lt__`/`__gt__`. The story says "add/subtract/multiply-style helpers", so the
omission matches the contract and adding them now would be speculative. Flagging because E9-S2 /
E9-S3 (schedule generation, named consumers) will need division for EMI amortisation and ordering
for overpayment checks — and division is the one operation where the rounding-mode choice is
materially load-bearing. It needs to land *inside* `Money`, not as `money.amount / n` at the call
site, which is precisely the leak CR-002's check cannot see.

### CR-015 — no rounding mode is ratified in the design; the code chose one and documented it
`backend/src/types/money.py:10` · `frontend/src/types/money.ts:11` · axis: spec · confidence: low

D-G and D-J specify decimal representation and 2dp but are silent on tie-breaking. Both sides
independently use `ROUND_HALF_UP`, both document the intent to match, and both pin
`-45.005 → -45.01` in tests, so the halves agree today and the choice is defensible for lending.
Worth ratifying in `specs/design/architecture.md` because nothing mechanical prevents the two from
drifting apart, and half-up vs half-even changes reported interest.

### CR-019 — `DPD_BUCKET_FLOORS` ordering is a load-bearing invariant enforced only by a comment
`backend/src/config/delinquency.py:20` · axis: standards · confidence: medium

`classify_by_days_past_due` is correct only if the tuple stays sorted ascending by floor; lines
20-21 say so in a comment. The existing sweep test would catch a reorder, so this is defensive only.
Fix: one assertion that the floors are strictly ascending, so the invariant fails at its own
location rather than as five confusing boundary failures.

### CR-021 — `tsconfig.json` includes a file that was never created, and the contract asked for it
`frontend/tsconfig.json:22` · axis: standards · confidence: low

`include` lists `vitest.config.ts`, and E9-S1 Operation 4 required `frontend/vitest.config.ts` (new).
The test config actually lives in `vite.config.ts` via `defineConfig` from `vitest/config` — a
legitimate and arguably better choice — and `include` tolerates the missing path, so nothing breaks.
Fix: drop the entry and correct the contract text.

### CR-022 — tsconfig omits `noUncheckedIndexedAccess`, and `format()` relies on unchecked destructuring
`frontend/src/types/money.ts:75` · axis: standards · confidence: low

`const [integerPart, fractionPart] = this.toWire().split(".")` treats both as `string`. Safe today
because `toFixed(2)` always yields exactly one `.`, but against the project's "static typing
everywhere" rule this is the one place the type system asserts more than it can prove.
Fix: enable `noUncheckedIndexedAccess` and handle the undefined branch.

### CR-023 — eslint uses the non-type-checked recommended set
`frontend/eslint.config.js:9` · axis: standards · confidence: low

The config spreads `tseslint.configs.recommended` rather than `recommendedTypeChecked`. For a
codebase whose central invariant is "no float touches money", the type-aware rules are the natural
mechanical enforcement point for D-J and would be far stronger than CR-002's regex test.
Fix: switch to `recommendedTypeChecked` with `parserOptions.project`, and add
`no-restricted-properties` for `toNumber`/`valueOf` scoped to the money module.

### CR-026 — `backend/src/__init__.py` has no owning story row in the component map
`specs/design/component-map.md:29` · axis: standards · confidence: medium

The `ownership-check` gate blocks on this (14 checked, 1 unowned). The file is an empty package
marker with zero behaviour, so this is a bookkeeping gap and not a defect — but the deterministic
gate blocks and the fix is one line. `backend/tests/__init__.py` is in the same position.
Fix: add both to E15-S1's owned-files row, which already owns the backend app factory.

### CR-027 — the group A amendment self-describes as sensor appeasement and overstates conformance
`specs/design/amendments/group-a-implementation-sync.md` · axis: standards · confidence: medium

The document states it "exists solely to satisfy the `amendment-provenance` sensor" and records
entries "only to satisfy the provenance sensor's literal requirement". It then asserts each story
was "implemented exactly as designed" — not accurate for E11-S1, whose sealed Operation 2 names a
different file and a different `classify` signature than what shipped (CR-009, CR-010). To its
credit the same document does describe the Config placement honestly further down. An amendment
whose stated purpose is to clear a sensor is not provenance.
Fix: replace the "implemented exactly as designed" claims with the actual divergences — classifier
location and signature, `vitest.config.ts` not created, AC1's schedule half deferred — so the record
matches the code.

---

## Items from the pack I did not sustain

- **`project-manifest.json` duplicate `mode` key** — not a defect. `JSON.parse` succeeds and
  `verification.mode` appears exactly once. Agrees with the re-entry addendum.
- **`regression-suite-full` 54/50 findings** — not a product regression. Every finding is an
  endpoint belonging to groups B..M, none implemented. Group A is the first landed group, so the
  prior-contract regression set is empty and the check is misapplied.
- **Log injection / header injection via `X-Request-ID`** — largely already mitigated:
  `json.dumps` escapes CR/LF in the log line, the ASGI server rejects CR/LF in raw header values,
  and latin-1 header decoding makes the echo round-trip safe. Downgraded to the robustness issue in
  CR-011. (The security reviewer owns the vulnerability angle regardless.)
- **Layering violation between `config/delinquency.py` and `types/delinquency.py`** — checked
  specifically as asked; the direction is Config→Types and `types/` imports nothing outside stdlib.
  Clean.
- **`api/platform/routes.py` as a pass-through** — not a violation. `GET /health` has no business
  rule and the router returns the body directly, which is what the no-pass-through rule asks for.
- **God functions / god files** — none. Measured: max function 14 lines, max file 149 lines.
