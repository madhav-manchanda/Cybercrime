"""Complaint ingestion schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.core.enums import (
    ComplaintSource,
    ComplaintStatus,
    DataSource,
    FraudType,
)
from app.schemas.common import GeoPoint, ORMModel, WritableModel


class ComplaintCreateRequest(WritableModel):
    source: ComplaintSource = ComplaintSource.PORTAL
    fraud_type: FraudType = FraudType.OTHER
    amount: float = Field(ge=0, le=1e12)
    reported_at: datetime | None = None
    victim_name: str | None = Field(default=None, max_length=240)
    victim_phone: str | None = Field(default=None, max_length=32)
    victim_email: str | None = Field(default=None, max_length=320)
    victim_account: str | None = Field(default=None, max_length=40)
    victim_address: str | None = Field(default=None, max_length=1000)
    description: str | None = None
    transaction_ref: str | None = Field(default=None, max_length=120)
    bank_ref: str | None = Field(default=None, max_length=120)
    ip_address: str | None = Field(default=None, max_length=64)
    device_info: str | None = Field(default=None, max_length=255)
    upi_ref: str | None = Field(default=None, max_length=160)
    location: GeoPoint | None = None
    data_source: DataSource = DataSource.OPERATIONAL

    @field_validator("victim_phone")
    @classmethod
    def _phone_digits(cls, v: str | None) -> str | None:
        if v is None:
            return v
        digits = [c for c in v if c.isdigit()]
        if len(digits) < 10:
            raise ValueError("phone number must contain at least 10 digits")
        return v


class ComplaintLinkRequest(BaseModel):
    case_id: uuid.UUID


class ComplaintOut(ORMModel):
    complaint_number: str
    source: ComplaintSource
    status: ComplaintStatus
    fraud_type: FraudType
    amount: float
    reported_at: datetime
    victim_name: str | None = None
    victim_phone_masked: str | None = None
    victim_email_masked: str | None = None
    victim_account_masked: str | None = None
    description: str | None = None
    transaction_ref: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    case_id: uuid.UUID | None = None
    data_source: DataSource


class ComplaintSummary(BaseModel):
    id: uuid.UUID
    complaint_number: str
    source: ComplaintSource
    amount: float
    fraud_type: FraudType
    reported_at: datetime
    status: ComplaintStatus


__all__ = [
    "ComplaintCreateRequest",
    "ComplaintLinkRequest",
    "ComplaintOut",
    "ComplaintSummary",
]
