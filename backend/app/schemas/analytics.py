"""Analytics, geospatial (GeoJSON) and audit schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import AuditAction, AuditResult


# ------------------------------------------------------------ analytics
class AnalyticsOverview(BaseModel):
    active_cases: int
    open_cases: int
    high_risk_cases: int
    active_alerts: int
    critical_alerts: int
    predicted_locations: int
    total_transaction_volume: float
    transaction_count: int
    prediction_count: int
    prediction_accuracy: float | None = None
    active_investigations: int
    resolved_cases: int
    total_exposure: float
    generated_at: datetime


class TimelinePoint(BaseModel):
    period: str
    count: int


class RiskDistributionBucket(BaseModel):
    bucket: str
    count: int


class RiskDistribution(BaseModel):
    buckets: list[RiskDistributionBucket]
    source_scope: str = "synthetic"


class HotspotSummary(BaseModel):
    id: str
    label: str
    latitude: float
    longitude: float
    risk_score: float
    case_count: int
    predicted_amount: float


class CaseSeriesPoint(BaseModel):
    period: str
    opened: int
    resolved: int


# --------------------------------------------------------------- geojson
class GeoJSONFeature(BaseModel):
    type: Literal["Feature"] = "Feature"
    geometry: dict[str, Any]
    properties: dict[str, Any]


class GeoJSONFeatureCollection(BaseModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[GeoJSONFeature]
    meta: dict[str, Any] = Field(default_factory=dict)


# ----------------------------------------------------------------- audit
class AuditLogOut(BaseModel):
    """Read model for audit events; config enables ORM validation."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    actor_id: uuid.UUID | None = None
    actor_email: str | None = None
    actor_role: str | None = None
    action: AuditAction | str
    resource: str | None = None
    resource_id: str | None = None
    result: AuditResult
    request_id: str | None = None
    client_ip: str | None = None
    event_payload: dict[str, Any] = {}
    prev_hash: str | None = None
    hash: str
    created_at: datetime


class AuditChainSummary(BaseModel):
    total: int
    verified: bool
    last_hash: str | None = None
    first_hash: str | None = None


# ------------------------------------------------------- investigator
class InvestigatorQuestion(BaseModel):
    case_id: uuid.UUID
    question: str = Field(min_length=3, max_length=2000)


class EvidenceItem(BaseModel):
    kind: str
    source: str
    content: str


class InvestigatorExplanation(BaseModel):
    case_id: str
    question: str
    evidence: list[EvidenceItem]
    answer: str
    generated: bool
    model: str | None = None
    disclaimer: str = (
        "This explanation summarises structured evidence already stored in the platform. "
        "It is an assistive summary and never a determination of criminality."
    )


__all__ = [
    "AnalyticsOverview",
    "AuditChainSummary",
    "AuditLogOut",
    "CaseSeriesPoint",
    "EvidenceItem",
    "GeoJSONFeature",
    "GeoJSONFeatureCollection",
    "HotspotSummary",
    "InvestigatorExplanation",
    "InvestigatorQuestion",
    "RiskDistribution",
    "RiskDistributionBucket",
    "TimelinePoint",
]
