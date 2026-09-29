"""User and role models (RBAC)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.core.database import Base
from app.core.enums import Permission, RoleName
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.case import Case
    from app.models.outcome import Outcome

# Portable JSON "JSONB-like" column: real JSONB on postgres, JSON elsewhere.
_JSON_TYPE: Any = JSONB


class Role(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A set of permitted actions."""

    __tablename__ = "roles"

    name: Mapped[RoleName] = mapped_column(String(32), unique=True, index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: JSON array of permission strings (see :class:`Permission`).
    permissions: Mapped[list[str]] = mapped_column(_JSON_TYPE, default=list, nullable=False)

    users: Mapped[list[User]] = relationship(back_populates="role")

    @property
    def permission_set(self) -> frozenset[Permission]:
        valid = {x.value for x in Permission}
        return frozenset(Permission(p) for p in self.permissions if p in valid)


class User(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    #: Mass-persisted identifier of the last refresh token (for rotation).
    refresh_token_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    role_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("roles.id", ondelete="RESTRICT"), nullable=False
    )

    role: Mapped[Role] = relationship(back_populates="users")
    cases: Mapped[list[Case]] = relationship(
        back_populates="assigned_investigator", foreign_keys="Case.assigned_user_id"
    )
    outcomes: Mapped[list[Outcome]] = relationship(
        back_populates="recorded_by_user", foreign_keys="Outcome.recorded_by"
    )

    # ----------------------------------------------------------- helpers
    @property
    def role_name(self) -> RoleName:
        return RoleName(self.role.name)

    def has_permission(self, permission: Permission) -> bool:
        return permission.value in self.role.permissions

    def check_permission(self, permission: Permission) -> bool:
        return self.has_permission(permission)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<User {self.email}>"


__all__ = ["Role", "User"]
