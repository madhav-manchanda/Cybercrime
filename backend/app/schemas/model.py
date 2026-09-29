"""Model registry, evaluation metrics and synthetic generation schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.core.enums import ModelKind, ModelStatus, TrainingStatus
from app.schemas.common import ORMModel, WritableModel


class ModelInfo(BaseModel):
    model_name: str
    model_version: str
    feature_version: str
    model_kind: ModelKind
    status: ModelStatus
    active: bool
    artifact_path: str | None = None
    params: dict[str, Any] = {}
    last_trained_at: datetime | None = None
    metrics: dict[str, Any] = {}


class MetricRow(BaseModel):
    metric_name: str
    value: float
    scope: str
    sample_size: int
    computed_at: datetime
    model_version: str


class ModelMetricsBundle(BaseModel):
    model_name: str
    version: str
    evaluated_on: Literal["synthetic", "operational", "unknown"] = "synthetic"
    sample_size: int | None = None
    metrics: dict[str, float] = {}
    detailed: list[MetricRow] = []
    disclaimer: str = "Evaluation performed on synthetic data only."


class TrainModelRequest(WritableModel):
    model_name: str = Field(default="cashout-risk", max_length=80)
    force: bool = False


SyntheticPattern = Literal["ALL", "UPI_FRAUD", "PHISHING", "ACCOUNT_TAKEOVER", "INVESTMENT_FRAUD"]


class SyntheticGenerateRequest(WritableModel):
    number_of_cases: int = Field(default=25, ge=1, le=500)
    number_of_transactions: int = Field(default=1200, ge=1, le=50_000)
    number_of_accounts: int = Field(default=300, ge=1, le=10_000)
    number_of_atms: int = Field(default=60, ge=1, le=5000)
    geographic_area: str = "Lucknow"
    center_lat: float | None = Field(default=None, ge=-90, le=90)
    center_lon: float | None = Field(default=None, ge=-180, le=180)
    time_range_days: int = Field(default=180, ge=1, le=3650)
    fraud_patterns: SyntheticPattern = "ALL"
    seed: int | None = Field(default=None, ge=0, le=2**32)


class SyntheticGenerateResult(BaseModel):
    job_id: str
    status: str
    dataset_id: str
    counts: dict[str, int]
    message: str
    disclaimer: str = (
        "All generated records are SYNTHETIC and clearly marked data_source='synthetic'. "
        "They must never be presented as real-world statistics."
    )


class SyntheticTaskStatus(BaseModel):
    job_id: str
    status: str
    progress: float = 0.0
    error: str | None = None
    result: SyntheticGenerateResult | None = None


class ModelRunOut(ORMModel):
    model_name: str
    model_version: str
    feature_version: str
    model_kind: ModelKind
    status: TrainingStatus
    started_at: datetime | None = None
    completed_at: datetime | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)
    artifact_path: str | None = None
    error_message: str | None = None


__all__ = [
    "MetricRow",
    "ModelInfo",
    "ModelMetricsBundle",
    "ModelRunOut",
    "SyntheticGenerateRequest",
    "SyntheticGenerateResult",
    "SyntheticTaskStatus",
    "TrainModelRequest",
]
