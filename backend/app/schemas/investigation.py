"""Investigation timeline + intervention simulation schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.core.enums import (
    InterventionStatus,
    InterventionType,
    InvestigationEventType,
)
from app.schemas.common import ORMModel, WritableModel


class InvestigationEventCreate(WritableModel):
    event_type: InvestigationEventType
    description: str | None = Field(default=None, max_length=1200)
    metadata: dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime | None = None


class InvestigationEventOut(BaseModel):
    id: uuid.UUID
    case_id: uuid.UUID
    event_type: InvestigationEventType
    description: str | None = None
    metadata: dict[str, Any] = {}
    occurred_at: datetime
    actor_id: uuid.UUID | None = None


class InterventionSimulateRequest(WritableModel):
    case_id: uuid.UUID
    intervention_type: InterventionType = InterventionType.MONITOR_ATM
    prediction_id: uuid.UUID | None = None
    notes: str | None = Field(default=None, max_length=1200)


class InterventionOut(ORMModel):
    case_id: uuid.UUID
    prediction_id: uuid.UUID | None = None
    intervention_type: InterventionType
    status: InterventionStatus
    description: str | None = None
    baseline_exposure: float | None = None
    simulated_exposure: float | None = None
    risk_reduction: float | None = None
    affected_location_ids: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    executed_at: datetime | None = None


class InterventionExecuteRequest(BaseModel):
    """Mark a simulated intervention as executed in the field."""

    note: str | None = Field(default=None, max_length=1200)


__all__ = [
    "InterventionExecuteRequest",
    "InterventionOut",
    "InterventionSimulateRequest",
    "InvestigationEventCreate",
    "InvestigationEventOut",
]
