"""Celery application, periodic beat schedule and task routing.

The worker runs blocking helpers inside ``asyncio.run`` because all domain
services are async (``AsyncSession``/``asyncpg``).  Each task opens its own
session via :func:`app.core.database.session_scope` so a failing task never
leaks a transaction.  The passage between greenlet worlds (Celery worker ->
asyncio event loop) happens once per task invocation, so ``MissingGreenlet``
is impossible by construction.

Run:
    celery -A app.workers.celery_app:celery_app worker --loglevel=info
    celery -A app.workers.celery_app:celery_app beat --loglevel=info
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime
from typing import Any, TypeVar

from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

logger = logging.getLogger("app.workers")

T = TypeVar("T")

celery_app = Celery(
    "cybercrime-intelligence",
    broker=settings.broker_url,
    backend=settings.result_backend,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_ignore_result=False,
    task_time_limit=10 * 60,
    task_soft_time_limit=9 * 60,
    broker_connection_retry_on_startup=True,
    task_default_queue="default",
    task_routes={"app.workers.tasks.purge_expired_refresh_tokens": {"queue": "maintenance"}},
    beat_schedule={
        "retrain-cashout-ranker-hourly": {
            "task": "app.workers.tasks.retrain_cashout_model",
            "schedule": crontab(minute=12),  # hourly
            "args": (),
        },
        "purge-expired-refresh-tokens-daily": {
            "task": "app.workers.tasks.purge_expired_refresh_tokens",
            "schedule": crontab(hour=3, minute=40),  # daily low-traffic window
            "args": (),
        },
        "prune-audit-consolidate-daily": {
            "task": "app.workers.tasks.log_daily_health",
            "schedule": crontab(hour=4, minute=10),
            "args": (),
        },
    },
)


def run_async[T](coro_factory: Callable[[], Coroutine[Any, Any, T]]) -> T:
    """Run an async callable to completion from a sync Celery context."""
    return asyncio.run(coro_factory())


def _run_task(
    block: Callable[[], Coroutine[Any, Any, dict[str, Any]]], *, name: str
) -> dict[str, Any]:
    """Shared wrapper: run one task body and log a consistent summary line."""
    started = datetime.now(UTC)
    logger.info("task=%s started", name)
    try:
        result = run_async(block)
        logger.info("task=%s finished took=%ss result=%s", name, (datetime.now(UTC) - started).total_seconds(), result)
        return result
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("task=%s failed", name)
        return {"ok": False, "task": name, "error": str(exc)[:2000]}