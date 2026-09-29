"""Synthetic-generation job manager (in-memory, per-process)."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

from app.core.database import async_session_factory
from app.core.enums import RealtimeEventType
from app.schemas.model import (
    SyntheticGenerateRequest,
    SyntheticGenerateResult,
    SyntheticTaskStatus,
)
from app.services.realtime_service import event_hub
from app.synthetic.generator import generate_dataset

_RESULTS: dict[str, SyntheticGenerateResult] = {}


class SyntheticService:
    """Submit and track synthetic dataset generation jobs."""

    def __init__(self) -> None:
        self._tasks: dict[str, dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    def submit(self, *, payload: SyntheticGenerateRequest) -> SyntheticGenerateResult:
        job_id = str(uuid.uuid4())
        result = SyntheticGenerateResult(
            job_id=job_id,
            status="QUEUED",
            dataset_id=job_id,
            counts={},
            message="Synthetic generation queued.",
        )
        _RESULTS[job_id] = result
        self._tasks[job_id] = {
            "status": "QUEUED",
            "progress": 0.0,
            "error": None,
            "result": result,
            "payload": payload,
        }
        asyncio.get_running_loop().create_task(self._run(job_id))
        return result

    def status(self, job_id: str) -> SyntheticTaskStatus | None:
        task = self._tasks.get(job_id)
        if task is None:
            return None
        return SyntheticTaskStatus(
            job_id=job_id,
            status=str(task["status"]),
            progress=float(task.get("progress", 0.0)),
            error=task.get("error"),
            result=task.get("result"),
        )

    async def _run(self, job_id: str) -> None:
        task = self._tasks[job_id]
        task["status"] = "RUNNING"
        task["progress"] = 0.05
        payload: SyntheticGenerateRequest = task["payload"]
        try:
            async with async_session_factory() as session:
                counts = await generate_dataset(
                    session,
                    number_of_cases=payload.number_of_cases,
                    number_of_transactions=payload.number_of_transactions,
                    number_of_accounts=payload.number_of_accounts,
                    number_of_atms=payload.number_of_atms,
                    geographic_area=payload.geographic_area,
                    center_lat=payload.center_lat,
                    center_lon=payload.center_lon,
                    time_range_days=payload.time_range_days,
                    fraud_patterns=payload.fraud_patterns,
                    seed=payload.seed,
                )
                await session.commit()
            result = SyntheticGenerateResult(
                job_id=job_id,
                status="SUCCEEDED",
                dataset_id=job_id,
                counts=counts,
                message=(
                    "Synthetic dataset generated. All records are marked "
                    "data_source='synthetic' and must not be presented as real-world data."
                ),
            )
            task.update({"status": "SUCCEEDED", "progress": 1.0, "result": result})
            _RESULTS[job_id] = result
            await event_hub.publish(
                RealtimeEventType.SYNTHETIC_GENERATED,
                {"job_id": job_id, "counts": counts},
            )
        except Exception as exc:  # pragma: no cover - defensive
            task["status"] = "FAILED"
            task["error"] = str(exc)[:2000]
            task["progress"] = 1.0
            result = SyntheticGenerateResult(
                job_id=job_id,
                status="FAILED",
                dataset_id=job_id,
                counts={},
                message=f"Synthetic generation failed: {str(exc)[:200]}",
            )
            _RESULTS[job_id] = result
            task["result"] = result

    @staticmethod
    def recent_results(limit: int = 20) -> list[SyntheticGenerateResult]:
        ordered = sorted(_RESULTS.values(), key=lambda r: r.dataset_id, reverse=True)
        return ordered[: max(limit, 1)]


synthetic_service: SyntheticService = SyntheticService()

__all__ = ["SyntheticService", "synthetic_service"]
