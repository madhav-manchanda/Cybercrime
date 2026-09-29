"""Audit chain endpoints: list events, verify chain integrity, export."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.database import get_db
from app.core.enums import AuditAction, AuditResult, Permission
from app.core.errors import AuthorizationError
from app.models import AuditLog, User
from app.schemas.analytics import AuditChainSummary, AuditLogOut
from app.schemas.common import Page
from app.services.audit_service import audit_service

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("", response_model=Page[AuditLogOut])
@router.get("/", response_model=Page[AuditLogOut], include_in_schema=False)
async def list_audit(
    session: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, Depends(require_permission(Permission.AUDIT_READ))],
    action: AuditAction | None = None,
    actor_id: uuid.UUID | None = None,
    resource: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> Page[AuditLogOut]:
    rows, total = await audit_service.list_events(
        session,
        action=action,
        actor_id=actor_id,
        resource=resource,
        page=max(page, 1),
        page_size=min(max(page_size, 1), 200),
    )
    items = [AuditLogOut.model_validate(r) for r in rows]
    pages = max((total + page_size - 1) // page_size, 1) if total else 0
    return Page[AuditLogOut](
        items=items,
        total=total,
        page=max(page, 1),
        page_size=page_size,
        pages=pages,
        has_next=page < pages,
    )


@router.get("/verify", response_model=AuditChainSummary)
async def verify_chain(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(Permission.AUDIT_READ))],
) -> AuditChainSummary:
    verified, detail = await audit_service.verify_chain(session)
    if not verified:
        await audit_service.record(
            session,
            action=AuditAction.AUDIT_READ,
            actor_id=user.id,
            actor_email=user.email,
            actor_role=user.role_name.value,
            resource="audit",
            result=AuditResult.FAILURE,
            payload={"event": "chain_verify", "broken_row": str(detail)},
            request_id=request.state.request_id or "",
        )
        await session.commit()
        raise AuthorizationError(
            f"Audit chain integrity check failed at {detail}",
            code="AUDIT_CHAIN_BROKEN",
        )
    total = int((await session.scalar(select(func.count()).select_from(AuditLog))) or 0)
    first = await session.scalar(select(AuditLog.hash).order_by(AuditLog.created_at, AuditLog.id).limit(1))
    await audit_service.record(
        session,
        action=AuditAction.AUDIT_READ,
        actor_id=user.id,
        actor_email=user.email,
        actor_role=user.role_name.value,
        resource="audit",
        payload={"event": "chain_verify"},
        request_id=request.state.request_id or "",
    )
    await session.commit()
    return AuditChainSummary(total=total, verified=True, last_hash=detail, first_hash=first)


@router.post("/export", response_model=dict)
async def export_audit(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(Permission.AUDIT_EXPORT))],
) -> dict:
    rows, total = await audit_service.list_events(session, page=1, page_size=10_000)
    await audit_service.record(
        session,
        action=AuditAction.EXPORT,
        actor_id=user.id,
        actor_email=user.email,
        actor_role=user.role_name.value,
        resource="audit",
        payload={"row_count": len(rows), "scope": "audit"},
        request_id=request.state.request_id or "",
    )
    await session.commit()
    return {
        "count": len(rows),
        "total_matching": total,
        "disclaimer": "Audit log contains no PII; sensitive payload fields are redacted.",
        "events": [AuditLogOut.model_validate(r).model_dump() for r in rows],
    }


__all__ = ["router"]
