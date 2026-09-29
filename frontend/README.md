# I4C // Predictive Cash-Out Intelligence — Command Center UI

Static single-page frontend wired directly to the FastAPI backend. No build step.

## Quick start

Fastest path (pre-seeded, geospatially rich demo dataset):

Terminal A — backend (from `backend/`):

```bash
DATABASE_URL=sqlite+aiosqlite:///./var/cybercrime.db \
  /home/madhav/Documents/cybercrime/.venv/bin/python -m uvicorn app.main:app --port 8000
```

Terminal B — frontend (from `frontend/`):

```bash
python3 -m http.server 3000
```

Then open **http://localhost:3000** and sign in as the demo admin
(`demoadmin@example.com` / `DemoAdmin!Passw0rd`).

### Reset / from scratch

To rebuild the datastore from seed instead of using the shipped demo DB:

```bash
DATABASE_URL=sqlite+aiosqlite:///./var/cybercrime.db \
  SEED_ADMIN_EMAIL=admin@example.com \
  SEED_ADMIN_PASSWORD='Adminp@ssw0rd!1' \
  /home/madhav/Documents/cybercrime/.venv/bin/python -m scripts.seed --demo
```

The seeded base set is intentionally sparse (a few cases, one ATM grid);
the shipped `var/cybercrime.db` additionally contains a 12-ATM corridor across
Delhi NCR/Lucknow/Mumbai/Bengaluru/Hyderabad/Patna/Jaipur/Chandigarh/Kolkata,
a geo-tagged caseload, recorded cash-outs (drives the hotspot clusters), and
recorded prediction outcomes (drives hit-precision), so the Command Center
opens already populated.

## How the wiring works

- `app.js` reads `http://<page-host>:8000/api/v1` by default. To point at a
  different API set `localStorage.cci.api` (e.g. in devtools) and reload.
- The backend's default CORS allow list includes `http://localhost:3000` and
  `http://localhost:5173`. If you serve the UI on another origin, set
  `CORS_ORIGINS` (comma separated) when launching the API, e.g.
  `CORS_ORIGINS=http://localhost:3000,http://192.168.1.10:3000`.

## What renders

| View                  | Real data source (backend API)                                            |
| --------------------- | ------------------------------------------------------------------------- |
| Command Center        | `/analytics/overview`, `/analytics/hotspots`, `/analytics/geojson`, `/cases`, `/alerts`, `/analytics/risk-distribution`, `/analytics/cases-over-time` |
| Investigations        | `/cases`, `/cases/stats`; register cases via `POST /cases`                |
| Case Investigation    | `/cases/{id}`, `/cases/{id}/timeline`, `/cases/{id}/predictions`, `/cases/{id}/predictions/latest-locations`, `/entities/cases/{id}/network`, `/transactions/cases/{id}`, `/analytics/risk-history` |
| Intervention Simulator| `/models`, `POST /cases/{id}/simulate`, `/cases/{id}/interventions`, `/analytics/outcomes-summary`, `/analytics/overview` |
| Audit Log             | `/audit`, `/audit/verify`                                                 |

Every figure on screen is computed from these responses. Where the API has no
value yet (e.g. hit precision before any predictions) the UI shows a neutral
`—`/`AWAITING DATA` instead of inventing numbers.

## Actions that write to the chain

- New case registration -> audit + case chain
- Status transition, add event/note -> case timeline + audit chain (SHA-256 hash
  chained server side)
- Run prediction -> background pipeline + prediction records + alert creation
- Ack alert -> alert lifecycle + audit
- Simulate -> intervention record; **EXECUTE INTERVENTION** logs
  `INTERVENTION_EXECUTED` on the case timeline and audit chain

## Tips

- The dashboard polls every 12s; the case workspace refreshes its live panels on
  the same cadence.
- Tag/encode hotspots render onto an SVG tactical grid projected from real
  latitudes/longitudes; if nothing is deployed yet the grid shows a
  "no hotspots" state.
- `data_source` of the newest case is echoed in the left rail ("DATA: …") so you
  can see at a glance whether you are looking at synthetic/demo/operational load.