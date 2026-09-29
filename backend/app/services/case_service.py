"""Case lifecycle service (CRUD + status transitions)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.enums import (
    AuditAction,
    CaseStatus,
    DataSource,
    InvestigationEventType,
)
from app.core.errors import CASE_NOT_FOUND, BadRequestError
from app.models import (
    Alert,
    Case,
    Complaint,
    InvestigationEvent,
    Prediction,
    Transaction,
    User,
)
from app.schemas.case import CaseCreateRequest, CaseUpdateRequest
from app.services.audit_service import audit_service
from app.services.realtime_service import event_hub
from app.utils.validators import as_enum, as_str, utc_aware

_VALID_TRANSITIONS: dict[CaseStatus, set[CaseStatus]] = {
    CaseStatus.NEW: {
        CaseStatus.PREDICTION_ACTIVE,
        CaseStatus.UNDER_ANALYSIS,
        CaseStatus.INVESTIGATION_ACTIVE,
        CaseStatus.RESOLVED,
        CaseStatus.CLOSED,
    },
    CaseStatus.UNDER_ANALYSIS: {
        CaseStatus.PREDICTION_ACTIVE,
        CaseStatus.ALERTED,
        CaseStatus.INVESTIGATION_ACTIVE,
        CaseStatus.RESOLVED,
        CaseStatus.CLOSED,
    },
    CaseStatus.PREDICTION_ACTIVE: {
        CaseStatus.ALERTED,
        CaseStatus.INVESTIGATION_ACTIVE,
        CaseStatus.RESOLVED,
        CaseStatus.CLOSED,
        CaseStatus.UNDER_ANALYSIS,
    },
    CaseStatus.ALERTED: {
        CaseStatus.INVESTIGATION_ACTIVE,
        CaseStatus.RESOLVED,
        CaseStatus.CLOSED,
        CaseStatus.PREDICTION_ACTIVE,
    },
    CaseStatus.INVESTIGATION_ACTIVE: {
        CaseStatus.INVESTIGATION_ACTIVE,
        CaseStatus.RESOLVED,
        CaseStatus.CLOSED,
        CaseStatus.ALERTED,
    },
    CaseStatus.RESOLVED: {CaseStatus.CLOSED, CaseStatus.INVESTIGATION_ACTIVE},
    CaseStatus.CLOSED: set(),
}

_SEED = 0


def _next_case_number() -> str:
    """Deterministic, unique-ish case number using timestamp + random."""
    global _SEED
    _SEED += 1
    suffix = (int(datetime.now(UTC).timestamp() * 1000)) % 1_000_000_000
    return f"CC-{suffix}-{_SEED % 1000:03d}"


class CaseService:
    """Owns case create/read/update/list logic plus status transitions."""

    async def create(
        self,
        session: AsyncSession,
        *,
        payload: CaseCreateRequest,
        actor: User,
    ) -> Case:
        from app.core.security import mask, mask_phone

        reported_at = utc_aware(payload.reported_at) if payload.reported_at else datetime.now(UTC)
        location = payload.location
        case = Case(
            case_number=_next_case_number(),
            title=payload.title,
            description=payload.description,
            fraud_type=payload.fraud_type,
            priority=payload.priority,
            amount=payload.amount,
            complaint_source=payload.complaint_source,
            reported_at=reported_at,
            opened_at=datetime.now(UTC),
            state=payload.state,
            district=payload.district,
            locality_note=payload.locality_note,
            latitude=location.latitude if location else None,
            longitude=location.longitude if location else None,
            data_source=payload.data_source,
            status=CaseStatus.NEW,
            assigned_user_id=actor.id,
            investigating_officer_name=actor.full_name,
            victim_name=mask(payload.victim.name, keep_last=2)
            if payload.victim and payload.victim.name
            else None,
            victim_masked_phone=mask_phone(payload.victim.phone)
            if payload.victim and payload.victim.phone
            else None,
            victim_masked_email=payload.victim.email if payload.victim and payload.victim.email else None,
            victim_masked_account=mask(payload.victim.account_number)
            if payload.victim and payload.victim.account_number
            else None,
        )
        session.add(case)
        await session.flush()

        session.add(
            InvestigationEvent(
                case_id=case.id,
                event_type=InvestigationEventType.COMPLAINT_RECEIVED,
                role=actor.role_name.value,
                description="Case opened",
                actor_id=actor.id,
                metadata_json={"case_number": case.case_number},
            )
        )
        await audit_service.record(
            session,
            action=AuditAction.CASE_CREATE,
            actor_id=actor.id,
            actor_email=actor.email,
            actor_role=actor.role_name.value,
            resource="case",
            resource_id=case.id,
            payload={"case_number": case.case_number, "fraud_type": as_str(payload.fraud_type)},
        )
        await session.flush()
        await event_hub.publish("case.created", {"case_id": str(case.id), "case_number": case.case_number})
        return case

    async def get(self, session: AsyncSession, *, case_id: uuid.UUID) -> Case:
        case = await session.scalar(
            select(Case)
            .options(selectinload(Case.assigned_investigator))
            .where(Case.id == case_id)
        )
        if case is None:
            raise CASE_NOT_FOUND
        return case

    async def list(
        self,
        session: AsyncSession,
        *,
        page: int = 1,
        page_size: int = 50,
        status: CaseStatus | None = None,
        priority: Any | None = None,
        fraud_type: Any | None = None,
        min_risk: float | None = None,
        assigned_to: uuid.UUID | None = None,
        search: str | None = None,
        state: str | None = None,
        district: str | None = None,
        data_source: DataSource | None = None,
    ) -> tuple[list[Case], int]:
        query = select(Case).options(selectinload(Case.assigned_investigator))
        if status:
            query = query.where(
                Case.status == status.value if hasattr(status, "value") else Case.status == str(status)
            )
        if priority:
            query = query.where(
                Case.priority == priority.value
                if hasattr(priority, "value")
                else Case.priority == str(priority)
            )
        if fraud_type:
            query = query.where(
                Case.fraud_type == fraud_type.value
                if hasattr(fraud_type, "value")
                else Case.fraud_type == str(fraud_type)
            )
        if min_risk is not None:
            query = query.where(Case.current_risk_score >= min_risk)
        if assigned_to:
            query = query.where(Case.assigned_user_id == assigned_to)
        if state:
            query = query.where(Case.state == state)
        if district:
            query = query.where(Case.district == district)
        if data_source:
            query = query.where(Case.data_source == data_source)
        if search:
            like = f"%{search.lower()}%"
            query = query.where(
                (func.lower(Case.case_number).like(like))
                | (func.lower(Case.title).like(like))
                | (func.coalesce(func.lower(Case.victim_name), "").like(like))
            )
        total = await session.scalar(select(func.count()).select_from(query.subquery())) or 0
        query = query.order_by(Case.opened_at.desc()).offset((page - 1) * page_size).limit(page_size)
        rows = (await session.scalars(query)).all()
        return list(rows), int(total)

    async def update(
        self,
        session: AsyncSession,
        *,
        case_id: uuid.UUID,
        payload: CaseUpdateRequest,
        actor: User,
    ) -> Case:
        case = await self.get(session, case_id=case_id)
        data = payload.model_dump(exclude_unset=True)
        new_status = data.get("status")
        if new_status:
            data.pop("status")
            await self.transition(session, case=case, target=new_status, actor=actor)

        for key, value in data.items():
            if key == "location":
                if value is not None:
                    case.latitude = value.latitude
                    case.longitude = value.longitude
                    case.location = None
            else:
                setattr(case, key, value)

        if data.get("assigned_user_id"):
            user = await session.get(User, data["assigned_user_id"])
            if user:
                case.assigned_investigator = user
                case.investigating_officer_name = user.full_name
            elif not data.get("investigating_officer_name"):
                case.investigating_officer_name = None

        session.add(
            InvestigationEvent(
                case_id=case.id,
                event_type=InvestigationEventType.CASE_STATUS_CHANGED,
                role=actor.role_name.value,
                description="Case details updated",
                actor_id=actor.id,
                metadata_json={"changed_fields": list(data.keys())},
            )
        )
        await audit_service.record(
            session,
            action=AuditAction.CASE_UPDATE,
            actor_id=actor.id,
            actor_email=actor.email,
            actor_role=actor.role_name.value,
            resource="case",
            resource_id=case.id,
            payload={"fields": list(data.keys())},
        )
        await session.flush()
        await event_hub.publish("case.updated", {"case_id": str(case.id)})
        return case

    async def transition(
        self,
        session: AsyncSession,
        *,
        case: Case,
        target: CaseStatus,
        actor: User,
        description: str | None = None,
    ) -> Case:
        current = as_enum(case.status, CaseStatus)
        allowed = _VALID_TRANSITIONS.get(current, set())
        if target not in allowed:
            raise BadRequestError(
                f"Invalid status transition {current.value} -> {target.value}",
                code="INVALID_STATUS_TRANSITION",
                details={
                    "from": current.value,
                    "to": target.value,
                    "allowed": sorted(x.value for x in allowed),
                },
            )
        previous = current
        case.status = as_str(target)  # type: ignore[assignment]
        session.add(
            InvestigationEvent(
                case_id=case.id,
                event_type=InvestigationEventType.CASE_STATUS_CHANGED,
                role=actor.role_name.value,
                description=description or f"Status changed {previous.value} -> {target.value}",
                actor_id=actor.id,
                metadata_json={"from": previous.value, "to": target.value},
            )
        )
        await session.flush()
        return case

    async def delete(self, session: AsyncSession, *, case_id: uuid.UUID, actor: User) -> None:
        case = await self.get(session, case_id=case_id)
        await audit_service.record(
            session,
            action=AuditAction.CASE_DELETE,
            actor_id=actor.id,
            actor_email=actor.email,
            actor_role=actor.role_name.value,
            resource="case",
            resource_id=case.id,
            payload={"case_number": case.case_number},
        )
        await session.delete(case)
        await session.flush()

    # -------------------------------------------------------- enrichments
    async def stats(self, session: AsyncSession) -> dict[str, Any]:
        by_status = dict(
            (await session.execute(select(Case.status, func.count()).group_by(Case.status))).all()
        )
        by_priority = dict(
            (await session.execute(select(Case.priority, func.count()).group_by(Case.priority))).all()
        )
        by_fraud = dict(
            (await session.execute(select(Case.fraud_type, func.count()).group_by(Case.fraud_type))).all()
        )
        total_exposed = await session.scalar(select(func.coalesce(func.sum(Case.amount), 0.0)))
        return {
            "total": sum(by_status.values()),
            "open": sum(v for k, v in by_status.items() if k in CaseStatus.open_states()),
            "by_status": by_status,
            "by_priority": by_priority,
            "by_fraud_type": by_fraud,
            "exposed_amount_total": float(total_exposed or 0.0),
        }

    async def counts_for(self, session: AsyncSession, case_id: uuid.UUID) -> dict[str, int]:
        complaints = await session.scalar(
            select(func.count()).select_from(Complaint).where(Complaint.case_id == case_id)
        )
        transactions = await session.scalar(
            select(func.count()).select_from(Transaction).where(Transaction.case_id == case_id)
        )
        predictions = await session.scalar(
            select(func.count()).select_from(Prediction).where(Prediction.case_id == case_id)
        )
        alerts = await session.scalar(select(func.count()).select_from(Alert).where(Alert.case_id == case_id))
        return {
            "complaint_count": int(complaints or 0),
            "transaction_count": int(transactions or 0),
            "prediction_count": int(predictions or 0),
            "alert_count": int(alerts or 0),
        }


case_service: CaseService = CaseService()

__all__ = ["CaseService", "case_service"]
