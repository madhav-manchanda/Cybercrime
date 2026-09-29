"""Risk-score history, alerts, investigation timeline + interventions."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON, Uuid

from app.core.database import Base
from app.core.enums import AlertSeverity, AlertStatus, AlertType
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin, utcnow

if TYPE_CHECKING:
    from app.models.case import Case
    from app.models.prediction import Prediction


class RiskScore(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Immutable risk-score history per case (feeds temporal analytics)."""

    __tablename__ = "risk_scores"
    __table_args__ = (Index("ix_risk_case_ts", "case_id", "computed_at"),)

    case_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("cases.id", ondelete="CASCADE"), nullable=True, index=True
    )
    entity_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("entities.id", ondelete="CASCADE"), nullable=True, index=True
    )
    atm_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("atm_locations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    score: Mapped[float] = mapped_column(Float, nullable=False)
    model_version: Mapped[str] = mapped_column(String(32), default="1.0.0")
    #: {"spatial": 0.2, "temporal": 0.4, "network": 0.1, "financial": 0.1}
    component_breakdown: Mapped[dict] = mapped_column(JSON, default=dict)
    feature_vector: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class Alert(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A generated alert for an investigator to acknowledge/resolve."""

    __tablename__ = "alerts"
    __table_args__ = (
        Index("ix_alerts_status_severity", "status", "severity"),
        Index("ix_alerts_created", "created_at"),
        Index("ix_alerts_type", "alert_type"),
    )

    alert_type: Mapped[AlertType] = mapped_column(String(48), nullable=False)
    severity: Mapped[AlertSeverity] = mapped_column(String(16), default=AlertSeverity.MEDIUM)
    status: Mapped[AlertStatus] = mapped_column(String(16), default=AlertStatus.OPEN)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1200), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    risk_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    acknowledged_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    case_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("cases.id", ondelete="CASCADE"), nullable=True, index=True
    )
    prediction_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("predictions.id", ondelete="CASCADE"), nullable=True, index=True
    )
    atm_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("atm_locations.id", ondelete="CASCADE"), nullable=True, index=True
    )

    case: Mapped[Case | None] = relationship(back_populates="alerts", foreign_keys=[case_id])
    prediction: Mapped[Prediction | None] = relationship(
        back_populates="alerts", foreign_keys=[prediction_id]
    )


__all__ = ["Alert", "RiskScore"]
