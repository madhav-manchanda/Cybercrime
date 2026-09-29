"""Transaction records (financial flows feeding fraud-network + features)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON, Uuid

from app.core.database import Base
from app.core.enums import Channel, DataSource, TransactionDirection, TransactionType
from app.models.mixins import (
    GeoPointMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    install_geo_listeners,
    utcnow,
)

if TYPE_CHECKING:
    from app.models.atm import AtmLocation
    from app.models.case import Case
    from app.models.complaint import Complaint
    from app.models.entity import Entity


class Transaction(Base, UUIDPrimaryKeyMixin, TimestampMixin, GeoPointMixin):
    """A single observed financial transaction."""

    __tablename__ = "transactions"
    __table_args__ = (
        Index("ix_transactions_case_ts", "case_id", "timestamp"),
        Index("ix_transactions_type_amount", "type", "amount"),
        Index("ix_transactions_source_account", "source_account_masked"),
        Index("ix_transactions_dest_account", "destination_account_masked"),
    )
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012

    transaction_ref: Mapped[str | None] = mapped_column(String(120), unique=True, index=True, nullable=True)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="INR", nullable=False)
    direction: Mapped[TransactionDirection] = mapped_column(
        String(8), default=TransactionDirection.DEBIT, nullable=False
    )
    type: Mapped[TransactionType] = mapped_column(String(24), default=TransactionType.UPI_P2M, nullable=False)
    channel: Mapped[Channel] = mapped_column(String(16), default=Channel.UPI, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False, index=True
    )

    source_account_masked: Mapped[str | None] = mapped_column(String(40), nullable=True)
    destination_account_masked: Mapped[str | None] = mapped_column(String(40), nullable=True)
    merchant: Mapped[str | None] = mapped_column(String(200), nullable=True)
    upi_reference: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    device_fingerprint_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    note: Mapped[str | None] = mapped_column(String(400), nullable=True)

    data_source: Mapped[DataSource] = mapped_column(String(16), default=DataSource.SYNTHETIC)
    feature_vector: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    case_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("cases.id", ondelete="SET NULL"), nullable=True, index=True
    )
    complaint_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("complaints.id", ondelete="SET NULL"), nullable=True, index=True
    )
    atm_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("atm_locations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    source_entity_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("entities.id", ondelete="SET NULL"), nullable=True, index=True
    )
    destination_entity_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("entities.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # relationships
    case: Mapped[Case | None] = relationship(back_populates="transactions", foreign_keys=[case_id])
    complaint: Mapped[Complaint | None] = relationship(back_populates="transactions")
    source_entity: Mapped[Entity | None] = relationship(foreign_keys=[source_entity_id])
    destination_entity: Mapped[Entity | None] = relationship(foreign_keys=[destination_entity_id])
    atm: Mapped[AtmLocation | None] = relationship(back_populates="transactions")


install_geo_listeners(Transaction)

__all__ = ["Transaction"]
