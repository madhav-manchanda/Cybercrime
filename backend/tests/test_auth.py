"""Auth service + API flow: register, verify gate, login, me, RBAC defaults."""

from __future__ import annotations

from sqlalchemy import select

from app.core.enums import Permission, RoleName
from app.models import Role
from app.services.auth_service import auth_service


async def test_default_analyst_excludes_sensitive_permissions(db_session: object) -> None:
    session = db_session
    # Self-registration bootstraps the default analyst role on first use.
    await auth_service.register(
        session, email="bootstrap-default@example.com", password="Bootstrap!Passw0rd", full_name="Bootstrapper"
    )
    await session.commit()
    role = await session.scalar(select(Role).where(Role.name == RoleName.I4C_ANALYST))
    assert role is not None
    perms = set(role.permissions or [])
    assert Permission.USER_MANAGE.value not in perms
    assert Permission.MODEL_TRAIN.value not in perms
    assert Permission.AUDIT_EXPORT.value not in perms
    assert Permission.CASE_READ.value in perms


async def test_self_register_is_unverified(client: object) -> None:
    resp = client.post(
        "/api/v1/auth/register",
        json={
            "email": "fresh@example.com",
            "password": "Fresh!Passw0rd",
            "full_name": "Fresh Analyst",
        },
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["is_verified"] is False

    login = client.post(
        "/api/v1/auth/login",
        json={"email": "fresh@example.com", "password": "Fresh!Passw0rd"},
    )
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]

    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 403, me.text
    assert me.json()["error"]["code"] == "ACCOUNT_NOT_VERIFIED"


async def test_admin_can_read_me(client: object, admin_headers: dict[str, str]) -> None:
    resp = client.get("/api/v1/auth/me", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["email"] == "testadmin@example.com"


async def test_wrong_password_rejected(client: object) -> None:
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": "testadmin@example.com", "password": "wrong-password"},
    )
    # AuthorizationError is surfaced as 403 with a machine-readable code.
    assert resp.status_code == 403, resp.text
    assert resp.json()["error"]["code"] == "INVALID_CREDENTIALS"


async def test_bad_token_rejected(client: object) -> None:
    resp = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer not.a.jwt"})
    assert resp.status_code == 401, resp.text


async def test_validation_envelope(client: object) -> None:
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": "not-an-email"},
    )
    assert resp.status_code == 422, resp.text
    body = resp.json()["error"]
    assert body["code"] == "VALIDATION_ERROR"
    assert body["message"]