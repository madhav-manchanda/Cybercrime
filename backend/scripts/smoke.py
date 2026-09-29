"""In-process API smoke flow executed on the FastAPI app (SQLite).

Exits non-zero on the first unexpected status.  Run from the backend dir:
    DATABASE_URL=sqlite+aiosqlite:///... python /tmp/smoke_api.py
"""

import json
import os
import sys

from fastapi.testclient import TestClient

os.environ["DATABASE_URL"] = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:////tmp/opencode/smoke.db")
os.environ.setdefault("JWT_SECRET", "smoke-secret")
os.environ.setdefault("REFRESH_SECRET", "smoke-refresh")
os.environ.setdefault("APP_ENV", "development")

from app.main import create_app

B = "/api/v1"
failures: list[str] = []


def check(name: str, method: str, path: str, *, expect: int, token: str | None = None, body: dict | None = None) -> dict:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    resp = client.request(method, path, headers=headers, json=body)
    try:
        payload = resp.json()
    except Exception:
        payload = {"raw": resp.text}
    if resp.status_code != expect:
        failures.append(f"{name}: got {resp.status_code} (want {expect}) -> {json.dumps(payload)[:300]}")
    return payload


with TestClient(create_app()) as client:
    # ---- identity
    reg = check("register", "POST", f"{B}/auth/register", expect=201, body={"email": "analyst@example.com", "password": "Passw0rd!xiA1", "full_name": "A Analyst"})
    user_id = reg.get("user", {}).get("id")
    login = check("login", "POST", f"{B}/auth/login", expect=200, body={"email": "analyst@example.com", "password": "Passw0rd!xiA1", "client_platform": "smoke"})
    tok = login.get("access_token")
    if not tok:
        failures.append("login: no access_token")
        tok = "INVALID"

    # emulate an ADMIN verifying the freshly registered analyst (real path: /users/{id}/verify)
    async def _verify():
        from sqlalchemy import select

        from app.core.database import async_session_factory
        from app.models import User
        async with async_session_factory() as session:
            u = await session.scalar(select(User).where(User.email == "analyst@example.com"))
            if u is not None:
                u.is_verified = True
            await session.commit()

    import asyncio

    asyncio.run(_verify())

    # bootstrap an ADMIN (role + user) so bank-side setup endpoints are reachable
    async def _seed_admin():
        from sqlalchemy import select

        from app.core.database import async_session_factory
        from app.core.enums import Permission, RoleName
        from app.core.security import hash_password
        from app.models import Role, User
        async with async_session_factory() as session:
            role = await session.scalar(select(Role).where(Role.name == RoleName.ADMIN))
            if role is None:
                role = Role(name=RoleName.ADMIN, description="Platform administrator", permissions=[p.value for p in Permission])
                session.add(role)
                await session.flush()
            admin = await session.scalar(select(User).where(User.email == "admin@example.com"))
            if admin is None:
                admin = User(email="admin@example.com", hashed_password=hash_password("Adminp@ssw0rd!1"), full_name="Platform Admin", role_id=role.id, is_verified=True, is_active=True)
                session.add(admin)
            await session.commit()

    asyncio.run(_seed_admin())

    admin_login = check("admin-login", "POST", f"{B}/auth/login", expect=200, body={"email": "admin@example.com", "password": "Adminp@ssw0rd!1"})
    adm_tok = admin_login.get("access_token") or "INVALID"

    atm = check("atm-create-admin", "POST", f"{B}/atms", expect=201, token=adm_tok, body={"code": "LKOHQ001", "name": "Hazratganj ATM", "bank_name": "State Bank of India", "latitude": 26.8453, "longitude": 80.9462, "address": "Hazratganj, Lucknow", "is_csp": False})
    atm_id = atm.get("id") or atm.get("atm", {}).get("id")

    me = check("me", "GET", f"{B}/auth/me", expect=200, token=tok)
    if me.get("email") != "analyst@example.com":
        failures.append(f"me: unexpected {me}")

    # ---- analyst RBAC restrictions
    check("roles-as-analyst", "GET", f"{B}/users/roles", expect=403, token=tok)
    check("atm-create-as-analyst", "POST", f"{B}/atms", expect=403, token=tok, body={"code": "X1", "name": "X", "bank_name": "SBI", "latitude": 26.0, "longitude": 80.0})
    check("model-list", "GET", f"{B}/models", expect=200, token=tok)
    check("audit-as-analyst", "GET", f"{B}/audit", expect=403, token=tok)

    # ---- case lifecycle
    case = check(
        "case-create", "POST", f"{B}/cases", expect=201,
        token=tok,
        body={"title": "UPI fraud cluster", "description": "smoke", "priority": "HIGH", "fraud_type": "UPI_FRAUD", "state": "Uttar Pradesh", "district": "Lucknow", "data_source": "synthetic"},
    )
    case_id = case.get("id") or case.get("case", {}).get("id")
    if not case_id:
        failures.append("case-create: no id")
        case_id = "00000000-0000-0000-0000-000000000000"
    check("cases-list", "GET", f"{B}/cases", expect=200, token=tok)
    check("cases-stats", "GET", f"{B}/cases/stats", expect=200, token=tok)
    check("cases-summary", "GET", f"{B}/cases/summary", expect=200, token=tok)
    check("case-get", "GET", f"{B}/cases/{case_id}", expect=200, token=tok)

    # ---- complaint masking
    comp = check(
        "complaint-create", "POST", f"{B}/complaints", expect=201,
        token=tok,
        body={"case_id": case_id, "category": "UPI_FRAUD", "amount": 45000, "narrative": "sent funds after OTP", "victim_name": "Priya Sharma", "victim_phone": "9876543210", "victim_email": "priya@example.com", "platform": "UPI", "data_source": "synthetic"},
    )
    comp_id = comp.get("id") or comp.get("complaint", {}).get("id")
    comp_get = check("complaint-get", "GET", f"{B}/complaints/{comp_id}", expect=200, token=tok)
    c = comp_get.get("complaint", comp_get)
    raw_name = "Priya Sharma"
    masked = c.get("victim_name")
    if not masked or "*" not in masked or masked == raw_name:
        failures.append(f"complaint victim_name not masked: {masked!r}")

    # ---- transaction + entity link (analyst allowed paths)
    txn = check("txn-create", "POST", f"{B}/transactions", expect=201, token=tok, body={"case_id": case_id, "amount": 9000, "sender_account": "912345678901", "receiver_account": "9988776655", "upi_ref": "upi-smoke-1", "channel": "UPI", "transaction_type": "UPI_P2M", "latitude": 26.84, "longitude": 80.95})
    txn_id = txn.get("id") or txn.get("transaction", {}).get("id")
    check("txn-get", "GET", f"{B}/transactions/{txn_id}", expect=200, token=tok)

    # ---- prediction (ATM exists nearby now)
    pred_body = {"source": "API", "notes": "smoke"}
    r = client.post(f"{B}/cases/{case_id}/predict", headers={"Authorization": f"Bearer {tok}"}, json=pred_body)
    if r.status_code not in (200, 201):
        payload = r.json()
        code = payload.get("error", {}).get("code", "")
        if code not in ("PREDICTION_UNAVAILABLE", "MODEL_NOT_FOUND", "MODEL_UNAVAILABLE", "INSUFFICIENT_DATA", "VALIDATION_ERROR"):
            failures.append(f"predict-run: got {r.status_code} {json.dumps(payload)[:200]}")

    # ---- case status transition once predicted (analyst has CASE_UPDATE)
    tr = client.post(f"{B}/cases/{case_id}/status", headers={"Authorization": f"Bearer {tok}"}, json={"status": "UNDER_ANALYSIS"})
    if tr.status_code not in (200, 201, 409):
        failures.append(f"case-transition: got {tr.status_code} {json.dumps(tr.json())[:200]}")

    # ---- validation error envelope
    bad = client.post(f"{B}/auth/login", headers={"Content-Type": "application/json"}, json={"email": "x"})
    if bad.status_code != 422 or bad.json().get("error", {}).get("code") != "VALIDATION_ERROR":
        failures.append(f"validation-envelope: got {bad.status_code} {bad.json()}")

    # ---- unauth 401
    anon = client.get(f"{B}/cases")
    if anon.status_code != 401:
        failures.append(f"anonymous-cases: got {anon.status_code}")

    # ---- bad token 401
    badtok = client.get(f"{B}/cases", headers={"Authorization": "Bearer nope"})
    if badtok.status_code != 401:
        failures.append(f"bad-token: got {badtok.status_code}")

print("SMOKE_RESULT:", "FAIL" if failures else "PASS")
for f in failures:
    print(" -", f)
sys.exit(1 if failures else 0)