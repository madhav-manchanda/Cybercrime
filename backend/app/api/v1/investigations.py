"""Investigation timeline + intervention simulation/execution endpoints."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.database import get_db
from app.core.enums import AuditAction, Permission
from app.core.errors import BadRequestError
from app.models import Intervention, User
from app.schemas.investigation import (
    InterventionExecuteRequest,
    InterventionOut,
    InterventionSimulateRequest,
    InvestigationEventCreate,
    InvestigationEventOut,
)
from app.services.audit_service import audit_service
from app.services.case_service import case_service
from app.services.investigation_service import investigation_service
from app.services.simulation_service import simulation_service

router = APIRouter(prefix="/cases", tags=["investigations"])


@router.get("/{case_id}/timeline", response_model=list[InvestigationEventOut])
async def case_timeline(
    case_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, Depends(require_permission(Permission.INVESTIGATION_READ))],
) -> list[InvestigationEventOut]:
    await case_service.get(session, case_id=case_id)
    events = await investigation_service.timeline(session, case_id=case_id)
    return [InvestigationEventOut.model_validate(e.as_timeline) for e in events]


@router.post("/{case_id}/events", response_model=InvestigationEventOut, status_code=201)
async def add_investigation_event(
    case_id: uuid.UUID,
    payload: InvestigationEventCreate,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(Permission.INVESTIGATION_WRITE))],
) -> InvestigationEventOut:
    await case_service.get(session, case_id=case_id)
    event = await investigation_service.add_event(
        session,
        case_id=case_id,
        event_type=payload.event_type,
        actor=user,
        description=payload.description,
        metadata=payload.metadata,
        occurred_at=payload.occurred_at,
    )
    await session.commit()
    await session.refresh(event)
    await audit_service.record(
        session,
        action=AuditAction.INVESTIGATION_EVENT_CREATE,
        actor_id=user.id,
        actor_email=user.email,
        actor_role=user.role_name.value,
        resource="case",
        resource_id=case_id,
        request_id=request.state.request_id or "",
    )
    await session.commit()
    return InvestigationEventOut.model_validate(event.as_timeline)


@router.post("/{case_id}/simulate", response_model=InterventionOut, status_code=201)
async def simulate_intervention(
    case_id: uuid.UUID,
    payload: InterventionSimulateRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(Permission.SIMULATION_RUN))],
) -> InterventionOut:
    if payload.case_id != case_id:
        raise BadRequestError(
            "case_id in the body must match the URL path",
            code="CASE_MISMATCH",
        )
    intervention = await simulation_service.simulate(
        session,
        case_id=case_id,
        intervention_type=payload.intervention_type,
        actor=user,
        prediction_id=payload.prediction_id,
        notes=payload.notes,
    )
    await session.commit()
    await session.refresh(intervention)
    await audit_service.record(
        session,
        action=AuditAction.SIMULATION_RUN,
        actor_id=user.id,
        actor_email=user.email,
        actor_role=user.role_name.value,
        resource="intervention",
        resource_id=intervention.id,
        payload={"intervention_type": payload.intervention_type},
        request_id=request.state.request_id or "",
    )
    await session.commit()
    return InterventionOut.model_validate(intervention)


@router.get("/{case_id}/interventions", response_model=list[InterventionOut])
async def case_interventions(
    case_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, Depends(require_permission(Permission.SIMULATION_RUN))],
) -> list[InterventionOut]:
    await case_service.get(session, case_id=case_id)
    rows: list[Intervention] = await simulation_service.list_by_case(session, case_id=case_id)
    return [InterventionOut.model_validate(i) for i in rows]


@router.post("/interventions/{intervention_id}/approve", response_model=InterventionOut)
async def approve_intervention(
    intervention_id: uuid.UUID,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(Permission.SIMULATION_RUN))],
) -> InterventionOut:
    intervention = await simulation_service.approve(session, intervention_id=intervention_id, actor=user)
    await session.commit()
    await session.refresh(intervention)
    await audit_service.record(
        session,
        action=AuditAction.INTERVENTION_APPROVE,
        actor_id=user.id,
        actor_email=user.email,
        actor_role=user.role_name.value,
        resource="intervention",
        resource_id=intervention.id,
        request_id=request.state.request_id or "",
    )
    await session.commit()
    return InterventionOut.model_validate(intervention)


@router.post("/interventions/{intervention_id}/execute", response_model=InterventionOut)
async def execute_intervention(
    intervention_id: uuid.UUID,
    payload: InterventionExecuteRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(Permission.SIMULATION_RUN))],
) -> InterventionOut:
    intervention = await simulation_service.execute(
        session, intervention_id=intervention_id, actor=user, note=payload.note
    )
    await session.commit()
    await session.refresh(intervention)
    await audit_service.record(
        session,
        action=AuditAction.INTERVENTION_EXECUTE,
        actor_id=user.id,
        actor_email=user.email,
        actor_role=user.role_name.value,
        resource="intervention",
        resource_id=intervention.id,
        request_id=request.state.request_id or "",
    )
    await session.commit()
    return InterventionOut.model_validate(intervention)


__all__ = ["router"]
