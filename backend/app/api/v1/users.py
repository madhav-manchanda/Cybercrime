"""User & RBAC administration endpoints (ADMIN / user:manage).

User management has no dedicated service - these routes perform direct ORM
work and always write hash-chained audit records.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_permission
from app.core.database import get_db
from app.core.enums import AuditAction, Permission, RoleName
from app.core.errors import USER_NOT_FOUND, BadRequestError
from app.core.security import hash_password, verify_password
from app.models import Role, User
from app.schemas.auth import (
    AssignRoleRequest,
    ChangePasswordRequest,
    RegisterRequest,
    RoleSchema,
    UserOut,
)
from app.schemas.common import Page
from app.services.audit_service import audit_service

router = APIRouter(prefix="/users", tags=["users"])

ManageUsers = Annotated[User, Depends(require_permission(Permission.USER_MANAGE))]


async def _role_or_raises(session: AsyncSession, name: RoleName) -> Role:
    role = await session.scalar(select(Role).where(Role.name == name))
    if role is None:
        raise BadRequestError(f"Unknown role {name.value}", code="UNKNOWN_ROLE")
    return role


@router.get("", response_model=Page[UserOut])
@router.get("/", response_model=Page[UserOut], include_in_schema=False)
async def list_users(
    session: Annotated[AsyncSession, Depends(get_db)],
    _: ManageUsers,
    page: int = 1,
    page_size: int = 50,
) -> Page[UserOut]:
    page = max(page, 1)
    page_size = min(max(page_size, 1), 200)
    total = int((await session.scalar(select(func.count()).select_from(User))) or 0)
    rows = list(
        (
            await session.scalars(
                select(User).order_by(User.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
            )
        ).all()
    )
    return _page([UserOut.model_validate(u) for u in rows], total, page, page_size)


@router.get("/roles", response_model=list[RoleSchema])
async def list_roles(
    session: Annotated[AsyncSession, Depends(get_db)],
    _: ManageUsers,
) -> list[RoleSchema]:
    roles = list((await session.scalars(select(Role).order_by(Role.name))).all())
    return [RoleSchema.model_validate(r) for r in roles]


@router.get("/{user_id}", response_model=UserOut)
async def get_user(
    user_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    _: ManageUsers,
) -> UserOut:
    user = await session.get(User, user_id)
    if user is None:
        raise USER_NOT_FOUND
    return UserOut.model_validate(user)


@router.post("", response_model=UserOut, status_code=201)
async def create_user(
    payload: RegisterRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
    actor: ManageUsers,
) -> UserOut:
    """Create a verified user with an explicit role (admin operation)."""
    if payload.role is None:
        raise BadRequestError("role is required when creating a user", code="ROLE_REQUIRED")
    role = await _role_or_raises(session, payload.role)
    existing = await session.scalar(select(User).where(User.email == str(payload.email)))
    if existing is not None:
        raise BadRequestError("A user with this email already exists.", code="EMAIL_EXISTS")
    user = User(
        email=str(payload.email),
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        role_id=role.id,
        is_active=True,
        is_verified=True,
    )
    session.add(user)
    await session.flush()
    await audit_service.record(
        session,
        action=AuditAction.USER_CREATE,
        actor_id=actor.id,
        actor_email=actor.email,
        actor_role=actor.role_name.value,
        resource="user",
        resource_id=user.id,
        request_id=request.state.request_id or "",
    )
    await session.commit()
    await session.refresh(user)
    return UserOut.model_validate(user)


@router.patch("/{user_id}/role", response_model=UserOut)
async def assign_role(
    user_id: uuid.UUID,
    payload: AssignRoleRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
    actor: ManageUsers,
) -> UserOut:
    user = await session.get(User, user_id)
    if user is None:
        raise USER_NOT_FOUND
    role = await _role_or_raises(session, payload.role)
    user.role_id = role.id
    await session.flush()
    await audit_service.record(
        session,
        action=AuditAction.USER_UPDATE,
        actor_id=actor.id,
        actor_email=actor.email,
        actor_role=actor.role_name.value,
        resource="user",
        resource_id=user.id,
        payload={"role": payload.role.value},
        request_id=request.state.request_id or "",
    )
    await session.commit()
    await session.refresh(user)
    return UserOut.model_validate(user)


@router.patch("/{user_id}/status", response_model=UserOut)
async def set_user_status(
    user_id: uuid.UUID,
    payload: dict,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
    actor: ManageUsers,
) -> UserOut:
    active = payload.get("is_active")
    if not isinstance(active, bool):
        raise BadRequestError("is_active must be a boolean", code="INVALID_STATUS")
    user = await session.get(User, user_id)
    if user is None:
        raise USER_NOT_FOUND
    if user.id == actor.id and not active:
        raise BadRequestError("You cannot deactivate your own account", code="SELF_DEACTIVATE")
    user.is_active = active
    await session.flush()
    await audit_service.record(
        session,
        action=AuditAction.USER_UPDATE,
        actor_id=actor.id,
        actor_email=actor.email,
        actor_role=actor.role_name.value,
        resource="user",
        resource_id=user.id,
        payload={"is_active": active},
        request_id=request.state.request_id or "",
    )
    await session.commit()
    await session.refresh(user)
    return UserOut.model_validate(user)


@router.put("/me/password", response_model=dict)
async def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict:
    """Rotate the caller's own password (no admin permission required)."""
    if not verify_password(payload.current_password, user.hashed_password):
        raise BadRequestError("Current password is incorrect.", code="WRONG_PASSWORD")
    user.hashed_password = hash_password(payload.new_password)
    await session.flush()
    await audit_service.record(
        session,
        action=AuditAction.USER_UPDATE,
        actor_id=user.id,
        actor_email=user.email,
        actor_role=user.role_name.value,
        resource="user",
        resource_id=user.id,
        payload={"action": "password_change"},
        request_id=request.state.request_id or "",
    )
    await session.commit()
    return {"message": "Password updated."}


def _page(items: list[UserOut], total: int, page: int, page_size: int) -> Page[UserOut]:
    pages = max((total + page_size - 1) // page_size, 1) if total else 0
    return Page[UserOut](
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
        has_next=page < pages,
    )


__all__ = ["router"]
