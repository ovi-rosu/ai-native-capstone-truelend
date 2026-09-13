# Folder structure

Layer directory names are **singular** and match the six configured layers
(`types, config, repository, service, api, ui`) so the one-way dependency test in
`E15-S2-AC2` resolves paths. `backend/CLAUDE.md` says `src/services/`; that
wording is the outlier and is corrected there, not here. Inside Repository,
Service and API, one package per bounded context (D-I).

```
ai-native-capstone-truelend/
├── backend/                       Python 3.12 / FastAPI / uv
│   ├── src/
│   │   ├── types/                 layer 1 — domain types, enums, typed errors; imports nothing
│   │   ├── config/                layer 2 — settings, DPD boundaries + classifier, logging, DB engine
│   │   ├── repository/            layer 3 — SQLAlchemy access; insert-only where D-E says so
│   │   │   ├── policy/            product, policy_version
│   │   │   ├── origination/       application, checklist_item, decision_record
│   │   │   ├── servicing/         loan, repayment_schedule + schedule_installment, disbursement, repayment_posting
│   │   │   ├── delinquency/       portfolio aggregation reads
│   │   │   └── identity/          app_user, audit_event
│   │   ├── service/               layer 4 — business rules, one package per context
│   │   │   ├── policy/            catalog, pinned-version accessor, version publisher
│   │   │   ├── origination/       intake, scoring stub, decision evaluator, override, document verification
│   │   │   ├── servicing/         EMI, schedule generation, installment ladder, projections, disbursement, repayment
│   │   │   ├── delinquency/       recalculation, end-of-day run, portfolio summary
│   │   │   └── identity/          authentication, audit append
│   │   └── api/                   layer 5 — routers, require_roles, middleware, money serializer, error mapping
│   │       ├── identity/          /auth/*, /audit-entries
│   │       ├── policy/            /products, /products/{code}/policy-versions
│   │       ├── origination/       /applications*, /documents/queue
│   │       ├── servicing/         /loans*, disbursement, repayments
│   │       ├── delinquency/       /operations/end-of-day, /dashboard
│   │       └── platform/          /health, /metrics
│   ├── migrations/                Alembic; append-only, linted for 0 destructive statements
│   │   └── versions/              one file per migration, including policy seed migrations
│   └── tests/
│       ├── architecture/          invariant registry, layer test, immutability scans, migration lint
│       ├── slo/                   read-heavy endpoint registry + in-process load harness
│       ├── unit/                  pure-function tests (EMI, residual, classifier, scoring stub)
│       └── integration/           API-level tests against a real Postgres
├── frontend/                      TypeScript 5.x / React + Vite / npm
│   ├── src/
│   │   ├── types/                 layer 1 — Money over a decimal library, API types, enums
│   │   ├── config/                layer 2 — environment, role-to-landing-surface map
│   │   ├── api/                   layer 5 — typed HTTP client per resource; components never call fetch
│   │   └── ui/                    layer 6 — app shell and router
│   │       ├── components/        one component per file (MoneyText, BucketBadge, ReasonCodeList, StatusPill)
│   │       └── pages/             one screen per file, one per UI story
│   └── tests/
│       ├── a11y/                  axe-core scan + keyboard traversal over the screen registry
│       └── unit/                  component and money-module tests
├── specs/                         planning artifacts (this design, stories, BRD, decisions)
│   └── design/
│       └── mockups/               one self-contained HTML mockup per screen-bearing UI story
├── docker-compose.yml             exactly three services: postgres, backend, frontend
├── Dockerfile.backend
├── Dockerfile.frontend
└── init.sh                        one-command bootstrap
```

Notes that matter to the layer gate:

- `frontend/src/ui/components/` sits under the `ui` layer rather than at
  `src/components/` (the `frontend/CLAUDE.md` wording) so every frontend file is
  inside a recognised layer directory and none is silently unchecked.
- `backend/src/repository/models.py` holds the SQLAlchemy table definitions and
  lives in the Repository layer only. No Service or API module imports it; they
  take and return the Types-layer objects.
- `backend/tests/architecture/` is the home of every invariant test `E16-S1`
  registers. A registered invariant without a test there fails the suite.
