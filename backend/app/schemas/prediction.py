"""Prediction schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.core.enums import (
    PredictionHorizon,
    PredictionStatus,
)
from app.schemas.common import FactorContribution, ORMModel, TimeWindowBound, WritableModel


class PredictionRequest(WritableModel):
    horizon: PredictionHorizon = PredictionHorizon.H24
    top_k: int = Field(default=5, ge=1, le=20)
    reference_time: datetime | None = None


class PredictionLocationOut(BaseModel):
    location_id: uuid.UUID
    atm_id: uuid.UUID
    rank: int
    risk_score: float = Field(ge=0, le=1)
    confidence: float = Field(ge=0, le=1)
    time_window: TimeWindowBound | None = None
    contributing_factors: list[FactorContribution] = []
    explanation_text: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    atm_code: str | None = None
    atm_name: str | None = None


class PredictionOut(ORMModel):
    case_id: uuid.UUID
    status: PredictionStatus
    horizon: PredictionHorizon
    headline_risk: float | None = None
    predicted_amount: float | None = None
    generated_at: datetime
    completed_at: datetime | None = None
    model_name: str
    model_version: str
    feature_version: str
    locations: list[PredictionLocationOut] = Field(default_factory=list)
    metadata_json: dict = Field(default_factory=dict)


class RunPredictionResponse(BaseModel):
    case_id: str
    prediction_id: str
    queued: bool = False
    completed: bool = True
    result: PredictionOut | None = None
    error: str | None = None


__all__ = [
    "PredictionLocationOut",
    "PredictionOut",
    "PredictionRequest",
    "RunPredictionResponse",
]
