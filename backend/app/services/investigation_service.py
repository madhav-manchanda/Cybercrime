"""Investigation timeline service."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import InvestigationEventType
from app.models import InvestigationEvent, User


class InvestigationService:
    """Appends to and reads the chronological case timeline."""

    async def add_event(
        self,
        session: AsyncSession,
        *,
        case_id: uuid.UUID,
        event_type: InvestigationEventType,
        actor: User | None = None,
        description: str | None = None,
        metadata: dict[str, Any] | None = None,
        occurred_at: datetime | None = None,
    ) -> InvestigationEvent:
        # avoid duplicate rows from double-invocation in the same request
        for pending in session.new:
            if (
                isinstance(pending, InvestigationEvent)
                and pending.case_id == case_id
                and pending.event_type
                == (event_type.value if hasattr(event_type, "value") else str(event_type))
                and pending.description == description
            ):
                return pending
        event = InvestigationEvent(
            case_id=case_id,
            event_type=event_type,
            role=actor.role_name.value if actor else None,
            description=description,
            metadata_json=metadata or {},
            occurred_at=occurred_at or datetime.now(UTC),
            actor_id=actor.id if actor else None,
        )
        session.add(event)
        await session.flush()
        return event

    async def timeline(self, session: AsyncSession, *, case_id: uuid.UUID) -> list[InvestigationEvent]:
        rows = await session.scalars(
            select(InvestigationEvent)
            .where(InvestigationEvent.case_id == case_id)
            .order_by(InvestigationEvent.occurred_at, InvestigationEvent.id)
        )
        return list(rows.all())


investigation_service: InvestigationService = InvestigationService()

__all__ = ["InvestigationService", "investigation_service"]
