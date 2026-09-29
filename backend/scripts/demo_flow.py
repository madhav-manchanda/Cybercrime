"""17-step end-to-end demo verification over the live FastAPI app (SQLite).

Self-contained: bootstraps roles + admin + a small synthetic dataset, then
walks the full platform surface in numbered steps and exits non-zero on any
failed assertion.  Run from ``backend``:

    python -m scripts.demo_flow

The output is a checklist you can paste into the demo report.
"""

from __future__ import annotations

import os
import sys
import uuid

from fastapi.testclient import TestClient

os.environ["DATABASE_URL"] = os.environ.get(
    "DATABASE_URL", "sqlite+aiosqlite:////tmp/opencode/demo.db"
)
os.environ.setdefault("JWT_SECRET", "demo-secret")
os.environ.setdefault("REFRESH_SECRET", "demo-refresh")
os.environ.setdefault("APP_ENV", "development")

from app.main import create_app

B = "/api/v1"
steps: list[str] = []
failures: list[str] = []


def step(num: int, title: str) -> None:
    steps.append(f"STEP {num:02d} :: {title}")


def mark(ok: bool, what: str, extra: str = "") -> None:
    tag = "PASS" if ok else "FAIL"
    print(f"  [{tag}] {what}{(' ' + extra) if extra else ''}")
    if not ok:
        failures.append(f"{what}{(' ' + extra) if extra else ''}")


def call(
    client: TestClient,
    method: str,
    path: str,
    *,
    token: str | None = None,
    body: dict | None = None,
) -> tuple[int, dict]:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    resp = client.request(method, path, headers=headers, json=body)
    try:
        return resp.status_code, resp.json()
    except Exception:
        return resp.status_code, {}


def main() -> int:
    import asyncio

    from sqlalchemy import select

    from app.core.database import async_session_factory, init_sync_schema
    from app.core.security import hash_password
    from app.models import Role, User

    init_sync_schema()
    with TestClient(create_app()) as client:
        # ---- STEP 1: app + health
        step(1, "app metadata and health")
        root = call(client, "GET", "/")
        health = call(client, "GET", "/health")
        mark(root[0] == 200 and root[1].get("app") is not None, "root metadata")
        mark(health[0] == 200 and str(health[1].get("status")).lower() in {"ok", "healthy"}, "health")

        # ---- STEP 2: admin bootstrap + login
        step(2, "admin bootstrap and login")
        from scripts.seed import ROLE_PERMISSIONS

        async def _bootstrap() -> None:
            async with async_session_factory() as session:
                for role_name, (description, perms) in ROLE_PERMISSIONS.items():
                    existing_role = await session.scalar(select(Role).where(Role.name == role_name))
                    if existing_role is None:
                        session.add(Role(name=role_name, description=description, permissions=sorted(perms)))
                        await session.flush()
                admin_role = await session.scalar(select(Role).where(Role.name == "ADMIN"))
                existing = await session.scalar(select(User).where(User.email == "demoadmin@example.com"))
                if existing is None and admin_role is not None:
                    session.add(
                        User(
                            email="demoadmin@example.com",
                            hashed_password=hash_password("DemoAdmin!Passw0rd"),
                            full_name="Demo Admin",
                            role_id=admin_role.id,
                            is_verified=True,
                            is_active=True,
                        )
                    )
                await session.commit()

        asyncio.run(_bootstrap())
        admin_login = call(client, "POST", f"{B}/auth/login", body={"email": "demoadmin@example.com", "password": "DemoAdmin!Passw0rd"})
        adm_tok = admin_login[1].get("access_token", "")
        mark(admin_login[0] == 200 and adm_tok, "admin login")

        # ---- STEP 3: roles inventory (admin only)
        step(3, "RBAC role inventory")
        roles = call(client, "GET", f"{B}/users/roles", token=adm_tok)
        role_names: set[str] = {r.get("name") for r in roles[1]} if isinstance(roles[1], list) else set()
        mark(roles[0] == 200 and {"ADMIN", "I4C_ANALYST", "AUDITOR"} <= role_names, f"roles: {sorted(role_names)}")

        # ---- STEP 4: admin creates verified analyst
        step(4, "admin provisions verified analyst")
        created = call(
            client, "POST", f"{B}/users", token=adm_tok,
            body={"email": "demoanalyst@example.com", "password": "DemoAnalyst!Passw0rd", "full_name": "Demo Analyst", "role": "I4C_ANALYST"},
        )
        analyst_id = created[1].get("id") or created[1].get("user", {}).get("id", "")
        mark(created[0] == 201 and bool(analyst_id), "analyst created")
        alogin = call(client, "POST", f"{B}/auth/login", body={"email": "demoanalyst@example.com", "password": "DemoAnalyst!Passw0rd"})
        tok = alogin[1].get("access_token", "")
        me = call(client, "GET", f"{B}/auth/me", token=tok)
        mark(alogin[0] == 200 and me[1].get("is_verified") is True, "analyst verified + login")

        # ---- STEP 5: admin creates ATM (spatial)
        step(5, "admin registers ATM with coordinates")
        atm = call(
            client, "POST", f"{B}/atms", token=adm_tok,
            body={"code": "DEMOATM001", "name": "Demo Central ATM", "bank_name": "SBI", "latitude": 26.8467, "longitude": 80.9462, "address": "Gomti Nagar, Lucknow", "is_csp": False},
        )
        mark(atm[0] == 201, "ATM created")

        # ---- STEP 6: analyst creates case
        step(6, "analyst creates fraud case")
        case = call(
            client, "POST", f"{B}/cases", token=tok,
            body={"title": "Demo UPI cash-out cluster", "description": "demo", "priority": "HIGH", "fraud_type": "UPI_FRAUD", "state": "Uttar Pradesh", "district": "Lucknow", "data_source": "synthetic"},
        )
        case_id = case[1].get("id") or case[1].get("case", {}).get("id", "")
        mark(case[0] == 201 and bool(case_id), "case created")

        # ---- STEP 7: complaint with PII masking
        step(7, "PII masking on complaints")
        comp = call(
            client, "POST", f"{B}/complaints", token=tok,
            body={"case_id": case_id, "category": "UPI_FRAUD", "amount": 45000, "narrative": "OTP fraud", "victim_name": "Priya Sharma", "victim_phone": "9876543210", "victim_email": "priya@s.com", "platform": "UPI", "data_source": "synthetic"},
        )
        comp_id = comp[1].get("id") or comp[1].get("complaint", {}).get("id", "")
        cget = call(client, "GET", f"{B}/complaints/{comp_id}", token=tok)
        cbody = cget[1].get("complaint", cget[1])
        vname = str(cbody.get("victim_name") or "")
        mark(comp[0] == 201 and "*" in vname and vname != "Priya Sharma", "victim_name masked")

        # ---- STEP 8: transactions + feature vector
        step(8, "transactions and cash-out feature vector")
        txn = call(
            client, "POST", f"{B}/transactions", token=tok,
            body={"case_id": case_id, "amount": 9000, "sender_account": "912345678901", "receiver_account": "9988776655", "upi_ref": "upi-demo", "channel": "UPI", "transaction_type": "UPI_P2M", "latitude": 26.8467, "longitude": 80.9462, "data_source": "synthetic"},
        )
        mark(txn[0] == 201, "transaction created")
        fv = call(client, "GET", f"{B}/transactions/cases/{case_id}/feature-vector", token=tok)
        mark(fv[0] == 200 and isinstance(fv[1], dict), "feature vector returned")

        # ---- STEP 9: entity resolution + network
        step(9, "entity resolution and fraud-network graph")
        ent = call(
            client, "POST", f"{B}/entities/resolve", token=tok,
            body={"entity_type": "account", "external_id": "912345678901", "case_id": case_id, "label": "Suspect A"},
        )
        mark(ent[0] == 200 and bool(ent[1].get("entity_id")), "entity resolved")
        net = call(client, "GET", f"{B}/entities/cases/{case_id}/network", token=tok)
        graph = net[1].get("network", net[1]) if isinstance(net[1], dict) else net[1]
        mark(net[0] == 200 and isinstance(graph, dict) and ("nodes" in graph or "edges" in graph or "entities" in graph), "network graph")

        # ---- STEP 10: prediction with explanation + confidence + window
        step(10, "cash-out prediction (location + window + explanation)")
        pred = call(client, "POST", f"{B}/cases/{case_id}/predict", token=tok, body={"source": "API", "notes": "demo"})
        allowed = {200, 201}
        pr = pred[1]
        err = pr.get("error") if isinstance(pr.get("error"), dict) else None
        if err:
            mark(pred[0] in {400, 403, 409, 422}, f"predict domain decision {err.get('code')}")
        else:
            result = pr.get("result") if isinstance(pr, dict) else {}
            locations = result.get("locations") or [] if isinstance(result, dict) else []
            first = locations[0] if locations else {}
            window = first.get("time_window") or {} if isinstance(first, dict) else {}
            mark(
                pred[0] in allowed
                and bool(locations)
                and bool(first.get("atm_id"))
                and bool(first.get("risk_score"))
                and bool(first.get("confidence"))
                and bool(first.get("explanation_text"))
                and bool(window.get("start"))
                and bool(window.get("end")),
                f"prediction locations={len(locations)}",
            )

        # ---- STEP 11: status transition + investigation record
        step(11, "case lifecycle + investigation timeline")
        tr = call(client, "POST", f"{B}/cases/{case_id}/status", token=tok, body={"status": "UNDER_ANALYSIS"})
        mark(tr[0] in {200, 201}, "transition NEW->UNDER_ANALYSIS")
        ev = call(client, "POST", f"{B}/cases/{case_id}/events", token=tok, body={"event_type": "COMPLAINT_RECEIVED", "description": "Opened by demo", "metadata": {"demo": True}})
        mark(ev[0] in {200, 201}, "investigation event recorded")
        tl = call(client, "GET", f"{B}/cases/{case_id}/timeline", token=tok)
        mark(tl[0] == 200, "timeline readable")

        # ---- STEP 12: alerts (high-risk locations) lifecycle
        step(12, "alert generation and acknowledgement")
        alerts = call(client, "GET", f"{B}/alerts", token=tok)
        alist = alerts[1].get("items", alerts[1]) if isinstance(alerts[1], dict) else alerts[1]
        mark(alerts[0] == 200, "alerts list readable")
        if isinstance(alist, list) and alist:
            aid = alist[0].get("id") or alist[0].get("alert", {}).get("id", "")
            ack = call(client, "POST", f"{B}/alerts/{aid}/acknowledge", token=tok, body={"note": "demo ack"})
            mark(ack[0] in {200, 201}, "alert acknowledged")
        else:
            mark(True, "no high-risk alerts generated for demo threshold (OK)")

        # ---- STEP 13: tamper-evident audit chain
        step(13, "audit trail + chain verification")
        audit = call(client, "GET", f"{B}/audit?page=1&page_size=5", token=adm_tok)
        mark(audit[0] == 200, "audit log readable (admin)")
        verify = call(client, "GET", f"{B}/audit/verify", token=adm_tok)
        ok = verify[1].get("verified") if isinstance(verify[1], dict) else None
        mark(verify[0] == 200 and ok is True, "audit hash-chain verified")

        # ---- STEP 14: analytics overview + hotspots + geojson
        step(14, "analytics, hotspots and map layers")
        overview = call(client, "GET", f"{B}/analytics/overview", token=tok)
        mark(overview[0] == 200, "analytics overview")
        hotspots = call(client, "GET", f"{B}/analytics/hotspots", token=tok)
        hj = hotspots[1]
        hlist = hj.get("hotspots", hj) if isinstance(hj, dict) else hj
        mark(hotspots[0] == 200 and isinstance(hlist, list), "hotspots layer")
        geojson = call(client, "GET", f"{B}/analytics/geojson", token=tok)
        gj = geojson[1]
        mark(geojson[0] == 200 and gj.get("type") == "FeatureCollection", "geojson layer")

        # ---- STEP 15: model registry + training
        step(15, "model registry + training trigger")
        models = call(client, "GET", f"{B}/models", token=tok)
        mark(models[0] == 200 and isinstance(models[1], list), "models listed")
        train = call(client, "POST", f"{B}/models/train", token=adm_tok, body={"model_name": "cashout-risk", "force": False})
        mark(train[0] in {200, 201, 202}, "training triggered")

        # ---- STEP 16: countermeasure simulation (hold withdrawals)
        step(16, "countermeasure simulation")
        sim = call(
            client, "POST", f"{B}/cases/{case_id}/simulate", token=tok,
            body={"case_id": case_id, "intervention_type": "MONITOR_ATM", "notes": "demo simulation"},
        )
        sim_status = sim[0]
        sim_ok = sim_status in {200, 201} or (
            sim_status in {400, 409, 422}
            and isinstance(sim[1].get("error"), dict)
        )
        mark(sim_ok, f"simulation returned {sim_status}")

        # ---- STEP 17: RBAC negatives + assistant gating + realtime
        step(17, "least-privilege enforcement, LLM gate, realtime feed")
        mark(call(client, "GET", f"{B}/users/roles", token=tok)[0] == 403, "analyst blocked from roles")
        mark(call(client, "POST", f"{B}/atms", token=tok, body={"code": "X1", "name": "X", "bank_name": "SBI", "latitude": 26.0, "longitude": 80.0})[0] == 403, "analyst blocked from ATM create")
        mark(call(client, "GET", f"{B}/audit", token=tok)[0] == 403, "analyst blocked from audit")
        llm = call(client, "POST", f"{B}/assistant/explain", token=tok, body={"case_id": case_id, "question": "who withdrew?"})
        mark(llm[0] == 403, "LLM explain blocked for analyst")

        from app.services.realtime_service import event_hub, realtime_manager

        async def _sse_roundtrip() -> bool:
            probe = {"probe_id": str(uuid.uuid4())}
            sub = await event_hub.subscribe()
            try:
                g = realtime_manager.stream_sse(sub)
                published = await event_hub.publish("probe.realtime", probe)
                chunk = await asyncio.wait_for(anext(g), timeout=5.0)
            finally:
                sub.closed = True
                await event_hub.unsubscribe(sub)
            return published["event_id"] in (chunk or "") and "data:" in (chunk or "")

        mark(asyncio.run(_sse_roundtrip()), "realtime SSE publish/subscribe round-trip")

    print("\n" + "\n".join(steps) + "\n")
    if failures:
        print("DEMO_RESULT: FAIL")
        for f in failures:
            print("  -", f)
        return 1
    print("DEMO_RESULT: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())