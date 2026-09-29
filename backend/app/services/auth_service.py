"""Authentication service: register, login, refresh rotation, logout."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.enums import AuditAction, AuditResult, Permission, RoleName
from app.core.errors import AuthorizationError, BadRequestError, ConflictError
from app.core.security import (
    create_token,
    generate_refresh_token_hash,
    hash_password,
    verify_password,
)
from app.models import RefreshTokenSession, Role, User
from app.services.audit_service import audit_service

# Permissions a self-registered analyst receives until an ADMIN verifies/upgrades them.
# Deliberately excludes user management, model training, synthetic generation, LLM,
# audit export and destructive actions.
_DEFAULT_ANALYST_PERMISSIONS: frozenset[Permission] = frozenset(
    {
        Permission.CASE_CREATE,
        Permission.CASE_READ,
        Permission.CASE_UPDATE,
        Permission.COMPLAINT_CREATE,
        Permission.COMPLAINT_READ,
        Permission.TRANSACTION_CREATE,
        Permission.TRANSACTION_READ,
        Permission.ENTITY_READ,
        Permission.NETWORK_READ,
        Permission.NETWORK_WRITE,
        Permission.PREDICTION_READ,
        Permission.PREDICTION_RUN,
        Permission.ATM_READ,
        Permission.ALERT_READ,
        Permission.ALERT_WRITE,
        Permission.INVESTIGATION_READ,
        Permission.INVESTIGATION_WRITE,
        Permission.SIMULATION_RUN,
        Permission.OUTCOME_WRITE,
        Permission.ANALYTICS_READ,
        Permission.MODEL_READ,
    }
)

REFRESH_TTL = timedelta(days=settings.refresh_token_expire_days)


def _later_refresh() -> datetime:
    return datetime.now(UTC) + REFRESH_TTL


class AuthService:
    """Orchestrates identity lifecycle. Sessions are always explicit."""

    # ------------------------------------------------------------ register
    async def register(
        self,
        session: AsyncSession,
        *,
        email: str,
        password: str,
        full_name: str,
        role_name: RoleName | None = None,
        actor: User | None = None,
    ) -> User:
        email = email.lower().strip()
        existing = await session.scalar(select(User).where(User.email == email))
        if existing:
            raise ConflictError("A user with this email already exists.", code="EMAIL_EXISTS")

        target_role = (
            await session.scalar(select(Role).where(Role.name == RoleName.I4C_ANALYST))
            if role_name is None
            else await session.scalar(select(Role).where(Role.name == role_name))
        )
        if target_role is None:
            if role_name is None:
                # fall back to creating default analyst role if missing (bootstrap)
                target_role = self._default_role()
                session.add(target_role)
                await session.flush()
            else:
                raise BadRequestError(f"Unknown role {role_name.value}", code="UNKNOWN_ROLE")

        user = User(
            email=email,
            hashed_password=hash_password(password),
            full_name=full_name,
            is_verified=actor is not None,  # self-registration requires manual verify
            role_id=target_role.id,
            is_active=True,
        )
        session.add(user)
        await session.flush()

        await audit_service.record(
            session,
            action=AuditAction.USER_CREATE,
            actor_id=actor.id if actor else None,
            actor_email=actor.email if actor else None,
            actor_role=actor.role_name.value if actor else None,
            resource="user",
            resource_id=user.id,
            payload={"email": email, "role": target_role.name},
        )
        return user

    @staticmethod
    def _default_role() -> Role:
        permissions = sorted({p.value for p in _DEFAULT_ANALYST_PERMISSIONS})
        return Role(
            name=RoleName.I4C_ANALYST,
            description="Default case analyst role (self-registration, verified by admin)",
            permissions=permissions,
        )

    # --------------------------------------------------------------- login
    async def login(
        self,
        session: AsyncSession,
        *,
        email: str,
        password: str,
        client_ip: str | None = None,
        user_agent: str | None = None,
    ) -> tuple[User, str, str]:
        email = email.lower().strip()
        user = await session.scalar(select(User).options(selectinload(User.role)).where(User.email == email))

        if user is None or not verify_password(password, user.hashed_password):
            await audit_service.record(
                session,
                action=AuditAction.LOGIN_FAILED,
                actor_email=email,
                actor_role=None,
                resource="auth",
                result=AuditResult.FAILURE,
                client_ip=client_ip,
                payload={"email": email},
            )
            raise AuthorizationError("Invalid email or password.", code="INVALID_CREDENTIALS")
        if not user.is_active:
            await audit_service.record(
                session,
                action=AuditAction.LOGIN_FAILED,
                actor_id=user.id,
                actor_email=user.email,
                actor_role=user.role_name.value,
                resource="auth",
                result=AuditResult.DENIED,
                client_ip=client_ip,
                payload={"reason": "inactive"},
            )
            raise AuthorizationError("Account is disabled.", code="ACCOUNT_DISABLED")

        tokens = await self._issue_tokens(session, user, client_ip=client_ip, user_agent=user_agent)
        user.last_login_at = datetime.now(UTC)
        await audit_service.record(
            session,
            action=AuditAction.LOGIN,
            actor_id=user.id,
            actor_email=user.email,
            actor_role=user.role_name.value,
            resource="auth",
            resource_id=user.id,
            client_ip=client_ip,
            payload={"email": email},
        )
        await session.flush()
        return user, tokens[0], tokens[1]

    async def _issue_tokens(
        self,
        session: AsyncSession,
        user: User,
        *,
        client_ip: str | None = None,
        user_agent: str | None = None,
    ) -> tuple[str, str]:
        refresh_token = create_token(str(user.id), "refresh", role=user.role_name.value)
        session_row = RefreshTokenSession(
            token_hash=generate_refresh_token_hash(refresh_token),
            user_id=user.id,
            expires_at=_later_refresh(),
            client_ip=client_ip,
            user_agent=user_agent,
        )
        session.add(session_row)
        user.refresh_token_hash = generate_refresh_token_hash(refresh_token)
        await session.flush()
        access_token = create_token(str(user.id), "access", role=user.role_name.value)
        return access_token, refresh_token

    # -------------------------------------------------------------- refresh
    async def refresh(
        self,
        session: AsyncSession,
        *,
        refresh_token: str,
        client_ip: str | None = None,
        user_agent: str | None = None,
    ) -> tuple[User, str, str]:
        token_hash = generate_refresh_token_hash(refresh_token)
        row = await session.scalar(
            select(RefreshTokenSession).where(RefreshTokenSession.token_hash == token_hash)
        )
        if row is None or row.revoked_at is not None:
            raise AuthorizationError("Refresh token is invalid or has been revoked.", code="REFRESH_INVALID")
        if row.expires_at < datetime.now(UTC):
            raise AuthorizationError("Refresh token has expired.", code="REFRESH_EXPIRED")

        user = await session.get(User, row.user_id)
        if user is None or not user.is_active:
            raise AuthorizationError("User account is unavailable.", code="ACCOUNT_DISABLED")

        # rotate: revoke current session, issue a new one
        new_refresh_token = create_token(str(user.id), "refresh", role=user.role_name.value)
        new_token_hash = generate_refresh_token_hash(new_refresh_token)
        row.revoked_at = datetime.now(UTC)
        row.replaced_by = new_token_hash
        session.add(
            RefreshTokenSession(
                token_hash=new_token_hash,
                user_id=user.id,
                expires_at=_later_refresh(),
                client_ip=client_ip,
                user_agent=user_agent,
            )
        )
        user.refresh_token_hash = new_token_hash

        access_token = create_token(str(user.id), "access", role=user.role_name.value)
        user.last_login_at = datetime.now(UTC)
        await audit_service.record(
            session,
            action=AuditAction.TOKEN_REFRESH,
            actor_id=user.id,
            actor_email=user.email,
            actor_role=user.role_name.value,
            resource="auth",
            resource_id=row.id,
            client_ip=client_ip,
        )
        await session.flush()
        return user, access_token, new_refresh_token

    # -------------------------------------------------------------- logout
    async def logout(
        self,
        session: AsyncSession,
        *,
        user: User,
        refresh_token: str | None = None,
    ) -> None:
        if refresh_token:
            token_hash = generate_refresh_token_hash(refresh_token)
            row = await session.scalar(
                select(RefreshTokenSession).where(RefreshTokenSession.token_hash == token_hash)
            )
            if row and row.user_id == user.id and row.revoked_at is None:
                row.revoked_at = datetime.now(UTC)
        user.refresh_token_hash = None
        await audit_service.record(
            session,
            action=AuditAction.LOGOUT,
            actor_id=user.id,
            actor_email=user.email,
            actor_role=user.role_name.value,
            resource="auth",
            resource_id=user.id,
        )
        await session.flush()


auth_service = AuthService()

__all__ = ["AuthService", "auth_service"]
