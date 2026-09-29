"""Periodic background jobs for the platform.

Tasks registered here drive the Celery beat schedule defined in
:mod:`app.workers.celery_app`.  Each task rehydrates the app session with
:func:`app.core.database.session_scope` and returns a plain JSON-safe summary
dict that is stored in the Celery result backend.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, cast

from celery.utils.log import get_task_logger
from sqlalchemy import delete, func, select
from sqlalchemy.engine import CursorResult

from app.core.database import session_scope
from app.models import User
from app.models.model_run import ModelRun
from app.models.refresh_token import RefreshTokenSession
from app.services.model_service import model_service
from app.utils.validators import as_str

logger = get_task_logger(__name__)


def retrain_cashout_model() -> dict[str, Any]:
    """Periodically re-train the ranker from the synthetic training frame.

    Uses ``force=True`` so the cadence is meaningful; training runs inside
    ``asyncio.to_thread`` upstream, keeping the worker loop responsive.
    """

    async def _body() -> dict[str, Any]:
        async with session_scope() as session:
            actor = await session.scalar(
                select(User).order_by(User.created_at).limit(1)
            )
            if actor is None:
                return {"ok": False, "reason": "no user to attribute training run"}
            run = await model_service.train(
                session,
                model_name="cashout-risk",
                force=True,
                actor=actor,
            )
            status = as_str(run.status)
            return {
                "ok": status == "SUCCEEDED",
                "model_name": run.model_name,
                "model_version": run.model_version,
                "status": status,
                "sample_count": run.train_sample_count,
                "error": run.error_message,
            }

    from app.workers.celery_app import _run_task

    return _run_task(_body, name=__name__)


def purge_expired_refresh_tokens() -> dict[str, Any]:
    """Remove refresh-token sessions that are expired (or revoked too old)."""

    async def _body() -> dict[str, Any]:
        now = datetime.now(UTC)
        async with session_scope() as session:
            result = cast(CursorResult[Any], await session.execute(delete(RefreshTokenSession).where(RefreshTokenSession.expires_at < now)))
            count = result.rowcount or 0
            logger.info("purged %s expired refresh tokens", count)
            return {"ok": True, "purged": count}

    from app.workers.celery_app import _run_task

    return _run_task(_body, name=__name__)


def log_daily_health() -> dict[str, Any]:
    """One-line health snapshot so operators can confirm the platform is alive."""

    async def _body() -> dict[str, Any]:
        async with session_scope() as session:
            user_count = await session.scalar(select(func.count(User.id)))
            recent_runs = await session.scalar(
                select(func.count(ModelRun.id)).where(ModelRun.created_at > datetime.now(UTC) - timedelta(days=1))
            )
            return {"ok": True, "users": user_count, "model_runs_24h": recent_runs or 0}

    from app.workers.celery_app import _run_task

    return _run_task(_body, name=__name__)


__all__ = ["log_daily_health", "purge_expired_refresh_tokens", "retrain_cashout_model"]