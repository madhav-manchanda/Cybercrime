"""ATMs / CSP locations and observed cash withdrawals."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.core.database import Base
from app.core.enums import AtmStatus, DataSource, WithdrawalOutcome
from app.models.mixins import (
    GeoPointMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    install_geo_listeners,
    utcnow,
)

if TYPE_CHECKING:
    from app.models.entity import Entity
    from app.models.transaction import Transaction


class AtmLocation(Base, UUIDPrimaryKeyMixin, TimestampMixin, GeoPointMixin):
    """An ATM / banking CSP / cash-out point of interest."""

    __tablename__ = "atm_locations"
    __table_args__ = (
        Index("ix_atms_status_bank", "status", "bank_name"),
        Index("ix_atms_grid", "latitude", "longitude"),
    )

    code: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    bank_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[AtmStatus] = mapped_column(String(24), default=AtmStatus.ACTIVE)
    is_csp: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    address: Mapped[str | None] = mapped_column(String(400), nullable=True)
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    state: Mapped[str | None] = mapped_column(String(120), nullable=True)
    service_hours: Mapped[str | None] = mapped_column(String(60), nullable=True)
    base_load: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    monthly_withdrawals: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    #: structural characterisation of the site (city centre/suburb/rural).
    zone_type: Mapped[str | None] = mapped_column(String(40), nullable=True)

    transactions: Mapped[list[Transaction]] = relationship(back_populates="atm")
    withdrawals: Mapped[list[CashWithdrawal]] = relationship(back_populates="atm")
    entities: Mapped[list[Entity]] = relationship(back_populates="atm", foreign_keys="Entity.atm_id")

    def to_geojson(self) -> dict:
        return {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [self.longitude, self.latitude],
            },
            "properties": {
                "id": str(self.id),
                "code": self.code,
                "name": self.name,
                "bank_name": self.bank_name,
                "status": self.status.value if hasattr(self.status, "value") else self.status,
                "is_csp": self.is_csp,
                "city": self.city,
                "state": self.state,
            },
        }


class CashWithdrawal(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """An observed cash withdrawal (the ground-truth target of predictions)."""

    __tablename__ = "cash_withdrawals"
    __table_args__ = (
        Index("ix_withdrawals_atm_ts", "atm_id", "timestamp"),
        Index("ix_withdrawals_amount", "amount"),
    )

    amount: Mapped[float] = mapped_column(Float, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False, index=True
    )
    outcome: Mapped[WithdrawalOutcome] = mapped_column(
        String(16), default=WithdrawalOutcome.SUCCESS, nullable=False
    )
    is_mule_withdrawal: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    atm_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("atm_locations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("transactions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    account_entity_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("entities.id", ondelete="SET NULL"), nullable=True, index=True
    )
    data_source: Mapped[DataSource] = mapped_column(String(16), default=DataSource.SYNTHETIC)

    atm: Mapped[AtmLocation | None] = relationship(back_populates="withdrawals")
    account_entity: Mapped[Entity | None] = relationship()


install_geo_listeners(AtmLocation)

__all__ = ["AtmLocation", "CashWithdrawal"]
