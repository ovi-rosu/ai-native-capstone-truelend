# Code Review — `/gate --group A`, round 3

**Range:** `14e9487..ba457bf` · **Branch:** `feat/harness-scaffold-and-planning`
**Scope:** production source + tests listed in `review-context-pack.md` §5, plus the files they call into
**Verdict:** **BLOCK** — 1 BLOCK, 12 WARN, 5 INFO
**Method:** every claim below was re-derived by execution at HEAD. Stored verdict files were
not treated as authority. Production files were mutated only to prove a finding and restored
(`git diff -- backend/src frontend/src` is empty).

---

## Disposition of the two round-2 findings I was asked to re-judge

### B-3 — `HTTPException.headers` discarded — **CLOSED**

Verified by request, not by reading. A throwaway app was mounted on the real
`create_app()` and driven across every envelope path:

| Request | Status | Headers on the response | Envelope |
|---|---|---|---|
| `POST /only-get` | 405 | `allow: GET` | `{"error":"HTTPError","detail":"Method Not Allowed","context":{}}` |
| `HEAD /health` | 405 | `allow: GET` | — |
| `GET /guarded` | 401 | `www-authenticate: Bearer realm="truelend"` | `{"error":"Unauthorized",...}` |
| `GET /retry` | 429 | `retry-after: 42` | `{"error":"HTTPError",...}` |
| `GET /nope` | 404 | — | `{"error":"NotFound","detail":"Not Found","context":{}}` |
| `POST /echo` (bad body) | 422 | — | `{"error":"ValidationError","detail":"request validation failed","context":{"field":"body.n"}}` |
| `GET /boom` | 500 | — | `{"error":"InternalServerError","detail":"internal server error","context":{}}` |
| `GET /health` | 200 | — | contract shape `{status,database,version}` |

`Allow` and `WWW-Authenticate` are both restored, arbitrary `HTTPException` headers
(`Retry-After`) survive too, and nothing regressed while the `headers` parameter was threaded
through `_envelope`: the three envelope keys, `content-type: application/json` and the
`X-Request-ID` stamp are intact on all eight paths, including 404/422/500. A regression test
exists and is real (`test_error_envelope.py:189`).

### B-4 — quadratic thousands-separator regex — **CONFIRMED as a defect, WARN on reachability**

Round 2's dispute is resolved: evaluator 3 timed the wrong sink. Measured through the real
class (`npx tsx`, `frontend/src/types/money.ts` unmodified):

```
input="1e10000"  (7 bytes) -> toWire length  10004 | fromWire 0.0 ms | toWire 0.2 ms | format   38.6 ms
input="1e50000"  (7 bytes) -> toWire length  50004 | fromWire 0.0 ms | toWire 0.7 ms | format 1035.9 ms
input="1e100000" (8 bytes) -> toWire length 100004 | fromWire 0.0 ms | toWire 2.5 ms | format 4167.8 ms
```

The cost is isolated to line 78; `fromWire` and `toWire` are both free. Raw-regex scaling
confirms it is quadratic (1000→0.4 ms, 2000→1.4 ms, 4000→5.4 ms, 8000→22.8 ms, 16000→99.5 ms,
32000→430 ms, 64000→1759 ms — 4× per doubling).

**Neither the constructor nor `toWire()` bounds the input.** `Money.fromWire` accepts anything
`decimal.js` parses, so an 8-byte string reaches `format()` as 100,004 digits.
Filed as **WARN**, not BLOCK: the only caller of `format()` is `MoneyText`, and the only
callers of `MoneyText` are its own tests — the frontend at HEAD (`src/` is two files) has no
fetch layer and no input control, so there is no untrusted path to it and the impact is a
client-side tab stall, not server availability. See **CR-304** for the fix.

---

## BLOCK

### CR-301 — the `method` label is unbounded; B-2 is only half-closed
`backend/src/api/middleware.py:50,72-73,132,141-143` · **spec** · confidence **high**

`f1367f5` bounded the *route* dimension (`route_label()` → matched template or one
`<unmatched>` bucket, with a 4-line comment explaining why). The *method* dimension of the
same keys got no bound, and the new E15-S4 histogram inherited the gap:

```python
_request_counts:  Counter[tuple[str, str, int]]              # (method, route, status)
_duration_counts: dict[tuple[str, str], list[int]]           # (method, route) -> 12 ints
_duration_totals: dict[tuple[str, str], tuple[int, float]]
```

`method` comes straight from `scope["method"]` with no allow-list. Measured against a **real
uvicorn server over raw sockets** with `http="h11"` — uvicorn's own pure-Python parser and its
fallback when `httptools` is unavailable:

```
=== h11: 3000 distinct method tokens on ONE keep-alive connection ===
   accepted: 3000 in 0.7s
   counter series: 2998
   histogram series: 2998
   retained metric-state bytes (lower bound): 2,522,096
   distinct method label values in exposition: 3000
   /metrics response size: 3,553,759 bytes
```

Per-method series confirmed in the exposition:

```
http_requests_total{method="FOO!#$%&'*+-.^_`|~9",route="/health",status="405"} 1
http_requests_total{method="XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX",route="/health",status="405"} 1
```

The histogram is worse per series than the counter it copied (a 12-element bucket list plus a
tuple per key), the state is never evicted, and `/metrics` is unauthenticated — so this is also
a response-amplification vector. Extrapolated to round 2's 60,000-request figure: ~50 MB
retained and a ~71 MB exposition body.

**Refutation attempted and partially succeeded — read this before deciding.** With the parser
the project actually declares (`uvicorn[standard]`, `httptools` pinned in `backend/uv.lock:229`)
the same probe is rejected upstream:

```
httptools: method='XPROBE1' -> 400 Bad Request ; method='PROPFIND' -> 405 (counted, bounded)
h11:       method='XPROBE1' -> 405 Method Not Allowed (counted, unbounded)
```

I am still filing BLOCK because:
1. the only thing holding the bound is an **optional C extension's method allow-list** —
   nothing in this repository documents, tests or pins it, and `uvicorn`'s `http=` is a
   first-party knob that flips it;
2. `middleware.py` is deliberately written as a **server-agnostic pure ASGI** middleware
   (module docstring lines 9-23), so it cannot rely on one server's parser for a bound it
   accepted responsibility for on the sibling label;
3. no `Dockerfile`/`docker-compose.yml` exists yet, so no committed artefact pins the parser;
4. round 2's B-2 would otherwise be recorded as closed when one of its two dimensions is open.

**Fix (3 lines, mirrors the existing in-file pattern):** add
`_KNOWN_METHODS = frozenset({"GET","HEAD","POST","PUT","PATCH","DELETE","OPTIONS","TRACE"})`
and a `method_label(scope)` that returns the method when it is in the set and a single
`"<other>"` bucket otherwise; call it from `_stamping_send` and `_observe` in place of
`str(scope.get("method", "-"))`. Add the h11 cardinality test as the regression guard.

---

## WARN

### CR-302 — `_escape_label` passes raw control characters other than LF into a label
`backend/src/api/platform/routes.py:78-83` · **spec** · confidence **high**

```
backslash    -> 'a\\\\b'    escaped=True
quote        -> 'a\\"b'     escaped=True
LF           -> 'a\\nb'     escaped=True
CR           -> 'a\rb'      escaped=False
NUL          -> 'a\x00b'    escaped=False
ESC          -> 'a\x1bb'    escaped=False
LS U+2028    -> 'a b'  escaped=False
```

With a CR in a label value, `_histogram_lines()` emits **14 lines containing a raw CR**:

```
'http_request_duration_seconds_bucket{method="GET\r999",route="/t",le="0.005"} 0'
```

E15-S4-AC2 states: *given* attacker-supplied text containing control characters *reaching a
metrics label*, *then* the output has *no raw control character*. Under the AC's own stated
precondition the renderer fails it. Not a BLOCK: the Prometheus exposition format itself only
*requires* `\`, `"` and `\n` to be escaped, so the docstring's "per the Prometheus exposition
format" is accurate and the official client libraries do exactly this much; and with CR-301
fixed neither label source can carry a control character. **Fix:** extend `_LABEL_ESCAPES` to
map `\r` (and, cheaply, the remaining C0 range) to their escaped forms, so the renderer
satisfies AC2 independently of which labels happen to exist.

### CR-303 — the label-escaping fix has zero test coverage; the tests named for it bite on something else
`backend/tests/architecture/test_observability_contract.py:90-103`, `backend/tests/unit/test_health_probe.py:93-118` · **standards** · confidence **high**

Mutation-proved. Reducing `_escape_label` to `return value` — deleting the entire B-1
remediation — leaves the suite green:

```
MUTANT A: _escape_label identity  -> 104 passed
```

Mutating `route_label` to the raw path instead fails four tests, including both
"…labels cannot be injected from a request path":

```
MUTANT C: route_label -> raw path -> 4 failed, 100 passed
  test_observability_contract.py::test_histogram_labels_cannot_be_injected_from_a_request_path
  test_observability_contract.py::test_histogram_cardinality_is_bounded_by_route_template
  test_health_probe.py::test_metrics_labels_cannot_be_injected_from_a_request_path
  test_health_probe.py::test_metrics_cardinality_is_bounded_by_route_not_path
```

So both injection tests actually assert the *cardinality bound*; the escaping layer is
unguarded and a future refactor can drop it silently. (The cumulative-bucket logic, by
contrast, **is** covered — `running = count` fails
`test_histogram_buckets_are_cumulative_and_carry_count_and_sum`.)
**Fix:** assert the renderer's escaping directly at the exposition boundary — after
`observe_duration('GET"x\\y', '/t', 0.01)`, `_histogram_lines()` must contain
`method="GET\\"x\\\\y"` and no unescaped quote. The exposition text is the public contract, so
this is a public-interface assertion, not a private-helper one.

### CR-304 — `Money.fromWire` does not bound the input its own docstring describes
`frontend/src/types/money.ts:24-35,45-48,78` · **spec** · confidence **high**

Evidence in the B-4 section above. `fromWire`'s docstring says "Parse the quoted 2dp wire
string", but `toQuantizedDecimal` accepts anything `decimal.js` parses, including `"1e100000"`,
so the documented bound does not exist and `format()` pays 4,168 ms for an 8-byte input.
**Fix:** in `toQuantizedDecimal`, reject a `string` that does not match the wire form the
backend declares (`/^-?\d+\.\d{2}$/` — `backend/src/api/serializers.py:24`) or at minimum cap
the integer digit count, throwing `InvalidMoneyAmountError`. That closes the cliff at the
boundary and makes the docstring true. Note the existing tests
(`money.test.ts:22,49`) rely on tolerant parsing of `"1234.5"` / `"42"`, so pick one tolerance
and apply it on both sides of the wire — see CR-306.

### CR-305 — both stated reasons for disabling `uvicorn.access` are false or overstated
`backend/src/config/logging.py:217-223` · **standards** · confidence **high**

Claim (a): *"`request_id_var` is already reset by the time it emits (it logs after the response
completes, outside the middleware scope), so it could only ever render request_id: ''"*.
**False at HEAD.** uvicorn emits the access line *inside its own `send()`*, in the
`http.response.start` branch (`uvicorn/protocols/http/httptools_impl.py:484`,
`h11_impl.py:481`) — and that `send` is the one `CorrelationIdMiddleware` wraps, so it fires
inside the middleware's `try` block while both contextvars are still bound. Replaying that
exact ordering with a stand-in for uvicorn's send:

```
request_id_var as seen at uvicorn's access-log call site: ['req-42']
after the request completes: ''
```

The claim was true of the `BaseHTTPMiddleware` version CR-003 deleted; it is stale.

Claim (b): *"its AccessFormatter reads record.args, which RedactionFilter clears, raising
ValueError and dropping the line entirely."* **Overstated** — `RedactionFilter.filter` clears
`record.args` only when a redaction actually changed the message:

```
with NO registered values      -> record.args = ('a', 'b')
with a MATCHING registered value -> record.args = ()
```

so the breakage is conditional on registered PII appearing in the access line, not inherent.
The third sentence — `CorrelationIdMiddleware` already emits an equivalent JSON line — is true
and is the real justification. **Fix:** delete the two false sentences; keep the third.

### CR-306 — `MoneyField`'s declared schema is not the contract the validator enforces
`backend/src/api/serializers.py:24,75-83` and `backend/tests/architecture/test_no_float_money.py:342` · **spec** · confidence **high**

The new JSON-schema hook works as its docstring claims — `model_json_schema()` renders, and
both a response model and a **request-body** model appear in `components.schemas` with the
`requestBody` `$ref` intact (verified against a live `/openapi.json`). But the declared
`pattern` is documentation only: `no_info_plain_validator_function` bypasses schema validation,
so the server accepts input the document calls invalid.

```
POST /quote {"principal": "1234.50"} -> 200 {"principal":"1234.50"}
POST /quote {"principal": 12.3}      -> 422   (float correctly rejected)
POST /quote {"principal": "12.3"}    -> 200 {"principal":"12.30"}   <-- schema says invalid
```

The docstring states the pattern exists *"so a generated client cannot send `12.3` or a JSON
number and still look contract-conformant"*; half of that is enforced. `test_no_float_money.py:342`
asserts `not re.fullmatch(field["pattern"], "1234.5")` — it locks in the documented contract
while nothing checks the enforced one. **Fix:** match a `str` input against `_WIRE_PATTERN` in
`_validate_money` before constructing `Money`, or narrow the pattern and the docstring to the
tolerance actually implemented. Pick the same answer as CR-304 so both sides of the wire agree.

### CR-307 — `sanitise_context` drops context values silently, with no marker and no log
`backend/src/api/errors.py:50-63,76,85-101` · **standards** · confidence **high**

Measured on live requests:

```
context={"note": "A"*300, "kept": "short"} -> {"kept":"short"}
context={"ratio": 0.5, "flag": None}       -> {}
```

A value over `_MAX_CONTEXT_VALUE_CHARS` is dropped rather than truncated, and floats, `None`,
lists and nested mappings vanish without trace. `context` is the machine-readable half of the
frozen envelope and `src/types/errors.py:20` records that E4-S4-AC2 depends on reading
`threshold_kind` / `configured_value` out of it, so a caller cannot distinguish "the service
did not set this" from "the sanitiser removed it". `_scalar`'s docstring says "Anything
structured is dropped", which under-describes what actually goes. **Fix:** substitute a marker
(`"<omitted>"`) for the dropped key instead of deleting it, and truncate over-long strings to
`_MAX_CONTEXT_VALUE_CHARS` rather than discarding them.

### CR-308 — `detail` bypasses the guards applied to `context` values
`backend/src/api/errors.py:115` · **spec** · confidence **medium**

`_sanitise_value` drops any context value matching `_CREDENTIAL_URI` or exceeding 200 chars.
`detail` gets `scrub_text()` only, which is a no-op unless the exact value was registered:

```
GET /dsn-in-detail  -> 500 {"error":"AppError","detail":"could not connect: postgresql://truelend_app:S3cr3tPass@db.internal:5432/truelend","context":{}}
GET /dsn-in-context -> 500 {"error":"AppError","detail":"could not connect","context":{}}
```

The identical string is blocked in one field of the same envelope and egressed verbatim in the
other. Medium confidence because `detail` is developer-authored and `handle_unexpected` already
pins a constant, so reaching this needs someone to interpolate a DSN into an `AppError` message
— but that is the likeliest carrier, which is why the guard exists. **Fix:** run `detail`
through the same `_CREDENTIAL_URI` / length check inside `_envelope`. (The PII half of this is
the security-reviewer's call, not mine.)

### CR-309 — `_database_status` swallows the probe's failure reason
`backend/src/api/platform/routes.py:57-60` · **standards** · confidence **high**

```python
except Exception:  # noqa: BLE001 - a probe must never break the probe
    return "down"
```

The *failure* does reach the caller (`"database":"down"`, `"status":"degraded"`), so this is
not a hidden error — but the reason is discarded entirely, and `/health` is the only signal an
operator has. A misconfigured probe and a dead database are indistinguishable, with nothing in
the logs. **Fix:** `logging.getLogger("truelend.access").warning("database probe failed",
exc_info=True)` before returning `"down"` — the traceback is already redaction-filtered.

### CR-310 — avoidable `# type: ignore` in production code
`backend/src/config/logging.py:84-91` · **standards** · confidence **high**

`begin_redaction_scope() -> object` throws away the `Token` type that `ContextVar.set` returns,
which then needs `# type: ignore[arg-type]` on the `reset`. CLAUDE.md requires static typing
everywhere. Verified the fix is clean: typing them as `contextvars.Token[set[str] | None]` and
deleting the ignore gives `mypy src/` → `Success: no issues found in 12 source files` and
`104 passed`. (Applied, verified, reverted.)

### CR-311 — both AC2 "every logger has the filter" tests still pass by construction
`backend/tests/unit/test_log_redaction.py:43-64,190-220` · **standards** · confidence **high**

Round 2's finding, unfixed at HEAD. Both tests build their logger list by iterating
`logging.root.manager.loggerDict` — the same collection
`_install_redaction_filter_everywhere()` (`logging.py:241-251`) had just iterated — so any
logger created *after* `configure_logging` runs is invisible to the assertion by construction.
The `unregistered-probe-logger` control proves the predicate function works, not that the
enumeration is complete. The real guarantee comes from the `RedactionFilter` on the **root
handler** (`logging.py:199`), which covers every propagating logger and is what
`test_sensitive_application_values_never_appear_in_any_log_line` actually exercises.
**Fix:** add one case that creates a logger *after* `configure_logging`, gives it its own
handler with `propagate=False`, and asserts a registered value is still redacted — the case the
enumeration cannot see.

### CR-312 — the p95 assertion cannot fail on latency, and the comment above it says otherwise
`backend/tests/architecture/test_observability_contract.py:86-87` · **spec** · confidence **high**

```python
# A no-I/O health probe must land far under the 500 ms budget.
assert p95_bound == "+Inf" or float(p95_bound) <= 0.5
```

`"+Inf"` is the unbounded bucket: the disjunct makes the assertion pass when p95 exceeds every
declared bound, which is the exact opposite of the stated requirement. E15-S4-AC1's purpose is
that the 500 ms SLO becomes measurable; this test proves p95 is *computable* but asserts
nothing about its value. **Fix:** `assert p95_bound != "+Inf" and float(p95_bound) <= 0.5`.

### CR-313 — process-global metric state has no enforced test isolation
`backend/src/api/middleware.py:50,72-73,108-112`, `backend/tests/conftest.py` · **standards** · confidence **medium**

`_request_counts` / `_duration_counts` / `_duration_totals` are module-global and never
evicted. Isolation holds today only because every count-asserting test remembers to call
`reset_request_counters()` first — verified across three orderings (file alone: 6 passed; file
last after the whole suite: 104 passed; reordered: 8 passed). One future test that forgets it
silently inherits another test's counts. `reset_request_counters()` is also production API
whose docstring says it exists "For tests". **Fix:** an autouse fixture in
`backend/tests/conftest.py` that calls `reset_request_counters()`, so isolation is structural
rather than conventional.

---

## INFO

- **CR-314** — `middleware.py:132-134`: the counter is incremented *before* `await send(message)`,
  so a response that fails mid-send is still recorded as served. Probe: with a `send` that
  raises at `http.response.start`, `request_counter_snapshot()` shows
  `{('GET','/health',200): 1}`. Minor over-count of successes in the SLO signal.
- **CR-315** — `middleware.py:98-100`: `latency_bucket_bounds()` is a single-use getter returning
  a module constant that `routes.py` could import directly. Borderline shallow wrapper
  (code-gen §8), kept only to preserve the leading-underscore convention.
- **CR-316** — `middleware.py:159,161`: `_observe` is called on both the success and exception
  branches rather than once in a `finally`. Duplicated call site, and if `_observe` itself
  raised inside the `try`, the `except` would record a second observation.
- **CR-317** — **Refuted, recorded for coverage.** `zip(..., strict=True)` at `routes.py:115` is
  safe: both sequence lengths derive from `_LATENCY_BUCKETS`, a module-level tuple, and
  `observe_duration` sizes the list from the same constant. The linear bucket scan
  (`middleware.py:80-83`) is also not a perf concern — 11 comparisons per request, below
  measurement noise, and faster than `bisect` at this size. Bucket `le` semantics verified
  correct (0.005 → bucket 0, 0.0050001 → bucket 1, 0.5 → bucket 6, 11.0 and NaN → `+Inf`).
  The exception path was verified to record both a duration and a counter, with
  `X-Request-ID` present on the 500.
- **CR-318** — `middleware.py:25-31`: a 7-line paragraph justifies deliberately not unwinding two
  contextvars on the failure path. The decision is sound and the reason is real, but this is the
  shape the code-gen paragraph rule warns about; a one-line comment plus the story reference
  would carry the same information.

---

## Checks run

| Check | Result |
|---|---|
| `uv run pytest -q` at HEAD | 104 passed |
| `uv run mypy src/` at HEAD and with the CR-310 fix | clean, 12 files |
| Mutant A — `_escape_label` → identity | **104 passed** (escaping unguarded) |
| Mutant B — buckets non-cumulative | 1 failed (correctly caught) |
| Mutant C — `route_label` → raw path | 4 failed (correctly caught) |
| Mutant D — proper `Token` typing | mypy clean, 104 passed |
| Envelope headers, 8 paths, live requests | `Allow` / `WWW-Authenticate` / `Retry-After` all present |
| `money.ts` regex timing, 7 sizes + per-sink isolation | quadratic, cost isolated to line 78 |
| Real uvicorn + raw sockets, `httptools` vs `h11` | method label bounded only by the parser |
| Method-cardinality flood, h11, 3000 tokens | 2998+2998 series, 3.55 MB body, ~2.5 MB retained |
| uvicorn access-log ordering, in-process replay | `request_id` bound, not empty |
| Test isolation, 3 orderings | no order dependence at HEAD |
| `git diff -- backend/src frontend/src` after all mutations | empty (restored) |

Files, function lengths and typing were checked mechanically: largest changed source file is
`backend/src/config/logging.py` at 251 lines (under the 300 limit, over the 200 warning
threshold); no changed function exceeds 30 lines; the only typing escapes in changed source are
`serializers.py:50` (`Any`, required by Pydantic's `__get_pydantic_core_schema__` protocol —
acceptable), `routes.py:59` (see CR-309) and `logging.py:91` (see CR-310).
