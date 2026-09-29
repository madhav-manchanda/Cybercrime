"""Predictions: model runs produce predictions + ranked locations + explanations."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON, Uuid

from app.core.database import Base
from app.core.enums import PredictionHorizon, PredictionStatus
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin, utcnow

if TYPE_CHECKING:
    from app.models.alert import Alert
    from app.models.case import Case
    from app.models.outcome import Outcome


class Prediction(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A prediction run for a case (multiple candidate locations)."""

    __tablename__ = "predictions"
    __table_args__ = (
        Index("ix_predictions_status", "status"),
        Index("ix_predictions_created", "created_at"),
        Index("ix_predictions_model_version", "model_name", "model_version"),
    )

    status: Mapped[PredictionStatus] = mapped_column(
        String(16), default=PredictionStatus.RUNNING, nullable=False
    )
    horizon: Mapped[PredictionHorizon] = mapped_column(
        String(8), default=PredictionHorizon.H24, nullable=False
    )
    headline_risk: Mapped[float | None] = mapped_column(Float, nullable=True)
    predicted_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    model_name: Mapped[str] = mapped_column(String(80), default="cashout-risk-v1")
    model_version: Mapped[str] = mapped_column(String(32), default="1.0.0")
    feature_version: Mapped[str] = mapped_column(String(32), default="1.0")
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)

    case_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    model_run_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("model_runs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    requested_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    case: Mapped[Case] = relationship(back_populates="predictions", foreign_keys=[case_id])
    locations: Mapped[list[PredictionLocation]] = relationship(
        back_populates="prediction", cascade="all, delete-orphan"
    )
    alerts: Mapped[list[Alert]] = relationship(
        back_populates="prediction", foreign_keys="Alert.prediction_id"
    )
    outcomes: Mapped[list[Outcome]] = relationship(
        back_populates="prediction", foreign_keys="Outcome.prediction_id"
    )


class PredictionLocation(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One ranked candidate cash-out location for a prediction."""

    __tablename__ = "prediction_locations"
    __table_args__ = (
        Index("ix_pred_loc_rank", "prediction_id", "rank"),
        Index("ix_pred_loc_risk", "risk_score"),
        Index("ix_pred_loc_atm", "atm_id"),
    )

    prediction_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("predictions.id", ondelete="CASCADE"), nullable=False
    )
    atm_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("atm_locations.id", ondelete="CASCADE"), nullable=False
    )
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    risk_score: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    time_window_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    time_window_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    #: {"factor": str, "impact": float}[] - human readable explanation pieces.
    contributing_factors: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    explanation_text: Mapped[str | None] = mapped_column(String(1200), nullable=True)

    prediction: Mapped[Prediction] = relationship(back_populates="locations")


__all__ = ["Prediction", "PredictionLocation"]
