"""Case schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.core.enums import CasePriority, CaseStatus, ComplaintSource, DataSource, FraudType
from app.schemas.common import GeoPoint, ORMModel, WritableModel


class VictimDetails(BaseModel):
    name: str | None = Field(default=None, max_length=240)
    phone: str | None = Field(default=None, max_length=32)
    email: str | None = Field(default=None, max_length=320)
    account_number: str | None = Field(default=None, max_length=40)


class CaseCreateRequest(WritableModel):
    title: str = Field(min_length=3, max_length=240)
    description: str | None = None
    fraud_type: FraudType = FraudType.OTHER
    priority: CasePriority = CasePriority.MEDIUM
    amount: float = Field(default=0.0, ge=0)
    complaint_source: ComplaintSource = ComplaintSource.PORTAL
    reported_at: datetime | None = None
    state: str | None = Field(default=None, max_length=120)
    district: str | None = Field(default=None, max_length=120)
    locality_note: str | None = Field(default=None, max_length=255)
    location: GeoPoint | None = None
    victim: VictimDetails | None = None
    data_source: DataSource = DataSource.OPERATIONAL

    @field_validator("amount")
    @classmethod
    def _amount_limits(cls, v: float) -> float:
        if v > 1e12:
            raise ValueError("amount is unrealistically large")
        return v


class CaseUpdateRequest(WritableModel):
    title: str | None = Field(default=None, min_length=3, max_length=240)
    description: str | None = None
    status: CaseStatus | None = None
    priority: CasePriority | None = None
    fraud_type: FraudType | None = None
    amount: float | None = Field(default=None, ge=0)
    state: str | None = None
    district: str | None = None
    locality_note: str | None = None
    location: GeoPoint | None = None
    assigned_user_id: uuid.UUID | None = None
    investigating_officer_name: str | None = None


class CaseOut(ORMModel):
    case_number: str
    title: str
    description: str | None = None
    status: CaseStatus
    priority: CasePriority
    fraud_type: FraudType
    amount: float
    complaint_source: ComplaintSource
    reported_at: datetime | None = None
    opened_at: datetime
    victim_name: str | None = None
    victim_masked_phone: str | None = None
    victim_masked_email: str | None = None
    victim_masked_account: str | None = None
    state: str | None = None
    district: str | None = None
    locality_note: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    current_risk_score: float | None = None
    data_source: DataSource
    assigned_investigator: str | None = None
    investigation_officer: str | None = None
    is_open: bool
    complaint_count: int = 0
    transaction_count: int = 0
    prediction_count: int = 0
    alert_count: int = 0


class CaseSummary(BaseModel):
    id: uuid.UUID
    case_number: str
    title: str
    status: CaseStatus
    priority: CasePriority
    fraud_type: FraudType
    amount: float
    reported_at: datetime | None = None
    current_risk_score: float | None = None
    assigned_investigator: str | None = None


class CaseStatistics(BaseModel):
    total: int
    open: int
    by_status: dict[str, int]
    by_priority: dict[str, int]
    by_fraud_type: dict[str, int]
    exposed_amount_total: float


__all__ = [
    "CaseCreateRequest",
    "CaseOut",
    "CaseStatistics",
    "CaseSummary",
    "CaseUpdateRequest",
    "VictimDetails",
]
