"""Transaction ingestion, retrieval, and case feature-vector endpoints."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.database import get_db
from app.core.enums import AuditAction, Permission
from app.models import User
from app.schemas.common import Page
from app.schemas.transaction import TransactionCreateRequest, TransactionOut
from app.services.audit_service import audit_service
from app.services.transaction_service import transaction_service

router = APIRouter(prefix="/transactions", tags=["transactions"])


@router.post("", response_model=TransactionOut, status_code=201)
@router.post("/", response_model=TransactionOut, include_in_schema=False)
async def create_transaction(
    payload: TransactionCreateRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(Permission.TRANSACTION_CREATE))],
) -> TransactionOut:
    txn = await transaction_service.create(session, payload=payload, actor=user)
    await session.commit()
    await audit_service.record(
        session,
        action=AuditAction.TRANSACTION_CREATE,
        actor_id=user.id,
        actor_email=user.email,
        actor_role=user.role_name.value,
        resource="transaction",
        resource_id=txn.id,
        request_id=request.state.request_id or "",
    )
    await session.commit()
    await session.refresh(txn)
    return TransactionOut.model_validate(txn)


@router.get("/{transaction_id}", response_model=TransactionOut)
async def get_transaction(
    transaction_id: uuid.UUID,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(Permission.TRANSACTION_READ))],
) -> TransactionOut:
    txn = await transaction_service.get(session, transaction_id=transaction_id)
    await audit_service.record(
        session,
        action=AuditAction.TRANSACTION_READ,
        actor_id=user.id,
        actor_email=user.email,
        actor_role=user.role_name.value,
        resource="transaction",
        resource_id=txn.id,
        request_id=request.state.request_id or "",
    )
    await session.commit()
    return TransactionOut.model_validate(txn)


@router.get("/cases/{case_id}", response_model=Page[TransactionOut])
async def list_case_transactions(
    case_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, Depends(require_permission(Permission.TRANSACTION_READ))],
    page: int = 1,
    page_size: int = 100,
) -> Page[TransactionOut]:
    rows, total = await transaction_service.list_by_case(
        session, case_id=case_id, page=max(page, 1), page_size=min(max(page_size, 1), 500)
    )
    items = [TransactionOut.model_validate(t) for t in rows]
    pages = max((total + page_size - 1) // page_size, 1) if total else 0
    return Page[TransactionOut](
        items=items,
        total=total,
        page=max(page, 1),
        page_size=page_size,
        pages=pages,
        has_next=page < pages,
    )


@router.get("/cases/{case_id}/feature-vector", response_model=dict)
async def case_feature_vector(
    case_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, Depends(require_permission(Permission.ENTITY_READ))],
) -> dict:
    return await transaction_service.case_feature_vector(session, case_id=case_id)


__all__ = ["router"]
