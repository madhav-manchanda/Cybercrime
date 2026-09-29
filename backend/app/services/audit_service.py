"""Hash-chained audit logging service.

Every sensitive operation produces an :class:`AuditLog` row whose ``hash`` is::

    SHA256(canonical_json(event_payload) || prev_hash)

Verifying the chain therefore detects tampering of any past record.  Callers
must never pass passwords/tokens/account numbers in ``payload`` - the service
re-masks known sensitive keys defensively.
"""

from __future__ import annotations

import uuid
from typing import Any

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import AuditAction, AuditResult
from app.core.errors import AppError
from app.models import AuditLog
from app.utils.hashing import audit_chain_hash

logger = structlog.get_logger("audit")

# defensive re-mask of keys that must never reach disk
_FORBIDDEN_KEYS = {
    "password",
    "hashed_password",
    "access_token",
    "refresh_token",
    "authorization",
    "api_key",
    "secret",
    "private_key",
    "card_number",
    "cvv",
    "otp",
}


def _sanitize(payload: dict[str, Any]) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for key, value in payload.items():
        low = key.lower()
        masked = any(token in low for token in _FORBIDDEN_KEYS)
        cleaned[key] = "[REDACTED]" if masked else value
    return cleaned


class AuditService:
    """Writes append-only, tamper-evident audit events."""

    async def record(
        self,
        session: AsyncSession,
        *,
        action: AuditAction,
        actor_id: uuid.UUID | None = None,
        actor_email: str | None = None,
        actor_role: str | None = None,
        resource: str | None = None,
        resource_id: str | uuid.UUID | None = None,
        result: AuditResult = AuditResult.SUCCESS,
        request_id: str | None = None,
        client_ip: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> AuditLog:
        """Append one chained audit event."""
        event_payload = _sanitize(payload or {})
        body = {
            "action": action.value if hasattr(action, "value") else str(action),
            "actor_id": str(actor_id) if actor_id else None,
            "actor_role": actor_role,
            "resource": resource,
            "resource_id": str(resource_id) if resource_id else None,
            "result": result.value if hasattr(result, "value") else str(result),
            "event_payload": event_payload,
        }
        prev_row = await session.scalar(
            select(AuditLog).order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(1)
        )
        prev_hash = prev_row.hash if prev_row else None
        chain_hash = audit_chain_hash(body, prev_hash)

        entry = AuditLog(
            actor_id=actor_id,
            actor_email=actor_email,
            actor_role=actor_role,
            action=action,
            resource=resource,
            resource_id=str(resource_id) if resource_id else None,
            result=result,
            request_id=request_id,
            client_ip=client_ip,
            event_payload=event_payload,
            prev_hash=prev_hash,
            hash=chain_hash,
        )
        session.add(entry)
        await session.flush()
        logger.info(
            "audit",
            action=entry.action.value if hasattr(entry.action, "value") else entry.action,
            resource=resource,
            resource_id=entry.resource_id,
            actor_id=str(actor_id) if actor_id else None,
            result=entry.result.value if hasattr(entry.result, "value") else entry.result,
        )
        return entry

    async def verify_chain(self, session: AsyncSession) -> tuple[bool, str | None]:
        """Replay the chain and confirm integrity."""
        rows = (await session.scalars(select(AuditLog).order_by(AuditLog.created_at, AuditLog.id))).all()
        prev_hash: str | None = None
        for row in rows:
            body = {
                "action": row.action.value if hasattr(row.action, "value") else row.action,
                "actor_id": str(row.actor_id) if row.actor_id else None,
                "actor_role": row.actor_role,
                "resource": row.resource,
                "resource_id": row.resource_id,
                "result": row.result.value if hasattr(row.result, "value") else row.result,
                "event_payload": row.event_payload,
            }
            expected = audit_chain_hash(body, prev_hash)
            if row.hash != expected:
                return False, str(row.id)
            prev_hash = row.hash
        return True, prev_hash

    async def list_events(
        self,
        session: AsyncSession,
        *,
        action: AuditAction | None = None,
        actor_id: uuid.UUID | None = None,
        resource: str | None = None,
        resource_id: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[AuditLog], int]:
        query = select(AuditLog)
        if action:
            query = query.where(
                AuditLog.action == action.value
                if hasattr(action, "value")
                else AuditLog.action == str(action)
            )
        if actor_id:
            query = query.where(AuditLog.actor_id == actor_id)
        if resource:
            query = query.where(AuditLog.resource == resource)
        if resource_id:
            query = query.where(AuditLog.resource_id == resource_id)
        total = await session.scalar(select(func.count()).select_from(query.subquery())) or 0
        query = query.order_by(AuditLog.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        rows = (await session.scalars(query)).all()
        return list(rows), int(total)


audit_service: AuditService = AuditService()

__all__ = ["AppError", "AuditService", "audit_service"]
