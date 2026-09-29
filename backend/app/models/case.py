"""Case lifecycle model."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.core.database import Base
from app.core.enums import (
    CasePriority,
    CaseStatus,
    ComplaintSource,
    DataSource,
    FraudType,
)
from app.models.mixins import (
    GeoPointMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    install_geo_listeners,
)

if TYPE_CHECKING:
    from app.models.alert import Alert
    from app.models.complaint import Complaint
    from app.models.entity import Entity
    from app.models.investigation import Intervention
    from app.models.outcome import Outcome
    from app.models.prediction import Prediction
    from app.models.transaction import Transaction
    from app.models.user import User


class Case(Base, UUIDPrimaryKeyMixin, TimestampMixin, GeoPointMixin):
    """A single cybercrime investigation case."""

    __tablename__ = "cases"
    __table_args__ = (
        Index("ix_cases_status_priority", "status", "priority"),
        Index("ix_cases_fraud_type", "fraud_type"),
        Index("ix_cases_risk_score", "current_risk_score"),
        Index("ix_cases_opened_at", "opened_at"),
        Index("ix_cases_state_district", "state", "district"),
    )

    case_number: Mapped[str] = mapped_column(String(40), unique=True, index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[CaseStatus] = mapped_column(String(32), default=CaseStatus.NEW, nullable=False)
    priority: Mapped[CasePriority] = mapped_column(String(16), default=CasePriority.MEDIUM, nullable=False)
    fraud_type: Mapped[FraudType] = mapped_column(String(40), default=FraudType.OTHER, nullable=False)
    amount: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    complaint_source: Mapped[ComplaintSource] = mapped_column(
        String(32), default=ComplaintSource.PORTAL, nullable=False
    )
    reported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.now, nullable=False)

    # victim contact kept masked unless the user holds an unmasking permission
    victim_name: Mapped[str | None] = mapped_column(String(240), nullable=True)
    victim_masked_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    victim_masked_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    victim_masked_account: Mapped[str | None] = mapped_column(String(40), nullable=True)

    state: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    district: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    locality_note: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # headline composite risk (0..1) maintained by the risk service
    current_risk_score: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)

    data_source: Mapped[DataSource] = mapped_column(String(16), default=DataSource.SYNTHETIC, nullable=False)

    assigned_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    investigating_officer_name: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # ------------------------------------------------------------- rels
    assigned_investigator: Mapped[User | None] = relationship(
        back_populates="cases", foreign_keys=[assigned_user_id]
    )
    complaints: Mapped[list[Complaint]] = relationship(back_populates="case")
    transactions: Mapped[list[Transaction]] = relationship(
        back_populates="case", foreign_keys="Transaction.case_id"
    )
    predictions: Mapped[list[Prediction]] = relationship(
        back_populates="case", foreign_keys="Prediction.case_id"
    )
    alerts: Mapped[list[Alert]] = relationship(back_populates="case", foreign_keys="Alert.case_id")
    entities: Mapped[list[Entity]] = relationship(back_populates="case", foreign_keys="Entity.case_id")
    interventions: Mapped[list[Intervention]] = relationship(back_populates="case")
    outcomes: Mapped[list[Outcome]] = relationship(back_populates="case")

    @property
    def is_open(self) -> bool:
        return self.status in CaseStatus.open_states()


install_geo_listeners(Case)

__all__ = ["Case"]
