# Cybercrime Cash-Out Intelligence Platform — SIH26184

> Predictive platform for I4C / state / district cybercrime units, banks and auditors: ingest complaints & transactions, link entities into a fraud network, **predict where and when mule cash-outs will happen**, and keep a tamper-evident audit trail. Every number is computed — nothing is fabricated.

**SIH Problem:** Build an AI/ML system that predicts cybercrime cash-out locations and time windows from complaint and transaction data to enable pre-emptive intervention.

---

## 1. Demo (fastest path)

Shipped demo DB `backend/var/cybercrime.db` is geospatially rich (12-ATM corridor, 15 geo-tagged cases, 29 predicted locations, 10 hotspot cells). No seeding needed.

**Terminal A — Backend** (`backend/`):

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
DATABASE_URL=sqlite+aiosqlite:///./var/cybercrime.db \
  .venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
# → http://127.0.0.1:8000/docs  (OpenAPI)
```

**Terminal B — Frontend** (`frontend/` — no build step):

```bash
python3 -m http.server 3000
# → http://localhost:3000  (also http://127.0.0.1:3000)
```

**Login:**

| User | Email | Password | Role |
|------|-------|----------|------|
| Demo Admin | `demoadmin@example.com` | `DemoAdmin!Passw0rd` | ADMIN (all permissions) |
| Demo Analyst | `demoanalyst@example.com` | `DemoAnalyst!Passw0rd` | I4C Analyst |

Backend CORS defaults allow both `http://localhost:3000` and `http://127.0.0.1:3000` (and `:5173`). For another origin set `CORS_ORIGINS='["http://…"]'` (JSON array) when launching the API.

### Reset from scratch

```bash
# Rebuild a sparse DB from seed (idempotent)
DATABASE_URL=sqlite+aiosqlite:///./var/cybercrime.db \
  SEED_ADMIN_EMAIL=admin@example.com \
  SEED_ADMIN_PASSWORD='Adminp@ssw0rd!1' \
  .venv/bin/python -m scripts.seed --demo
```

The seed creates RBAC roles, a verified admin, and a small labelled synthetic dataset. The shipped DB is the seed **plus** enrichment: 12 ATMs (Delhi NCR, Lucknow, Mumbai, Bengaluru, Hyderabad, Patna, Jaipur, Chandigarh, Kolkata), geo-tagged cases, recorded `ATM_WITHDRAWAL` cash-outs (drives hotspot clusters), and recorded `PREDICTION_CONFIRMED` outcomes (drives hit-precision).

---

## 2. Architecture

```
                ┌─────────────────────┐
                │  Command Center UI  │  frontend/  (static SPA, Tailwind CDN)
                │  localhost:3000     │  app.js → http://<host>:8000/api/v1
                └──────────┬──────────┘
                           │  fetch + JWT (localStorage cci.token)
                           ▼
┌─────────────────────────────────────────────────────────┐
│  FastAPI (async)  app/main.py  —  /api/v1/*             │
│  Routers: auth, cases, complaints, transactions,        │
│  predictions, atms, alerts, analytics, outcomes,        │
│  audit, entities, investigations, realtime (SSE/WS)     │
│  RBAC via app/api/deps.py  ·  Rate-limit  ·  Audit     │
└──────────────┬──────────────────────┬───────────────────┘
               │                      │
        ┌──────▼──────┐        ┌──────▼──────┐
        │  Services   │        │  ML Stack   │  app/ml/
        │  domain     │        │  features, ranker, spatial/temporal,
        │  logic      │◄──────►│  explain, evaluation, registry
        └──────┬──────┘        └──────┬──────┘
               │                      │
        ┌──────▼──────────────────────▼──────┐
        │  Persistence                      │
        │  SQLAlchemy 2 async ·  24 models  │
        │  SQLite (local/tests) /           │
        │  PostgreSQL + PostGIS (prod)      │
        │  Alembic migrations               │
        └──────┬────────────────────────────┘
               │
        ┌──────▼──────┐
        │  Workers    │  Celery + Redis + beat
        │  hourly model refresh, token purge
        └─────────────┘
```

**Request lifecycle:** `RequestIdMiddleware` → `SecurityHeadersMiddleware` → `CORSMiddleware` → `RateLimit` → `RBAC` → `Service` → `Audit (SHA-256 hash-chained)` → `EventHub (SSE/WS)`.

---

## 3. Tech Stack

| Layer | Choice | Why |
|-------|--------|-----|
| API | FastAPI (async), Pydantic v2, structlog | Async, typed, fast OpenAPI |
| DB | SQLAlchemy 2 async, Alembic, SQLite (dev) / Postgres+PostGIS (prod) | Async ORM, spatial queries |
| ML | scikit-learn ranker + custom spatiotemporal scoring, SHAP-style factor contributions | Explainable, location+time aware |
| Workers | Celery + Redis, beat schedule | Hourly retrain, daily purge |
| Realtime | In-process EventHub → SSE/WS | No extra infra for demo |
| Frontend | Static SPA (`index.html` + `app.js` + `styles.css`), Tailwind CDN | No build, matches mockups |

Python 3.12+, Node not required.

---

## 4. What the UI Shows (and where data comes from)

| View | What renders | Real API source |
|------|--------------|-----------------|
| **Command Center** | 5 telemetry cards, tactical SVG map (hotspots / cases / forecast nodes), incident & signal streams, risk distribution, cases-over-time, alert center | `GET /analytics/overview`, `/hotspots`, `/geojson`, `/cases`, `/alerts`, `/risk-distribution`, `/cases-over-time` |
| **Investigations** | Case table (search + status/fraud filters), stats chips, register case modal | `GET /cases`, `/cases/stats`, `POST /cases` |
| **Case Workspace** | Golden-hour countdown, tactical forecast map (top predicted ATMs), “why this location” contributors, top ATMs, network graph (SVG), metadata ledger, risk signals, audit timeline, transaction ledger | `GET /cases/{id}`, `/predictions/latest-locations`, `/predictions`, `/timeline`, `/entities/cases/{id}/network`, `/transactions/cases/{id}`, `/analytics/risk-history` |
| **Intervention Simulator** | Tactic picker (e.g. ATM surveillance, account freeze), simulate → baseline vs simulated exposure + degradation curve + assumptions, dispatch | `GET /models`, `POST /cases/{id}/simulate`, `GET /cases/{id}/interventions`, `/analytics/outcomes-summary` |
| **Audit Log** | Hash-chained table, chain verify, link preview | `GET /audit`, `GET /audit/verify` |

Every figure is computed from responses. Missing values render `—`/`AWAITING DATA` — never invented.

**Writes that are hash-chained:** new case, status transition, add event/note, run prediction, ack alert, simulate, `EXECUTE INTERVENTION` (`INTERVENTION_EXECUTED` on case timeline).

Frontend auto-detects API base: `http://<page-host>:8000/api/v1` (override via `localStorage.cci.api`). Dashboard polls every 12s; forecast layer refreshes every 60s (6 open cases × top-5).

---

## 5. Project Structure

```
backend/
  app/
    core/       settings, DB, security, enums, errors, middleware, rate-limit, geo, redis, logging
    models/     24 ORM models on single DeclarativeBase (case, complaint, transaction, atm, cash_withdrawal, prediction, outcome, alert, audit, entity…)
    schemas/    request/response contracts
    services/   domain logic (case_service, prediction_service, risk_service, analytics_service, outcome_service…)
    api/v1/     routers + RBAC (auth, cases, predictions, atms, analytics, outcomes, audit…)
    ml/         features, ranker, spatial/temporal, explain, evaluation, train, registry
    synthetic/  deterministic synthetic cash-out/mule dataset generator
    workers/    Celery app + beat schedule
    main.py     FastAPI factory + lifecycle + error envelope ({"error":{code,message,request_id}})
  migrations/   Alembic (PostGIS baseline 0001)
  scripts/      seed.py (idempotent RBAC + admin + --demo), smoke.py
  tests/        pytest (26 tests, SQLite, no external services)
  var/
    cybercrime.db   ← shipped enriched demo DB
    ml/             ← trained artifacts
frontend/
  index.html    SPA shell + Tailwind CDN + design tokens
  styles.css    cards, map grid/scanner, tables, print
  app.js        API client (JWT in localStorage), router, 5 views, 12s poller, SVG maps
  README.md     wiring table + tips
stitch_aegis_cyber_predictive_cash_out_intelligence_platform/
  command_center_dashboard/, case_investigation_workspace/, intervention_simulator/, …
  (original design source)
```

---

## 6. Local Setup (SQLite, no Docker)

```bash
cd backend
cp .env.example .env          # dev defaults are safe
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Option A: use shipped demo DB (recommended)
DATABASE_URL=sqlite+aiosqlite:///./var/cybercrime.db \
  .venv/bin/python -m uvicorn app.main:app --reload

# Option B: rebuild from seed
make seed                     # prompts for admin password (or set SEED_ADMIN_PASSWORD)
# or
DATABASE_URL=sqlite+aiosqlite:///./var/cybercrime.db \
  .venv/bin/python -m scripts.seed --demo

# Checks
make check   # ruff + mypy
make test    # 26 tests, SQLite
.venv/bin/python -m scripts.smoke  # full API scenario: register → predict → …
```

Frontend needs no install:

```bash
cd frontend && python3 -m http.server 3000
```

---

## 7. Docker (production-like)

```bash
cd backend
cp .env.example .env
make db-up        # postgres+postgis + redis
make seed
make docker-up    # api :8000, worker, beat
# Alembic for Postgres (when needed):
DATABASE_URL=postgresql+asyncpg://cybercrime:cybercrime@localhost:5432/cybercrime \
  alembic upgrade head
```

---

## 8. API Surface (representative)

Auth: `POST /api/v1/auth/login`, `POST /auth/refresh`, `GET /auth/me`  
Cases: `POST /cases`, `GET /cases`, `GET /cases/{id}`, `PATCH /cases/{id}/status`, `POST /cases/{id}/events`, `GET /cases/{id}/timeline`, `GET /cases/stats`  
Predictions: `POST /cases/{id}/predict` (`{horizon:"H24", top_k:5}`), `GET /cases/{id}/predictions`, `GET /cases/{id}/predictions/latest-locations`, `GET /cases/{id}/predictions/{pid}`  
ATMs & Risk: `POST /atms`, `GET /atms`, `GET /atms/rank`, `GET /atms/{id}/risk`  
Transactions: `POST /transactions`, `GET /transactions/cases/{id}`, `GET /transactions/cases/{id}/feature-vector`  
Alerts: `GET /alerts`, `POST /alerts/{id}/acknowledge`  
Analytics: `GET /analytics/overview`, `/hotspots`, `/geojson`, `/risk-distribution`, `/cases-over-time`, `/risk-history`, `/outcomes-summary`  
Outcomes: `POST /cases/{id}/outcomes` (`{outcome_type:"PREDICTION_CONFIRMED"|"PARTIAL"|"INCORRECT"|"NO_CASHOUT"|"UNKNOWN", was_cashout, predicted_atm_id, actual_atm_id, predicted_time_start/end, actual_time, amount_withdrawn}`)  
Interventions: `POST /cases/{id}/simulate` (`{intervention_type, notes, prediction_id?}`), `GET /cases/{id}/interventions`  
Entities/Network: `GET /entities/cases/{id}/network`  
Audit: `GET /audit`, `GET /audit/verify`, `GET /audit/{id}`  
Realtime: `GET /realtime/stream` (SSE), `WS /realtime/ws`

All errors use a stable envelope: `{"error":{"code","message","request_id","details"}}` — `VALIDATION_ERROR` is 422, never a stack trace.

---

## 9. RBAC

Roles: `ADMIN`, `I4C_ANALYST` (default for self-registration, unverified until admin approves), `STATE_OFFICER`, `DISTRICT_OFFICER`, `BANK_ANALYST`, `AUDITOR`. Public registration yields minimal analyst perms and is gated (`403 ACCOUNT_NOT_VERIFIED`) until verified. Every router enforces via `app.api.deps.require_permission`.

---

## 10. ML Pipeline

- **Features:** `app/ml/features.py` builds per-ATM case proximity, temporal similarity, network proximity, hotspot intensity.
- **Ranker:** `rank_predict.py` + `train.py` (scikit-learn, negative sampling 6:1, top-k 10, 75km radius, 60 nearest ATMs per anchor).
- **Explain:** per-ATM `contributing_factors[]` with `factor, impact (-1..1), detail` and `confidence` (spread-based).
- **Registry:** `var/ml/` artifacts with `model_name, model_version, active` (`GET /models`).
- **Outcomes:** `POST /cases/{id}/outcomes` closes the loop; `prediction_accuracy` (hit-precision) is computed from `PREDICTION_CONFIRMED` outcomes.

---

## 11. Invariants Evaluators Check

- Every prediction carries `explanation` + `confidence`; metrics are computed from the labelled frame, not invented.
- Synthetic records flagged `data_source="synthetic"` (or `"demo"`).
- PII masked at the boundary: `victim_masked_phone/email/account`, `source_account_masked`; raw PII never echoed.
- Audit log is SHA-256 hash-chained; `GET /audit/verify` returns `{verified,total,first_hash,last_hash}`.
- LLM assistant is **off by default** (`LLM_ENABLED=false`) and never declares criminality.
- Rate limits: login 10/min, write 60/min, predict 12/min, synthetic 20/hr.

---

## 12. Troubleshooting

- **“Network error while fetching”** → CORS. Frontend uses `http://<host>:8000/api/v1`. Backend now allows `http://localhost:3000` **and** `http://127.0.0.1:3000` (and `:5173`). Use either URL consistently, or set `CORS_ORIGINS='["http://…"]'` (JSON array) when launching the API.
- **Login 401** → use demo creds above; or create an admin via `make seed` and approve the analyst in `GET /users` (admin only).
- **`MissingGreenlet` on /cases or /hotspots** → fixed via `selectinload` eager loads for `assigned_investigator`, `CashWithdrawal.atm`/`account_entity`. If you add a new relationship access in a service, add the corresponding `selectinload`.
- **`VALIDATION_ERROR` on `POST /transactions`** → `data_source` enum is lowercase: `"synthetic"|"demo"|"operational"`; `type` must be `"ATM_WITHDRAWAL"` for cash-outs; `CORS_ORIGINS` must be a JSON array string, not CSV.

---

## 13. License & Credits

SIH 2026 — Team SIH26184. Backend: FastAPI + SQLAlchemy + PostGIS + Celery + scikit-learn. Frontend: static SPA (Tailwind CDN). Design source in `stitch_aegis_cyber_predictive_cash_out_intelligence_platform/`.

---

## 14. Quick Reference

```bash
# Backend health
curl http://127.0.0.1:8000/docs
# Login
curl -X POST http://127.0.0.1:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"demoadmin@example.com","password":"DemoAdmin!Passw0rd"}'
# Overview (needs Authorization: Bearer <token>)
curl http://127.0.0.1:8000/api/v1/analytics/overview -H "Authorization: Bearer $TOKEN"
```
