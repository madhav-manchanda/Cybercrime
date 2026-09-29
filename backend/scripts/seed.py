"""Dev/demo bootstrap: idempotently create RBAC roles + a platform admin.

Usage (from ``backend``):
    DATABASE_URL=sqlite+aiosqlite:///./var/cybercrime.db \\
        SEED_ADMIN_EMAIL=admin@example.com SEED_ADMIN_PASSWORD='<strong-password>' \\
        python -m scripts.seed --demo

- Ensure all six :class:`RoleName` roles exist.
- Create (once) a verified ADMIN user.  If ``SEED_ADMIN_PASSWORD`` is missing the
  script generates a random password and prints it exactly once for the operator.
- ``--demo`` additionally loads synthetic cases/accounts/transactions/ATMs via
  :func:`app.synthetic.generator.generate_dataset` (data_source="synthetic").

Idempotent: safe to run repeatedly.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import secrets
from typing import Any

from sqlalchemy import select

from app.core.config import settings
from app.core.database import init_sync_schema, session_scope
from app.core.enums import AuditAction, Permission, RoleName
from app.core.security import hash_password
from app.models import Role, User
from app.services.audit_service import audit_service

ALL_PERMISSIONS: set[str] = {p.value for p in Permission}

ROLE_PERMISSIONS: dict[RoleName, tuple[str, set[str]]] = {
    RoleName.ADMIN: ("Platform administrator, unrestricted.", ALL_PERMISSIONS),
    RoleName.I4C_ANALYST: (
        "Central cybercrime analytics cell: full case/analytic read-write.",
        {
            "case:create", "case:read", "case:update", "case:assign",
            "complaint:create", "complaint:read",
            "transaction:create", "transaction:read",
            "entity:read", "network:read", "network:write",
            "prediction:read", "prediction:run",
            "atm:read", "alert:read", "alert:write",
            "investigation:read", "investigation:write",
            "simulation:run", "outcome:write",
            "analytics:read", "model:read",
        },
    ),
    RoleName.STATE_OFFICER: (
        "State-level oversight: read across own state.",
        {
            "case:read", "complaint:read", "transaction:read",
            "entity:read", "network:read", "prediction:read", "prediction:run",
            "atm:read", "alert:read", "analytics:read",
        },
    ),
    RoleName.DISTRICT_OFFICER: (
        "District-level officer: read/write within own district.",
        {
            "case:read", "case:create", "case:update",
            "complaint:read", "complaint:create",
            "transaction:read", "transaction:create",
            "entity:read", "network:read",
            "prediction:read", "prediction:run",
            "atm:read", "alert:read", "alert:write",
            "investigation:read", "investigation:write",
            "analytics:read",
        },
    ),
    RoleName.BANK_ANALYST: (
        "Financial-institution liaison: read on linked accounts/transactions.",
        {"case:read", "complaint:read", "transaction:read", "entity:read", "atm:read", "alert:read", "prediction:read"},
    ),
    RoleName.AUDITOR: (
        "Read-only across the audit trail; no case mutation.",
        {"audit:read", "audit:export", "analytics:read"},
    ),
}


def _password_from_env() -> str:
    """Resolve the ADMIN password; generate + print once when unset (dev only)."""
    explicit = os.environ.get("SEED_ADMIN_PASSWORD", "").strip()
    if explicit:
        return explicit
    if settings.is_production:
        raise SystemExit("SEED_ADMIN_PASSWORD is required in production.")
    generated = secrets.token_urlsafe(18)
    print(f"ADMIN_PASSWORD_GENERATED {generated}", flush=True)
    print("NOTE: store this password now; it will not be printed again.", flush=True)
    return generated


async def _ensure_roles(session: Any) -> None:
    existing = {
        RoleName(row.name): row
        for row in (await session.scalars(select(Role))).all()
    }
    for role_name, (description, perms) in ROLE_PERMISSIONS.items():
        role = existing.get(role_name)
        if role is None:
            session.add(
                Role(
                    name=role_name,
                    description=description,
                    permissions=sorted(perms),
                )
            )
            print(f"role created {role_name}")
        elif set(role.permissions or []) != perms:
            role.permissions = sorted(perms)
            role.description = description
            print(f"role refreshed {role_name}")
        else:
            print(f"role ok {role_name}")


async def _ensure_admin(session: Any, email: str, password: str, full_name: str) -> None:
    existing = await session.scalar(select(User).where(User.email == email))
    if existing is not None:
        print(f"admin ok {email}")
        return
    admin_role = await session.scalar(select(Role).where(Role.name == RoleName.ADMIN))
    admin = User(
        email=email,
        hashed_password=hash_password(password),
        full_name=full_name,
        is_verified=True,
        is_active=True,
        role_id=admin_role.id,
    )
    session.add(admin)
    await session.flush()
    await audit_service.record(
        session,
        action=AuditAction.USER_CREATE,
        actor_id=admin.id,
        actor_email=admin.email,
        actor_role=RoleName.ADMIN.value,
        resource="user",
        resource_id=admin.id,
        payload={"via": "seed", "role": "ADMIN"},
    )
    print(f"admin created {email}")


async def _demo(session: Any, args: argparse.Namespace) -> None:
    from app.synthetic.generator import generate_dataset

    counts = await generate_dataset(
        session,
        number_of_cases=args.cases,
        number_of_transactions=args.transactions,
        number_of_accounts=args.accounts,
        number_of_atms=args.atms,
        geographic_area=settings.default_city,
        center_lat=settings.default_city_lat,
        center_lon=settings.default_city_lon,
        time_range_days=180,
        fraud_patterns="ALL",
        seed=settings.ml_random_seed,
    )
    print(f"demo data loaded {counts}")
    await session.commit()


async def _main(args: argparse.Namespace) -> None:
    async with session_scope() as session:
        await _ensure_roles(session)
        await session.flush()
        await _ensure_admin(
            session,
            email=os.environ.get("SEED_ADMIN_EMAIL", "admin@example.com").strip().lower(),
            password=_password_from_env(),
            full_name=os.environ.get("SEED_ADMIN_FULL_NAME", "Platform Administrator").strip(),
        )
        await session.commit()
        if args.demo:
            await _demo(session, args)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo", action="store_true", help="generate synthetic demo records")
    parser.add_argument("--cases", type=int, default=settings.demo_cases)
    parser.add_argument("--accounts", type=int, default=120)
    parser.add_argument("--atms", type=int, default=settings.demo_atms)
    parser.add_argument("--transactions", type=int, default=2200)
    args = parser.parse_args()

    init_sync_schema()
    asyncio.run(_main(args))


if __name__ == "__main__":
    main()