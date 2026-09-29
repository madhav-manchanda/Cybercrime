"""Shared FastAPI dependencies: authentication, RBAC, rate limiting.

Every guarded route depends on :func:`get_current_user` (or on a permission /
role wrapper around it).  The authenticated user is set on
``request.state.user_id`` so :func:`app.core.rate_limit.default_identity`
can key limits by the caller instead of by IP.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from typing import Annotated, TypeVar

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.enums import Permission, RoleName
from app.core.errors import (
    USER_NOT_FOUND,
    AuthenticationError,
    AuthorizationError,
)
from app.core.rate_limit import Limit, default_identity, get_limiter
from app.core.security import decode_token
from app.models import User

_bearer = HTTPBearer(auto_error=False)

_T = TypeVar("_T")
_DepT = Callable[..., Awaitable[_T]]


async def get_access_token(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> str:
    """Extract and validate the presence of a bearer token."""
    if creds is None or not creds.credentials:
        raise AuthenticationError("Missing bearer token.", code="TOKEN_MISSING")
    return creds.credentials


async def get_current_user(
    session: Annotated[AsyncSession, Depends(get_db)],
    token: Annotated[str, Depends(get_access_token)],
    request: Request,
) -> User:
    """Resolve the authenticated user from the access token."""
    claims = decode_token(token, "access")
    try:
        user_id = uuid.UUID(str(claims.get("sub")))
    except (ValueError, TypeError):
        raise AuthenticationError("Invalid token subject.", code="TOKEN_INVALID") from None
    user = await session.scalar(select(User).options(selectinload(User.role)).where(User.id == user_id))
    if user is None:
        raise USER_NOT_FOUND
    if not user.is_active:
        raise AuthenticationError("Account is disabled.", code="ACCOUNT_DISABLED")
    if not user.is_verified:
        raise AuthorizationError(
            "Account is not verified. Contact an administrator.",
            code="ACCOUNT_NOT_VERIFIED",
        )
    request.state.user_id = str(user.id)
    return user


def require_permission(permission: Permission) -> _DepT:
    """Dependency factory enforcing a single permission on the current user."""

    async def _dep(user: Annotated[User, Depends(get_current_user)]) -> User:
        if not user.has_permission(permission):
            raise AuthorizationError(
                f"Missing required permission: {permission.value}",
                code="PERMISSION_DENIED",
            )
        return user

    return _dep


def require_roles(*roles: RoleName) -> _DepT:
    """Dependency factory requiring the current user to hold one of ``roles``."""

    async def _dep(user: Annotated[User, Depends(get_current_user)]) -> User:
        if user.role_name not in roles:
            allowed = ", ".join(r.value for r in roles)
            raise AuthorizationError(
                f"Requires one of the roles: {allowed}",
                code="ROLE_REQUIRED",
            )
        return user

    return _dep


def rate_limit(scope: str, limit: Limit) -> _DepT:
    """FastAPI-suitable wrapper over the sliding-window limiter."""

    async def _dep(request: Request) -> None:
        await get_limiter().check(scope, default_identity(request), limit)

    return _dep


def request_client_ip(request: Request) -> str | None:
    """Best-effort client IP honouring the forwarding proxy header."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        first = forwarded.split(",", 1)[0].strip()
        if first:
            return first
    return request.client.host if request.client else None


AnnotatedUser = Annotated[User, Depends(get_current_user)]

__all__ = [
    "AnnotatedUser",
    "get_access_token",
    "get_current_user",
    "rate_limit",
    "request_client_ip",
    "require_permission",
    "require_roles",
]
