"""Hash-chained audit log (tamper-evident event trail)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON, Uuid

from app.core.database import Base
from app.core.enums import AuditAction, AuditResult
from app.models.mixins import UUIDPrimaryKeyMixin, utcnow


class AuditLog(Base, UUIDPrimaryKeyMixin):
    """One immutable audit event.

    Every record carries ``prev_hash``/``hash`` where::

        hash = SHA256(canonical(event payload) + prev_hash)

    so tampering with any past record breaks the chain and is detectable.
    """

    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_actor", "actor_id"),
        Index("ix_audit_action", "action"),
        Index("ix_audit_created", "created_at"),
        Index("ix_audit_resource", "resource", "resource_id"),
        Index("ix_audit_result", "result"),
    )

    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    actor_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    actor_role: Mapped[str | None] = mapped_column(String(32), nullable=True)
    action: Mapped[AuditAction] = mapped_column(String(40), nullable=False)
    resource: Mapped[str | None] = mapped_column(String(120), nullable=True)
    resource_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    result: Mapped[AuditResult] = mapped_column(String(16), nullable=False, default=AuditResult.SUCCESS)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    client_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    event_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    prev_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


__all__ = ["AuditLog"]
