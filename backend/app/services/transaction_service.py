"""Transaction ingestion and on-demand feature extraction."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import AuditAction, RealtimeEventType
from app.core.errors import (
    TRANSACTION_NOT_FOUND,
    BadRequestError,
)
from app.core.security import mask
from app.models import CashWithdrawal, Transaction, User
from app.schemas.transaction import TransactionCreateRequest
from app.services.audit_service import audit_service
from app.services.realtime_service import event_hub
from app.utils.validators import as_str, utc_aware


class TransactionService:
    """Creates transaction rows, optionally resolving entities for them."""

    async def create(
        self,
        session: AsyncSession,
        *,
        payload: TransactionCreateRequest,
        actor: User,
    ) -> Transaction:
        from app.services.entity_service import entity_service

        location = payload.location
        if payload.transaction_ref:
            duplicate = await session.scalar(
                select(Transaction).where(Transaction.transaction_ref == payload.transaction_ref)
            )
            if duplicate is not None:
                raise BadRequestError(
                    "A transaction with this reference already exists.",
                    code="DUPLICATE_TRANSACTION",
                )

        source_entity = None
        dest_entity = None
        # resolve both accounts as entities so the graph obtains typed edges
        if payload.source_account:
            source_entity = await entity_service.resolve_from_account(
                session, account_number=payload.source_account, case_id=payload.case_id
            )
        if payload.destination_account:
            dest_entity = await entity_service.resolve_from_account(
                session, account_number=payload.destination_account, case_id=payload.case_id
            )

        transaction = Transaction(
            transaction_ref=payload.transaction_ref,
            amount=payload.amount,
            direction=payload.direction,
            type=payload.type,
            channel=payload.channel,
            timestamp=utc_aware(payload.timestamp) if payload.timestamp else datetime.now(UTC),
            source_account_masked=mask(payload.source_account) if payload.source_account else None,
            destination_account_masked=mask(payload.destination_account)
            if payload.destination_account
            else None,
            merchant=payload.merchant,
            upi_reference=payload.upi_reference,
            device_fingerprint_hash=payload.device_fingerprint,
            ip_address=payload.ip_address,
            note=payload.note,
            case_id=payload.case_id,
            complaint_id=payload.complaint_id,
            atm_id=payload.atm_id,
            latitude=location.latitude if location else None,
            longitude=location.longitude if location else None,
            data_source=payload.data_source,
            source_entity_id=source_entity.id if source_entity else None,
            destination_entity_id=dest_entity.id if dest_entity else None,
        )
        session.add(transaction)
        await session.flush()

        if transaction.atm_id and as_str(payload.type) == "ATM_WITHDRAWAL":
            session.add(
                CashWithdrawal(
                    amount=payload.amount,
                    timestamp=transaction.timestamp,
                    atm_id=transaction.atm_id,
                    transaction_id=transaction.id,
                    account_entity_id=source_entity.id if source_entity else None,
                    data_source=payload.data_source,
                )
            )

        # entity relationship: funds transferred
        if source_entity and dest_entity:
            await entity_service.link(
                session,
                source=source_entity,
                target=dest_entity,
                relationship="FUNDS_TRANSFERRED_TO",
                weight=min(payload.amount / 1000.0, 10.0),
                confidence=0.9,
                timestamp=transaction.timestamp,
                evidence={"transaction_id": str(transaction.id), "amount": payload.amount},
                actor=actor,
            )

        await audit_service.record(
            session,
            action=AuditAction.TRANSACTION_CREATE,
            actor_id=actor.id,
            actor_email=actor.email,
            actor_role=actor.role_name.value,
            resource="transaction",
            resource_id=transaction.id,
            payload={
                "amount": payload.amount,
                "type": as_str(payload.type),
                "case_id": str(payload.case_id) if payload.case_id else None,
            },
        )
        await session.flush()
        await event_hub.publish(
            RealtimeEventType.TRANSACTION_CREATED,
            {"transaction_id": str(transaction.id), "amount": transaction.amount},
        )
        return transaction

    async def get(self, session: AsyncSession, *, transaction_id: uuid.UUID) -> Transaction:
        transaction = await session.get(Transaction, transaction_id)
        if transaction is None:
            raise TRANSACTION_NOT_FOUND
        return transaction

    async def list_by_case(
        self,
        session: AsyncSession,
        *,
        case_id: uuid.UUID,
        page: int = 1,
        page_size: int = 100,
    ) -> tuple[list[Transaction], int]:
        query = select(Transaction).where(Transaction.case_id == case_id)
        total = await session.scalar(select(func.count()).select_from(query.subquery())) or 0
        rows = (
            await session.scalars(
                query.order_by(Transaction.timestamp.desc()).offset((page - 1) * page_size).limit(page_size)
            )
        ).all()
        return list(rows), int(total)

    # -------------------------------------------------------- features
    async def case_feature_vector(self, session: AsyncSession, *, case_id: uuid.UUID) -> dict[str, Any]:
        """Aggregate velocity/statistical features for a case (cached by FE)."""
        rows = await session.scalars(select(Transaction).where(Transaction.case_id == case_id))
        txns = list(rows.all())
        if not txns:
            return self._empty_features()

        amounts = [t.amount for t in txns]
        total = sum(amounts)
        mean = total / len(amounts)
        dev = (max(amounts) - mean) / max(mean, 1.0)
        timestamps = sorted(t.timestamp for t in txns)
        span_h = (timestamps[-1] - timestamps[0]).total_seconds() / 3600.0 if len(timestamps) > 1 else 0.0
        velocity_per_hour = len(txns) / max(span_h, 0.0167)

        hours = [t.timestamp.hour for t in txns]
        days = [t.timestamp.weekday() for t in txns]
        withdrawals = [t for t in txns if t.type == "ATM_WITHDRAWAL"]
        last_ts = timestamps[-1]
        if last_ts.tzinfo is None:
            last_ts = last_ts.replace(tzinfo=UTC)

        return {
            "transaction_count": len(txns),
            "total_amount": total,
            "mean_amount": mean,
            "max_amount": max(amounts),
            "min_amount": min(amounts),
            "std_amount": (sum((a - mean) ** 2 for a in amounts) / len(amounts)) ** 0.5,
            "amount_deviation_ratio": round(dev, 4),
            "velocity_per_hour": round(velocity_per_hour, 4),
            "time_span_hours": round(span_h, 2),
            "hour_of_day_mean": sum(hours) / len(hours) if hours else None,
            "day_of_week_modes": {d: days.count(d) for d in set(days)},
            "withdrawal_count": len(withdrawals),
            "withdrawal_total": sum(w.amount for w in withdrawals),
            "withdrawal_mean_amount": (sum(w.amount for w in withdrawals) / len(withdrawals))
            if withdrawals
            else 0.0,
            "hours_since_last_txn": round((datetime.now(UTC) - last_ts).total_seconds() / 3600.0, 2),
            "distinct_dest": len(
                {t.destination_account_masked for t in txns if t.destination_account_masked}
            ),
            "distinct_src": len({t.source_account_masked for t in txns if t.source_account_masked}),
        }

    @staticmethod
    def _empty_features() -> dict[str, Any]:
        return {
            "transaction_count": 0,
            "total_amount": 0.0,
            "mean_amount": 0.0,
            "max_amount": 0.0,
            "min_amount": 0.0,
            "std_amount": 0.0,
            "amount_deviation_ratio": 0.0,
            "velocity_per_hour": 0.0,
            "time_span_hours": 0.0,
            "hour_of_day_mean": None,
            "day_of_week_modes": {},
            "withdrawal_count": 0,
            "withdrawal_total": 0.0,
            "withdrawal_mean_amount": 0.0,
            "hours_since_last_txn": 0.0,
            "distinct_dest": 0,
            "distinct_src": 0,
        }


transaction_service: TransactionService = TransactionService()

__all__ = ["TransactionService", "transaction_service"]
