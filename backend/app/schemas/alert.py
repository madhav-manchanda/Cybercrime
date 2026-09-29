"""Alert + realtime schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.core.enums import AlertSeverity, AlertStatus, AlertType
from app.schemas.common import ORMModel


class AlertOut(ORMModel):
    alert_type: AlertType
    severity: AlertSeverity
    status: AlertStatus
    title: str
    description: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    risk_score: float | None = None
    case_id: uuid.UUID | None = None
    prediction_id: uuid.UUID | None = None
    atm_id: uuid.UUID | None = None
    acknowledged_at: datetime | None = None
    resolved_at: datetime | None = None


class AlertAckRequest(BaseModel):
    note: str | None = Field(default=None, max_length=600)


class AlertResolveRequest(BaseModel):
    note: str | None = Field(default=None, max_length=600)


class RealtimeEvent(BaseModel):
    type: str
    payload: dict[str, Any]
    event_id: str
    timestamp: datetime


__all__ = ["AlertAckRequest", "AlertOut", "AlertResolveRequest", "RealtimeEvent"]
