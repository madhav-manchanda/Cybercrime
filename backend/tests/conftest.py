"""Shared fixtures: per-session SQLite DB + TestClient."""

from __future__ import annotations

import os
import tempfile
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_TMP = tempfile.TemporaryDirectory()
_DB = Path(_TMP.name) / "test.db"

os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_DB}"
os.environ["PUBLIC_BASE_URL"] = "http://testserver"


@pytest.fixture(scope="session")
def db_path() -> Iterator[Path]:
    from app.core.database import init_sync_schema

    init_sync_schema()
    yield _DB


@pytest.fixture(scope="session")
def client(db_path: Path) -> Iterator[TestClient]:
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
async def db_session() -> AsyncIterator[object]:
    from app.core.database import async_session_factory, init_sync_schema

    init_sync_schema()  # idempotent; guarantees tables exist without a client fixture
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@pytest.fixture(scope="session")
def admin_headers(client: TestClient) -> dict[str, str]:
    """Bootstrap an admin (role + user) once and return bearer headers."""
    import asyncio

    from sqlalchemy import select

    from app.core.database import async_session_factory
    from app.core.enums import Permission, RoleName
    from app.core.security import hash_password
    from app.models import Role, User

    async def _bootstrap() -> User:
        async with async_session_factory() as session:
            role = await session.scalar(select(Role).where(Role.name == RoleName.ADMIN))
            if role is None:
                role = Role(
                    name=RoleName.ADMIN,
                    description="Platform administrator, unrestricted.",
                    permissions=sorted({p.value for p in Permission}),
                )
                session.add(role)
                await session.flush()
            user = await session.scalar(select(User).where(User.email == "testadmin@example.com"))
            if user is None:
                user = User(
                    email="testadmin@example.com",
                    hashed_password=hash_password("Admin!TestP@ssw0rd"),
                    full_name="Test Admin",
                    is_verified=True,
                    is_active=True,
                    role_id=role.id,
                )
                session.add(user)
                await session.flush()
            await session.commit()
            return user

    user = asyncio.run(_bootstrap())
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": "Admin!TestP@ssw0rd"},
    )
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}