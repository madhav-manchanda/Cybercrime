"""Complaint ingestion, linking, and retrieval endpoints."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.database import get_db
from app.core.enums import AuditAction, Permission
from app.core.security import mask, mask_email, mask_phone
from app.models import Complaint, User
from app.schemas.common import Page
from app.schemas.complaint import (
    ComplaintCreateRequest,
    ComplaintLinkRequest,
    ComplaintOut,
)
from app.services.audit_service import audit_service
from app.services.complaint_service import complaint_service

router = APIRouter(prefix="/complaints", tags=["complaints"])


def _complaint_out(c: Complaint) -> ComplaintOut:
    return ComplaintOut(
        id=c.id,
        created_at=c.created_at,
        updated_at=c.updated_at,
        complaint_number=c.complaint_number,
        source=c.source,
        status=c.status,
        fraud_type=c.fraud_type,
        amount=c.amount,
        reported_at=c.reported_at,
        victim_name=mask(c.victim_name, keep_last=1) if c.victim_name else None,
        victim_phone_masked=mask_phone(c.victim_phone) or None,
        victim_email_masked=mask_email(c.victim_email) or None,
        victim_account_masked=c.victim_account_masked,
        description=c.description,
        transaction_ref=c.transaction_ref,
        latitude=c.latitude,
        longitude=c.longitude,
        case_id=c.case_id,
        data_source=c.data_source,
    )


@router.post("", response_model=ComplaintOut, status_code=201)
@router.post("/", response_model=ComplaintOut, include_in_schema=False)
async def create_complaint(
    payload: ComplaintCreateRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(Permission.COMPLAINT_CREATE))],
) -> ComplaintOut:
    complaint = await complaint_service.ingest(session, payload=payload, actor=user)
    await session.commit()
    await audit_service.record(
        session,
        action=AuditAction.COMPLAINT_CREATE,
        actor_id=user.id,
        actor_email=user.email,
        actor_role=user.role_name.value,
        resource="complaint",
        resource_id=complaint.id,
        request_id=request.state.request_id or "",
    )
    await session.commit()
    await session.refresh(complaint)
    return _complaint_out(complaint)


@router.get("/{complaint_id}", response_model=ComplaintOut)
async def get_complaint(
    complaint_id: uuid.UUID,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(Permission.COMPLAINT_READ))],
) -> ComplaintOut:
    complaint = await complaint_service.get(session, complaint_id=complaint_id)
    await audit_service.record(
        session,
        action=AuditAction.COMPLAINT_READ,
        actor_id=user.id,
        actor_email=user.email,
        actor_role=user.role_name.value,
        resource="complaint",
        resource_id=complaint.id,
        request_id=request.state.request_id or "",
    )
    await session.commit()
    return _complaint_out(complaint)


@router.post("/{complaint_id}/link", response_model=ComplaintOut)
async def link_complaint(
    complaint_id: uuid.UUID,
    payload: ComplaintLinkRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(Permission.COMPLAINT_CREATE))],
) -> ComplaintOut:
    complaint = await complaint_service.get(session, complaint_id=complaint_id)
    complaint = await complaint_service.auto_link_to_case(
        session, complaint=complaint, case_id=payload.case_id
    )
    await session.commit()
    await session.refresh(complaint)
    return _complaint_out(complaint)


def _page(items: list[ComplaintOut], total: int, page: int, page_size: int) -> Page[ComplaintOut]:
    pages = max((total + page_size - 1) // page_size, 1) if total else 0
    return Page[ComplaintOut](
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
        has_next=page < pages,
    )


__all__ = ["router"]
