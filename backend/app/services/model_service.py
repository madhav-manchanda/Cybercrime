"""Model registry/training facade for the HTTP layer.

Wraps :mod:`app.ml.model_registry`, :mod:`app.ml.datasets` and
:mod:`app.ml.train` behind a service interface and journal every run in the
``model_runs`` table.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.enums import (
    ModelKind,
    ModelStatus,
    RealtimeEventType,
    TrainingStatus,
)
from app.core.errors import MODEL_NOT_FOUND
from app.ml.datasets import build_training_frame
from app.ml.model_registry import registry
from app.ml.train import train_ranker_on_frame
from app.models import ModelRun, User
from app.schemas.model import ModelInfo
from app.services.realtime_service import event_hub

_MODEL_STATES: dict[str, ModelStatus] = {
    TrainingStatus.SUCCEEDED.value: ModelStatus.ACTIVE,
    TrainingStatus.FAILED.value: ModelStatus.FAILED,
    TrainingStatus.SKIPPED.value: ModelStatus.DRAFT,
    TrainingStatus.RUNNING.value: ModelStatus.TRAINING,
    TrainingStatus.QUEUED.value: ModelStatus.DRAFT,
}


class ModelService:
    """Journal + registry facade for model training/listing."""

    async def list_models(self, session: AsyncSession) -> list[ModelInfo]:
        runs = list((await session.scalars(select(ModelRun).order_by(desc(ModelRun.created_at)))).all())
        latest: dict[str, ModelRun] = {}
        for run in runs:
            if run.model_name not in latest and run.model_version != "none":
                latest[run.model_name] = run
        infos: list[ModelInfo] = []
        registry_meta = self._registry_versions()
        for name, run in latest.items():
            meta = registry_meta.get(name)
            status = _MODEL_STATES.get(
                run.status.value if hasattr(run.status, "value") else str(run.status),
                ModelStatus.DRAFT,
            )
            infos.append(
                ModelInfo(
                    model_name=run.model_name,
                    model_version=run.model_version,
                    feature_version=run.feature_version,
                    model_kind=run.model_kind,
                    status=status,
                    active=status == ModelStatus.ACTIVE,
                    artifact_path=run.artifact_path,
                    params=run.params or {},
                    last_trained_at=run.completed_at or run.started_at or run.created_at,
                    metrics=self._metrics_public(run.metrics or {}),
                )
            )
            if meta:
                infos[-1] = infos[-1].model_copy(
                    update={"artifact_path": meta.get("artifact"), "active": bool(meta.get("active"))}
                )
        if not infos:
            infos.append(self._placeholder_model())
        return infos

    async def get_model(self, session: AsyncSession, model_name: str) -> ModelInfo:
        run = await session.scalar(
            select(ModelRun)
            .where(ModelRun.model_name == model_name)
            .order_by(desc(ModelRun.created_at))
            .limit(1)
        )
        if run is None:
            raise MODEL_NOT_FOUND
        infos = await self.list_models(session)
        for info in infos:
            if info.model_name == model_name:
                return info
        raise MODEL_NOT_FOUND

    async def train(
        self,
        session: AsyncSession,
        *,
        model_name: str,
        force: bool,
        actor: User,
    ) -> ModelRun:
        """Train (or re-train) the ranker on the synthetic training frame."""
        active = await session.scalar(
            select(ModelRun)
            .where(
                ModelRun.model_name == model_name,
                ModelRun.status == TrainingStatus.SUCCEEDED,
            )
            .order_by(desc(ModelRun.created_at))
            .limit(1)
        )
        if active is not None and not force:
            active.triggered_by = actor.id
            await session.commit()
            await session.refresh(active)
            return active

        run = ModelRun(
            model_name=model_name,
            model_version="queued",
            model_kind=ModelKind.RANKER,
            status=TrainingStatus.RUNNING,
            started_at=datetime.now(UTC),
            triggered_by=actor.id,
        )
        session.add(run)
        await session.flush()

        try:
            frame = await build_training_frame(
                session, limit_cases=settings.ml_train_limit_cases, seed=settings.ml_random_seed
            )
            result = await asyncio.to_thread(
                train_ranker_on_frame, frame, tune=True, random_state=settings.ml_random_seed
            )
        except Exception as exc:  # pragma: no cover - defensive
            run.status = TrainingStatus.FAILED
            run.error_message = str(exc)[:2000]
            run.completed_at = datetime.now(UTC)
            await session.commit()
            await session.refresh(run)
            return run

        run.model_version = result.model_version
        run.status = TrainingStatus(result.status)
        run.completed_at = datetime.now(UTC)
        run.train_sample_count = result.sample_count or None
        run.metrics = {"provenance": "synthetic", **result.metrics}
        run.params = {"tune": True}
        run.artifact_path = result.artifact_path
        run.error_message = result.error
        await session.commit()
        await session.refresh(run)
        if run.status == TrainingStatus.SUCCEEDED:
            await event_hub.publish(
                RealtimeEventType.MODEL_TRAINED,
                {"model_name": run.model_name, "model_version": run.model_version},
            )
        return run

    @staticmethod
    def _metrics_public(metrics: dict[str, Any]) -> dict[str, Any]:
        public = {k: v for k, v in metrics.items() if k != "provenance"}
        public["source"] = "synthetic"
        return public

    @staticmethod
    def _registry_versions() -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for name in ("cashout-risk", "cashout-risk-ranker"):
            for meta in registry.list_versions(name):
                out.setdefault(name, meta)
        return out

    @staticmethod
    def _placeholder_model() -> ModelInfo:
        return ModelInfo(
            model_name="cashout-risk",
            model_version="none",
            feature_version="1.0",
            model_kind=ModelKind.RANKER,
            status=ModelStatus.DRAFT,
            active=False,
            metrics={"source": "synthetic"},
        )


model_service: ModelService = ModelService()

__all__ = ["ModelService", "model_service"]
