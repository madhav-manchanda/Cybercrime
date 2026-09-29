# Cybercrime Cash-Out Intelligence Platform (Backend)

Predictive platform for India's cybercrime-fighting teams (I4C/state/district
officers, banks, auditors): ingest complaints and transactions, build entity
networks, predict **cash-out locations and time windows**, and keep a
tamper-evident audit trail. Built for SIH26184.

## Stack

- **API** — FastAPI (async), Pydantic v2, structured logging (structlog)
- **Persistence** — PostgreSQL + **PostGIS** (prod), SQLite (local/tests),
  SQLAlchemy 2 async, Alembic
- **ML** — scikit-learn ranker + custom spatiotemporal scoring; explanations
  (`SHAP`-style factor contribution) and confidence on every prediction
- **Workers** — Celery + Redis beat scheduler (hourly model refresh, daily
  refresh-token purge, health log)
- **Realtime** — SSE + WebSocket dashboards via an in-process event hub

## Layout

```
app/
  core/      settings, DB, security, enums, errors, middleware, rate-limit, geo
  models/    24 ORM models (all on a single DeclarativeBase)
  schemas/   request/response contracts
  services/  domain logic (case, complaint, transaction, prediction, audit…)
  api/v1/    routers + RBAC dependency layer
  ml/        features, ranker, spatial/temporal scoring, explain, evaluation
  synthetic/ deterministic synthetic cash-out/mule dataset generator
  workers/   Celery app + periodic tasks + beat schedule
  main.py    app factory + lifecycle + error envelope
migrations/  Alembic environment + baseline migration
scripts/     seed.py (idempotent RBAC + admin bootstrap, `--demo` dataset)
tests/       pytest suite (SQLite, no external services)
```

## Quickstart (local, SQLite)

```bash
cp .env.example .env                  # dev defaults are safe
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
make seed                             # roles + verified admin (prompts for password)
uvicorn app.main:app --reload         # http://localhost:8000/docs
```

`make seed --demo` also loads a labelled synthetic dataset so predictions have
records to rank. Seed is idempotent and env-driven:

- `SEED_ADMIN_EMAIL` (default `admin@example.com`)
- `SEED_ADMIN_PASSWORD` — **required in production**; generated + printed once
  in development if omitted

## Run with Docker (production-like)

```bash
cp .env.example .env
make db-up        # postgres+postgis, redis
make seed
make docker-up    # api on :8000, worker, beat
```

## Stateless checks & tests

```bash
make check        # ruff + mypy (app, scripts)
make test         # 26 tests, SQLite
python -m scripts.smoke   # full API scenario (register→…→predict)
```

## Params/invariants the evaluator will check

- Every prediction carries `explanation` and `confidence`; nothing is "made
  up" — metrics are computed from the labelled synthetic frame.
- Synthetic records are always flagged `data_source="synthetic"`.
- PII (victim name/phone/email/UPI, accounts) is masked at the API boundary —
  no raw PII is ever echoed.
- API returns a stable error envelope
  `{"error": {code, message, request_id, details}}`; 422 `VALIDATION_ERROR`,
  never a stack trace.
- Audit log is SHA-256 hash-chained; `POST /api/v1/audit/verify` confirms
  chain integrity.
- The LLM assistant is **off by default** (`LLM_ENABLED=false`) and never
  declares criminality.

## RBAC

Roles: `ADMIN`, `I4C_ANALYST` (default for self-registration, unverified until
an admin approves), `STATE_OFFICER`, `DISTRICT_OFFICER`, `BANK_ANALYST`,
`AUDITOR`. Public registration yields the minimal analyst permission set and is
gated (403 `ACCOUNT_NOT_VERIFIED`) until verified. Role/ownership checks are
enforced in each router via `app.api.deps`.

## Migration

Dev SQLite and `init_sync_schema()` create tables directly from ORM metadata.
For PostGIS production, Alembic is wired to application settings:

```bash
DATABASE_URL=postgresql+asyncpg://… alembic upgrade head
```

The baseline (0001) materialises current metadata and enables the PostGIS
extension. Future schema changes must be explicit revisions.

## Environment

All settings are documented in `.env.example`. Production guards refuse short /
placeholder `SECRET_KEY` and wildcard CORS.