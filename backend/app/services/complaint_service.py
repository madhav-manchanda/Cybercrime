"""Complaint ingestion + auto case-linking service."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import (
    AuditAction,
    CaseStatus,
    ComplaintStatus,
    DataSource,
    FraudType,
    RealtimeEventType,
)
from app.core.errors import (
    COMPLAINT_NOT_FOUND,
    BadRequestError,
)
from app.core.security import mask, mask_phone
from app.models import Complaint, User
from app.schemas.complaint import ComplaintCreateRequest
from app.services.audit_service import audit_service
from app.services.realtime_service import event_hub
from app.utils.validators import utc_aware


def _next_complaint_number() -> str:
    return f"NCRP-{int(datetime.now(UTC).timestamp() * 1000) % 100_000_000:08d}"


class ComplaintService:
    """Validates, masks and persists complaints; links them to cases."""

    async def ingest(
        self,
        session: AsyncSession,
        *,
        payload: ComplaintCreateRequest,
        actor: User,
    ) -> Complaint:
        data_source = (
            DataSource(payload.data_source) if isinstance(payload.data_source, str) else payload.data_source
        )
        fraud_type = (
            FraudType(payload.fraud_type) if isinstance(payload.fraud_type, str) else payload.fraud_type
        )
        reported_at = utc_aware(payload.reported_at) if payload.reported_at else datetime.now(UTC)
        location = payload.location
        existing_ref = None
        if payload.transaction_ref:
            existing_ref = await session.scalar(
                select(Complaint).where(Complaint.transaction_ref == payload.transaction_ref)
            )
            if existing_ref is not None:
                raise BadRequestError(
                    "A complaint with this transaction reference already exists.",
                    code="DUPLICATE_COMPLAINT",
                )

        complaint = Complaint(
            complaint_number=_next_complaint_number(),
            source=payload.source,
            status=ComplaintStatus.RECEIVED,
            fraud_type=fraud_type,
            amount=payload.amount,
            reported_at=reported_at,
            victim_name=mask(payload.victim_name, keep_last=2) if payload.victim_name else None,
            victim_phone=mask_phone(payload.victim_phone) if payload.victim_phone else None,
            victim_email=payload.victim_email,
            victim_account_masked=mask(payload.victim_account) if payload.victim_account else None,
            victim_address=payload.victim_address,
            description=payload.description,
            transaction_ref=payload.transaction_ref,
            bank_ref=payload.bank_ref,
            ip_address=payload.ip_address,
            device_info=payload.device_info,
            upi_ref=payload.upi_ref,
            latitude=location.latitude if location else None,
            longitude=location.longitude if location else None,
            data_source=data_source,
        )
        session.add(complaint)
        await session.flush()

        if complaint.case_id is None and data_source.value == "operational":
            await self.try_auto_link(session, complaint)

        await audit_service.record(
            session,
            action=AuditAction.COMPLAINT_CREATE,
            actor_id=actor.id,
            actor_email=actor.email,
            actor_role=actor.role_name.value,
            resource="complaint",
            resource_id=complaint.id,
            payload={
                "complaint_number": complaint.complaint_number,
                "fraud_type": fraud_type.value,
                "amount": payload.amount,
            },
        )
        await session.flush()
        await event_hub.publish(
            RealtimeEventType.COMPLAINT_CREATED,
            {"complaint_id": str(complaint.id), "amount": complaint.amount},
        )
        return complaint

    async def try_auto_link(self, session: AsyncSession, complaint: Complaint) -> None:
        """Link the complaint to an existing case sharing a victim phone/account.

        Deliberately conservative: it only matches on the **masked** identifier
        already stored, so it never compares raw PII across the boundary.
        """
        if not (complaint.victim_phone or complaint.victim_account_masked):
            return
        from app.models import Case

        rows = await session.scalars(
            select(Case).where(Case.status.in_([s.value for s in CaseStatus.open_states()]))
        )
        for case in rows:
            phone_match = (
                case.victim_masked_phone
                and complaint.victim_phone
                and case.victim_masked_phone == complaint.victim_phone
            )
            account_match = (
                case.victim_masked_account
                and complaint.victim_account_masked
                and case.victim_masked_account.endswith(complaint.victim_account_masked[-4:])
            )
            if phone_match or account_match:
                complaint.case_id = case.id
                complaint.status = ComplaintStatus.REFERRED
                break

    async def auto_link_to_case(
        self, session: AsyncSession, *, complaint: Complaint, case_id: uuid.UUID
    ) -> Complaint:
        if complaint.case_id is not None and complaint.case_id != case_id:
            raise BadRequestError(
                "Complaint is already linked to another case.", code="COMPLAINT_ALREADY_LINKED"
            )
        complaint.case_id = case_id
        complaint.status = ComplaintStatus.REFERRED
        await session.flush()
        return complaint

    async def get(self, session: AsyncSession, *, complaint_id: uuid.UUID) -> Complaint:
        complaint = await session.get(Complaint, complaint_id)
        if complaint is None:
            raise COMPLAINT_NOT_FOUND
        return complaint

    async def list_by_case(self, session: AsyncSession, *, case_id: uuid.UUID) -> list[Complaint]:
        rows = await session.scalars(
            select(Complaint).where(Complaint.case_id == case_id).order_by(Complaint.reported_at.desc())
        )
        return list(rows.all())


complaint_service: ComplaintService = ComplaintService()

__all__ = ["ComplaintService", "complaint_service"]
