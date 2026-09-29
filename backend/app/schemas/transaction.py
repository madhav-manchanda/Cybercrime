"""Transaction schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.core.enums import (
    Channel,
    DataSource,
    TransactionDirection,
    TransactionType,
)
from app.schemas.common import GeoPoint, ORMModel, WritableModel


class TransactionCreateRequest(WritableModel):
    transaction_ref: str | None = Field(default=None, max_length=120)
    amount: float = Field(gt=0, le=1e9)
    direction: TransactionDirection = TransactionDirection.DEBIT
    type: TransactionType = TransactionType.UPI_P2M
    channel: Channel = Channel.UPI
    timestamp: datetime | None = None
    source_account: str | None = Field(default=None, max_length=40)
    destination_account: str | None = Field(default=None, max_length=40)
    merchant: str | None = Field(default=None, max_length=200)
    upi_reference: str | None = Field(default=None, max_length=160)
    device_fingerprint: str | None = Field(default=None, max_length=128)
    ip_address: str | None = Field(default=None, max_length=64)
    note: str | None = Field(default=None, max_length=400)
    case_id: uuid.UUID | None = None
    complaint_id: uuid.UUID | None = None
    atm_id: uuid.UUID | None = None
    location: GeoPoint | None = None
    data_source: DataSource = DataSource.OPERATIONAL


class TransactionOut(ORMModel):
    transaction_ref: str | None = None
    amount: float
    currency: str
    direction: TransactionDirection
    type: TransactionType
    channel: Channel
    timestamp: datetime
    source_account_masked: str | None = None
    destination_account_masked: str | None = None
    merchant: str | None = None
    upi_reference: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    case_id: uuid.UUID | None = None
    complaint_id: uuid.UUID | None = None
    atm_id: uuid.UUID | None = None
    data_source: DataSource


class TransactionSummary(BaseModel):
    id: uuid.UUID
    amount: float
    direction: TransactionDirection
    type: TransactionType
    timestamp: datetime
    source_account_masked: str | None = None
    destination_account_masked: str | None = None


__all__ = [
    "TransactionCreateRequest",
    "TransactionOut",
    "TransactionSummary",
]
