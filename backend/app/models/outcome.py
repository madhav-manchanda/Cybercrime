"""Actual outcomes and their recorded error vs the prediction."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.core.database import Base
from app.core.enums import OutcomeType
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin, utcnow

if TYPE_CHECKING:
    from app.models.case import Case
    from app.models.prediction import Prediction
    from app.models.user import User


class Outcome(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Ground-truth outcome recorded for a prediction (feeds the feedback loop)."""

    __tablename__ = "outcomes"
    __table_args__ = (
        Index("ix_outcomes_case", "case_id"),
        Index("ix_outcomes_prediction", "prediction_id"),
        Index("ix_outcomes_type", "outcome_type"),
    )

    outcome_type: Mapped[OutcomeType] = mapped_column(String(32), nullable=False)
    predicted_atm_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("atm_locations.id", ondelete="SET NULL"), nullable=True
    )
    actual_atm_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("atm_locations.id", ondelete="SET NULL"), nullable=True
    )
    predicted_time_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    predicted_time_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    actual_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    distance_error_km: Mapped[float | None] = mapped_column(Float, nullable=True)
    time_error_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    was_cashout: Mapped[bool | None] = mapped_column(default=None, nullable=True)
    amount_withdrawn: Mapped[float | None] = mapped_column(Float, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    recorded_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    case_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    prediction_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("predictions.id", ondelete="SET NULL"), nullable=True
    )

    case: Mapped[Case] = relationship(back_populates="outcomes")
    prediction: Mapped[Prediction | None] = relationship(
        back_populates="outcomes", foreign_keys=[prediction_id]
    )
    recorded_by_user: Mapped[User | None] = relationship(back_populates="outcomes")


__all__ = ["Outcome"]
