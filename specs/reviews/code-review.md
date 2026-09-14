# Code Review — story group A (fresh round, HEAD `f4abd41`)

| Field | Value |
|---|---|
| Range | `14e9487..f4abd41` — `backend/`, `frontend/` |
| Stories | E15-S1, E9-S1, E11-S1 |
| Files judged | 13 production, 5 test, 4 tooling (all additions) |
| Verdict | **BLOCK** |
| Counts | 3 BLOCK · 20 WARN · 8 INFO |

This round was judged from the tree at HEAD. The prior round's verdict files were not
read. Method: full read of every changed file, plus eleven executable probes run against
the built app and the shipped modules (`uv run python`, no source edits) — every BLOCK
below was reproduced, not inferred.

## Prior-round BLOCKs — verified on their merits

| Prior | Claim | Verified? |
|---|---|---|
| CR-001 | `Money` rejects non-finite input | **Yes.** `is_finite()` guard at `money.py:65`; 9 parametrized cases incl. `sNaN`, `-Infinity`, and the string forms. The frontend matches (`money.ts:31`). |
| CR-002 | float guard walks `Div`/`FloorDiv`/`math.*` | **Partly.** Detection is genuinely fixed (probe: all four leak shapes counted). The *exemption* added alongside it is over-broad — see CR-003 below. |
| CR-003 | correlation id survives the 500 path | **Yes.** Pure-ASGI middleware outside `ServerErrorMiddleware`; probe confirms a 500 echoes `X-Request-ID: req-probe` and emits a `truelend.access` line at the real status. |
| CR-004 | uvicorn loggers routed through the JSON root formatter | **Yes** for `uvicorn`/`uvicorn.error`. But routing `uvicorn.error` to the JSON stream is what makes CR-002 (below) visible in that stream. |

Three of four are genuinely closed. Nothing was accepted on the strength of the table.

---

## BLOCK

### CR-001 — `backend/src/api/errors.py:15` · spec · high confidence
**The frozen "one shape for every non-2xx response" is applied only to `AppError`.**

`specs/design/api-contracts.md:26-29` mandates `{ "error": "<ErrorName>", "detail":
"<message>", "context": {...} }` for **every** non-2xx response, and names `401`, `403`,
`404`, `409`, `422` explicitly. `register_exception_handlers` registers one handler, for
`AppError`. Probe 11 against the shipped app:

```
404 -> {"detail":"Not Found"}
405 -> {"detail":"Method Not Allowed"}
422 -> {"detail":[{"type":"int_parsing","loc":["body","n"], ...}]}
500 -> text/plain; charset=utf-8  'Internal Server Error'
```

None of the four carries `error` or `context`; the 500 is not even JSON. `GET /nope` on
the app as merged reproduces this today — this is not a future-story gap. The
component-map records E15-S1 as producing "the single error-mapping table", and E4-S4
reads `threshold_kind`/`configured_value` out of `context`, so every client error path is
written against a shape the API does not emit. No test covers any non-`AppError` status;
the two envelope tests (`test_log_redaction.py:398`, `:431`) both raise `AppError`.

**Fix:** in `register_exception_handlers`, extract the body construction into one
`_envelope(error, detail, context)` helper and register three more handlers over it:
`starlette.exceptions.HTTPException` (`error = type(exc).__name__`, `detail = exc.detail`,
`context = {}`), `fastapi.exceptions.RequestValidationError` (`context =
{"errors": exc.errors()}`), and `Exception` → 500 `{"error": "InternalServerError",
"detail": "Internal Server Error", "context": {}}`. Add one test per status asserting the
three keys are present.

### CR-002 — `backend/src/config/logging.py:34` · spec · high confidence
**A value registered with `redact_values` leaks unredacted when the exception that carries
it escapes the scope — which is the only way an unhandled exception can behave.**

`redact_values` is a context manager: `__exit__` resets `_sensitive_values` during stack
unwinding. The server's logger of last resort (`uvicorn.error`, "Exception in ASGI
application", now routed into the JSON stream by the CR-004 fix) runs *after* that reset,
and after `CorrelationIdMiddleware` has reset `request_id_var`. Probe 1, verbatim output:

```
PAN LEAKED: True
{"timestamp":"...","level":"ERROR","logger":"uvicorn.error",
 "message":"Exception in ASGI application","request_id":"",
 "exception":"...ValueError: rejected application for pan=ABCDE1234F\n"}
```

Two ACs break on the same path: **E15-S1-AC1** ("the captured buffer contains 0
occurrences") and **E15-S1-AC3** ("100% of the lines ... each carries request_id equal to
req-abc") — that line carries `""`. Reachability is not hypothetical: `api-contracts.md:145`
puts a monetary amount into an error `detail`, so domain values do travel in exception
messages, and `RedactionFilter` already has an exception-path branch, so the risk was
anticipated.

The existing coverage misses it precisely because it is arranged backwards:
`test_exception_tracebacks_are_redacted_and_rendered` (`test_log_redaction.py:165`) logs
*inside* the `with redact_values(pan):` block — the one arrangement that cannot occur when
an exception propagates.

**Fix (two surgical parts):**
1. Make the sensitive set request-scoped rather than block-scoped: have
   `CorrelationIdMiddleware` bind `_sensitive_values` to a fresh set at request start and
   reset it in the same `finally` as `request_id_var`; `redact_values` then adds to the
   live set without removing on exit. The unwinding traceback is then still in scope.
2. Stop the server from rendering a second, unscrubbed copy: wrap
   `await self.app(scope, receive, send_with_correlation_id)` in
   `except BaseException: _access_logger.exception(...)` and suppress the re-raise once
   `http.response.start` has been seen (`ServerErrorMiddleware` has already sent the 500).
   Both contextvars are still live at that point.

Add a test that raises inside a `redact_values` scope, lets it escape the route, and
asserts the PAN is absent from **and** the request id present on every captured line.

### CR-003 — `backend/tests/architecture/test_no_float_money.py:32` · standards · high confidence
**The per-line exemption silences every float category on the line, not just division —
so a real float leak can be hidden behind a comment that claims to be a Decimal division.**

`_exempt_lines` is a plain substring scan, and the `lineno in exempt` check at line 70
short-circuits the `float(...)`, float-literal and `math.*` tests as well as `Div`/
`FloorDiv`. Probe 3, verbatim:

```
float() call exempted      -> 0
float literal exempted     -> 0
math.* exempted            -> 0
int/int div exempted       -> 0
```

`rate = float(raw)  # money-guard: decimal-division` reports **zero** float usages. This
file is the AC2/AC3 oracle ("reports 0 float arithmetic operations in those paths") and the
guard every later money story inherits (E9-S3's EMI is named in its own docstring), so the
escape hatch is exactly where a float will be introduced. `test_float_guard_allows_
explicitly_marked_decimal_division` (line 193) pins the over-broad behaviour as desired,
so no existing test objects.

**Fix:** narrow the exemption to the node kind it names. Move the `exempt` check inside the
division branch only:

```python
is_division = isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Div, ast.FloorDiv))
if is_division and getattr(node, "lineno", None) in exempt:
    continue
```

and delete the blanket `if getattr(node, "lineno", None) in exempt: continue` at line 70.
Then add the negative tests this needs: assert `_count_float_usages` is **non-zero** for
`float(raw)`, `0.105` and `math.floor(y)` each carrying the exemption comment.

---

## WARN

### CR-004 — `backend/src/api/platform/routes.py:11` · spec · high
`GET /health` returns `{"status": "ok"}`. Frozen `api-contracts.md:315` specifies
`{ "status": "ok", "database": "ok", "version": "..." }`. E15-S1-AC5 only requires "a JSON
body", so no AC fails, but the endpoint contract does. Note the conflict: the security
posture for an unauthenticated probe argues against disclosing `version` at all.
**Fix:** add `version` from `Settings` now, and record an amendment under
`specs/design/amendments/` deferring `database` to E15-S2 (when a DB exists) — or a human
decision to amend the frozen contract. Do not silently ship two shapes. `api-contracts.md`
is frozen: reported as a conflict, not edited.

### CR-005 — `backend/src/api/platform/routes.py:1` · spec · medium
`GET /metrics` is assigned to **E15-S1** by frozen `api-contracts.md:38` and
`architecture.md:257`, and appears in `reasons-canvas.md:234`'s platform-first step. It is
not implemented and no deferral is recorded. The story's own ACs and Generation Contract
Operations omit it, so the sealed story and the frozen design disagree.
**Fix:** record the deferral (to E15-S3, which owns the SLO ACs) in
`specs/design/amendments/`, or implement it. Report, do not edit the frozen docs.

### CR-006 — `backend/src/types/money.py:59` · spec · high
`Money` enforces no magnitude bound. Probe 6: `Money(Decimal("1E+20"))` is accepted and
`_serialize_money` emits `"100000000000000000000.00"` — 21 integer digits. The frozen wire
schema is `{"type":"string","pattern":"^-?[0-9]{1,12}\\.[0-9]{2}$"}`
(`api-contracts.schema.json:893`), and D-G fixes storage at `NUMERIC(14,2)`. The type is
the designated single enforcement point for D-G, so the range half of the invariant is
currently enforced nowhere; the failure would surface as an unmapped driver error at
insert time.
**Fix:** in `Money.__init__`, after quantization, reject `abs(amount) >= Decimal("1E12")`
with `InvalidMoneyAmountError`. Add the boundary tests (`999999999999.99` accepted,
`1000000000000.00` rejected).

### CR-007 — `backend/src/config/settings.py:24` · standards · high
`log_level: str` is unvalidated and passed straight to `root.setLevel`. Probe 4:
`TRUELEND_LOG_LEVEL=debug` → `ValueError: Unknown level: 'debug'`; same for `""` and any
typo. Because `app = create_app()` runs at module import, this is an unhandled exception
at **import** of `src.api.app`, i.e. the server refuses to boot on the conventional
lowercase spelling uvicorn itself uses (`--log-level debug`).
**Fix:** type it `Literal["DEBUG","INFO","WARNING","ERROR","CRITICAL"]` with a
`field_validator(mode="before")` that upper-cases, so a bad value fails as a settings
validation error at startup with a readable message.

### CR-008 — `backend/src/config/logging.py:63` · standards · high
`_MIN_REDACTABLE_LENGTH = 6` makes `_scrub` **silently skip** any registered value shorter
than 6 characters. Probe 5: `redact_values("12345")` → `"message": "value=12345"`, leaked,
with no warning to the caller who explicitly marked it sensitive. AC1's three values are
all ≥10 chars so AC1 passes; a short document id or amount marked sensitive by a later
story will not be.
**Fix:** do not skip silently. Either match short values with `\b` word boundaries instead
of the separator-tolerant pattern, or raise/`logger.warning` at `redact_values` time so the
caller learns the value will not be protected. Add a test for the short-value path.

### CR-009 — `backend/src/config/logging.py:88` · standards · medium
`RedactionFilter.filter` sets `record.args = ()`, destroying the argument tuple on the
shared record. Any formatter that reads `record.args` then breaks — which is the stated
root cause of the 7-line apology at `logging.py:143-149` silencing `uvicorn.access`
("its AccessFormatter reads record.args, which RedactionFilter clears, raising
ValueError"). A workaround that needs a paragraph of justification is a signal the code is
wrong, and here it is fixable.
**Fix:** preserve the record shape — scrub the template and each argument separately
(`record.msg = _scrub(str(record.msg), vals)` and
`record.args = tuple(_scrub(str(a), vals) for a in record.args)`), then reformat
`uvicorn.access` through the JSON formatter instead of disabling it, and delete the
apology comment.

### CR-010 — `backend/src/api/middleware.py:61` · standards · medium
The one surviving access-log line is `"%s %s -> %s"` (method, path, status). It carries no
duration, and `uvicorn.access` — the only other source of per-request timing — is
disabled. Nothing in the log stream supports the project runtime SLO
(`{"p95_ms": 500}`) or E15-S3-AC1.
**Fix:** capture `time.perf_counter()` at scope entry and emit `duration_ms` on the access
line (as a formatter field, not string-interpolated), so the SLO sensor has a source.

### CR-011 — `backend/src/config/logging.py:103` · standards · medium
`JSONLogFormatter` builds its payload from a fixed key list, so `logger.info(...,
extra={...})` fields are silently discarded (probe 9: `applicant_pan` set on the record
never appears). Today that is accidentally safe, because `RedactionFilter` never scrubs
`record.__dict__` either — the moment a later story adds extras to the payload, they will
ship unredacted.
**Fix:** either serialise a whitelisted `extra` mapping through `_scrub` in the same
change, or assert the limitation with a test so no story adds extras without also adding
redaction for them.

### CR-012 — `backend/src/config/logging.py:49` · standards · medium
`_redaction_pattern` is `@lru_cache(maxsize=256)` keyed on the raw sensitive value, and the
compiled `re.Pattern` retains it in `.pattern`. Up to 256 applicant PANs/Aadhaars therefore
stay resident in process memory indefinitely, long past the request scope that marked them
sensitive — the opposite of the module's purpose. Secondary: for salary-document
*content* (an explicit AC1 target), the compiled pattern is proportional to the document
size and is re-applied to every log line in scope, against a 500 ms p95 budget.
**Fix:** key the cache on a `hashlib.sha256` digest of the value, or drop the cache and
compile per call for values above a size threshold. (Disclosure impact is the
security-reviewer's call; flagged here as a lifecycle/retention defect.)

### CR-013 — `backend/src/config/delinquency.py:31` · spec · high
E11-S1 Generation Contract Operation 2 seals `classify(days_past_due: int) ->
DelinquencyBucket` in `backend/src/types/delinquency.py`, "reading the floors from
`backend/src/config/delinquency.py`". Shipped instead: `classify_by_days_past_due(int)`
and `classify(date, date)` in `config/delinquency.py`, with `types/delinquency.py` holding
only the enum. The implementation is **right** — the sealed text would require Types to
import Config, which the one-way layering forbids — but the published name and signature
of the single classifier changed, and E11-S2/E12-S1 are planned against the sealed one.
No amendment is recorded.
**Fix:** record the deviation in `specs/design/amendments/` (an allowed path) naming both
shipped signatures, so the consuming stories are planned against what exists. Do not edit
the frozen component-map or the story's sealed Operations.

### CR-014 — `frontend/tests/unit/money.test.ts:79` · standards · medium
`FLOAT_RISK_PATTERNS` has no pattern for division, and `countFloatRisks` is only ever run
against `src/types/money.ts`. The backend guard's own docstring names `principal / months`
as "the most likely leak"; the frontend guard cannot see it. `MoneyText.tsx` — the other
half of the E9-S1 frontend surface, and where AC3's "carried and formatted" formatting is
consumed — is never scanned.
**Fix:** add `/[^*/\s]\s*\/\s*[A-Za-z_$(\d]/` (or equivalent) to the pattern list with a
matching positive case in the `it.each` table, and scan `src/ui/components/MoneyText.tsx`
in the same test.

### CR-015 — `frontend/src/types/money.ts:64` · standards · medium
`multiply` calls `new Decimal(scalar)` outside any try/catch, so a non-numeric scalar
string throws a raw `decimal.js` `Error`, not the module's own
`InvalidMoneyAmountError` — inconsistent with `fromWire`, which wraps it. Separately, the
frontend non-finite guard (`money.ts:31`) has **no test**, while the backend has nine
parametrized cases for the same rule.
**Fix:** route the scalar through `toQuantizedDecimal` (or wrap the construction in the
same try/catch), and add `expect(() => Money.fromWire("NaN")).toThrow(InvalidMoneyAmountError)`
plus the `"Infinity"` case.

### CR-016 — `backend/src/types/money.py:69` · standards · medium
`ROUND_HALF_UP` on a small negative produces negative zero, which survives to the wire and
to the UI. Probe 6: `Money("-0.001")` → amount `Decimal("-0.00")`, `_serialize_money` →
`"-0.00"`, and `MoneyText` renders `-0.00`. Equality and hashing are correct
(`Money("-0.001") == Money("0.00")` is `True`), so this is presentation, not arithmetic —
but an outstanding balance displayed as "-0.00" is a defect a user will report.
**Fix:** normalise in `_quantize`: `if quantized.is_zero(): return quantized.copy_abs()`.
Add the case to the quantization table.

### CR-017 — `backend/tests/unit/test_log_redaction.py:149` and `:310` · standards · high
Both tests call `logging.config.dictConfig(uvicorn LOGGING_CONFIG)` followed by
`configure_logging(...)` and never restore the previous configuration. They leave
`uvicorn.access` permanently `disabled = True` and the root handler list replaced for the
remainder of the session, making the suite order-dependent — the exact failure mode that
forced `log_capture` to declare a dependency on `client` (`conftest.py:36`).
**Fix:** wrap both in a fixture that snapshots `logging.root.handlers`, `root.level` and
the `disabled`/`propagate`/`handlers` state of the touched loggers, and restores them in
teardown.

### CR-018 — `backend/tests/unit/test_log_redaction.py:66` · standards · medium
E15-S1-AC2 requires that "a logger **registered** without it fails the assertion". The
negative control constructs `logging.Logger("unregistered-probe-logger")` directly, which
is *not* in `logging.root.manager.loggerDict` — so it dodges the real question. Any logger
created after `configure_logging` runs genuinely has no filter (the handler-level filter is
what actually protects those lines), and a registered probe would expose that.
**Fix:** use `logging.getLogger("probe-after-configure")` and assert the intended
behaviour explicitly — either that `_install_redaction_filter_everywhere` is re-runnable,
or that the handler-level filter is the real control and the per-logger install is
belt-and-braces. Note also that with the filter on the handler, the per-logger loop at
`logging.py:167` is redundant for every propagating logger.

### CR-019 — `backend/tests/unit/test_log_redaction.py:237` · standards · medium
`_modules_referencing_pii` substring-matches `"pan"`, `"aadhaar"`, `"salary_doc"` against
the lower-cased whole file. `"pan"` matches `expand`, `company`, `panel`, `span` — so this
control will fail on unrelated modules as the codebase grows, and the natural response to
a false positive is to weaken it. It also skips **any** file basenamed `logging.py`
anywhere under `src/`, so a future `src/service/logging.py` is silently exempt from the
PII control.
**Fix:** match with `re.search(rf"\b{field}\b", lowered)`, and compare the resolved path
against `src/config/logging.py` rather than `module.name`.

### CR-020 — `backend/tests/unit/test_log_redaction.py:113` · standards · medium
`test_app_error_is_mapped_to_a_typed_json_response` and
`test_error_envelope_context_defaults_to_empty` (`:431`) are the same test: both register a
throwaway route raising `AppError("boom", status_code=418)` and both assert
`{"error": "AppError", "detail": "boom", "context": {}}`.
**Fix:** delete the earlier one; the later one carries the clearer name and docstring.

### CR-021 — `backend/src/__init__.py:1` · standards · medium
A 0-byte package marker with no row in the frozen `component-map.md` (the open
`ownership-check` block). Judged on need: `src/api`, `src/config`, `src/types` and
`src/api/platform` have **no** `__init__.py`, so the tree is already an implicit-namespace
layout and this single marker is inconsistent with its own siblings.
**Fix:** delete it and re-run `uv run pytest -q` + `uv run mypy src/`. If both stay green,
that clears the ownership block without amending a frozen artefact or spending a human
re-record on a receipt. If mypy needs it, add the three sibling `__init__.py` files for
consistency and take the map amendment to a human.

### CR-022 — `backend/src/api/app.py:52` · standards · medium
`app = create_app()` at module scope means importing `src.api.app` reads the environment
(`Settings()`) and mutates global logging state (`root.handlers.clear()`). Every
`build_fastapi_app()` call repeats the handler reset — which is why `log_capture` must
depend on `client` and documents the ordering in a four-line docstring. Import-time
side effects also make CR-007 a boot failure rather than a startup validation error.
**Fix:** move `configure_logging(settings)` out of `build_fastapi_app` into a FastAPI
`lifespan` startup hook (or keep it in the factory but make the handler install
idempotent), so importing the module has no side effect and fixtures need no ordering
trick.

### CR-023 — `backend/tests/unit/test_log_redaction.py:165` · spec · high
`test_exception_tracebacks_are_redacted_and_rendered` constructs the record and formats it
**inside** the `with redact_values(pan):` block. An exception that reaches the server's
logger has by definition unwound out of that block, so the test asserts a state the
production path never reaches and would not fail if CR-002 were present. This is the
assertion that let CR-002 through.
**Fix:** move the `filt.filter(record)` / `formatter.format(record)` calls outside the
`with` block. That test then fails until CR-002 is fixed, which is the point.

---

## INFO

- **CR-024** — `backend/src/config/logging.py:141`: `_JSON_ROUTED_LOGGERS` includes
  `"gunicorn.error"`; gunicorn is not a dependency (`uvicorn[standard]` only). Speculative
  entry for a server this project does not run.
- **CR-025** — `backend/src/types/money.py:52` and
  `tests/architecture/test_no_float_money.py:159`: both justify the non-finite guard by
  claiming "an ordering comparison against an underwriting threshold raises
  `InvalidOperation`". `Money` defines no ordering operators, so *any* comparison raises
  `TypeError` (probe 6). The guard is right; the stated reason is not. Also worth noting
  E4-S4's threshold checks will need `__lt__`/`__le__`, which no story has yet assigned.
- **CR-026** — `backend/src/types/money.py:101`: arithmetic runs in the mutable global
  decimal context. Probe 6 with `getcontext().prec = 6` makes `multiply` raise
  `InvalidMoneyAmountError` on an ordinary amount. Wrap arithmetic in
  `decimal.localcontext()` with an explicit `prec` so no unrelated module can change money
  behaviour.
- **CR-027** — `backend/src/api/serializers.py:20`: `_validate_money` accepts
  `Money | str | Decimal` but rejects `int`, while `Money.__init__` accepts `int`. Probe 7:
  `Model(amount=1234)` is a `ValidationError`. Harmless but an inconsistency between the
  type and its only serializer.
- **CR-028** — `backend/src/config/delinquency.py:39`: `bucket = DPD_BUCKET_FLOORS[0][0]`
  can never be read (the first floor is 0 and negatives are rejected above). If the table
  is ever reordered or its first floor changes, it silently returns `CURRENT` instead of
  failing. Prefer raising on a table whose first floor is not 0.
- **CR-029** — `specs/stories/E9-S1.md` Scope In still reads "Frontend integer-minor-unit
  money module", which D-J and `component-map.md:123-129` forbid. The shipped code
  correctly follows D-J. `specs/stories/**` is an allowed path; the stale scope line
  should be re-rendered so a later reader does not implement the forbidden form.
- **CR-030** — `frontend/vitest.config.ts` is named in E9-S1 Operation 4 and listed in
  `tsconfig.json` `include`, but does not exist; the vitest config lives in
  `vite.config.ts`. Functionally equivalent — remove the dead `include` entry.
- **CR-031** — `backend/tests/unit/test_log_redaction.py:71`: AC3's "100% of the lines" is
  proven over exactly one line (`truelend.access`), and no test asserts that a line logged
  from *inside* a route handler carries the id — the actual propagation claim. Probe 10
  confirms it works for both `async def` and threadpool `def` handlers, so this is a
  coverage gap, not a defect. Add one handler-emitted log line to the AC3 test.

## Things checked and found correct

- Layering is clean: `src/types/*` imports only stdlib; `src/config/delinquency.py` and
  `logging.py` import Types/Config only; `src/api/*` imports downward only. No cycle, no
  pass-through module (the health router returns its body directly, no service layer).
- Delinquency ladder boundaries are exhaustively correct at every edge — probed 0, 29, 30,
  59, 60, 89, 90, 179, 180 and the full 0..400 sweep against an independent oracle; negative
  DPD raises, zero is `CURRENT`, future due dates clamp to 0. `test_bucket_ladder.py`'s
  oracle is written from D-B's literal ranges rather than the production table, which is
  exactly right — it would catch a table edit.
- Money rounding is `ROUND_HALF_UP` on the same tie in both languages (`0.005 → 0.01`,
  `-0.005 → -0.01` on the backend; `-45.005 → -45.01` on the frontend), quantization is to
  exponent -2 on construction *and* after every operation, floats and bools are rejected at
  construction and as multiply scalars, and equality/hash are consistent.
- `MoneyField` is the only wire conversion, emits a quoted 2dp string
  (`{"amount":"1234.50"}`), and rejects JSON numbers, ints and floats on input (probe 7).
  FastAPI's generated response schema is `{"type":"string"}` — no JSON number can carry an
  amount.
- Correlation id propagates into both `async def` and threadpool `def` handlers, is echoed
  on 200/404/405/500, and generates a non-empty id when the header is absent.
- Every line reaching the root handler is `json.dumps`-produced, so CR/LF in a
  caller-supplied `X-Request-ID` cannot break the JSON stream.
- All changed functions and files are within the project's ratcheted limits
  (test files 500, production 300, functions 30); per `REVIEW.md` these are sensor-enforced
  and not re-litigated here.

## Conflicts reported, not edited

Frozen paths were not modified. CR-004, CR-005 and CR-013 each need a human decision
recorded under `specs/design/amendments/` (or an explicit re-record of the design receipt);
CR-021 is the open `ownership-check` block, and the recommendation there avoids touching
`component-map.md` at all.
