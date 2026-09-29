"""Outcome (feedback loop) schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import Field

from app.core.enums import OutcomeType
from app.schemas.common import ORMModel, WritableModel


class OutcomeCreateRequest(WritableModel):
    outcome_type: OutcomeType
    prediction_id: uuid.UUID | None = None
    predicted_atm_id: uuid.UUID | None = None
    actual_atm_id: uuid.UUID | None = None
    predicted_time_start: datetime | None = None
    predicted_time_end: datetime | None = None
    actual_time: datetime | None = None
    was_cashout: bool | None = None
    amount_withdrawn: float | None = Field(default=None, ge=0)
    notes: str | None = Field(default=None, max_length=2000)


class OutcomeOut(ORMModel):
    case_id: uuid.UUID
    prediction_id: uuid.UUID | None = None
    outcome_type: OutcomeType
    predicted_atm_id: uuid.UUID | None = None
    actual_atm_id: uuid.UUID | None = None
    predicted_time_start: datetime | None = None
    predicted_time_end: datetime | None = None
    actual_time: datetime | None = None
    distance_error_km: float | None = None
    time_error_hours: float | None = None
    was_cashout: bool | None = None
    amount_withdrawn: float | None = None
    notes: str | None = None
    recorded_at: datetime
    recorded_by: uuid.UUID | None = None


__all__ = ["OutcomeCreateRequest", "OutcomeOut"]
