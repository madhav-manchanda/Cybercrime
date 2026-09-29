"""Complaint ingestion model."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON, Uuid

from app.core.database import Base
from app.core.enums import ComplaintSource, ComplaintStatus, DataSource, FraudType
from app.models.mixins import (
    GeoPointMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    install_geo_listeners,
    utcnow,
)

if TYPE_CHECKING:
    from app.models.case import Case
    from app.models.transaction import Transaction


class Complaint(Base, UUIDPrimaryKeyMixin, TimestampMixin, GeoPointMixin):
    """A complaint reported by a victim / citizen channel."""

    __tablename__ = "complaints"

    complaint_number: Mapped[str] = mapped_column(String(40), unique=True, index=True, nullable=False)
    source: Mapped[ComplaintSource] = mapped_column(
        String(32), default=ComplaintSource.PORTAL, nullable=False
    )
    status: Mapped[ComplaintStatus] = mapped_column(
        String(32), default=ComplaintStatus.RECEIVED, nullable=False
    )
    fraud_type: Mapped[FraudType] = mapped_column(String(40), default=FraudType.OTHER, nullable=False)
    amount: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    reported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False, index=True
    )

    victim_name: Mapped[str | None] = mapped_column(String(240), nullable=True)
    victim_phone: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    victim_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    victim_account_masked: Mapped[str | None] = mapped_column(String(40), nullable=True)
    victim_address: Mapped[str | None] = mapped_column(Text, nullable=True)

    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    transaction_ref: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    bank_ref: Mapped[str | None] = mapped_column(String(120), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    device_info: Mapped[str | None] = mapped_column(String(255), nullable=True)
    upi_ref: Mapped[str | None] = mapped_column(String(160), nullable=True)

    data_source: Mapped[DataSource] = mapped_column(String(16), default=DataSource.SYNTHETIC)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)

    case_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("cases.id", ondelete="SET NULL"), nullable=True, index=True
    )

    case: Mapped[Case | None] = relationship(back_populates="complaints")
    transactions: Mapped[list[Transaction]] = relationship(back_populates="complaint")

    @property
    def masked(self) -> dict:
        """Safe serialisable view with PII masked."""
        from app.core.security import mask, mask_phone

        return {
            "id": str(self.id),
            "complaint_number": self.complaint_number,
            "source": self.source.value if hasattr(self.source, "value") else self.source,
            "status": self.status.value if hasattr(self.status, "value") else self.status,
            "fraud_type": self.fraud_type.value if hasattr(self.fraud_type, "value") else self.fraud_type,
            "amount": self.amount,
            "reported_at": self.reported_at,
            "victim_name": mask(self.victim_name, keep_last=1) if self.victim_name else None,
            "victim_phone": mask_phone(self.victim_phone),
            "victim_email": self.victim_email,
            "victim_account_masked": self.victim_account_masked,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "case_id": self.case_id,
        }


install_geo_listeners(Complaint)

__all__ = ["Complaint"]
