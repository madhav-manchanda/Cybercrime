"""Refresh-token sessions (rotation + revocation tracking)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.core.database import Base
from app.models.mixins import UUIDPrimaryKeyMixin, utcnow


class RefreshTokenSession(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "refresh_token_sessions"
    __table_args__ = (
        Index("ix_refresh_user", "user_id"),
        Index("ix_refresh_token_hash", "token_hash"),
        Index("ix_refresh_expires", "expires_at"),
    )

    token_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    replaced_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(300), nullable=True)
    client_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)


__all__ = ["RefreshTokenSession"]
