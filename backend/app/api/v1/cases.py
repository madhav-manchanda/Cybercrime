"""Case lifecycle endpoints: register, view, update, transition, delete, stats."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.database import get_db
from app.core.enums import AuditAction, CaseStatus, DataSource, Permission
from app.core.errors import BadRequestError
from app.models import Case, User
from app.schemas.case import (
    CaseCreateRequest,
    CaseOut,
    CaseStatistics,
    CaseSummary,
    CaseUpdateRequest,
)
from app.schemas.common import Page
from app.services.audit_service import audit_service
from app.services.case_service import case_service

router = APIRouter(prefix="/cases", tags=["cases"])


async def _case_out(session: AsyncSession, case: Case) -> CaseOut:
    counts = await case_service.counts_for(session, case.id)
    assigned = case.assigned_investigator.full_name if case.assigned_investigator else None
    return CaseOut.model_validate(
        {
            **{
                "id": case.id,
                "created_at": case.created_at,
                "updated_at": case.updated_at,
                "case_number": case.case_number,
                "title": case.title,
                "description": case.description,
                "status": case.status,
                "priority": case.priority,
                "fraud_type": case.fraud_type,
                "amount": case.amount,
                "complaint_source": case.complaint_source,
                "reported_at": case.reported_at,
                "opened_at": case.opened_at,
                "victim_name": case.victim_name,
                "victim_masked_phone": case.victim_masked_phone,
                "victim_masked_email": case.victim_masked_email,
                "victim_masked_account": case.victim_masked_account,
                "state": case.state,
                "district": case.district,
                "locality_note": case.locality_note,
                "latitude": case.latitude,
                "longitude": case.longitude,
                "current_risk_score": case.current_risk_score,
                "data_source": case.data_source,
                "assigned_investigator": assigned,
                "investigation_officer": case.investigating_officer_name,
                "is_open": case.is_open,
            },
            **counts,
        }
    )


@router.post("", response_model=CaseOut, status_code=201)
async def create_case(
    payload: CaseCreateRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(Permission.CASE_CREATE))],
) -> CaseOut:
    case = await case_service.create(session, payload=payload, actor=user)
    await session.commit()
    await audit_service.record(
        session,
        action=AuditAction.CASE_CREATE,
        actor_id=user.id,
        actor_email=user.email,
        actor_role=user.role_name.value,
        resource="case",
        resource_id=case.id,
        request_id=request.state.request_id or "",
    )
    out = await _case_out(session, case)
    await session.commit()
    await session.refresh(case)
    return out


@router.get("", response_model=Page[CaseOut])
@router.get("/", response_model=Page[CaseOut], include_in_schema=False)
async def list_cases(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, Depends(require_permission(Permission.CASE_READ))],
    page: int = 1,
    page_size: int = 50,
    status: CaseStatus | None = None,
    fraud_type: str | None = None,
    priority: str | None = None,
    min_risk: float | None = None,
    search: str | None = None,
    state: str | None = None,
    district: str | None = None,
    data_source: DataSource | None = None,
    assigned_to: uuid.UUID | None = None,
) -> Page[CaseOut]:
    rows, total = await case_service.list(
        session,
        page=page,
        page_size=page_size,
        status=status,
        fraud_type=fraud_type,
        priority=priority,
        min_risk=min_risk,
        search=search,
        state=state,
        district=district,
        data_source=data_source,
        assigned_to=assigned_to,
    )
    items = [await _case_out(session, c) for c in rows]
    return _page(items, total, page, page_size)


@router.get("/stats", response_model=CaseStatistics)
async def case_stats(
    session: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, Depends(require_permission(Permission.CASE_READ))],
) -> CaseStatistics:
    stats = await case_service.stats(session)
    return CaseStatistics(**stats)


@router.get("/summary", response_model=list[CaseSummary])
async def case_summary(
    session: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, Depends(require_permission(Permission.CASE_READ))],
    limit: int = 100,
) -> list[CaseSummary]:
    rows, _total = await case_service.list(session, page=1, page_size=min(limit, 200))
    from app.schemas.case import CaseSummary

    summaries: list[CaseSummary] = []
    for case in rows:
        assigned = case.assigned_investigator.full_name if case.assigned_investigator else None
        summaries.append(
            CaseSummary(
                id=case.id,
                case_number=case.case_number,
                title=case.title,
                status=case.status,
                priority=case.priority,
                fraud_type=case.fraud_type,
                amount=case.amount,
                reported_at=case.reported_at,
                current_risk_score=case.current_risk_score,
                assigned_investigator=assigned,
            )
        )
    return summaries


@router.get("/{case_id}", response_model=CaseOut)
async def get_case(
    case_id: uuid.UUID,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(Permission.CASE_READ))],
) -> CaseOut:
    case = await case_service.get(session, case_id=case_id)
    out = await _case_out(session, case)
    await session.commit()
    return out


@router.patch("/{case_id}", response_model=CaseOut)
async def update_case(
    case_id: uuid.UUID,
    payload: CaseUpdateRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(Permission.CASE_UPDATE))],
) -> CaseOut:
    case = await case_service.update(session, case_id=case_id, payload=payload, actor=user)
    await session.commit()
    await audit_service.record(
        session,
        action=AuditAction.CASE_UPDATE,
        actor_id=user.id,
        actor_email=user.email,
        actor_role=user.role_name.value,
        resource="case",
        resource_id=case.id,
        request_id=request.state.request_id or "",
    )
    out = await _case_out(session, case)
    await session.commit()
    return out


@router.post("/{case_id}/status", response_model=CaseOut)
async def transition_case(
    case_id: uuid.UUID,
    payload: dict,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(Permission.CASE_UPDATE))],
) -> CaseOut:
    target_raw = payload.get("status")
    if not target_raw or target_raw not in {s.value for s in CaseStatus}:
        raise BadRequestError("A valid target status is required.", code="INVALID_STATUS")
    case = await case_service.get(session, case_id=case_id)
    case = await case_service.transition(
        session,
        case=case,
        target=CaseStatus(target_raw),
        actor=user,
        description=payload.get("description"),
    )
    await session.commit()
    out = await _case_out(session, case)
    await session.commit()
    return out


@router.delete("/{case_id}", response_model=dict)
async def delete_case(
    case_id: uuid.UUID,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(Permission.CASE_DELETE))],
) -> dict:
    await case_service.delete(session, case_id=case_id, actor=user)
    await session.commit()
    await audit_service.record(
        session,
        action=AuditAction.CASE_DELETE,
        actor_id=user.id,
        actor_email=user.email,
        actor_role=user.role_name.value,
        resource="case",
        resource_id=str(case_id),
        request_id=request.state.request_id or "",
    )
    await session.commit()
    return {"message": "Case deleted."}


@router.get("/{case_id}/counts", response_model=dict)
async def case_counts(
    case_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, Depends(require_permission(Permission.CASE_READ))],
) -> dict:
    await case_service.get(session, case_id=case_id)
    return await case_service.counts_for(session, case_id)


def _page(items: list[CaseOut], total: int, page: int, page_size: int) -> Page[CaseOut]:
    pages = max((total + page_size - 1) // page_size, 1) if total else 0
    return Page[CaseOut](
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
        has_next=page < pages,
    )


__all__ = ["router"]
