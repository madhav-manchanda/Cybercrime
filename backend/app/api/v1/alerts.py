"""Alert endpoints: create, list, view, acknowledge, resolve."""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.database import get_db
from app.core.enums import (
    AlertSeverity,
    AlertStatus,
    AlertType,
    AuditAction,
    Permission,
)
from app.core.errors import BadRequestError
from app.models import User
from app.schemas.alert import (
    AlertAckRequest,
    AlertOut,
    AlertResolveRequest,
)
from app.schemas.common import Page
from app.services.alert_service import alert_service
from app.services.audit_service import audit_service

router = APIRouter(prefix="/alerts", tags=["alerts"])


def _enum_field(name: str, enum_class: type, value: Any, *, required: bool) -> Any:
    if value is None:
        if required:
            raise BadRequestError(f"{name} is required", code="MISSING_FIELD")
        return None
    try:
        return enum_class(value)
    except (ValueError, TypeError):
        raise BadRequestError(f"Invalid {name}: {value!r}", code="INVALID_ENUM") from None


@router.post("", response_model=AlertOut, status_code=201)
@router.post("/", response_model=AlertOut, include_in_schema=False)
async def create_alert(
    payload: dict,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(Permission.ALERT_WRITE))],
) -> AlertOut:
    alert_type = _enum_field("alert_type", AlertType, payload.get("alert_type"), required=True)
    severity = _enum_field("severity", AlertSeverity, payload.get("severity"), required=True)
    title = payload.get("title")
    if not isinstance(title, str) or not title.strip():
        raise BadRequestError("title is required", code="MISSING_FIELD")
    case_id = _uuid_or_none(payload.get("case_id"), "case_id")
    prediction_id = _uuid_or_none(payload.get("prediction_id"), "prediction_id")
    atm_id = _uuid_or_none(payload.get("atm_id"), "atm_id")
    risk_score = payload.get("risk_score")
    try:
        risk_score = float(risk_score) if risk_score is not None else None
    except (ValueError, TypeError):
        raise BadRequestError("risk_score must be a number", code="INVALID_RISK") from None
    alert = await alert_service.create(
        session,
        alert_type=alert_type,
        severity=severity,
        title=title,
        description=payload.get("description"),
        metadata_json=payload.get("metadata") or payload.get("metadata_json"),
        risk_score=risk_score,
        case_id=case_id,
        prediction_id=prediction_id,
        atm_id=atm_id,
    )
    await session.commit()
    await session.refresh(alert)
    return AlertOut.model_validate(alert)


@router.get("", response_model=Page[AlertOut])
@router.get("/", response_model=Page[AlertOut], include_in_schema=False)
async def list_alerts(
    session: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, Depends(require_permission(Permission.ALERT_READ))],
    status: AlertStatus | None = None,
    severity: AlertSeverity | None = None,
    alert_type: AlertType | None = None,
    case_id: uuid.UUID | None = None,
    page: int = 1,
    page_size: int = 50,
    sort: str = "created_at",
) -> Page[AlertOut]:
    rows, total = await alert_service.list(
        session,
        status=status,
        severity=severity,
        alert_type=alert_type,
        case_id=case_id,
        page=max(page, 1),
        page_size=min(max(page_size, 1), 200),
        sort=sort,
    )
    items = [AlertOut.model_validate(a) for a in rows]
    pages = max((total + page_size - 1) // page_size, 1) if total else 0
    return Page[AlertOut](
        items=items,
        total=total,
        page=max(page, 1),
        page_size=page_size,
        pages=pages,
        has_next=page < pages,
    )


@router.get("/{alert_id}", response_model=AlertOut)
async def get_alert(
    alert_id: uuid.UUID,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(Permission.ALERT_READ))],
) -> AlertOut:
    alert = await alert_service.get(session, alert_id=alert_id)
    await audit_service.record(
        session,
        action=AuditAction.ALERT_READ,
        actor_id=user.id,
        actor_email=user.email,
        actor_role=user.role_name.value,
        resource="alert",
        resource_id=alert.id,
        request_id=request.state.request_id or "",
    )
    await session.commit()
    return AlertOut.model_validate(alert)


@router.post("/{alert_id}/acknowledge", response_model=AlertOut)
async def acknowledge_alert(
    alert_id: uuid.UUID,
    payload: AlertAckRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(Permission.ALERT_WRITE))],
) -> AlertOut:
    alert = await alert_service.acknowledge(session, alert_id=alert_id, actor=user, note=payload.note)
    await session.commit()
    await session.refresh(alert)
    return AlertOut.model_validate(alert)


@router.post("/{alert_id}/resolve", response_model=AlertOut)
async def resolve_alert(
    alert_id: uuid.UUID,
    payload: AlertResolveRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(Permission.ALERT_WRITE))],
) -> AlertOut:
    alert = await alert_service.resolve(session, alert_id=alert_id, actor=user, note=payload.note)
    await session.commit()
    await session.refresh(alert)
    return AlertOut.model_validate(alert)


def _uuid_or_none(value: Any, name: str) -> uuid.UUID | None:
    if value in (None, ""):
        return None
    try:
        return uuid.UUID(str(value))
    except ValueError:
        raise BadRequestError(f"{name} must be a valid UUID", code="INVALID_UUID") from None


__all__ = ["router"]
