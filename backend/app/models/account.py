"""Bank accounts (incl. suspected mule accounts), phone numbers, devices, UPIs."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Float, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.entity import Entity


class Account(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "accounts"

    account_number_masked: Mapped[str | None] = mapped_column(String(40), index=True, nullable=True)
    account_number_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    bank_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    ifsc: Mapped[str | None] = mapped_column(String(32), index=True, nullable=True)
    holder_name: Mapped[str | None] = mapped_column(String(240), nullable=True)
    is_mule: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    risk_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    entity: Mapped[Entity | None] = relationship(back_populates="account", uselist=False)


class PhoneNumber(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "phone_numbers"

    phone_masked: Mapped[str] = mapped_column(String(24), index=True)
    phone_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    entity: Mapped[Entity | None] = relationship(back_populates="phone", uselist=False)


class Device(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "devices"

    device_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    device_type: Mapped[str | None] = mapped_column(String(60), nullable=True)
    os: Mapped[str | None] = mapped_column(String(60), nullable=True)
    app_version: Mapped[str | None] = mapped_column(String(32), nullable=True)

    entity: Mapped[Entity | None] = relationship(back_populates="device", uselist=False)


class UpiId(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "upi_ids"

    upi_masked: Mapped[str] = mapped_column(String(160), index=True)
    upi_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    bank_name: Mapped[str | None] = mapped_column(String(120), nullable=True)

    entity: Mapped[Entity | None] = relationship(back_populates="upi", uselist=False)


__all__ = ["Account", "Device", "PhoneNumber", "UpiId"]
