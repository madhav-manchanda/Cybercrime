"""Outcome feedback-loop endpoints (prediction ground-truth capture)."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.database import get_db
from app.core.enums import AuditAction, Permission
from app.models import User
from app.schemas.outcome import OutcomeCreateRequest, OutcomeOut
from app.services.audit_service import audit_service
from app.services.outcome_service import outcome_service

router = APIRouter(prefix="/cases", tags=["outcomes"])


@router.post("/{case_id}/outcomes", response_model=OutcomeOut, status_code=201)
async def record_outcome(
    case_id: uuid.UUID,
    payload: OutcomeCreateRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(Permission.OUTCOME_WRITE))],
) -> OutcomeOut:
    outcome = await outcome_service.record(session, case_id=case_id, payload=payload, actor=user)
    await session.commit()
    await session.refresh(outcome)
    await audit_service.record(
        session,
        action=AuditAction.OUTCOME_RECORD,
        actor_id=user.id,
        actor_email=user.email,
        actor_role=user.role_name.value,
        resource="outcome",
        resource_id=outcome.id,
        request_id=request.state.request_id or "",
    )
    await session.commit()
    return OutcomeOut.model_validate(outcome)


@router.get("/{case_id}/outcomes", response_model=list[OutcomeOut])
async def list_case_outcomes(
    case_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, Depends(require_permission(Permission.PREDICTION_READ))],
) -> list[OutcomeOut]:
    rows = await outcome_service.list_by_case(session, case_id=case_id)
    return [OutcomeOut.model_validate(o) for o in rows]


__all__ = ["router"]
