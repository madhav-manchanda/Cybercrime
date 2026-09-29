"""ATM + risk schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.core.enums import AtmStatus
from app.schemas.common import ORMModel, WritableModel


class AtmCreateRequest(WritableModel):
    code: str = Field(min_length=2, max_length=40)
    name: str = Field(min_length=2, max_length=200)
    bank_name: str | None = Field(default=None, max_length=120)
    status: AtmStatus = AtmStatus.ACTIVE
    is_csp: bool = False
    address: str | None = Field(default=None, max_length=400)
    city: str | None = Field(default=None, max_length=120)
    state: str | None = Field(default=None, max_length=120)
    service_hours: str | None = Field(default=None, max_length=60)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    base_load: float = Field(default=0.5, ge=0, le=1)
    zone_type: str | None = Field(default=None, max_length=40)


class AtmOut(ORMModel):
    code: str
    name: str
    bank_name: str | None = None
    status: AtmStatus
    is_csp: bool
    address: str | None = None
    city: str | None = None
    state: str | None = None
    service_hours: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    zone_type: str | None = None
    base_load: float = 0.5


class RiskFactor(BaseModel):
    factor: str
    impact: float = Field(ge=-1, le=1)
    detail: str | None = None


class AtmRiskOut(BaseModel):
    atm_id: uuid.UUID
    code: str
    name: str
    latitude: float | None = None
    longitude: float | None = None
    risk_score: float = Field(ge=0, le=1)
    confidence: float = Field(ge=0, le=1)
    status: AtmStatus
    contributing_factors: list[RiskFactor] = []
    as_of: datetime


class AtmRiskRankingItem(AtmRiskOut):
    rank: int


__all__ = [
    "AtmCreateRequest",
    "AtmOut",
    "AtmRiskOut",
    "AtmRiskRankingItem",
    "RiskFactor",
]
