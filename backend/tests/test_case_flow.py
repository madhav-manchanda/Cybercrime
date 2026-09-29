"""End-to-end API flow over one case: register → verify → case → PII mask → predict."""

from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.core.database import async_session_factory
from app.models import User

B = "/api/v1"


def _verify_user(email: str) -> None:
    async def _update() -> None:
        async with async_session_factory() as session:
            user = await session.scalar(select(User).where(User.email == email))
            assert user is not None
            user.is_verified = True
            await session.commit()

    asyncio.run(_update())


def test_case_complaint_txn_predict_flow(client: object, admin_headers: dict[str, str]) -> None:
    import uuid

    suffix = uuid.uuid4().hex[:8]
    email = f"flow-{suffix}@example.com"

    reg = client.post(
        f"{B}/auth/register",
        json={"email": email, "password": "Flow!Passw0rd", "full_name": "Flow Analyst"},
    )
    assert reg.status_code == 201, reg.text
    login = client.post(
        f"{B}/auth/login", json={"email": email, "password": "Flow!Passw0rd"}
    )
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]

    _verify_user(email)

    atm = client.post(
        f"{B}/atms",
        headers=admin_headers,
        json={
            "code": f"ATMF{suffix[:5]}",
            "name": "Flora Fountain ATM",
            "bank_name": "Bank of Baroda",
            "latitude": 26.8453,
            "longitude": 80.9462,
            "address": "Hazratganj, Lucknow",
            "is_csp": False,
        },
    )
    assert atm.status_code == 201, atm.text

    case = client.post(
        f"{B}/cases",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "title": "UPI fraud cluster",
            "description": "integration test",
            "priority": "HIGH",
            "fraud_type": "UPI_FRAUD",
            "state": "Uttar Pradesh",
            "district": "Lucknow",
            "data_source": "synthetic",
        },
    )
    assert case.status_code == 201, case.text
    case_id = case.json().get("id") or case.json().get("case", {}).get("id")
    assert case_id

    comp = client.post(
        f"{B}/complaints",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "case_id": case_id,
            "category": "UPI_FRAUD",
            "amount": 45000,
            "narrative": "sent funds after OTP",
            "victim_name": "Priya Sharma",
            "victim_phone": "9876543210",
            "victim_email": "priya@example.com",
            "platform": "UPI",
            "data_source": "synthetic",
        },
    )
    assert comp.status_code == 201, comp.text
    comp_id = comp.json().get("id") or comp.json().get("complaint", {}).get("id")

    comp_get = client.get(
        f"{B}/complaints/{comp_id}", headers={"Authorization": f"Bearer {token}"}
    )
    assert comp_get.status_code == 200, comp_get.text
    c = comp_get.json().get("complaint", comp_get.json())
    assert c.get("victim_name") and "*" in str(c.get("victim_name"))
    assert c.get("victim_name") != "Priya Sharma"

    txn = client.post(
        f"{B}/transactions",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "case_id": case_id,
            "amount": 9000,
            "sender_account": "912345678901",
            "receiver_account": "9988776655",
            "upi_ref": f"upi-{suffix}",
            "channel": "UPI",
            "transaction_type": "UPI_P2M",
            "latitude": 26.8453,
            "longitude": 80.9462,
            "data_source": "synthetic",
        },
    )
    assert txn.status_code == 201, txn.text

    pred = client.post(
        f"{B}/cases/{case_id}/predict",
        headers={"Authorization": f"Bearer {token}"},
        json={"source": "API", "notes": "integration"},
    )
    allowed = {200, 201, 409}
    assert pred.status_code in allowed, pred.text

    tr = client.post(
        f"{B}/cases/{case_id}/status",
        headers={"Authorization": f"Bearer {token}"},
        json={"status": "UNDER_ANALYSIS"},
    )
    assert tr.status_code in {200, 201, 409}, tr.text