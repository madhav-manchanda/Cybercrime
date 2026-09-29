"""Alert lifecycle: creation (with realtime fan-out), acknowledge, resolve."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import (
    AlertSeverity,
    AlertStatus,
    AlertType,
    AuditAction,
    InvestigationEventType,
    RealtimeEventType,
)
from app.core.errors import ALERT_NOT_FOUND, BadRequestError
from app.models import Alert, User
from app.services.audit_service import audit_service
from app.services.investigation_service import investigation_service
from app.services.realtime_service import event_hub
from app.utils.validators import as_str


class AlertService:
    """Create, list, acknowledge and resolve alerts."""

    async def create(
        self,
        session: AsyncSession,
        *,
        alert_type: AlertType,
        severity: AlertSeverity,
        title: str,
        description: str | None = None,
        metadata_json: dict[str, Any] | None = None,
        risk_score: float | None = None,
        case_id: uuid.UUID | None = None,
        prediction_id: uuid.UUID | None = None,
        atm_id: uuid.UUID | None = None,
    ) -> Alert:
        alert = Alert(
            alert_type=alert_type,
            severity=severity,
            status=AlertStatus.OPEN,
            title=title,
            description=description,
            metadata_json=metadata_json or {},
            risk_score=risk_score,
            case_id=case_id,
            prediction_id=prediction_id,
            atm_id=atm_id,
        )
        session.add(alert)
        await session.flush()

        if case_id:
            await event_hub.publish(
                RealtimeEventType.ALERT_CREATED,
                {
                    "alert_id": str(alert.id),
                    "case_id": str(case_id),
                    "type": alert_type.value if hasattr(alert_type, "value") else str(alert_type),
                    "severity": severity.value if hasattr(severity, "value") else str(severity),
                    "title": title,
                },
            )
        return alert

    async def get(self, session: AsyncSession, *, alert_id: uuid.UUID) -> Alert:
        alert = await session.get(Alert, alert_id)
        if alert is None:
            raise ALERT_NOT_FOUND
        return alert

    async def list(
        self,
        session: AsyncSession,
        *,
        status: AlertStatus | None = None,
        severity: AlertSeverity | None = None,
        alert_type: AlertType | None = None,
        case_id: uuid.UUID | None = None,
        actor_id: uuid.UUID | None = None,
        page: int = 1,
        page_size: int = 50,
        sort: str = "created_at",
    ) -> tuple[list[Alert], int]:
        query = select(Alert)
        if status:
            query = query.where(
                Alert.status == status.value if hasattr(status, "value") else Alert.status == str(status)
            )
        if severity:
            query = query.where(
                Alert.severity == severity.value
                if hasattr(severity, "value")
                else Alert.severity == str(severity)
            )
        if alert_type:
            query = query.where(
                Alert.alert_type == alert_type.value
                if hasattr(alert_type, "value")
                else Alert.alert_type == str(alert_type)
            )
        if case_id:
            query = query.where(Alert.case_id == case_id)
        if actor_id:
            query = query.where(Alert.acknowledged_by == actor_id)
        total = await session.scalar(select(func.count()).select_from(query.subquery())) or 0
        order = Alert.created_at.desc() if sort == "created_at" else Alert.risk_score.desc()
        rows = (
            await session.scalars(query.order_by(order).offset((page - 1) * page_size).limit(page_size))
        ).all()
        return list(rows), int(total)

    async def acknowledge(
        self, session: AsyncSession, *, alert_id: uuid.UUID, actor: User, note: str | None = None
    ) -> Alert:
        alert = await self.get(session, alert_id=alert_id)
        if alert.status in {AlertStatus.RESOLVED, AlertStatus.DISMISSED}:
            raise BadRequestError("Resolved alerts cannot be acknowledged.", code="ALERT_NOT_OPEN")
        alert.status = AlertStatus.ACKNOWLEDGED
        alert.acknowledged_by = actor.id
        alert.acknowledged_at = datetime.now(UTC)
        if note:
            alert.metadata_json = {**alert.metadata_json, "acknowledgement_note": note}

        if alert.case_id:
            await investigation_service.add_event(
                session,
                case_id=alert.case_id,
                event_type=InvestigationEventType.ALERT_ACKNOWLEDGED,
                actor=actor,
                description=f"Alert acknowledged: {alert.title}",
                metadata={"alert_id": str(alert.id), "note": note},
            )
        await audit_service.record(
            session,
            action=AuditAction.ALERT_ACKNOWLEDGE,
            actor_id=actor.id,
            actor_email=actor.email,
            actor_role=actor.role_name.value,
            resource="alert",
            resource_id=alert.id,
            payload={"note": note, "severity": as_str(alert.severity)},
        )
        await session.flush()
        await event_hub.publish(
            RealtimeEventType.ALERT_ACKNOWLEDGED,
            {"alert_id": str(alert.id), "case_id": str(alert.case_id) if alert.case_id else None},
        )
        return alert

    async def resolve(
        self, session: AsyncSession, *, alert_id: uuid.UUID, actor: User, note: str | None = None
    ) -> Alert:
        alert = await self.get(session, alert_id=alert_id)
        alert.status = AlertStatus.RESOLVED
        alert.resolved_by = actor.id
        alert.resolved_at = datetime.now(UTC)
        if note:
            alert.metadata_json = {**alert.metadata_json, "resolution_note": note}

        if alert.case_id:
            await investigation_service.add_event(
                session,
                case_id=alert.case_id,
                event_type=InvestigationEventType.NOTE_ADDED,
                actor=actor,
                description=f"Alert resolved: {alert.title}",
                metadata={"alert_id": str(alert.id), "note": note},
            )
        await audit_service.record(
            session,
            action=AuditAction.ALERT_RESOLVE,
            actor_id=actor.id,
            actor_email=actor.email,
            actor_role=actor.role_name.value,
            resource="alert",
            resource_id=alert.id,
        )
        await session.flush()
        await event_hub.publish(
            RealtimeEventType.ALERT_RESOLVED,
            {"alert_id": str(alert.id), "case_id": str(alert.case_id) if alert.case_id else None},
        )
        return alert


alert_service: AlertService = AlertService()

__all__ = ["AlertService", "alert_service"]
