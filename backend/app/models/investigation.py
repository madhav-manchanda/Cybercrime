"""Investigation timeline events and intervention simulations."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON, Uuid

from app.core.database import Base
from app.core.enums import (
    InterventionStatus,
    InterventionType,
    InvestigationEventType,
)
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin, utcnow

if TYPE_CHECKING:
    from app.models.case import Case
    from app.models.prediction import Prediction


class InvestigationEvent(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One entry in the chronological case timeline."""

    __tablename__ = "investigation_events"
    __table_args__ = (Index("ix_tl_case_ts", "case_id", "occurred_at"),)

    case_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_type: Mapped[InvestigationEventType] = mapped_column(String(48), nullable=False)
    role: Mapped[str | None] = mapped_column(String(32), nullable=True)
    description: Mapped[str | None] = mapped_column(String(1200), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    @property
    def as_timeline(self) -> dict:
        return {
            "id": str(self.id),
            "case_id": str(self.case_id),
            "event_type": self.event_type.value
            if hasattr(self.event_type, "value")
            else str(self.event_type),
            "role": self.role,
            "description": self.description,
            "metadata": self.metadata_json,
            "occurred_at": self.occurred_at.isoformat() if self.occurred_at else None,
            "actor_id": str(self.actor_id) if self.actor_id else None,
        }


class Intervention(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A modelled / executed intervention on a prediction."""

    __tablename__ = "interventions"
    __table_args__ = (Index("ix_int_case_created", "case_id", "created_at"),)

    intervention_type: Mapped[InterventionType] = mapped_column(String(32), nullable=False)
    status: Mapped[InterventionStatus] = mapped_column(
        String(16), default=InterventionStatus.SIMULATED, nullable=False
    )
    description: Mapped[str | None] = mapped_column(String(1200), nullable=True)

    baseline_exposure: Mapped[float | None] = mapped_column(Float, nullable=True)
    simulated_exposure: Mapped[float | None] = mapped_column(Float, nullable=True)
    risk_reduction: Mapped[float | None] = mapped_column(Float, nullable=True)
    #: list[UUID] of affected ATM ids.
    affected_location_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    assumptions: Mapped[list[str]] = mapped_column(JSON, default=list)

    case_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    prediction_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("predictions.id", ondelete="SET NULL"), nullable=True
    )
    suggested_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    executed_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    case: Mapped[Case] = relationship(back_populates="interventions")
    prediction: Mapped[Prediction | None] = relationship()


__all__ = ["Intervention", "InvestigationEvent"]
