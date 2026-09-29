"""Model runs and evaluation metrics."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON, Uuid

from app.core.database import Base
from app.core.enums import ModelKind, TrainingStatus
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin, utcnow

if TYPE_CHECKING:
    pass


class ModelRun(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One training / evaluation run of a registered model."""

    __tablename__ = "model_runs"
    __table_args__ = (
        Index("ix_model_runs_name_status", "model_name", "status"),
        Index("ix_model_runs_version", "model_name", "model_version"),
    )

    model_name: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    model_version: Mapped[str] = mapped_column(String(32), nullable=False)
    feature_version: Mapped[str] = mapped_column(String(32), default="1.0", nullable=False)
    model_kind: Mapped[ModelKind] = mapped_column(String(16), default=ModelKind.RANKER)
    status: Mapped[TrainingStatus] = mapped_column(String(16), default=TrainingStatus.QUEUED, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    train_sample_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    artifact_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    params: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    error_message: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    triggered_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class ModelMetric(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Flat, queryable metric rows from a model run."""

    __tablename__ = "model_metrics"
    __table_args__ = (Index("ix_model_metrics_run", "model_run_id"),)

    model_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("model_runs.id", ondelete="CASCADE"), nullable=False
    )
    model_name: Mapped[str] = mapped_column(String(80), nullable=False)
    model_version: Mapped[str] = mapped_column(String(32), nullable=False)
    metric_name: Mapped[str] = mapped_column(String(64), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    scope: Mapped[str] = mapped_column(String(16), default="TEST", nullable=False)
    sample_size: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


__all__ = ["ModelMetric", "ModelRun"]
