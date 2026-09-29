"""Authentication endpoints: register, login, refresh, logout, me."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, rate_limit, request_client_ip
from app.core.config import settings
from app.core.database import get_db
from app.core.enums import AuditAction
from app.core.rate_limit import Limit
from app.models import User
from app.schemas.auth import (
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    Tokens,
    UserMe,
)
from app.services.audit_service import audit_service
from app.services.auth_service import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])

_l_login = Limit(key="login", per=settings.rate_limit_login_per_minute, unit="minute")
_l_write = Limit(key="write", per=settings.rate_limit_write_per_minute, unit="minute")


@router.post("/register", response_model=UserMe, status_code=201)
async def register(
    payload: RegisterRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[None, Depends(rate_limit("auth:register", _l_write))],
) -> UserMe:
    """Public self-registration.  Creates an unverified default analyst account.

    Role assignment is reserved for administrators via ``/users``.  The chosen
    ``role`` on the public path is deliberately ignored.
    """
    user = await auth_service.register(
        session,
        email=str(payload.email),
        password=payload.password,
        full_name=payload.full_name,
    )
    await session.commit()
    await session.refresh(user, attribute_names=["role"])
    return UserMe.model_validate(user)


@router.post("/login", response_model=Tokens)
async def login(
    payload: LoginRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[None, Depends(rate_limit("auth:login", _l_login))],
) -> Tokens:
    ua = payload.client_platform or request.headers.get("user-agent")
    user, access, refresh = await auth_service.login(
        session,
        email=str(payload.email),
        password=payload.password,
        client_ip=request_client_ip(request),
        user_agent=(ua or "")[:200],
    )
    request.state.user_id = str(user.id)
    await session.refresh(user, attribute_names=["role"])
    await session.commit()
    await audit_service.record(
        session,
        action=AuditAction.LOGIN,
        actor_id=user.id,
        actor_email=user.email,
        actor_role=user.role_name.value,
        resource="auth",
        request_id=request.state.request_id or "",
        client_ip=request_client_ip(request),
    )
    await session.commit()
    return _tokens(access, refresh)


@router.post("/refresh", response_model=Tokens)
async def refresh(
    payload: RefreshRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> Tokens:
    user, access, refresh_token = await auth_service.refresh(
        session,
        refresh_token=payload.refresh_token,
        client_ip=request_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    request.state.user_id = str(user.id)
    await session.commit()
    return _tokens(access, refresh_token)


@router.post("/logout", response_model=dict)
async def logout(
    payload: LogoutRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict:
    await auth_service.logout(session, user=user, refresh_token=payload.refresh_token)
    await session.commit()
    return {"message": "Logged out."}


@router.get("/me", response_model=UserMe)
async def me(
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> UserMe:
    return UserMe.model_validate(user)


def _tokens(access: str, refresh: str) -> Tokens:
    return Tokens(
        access_token=access,
        refresh_token=refresh,
        expires_in=settings.access_token_expire_minutes * 60,
    )


__all__ = ["router"]
