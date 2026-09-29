"""Synthetic dataset generation endpoints (prototype demo + training data)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import rate_limit, require_permission
from app.core.config import settings
from app.core.database import get_db
from app.core.enums import AuditAction, Permission
from app.core.errors import BadRequestError
from app.core.rate_limit import Limit
from app.models import User
from app.schemas.model import (
    SyntheticGenerateRequest,
    SyntheticGenerateResult,
    SyntheticTaskStatus,
)
from app.services.audit_service import audit_service
from app.services.synthetic_service import synthetic_service

router = APIRouter(prefix="/synthetic", tags=["synthetic"])

_gen_limit = Limit(key="synthetic", per=settings.rate_limit_synthetic_per_hour, unit="hour")


@router.post("/generate", response_model=SyntheticGenerateResult, status_code=202)
async def generate_synthetic(
    payload: SyntheticGenerateRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[None, Depends(rate_limit("synthetic:generate", _gen_limit))],
    user: Annotated[User, Depends(require_permission(Permission.SYNTHETIC_GENERATE))],
) -> SyntheticGenerateResult:
    result = synthetic_service.submit(payload=payload)
    await audit_service.record(
        session,
        action=AuditAction.SYNTHETIC_GENERATE,
        actor_id=user.id,
        actor_email=user.email,
        actor_role=user.role_name.value,
        resource="synthetic",
        resource_id=result.job_id,
        payload={"cases": payload.number_of_cases, "transactions": payload.number_of_transactions},
        request_id=request.state.request_id or "",
    )
    await session.commit()
    return result


@router.get("/jobs/{job_id}", response_model=SyntheticTaskStatus)
async def synthetic_status(
    job_id: str,
    session: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, Depends(require_permission(Permission.SYNTHETIC_GENERATE))],
) -> SyntheticTaskStatus:
    status = synthetic_service.status(job_id)
    if status is None:
        raise BadRequestError("Unknown synthetic job", code="JOB_NOT_FOUND")
    return status


@router.get("/jobs", response_model=list[SyntheticGenerateResult])
async def synthetic_jobs(
    session: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, Depends(require_permission(Permission.SYNTHETIC_GENERATE))],
    limit: int = 20,
) -> list[SyntheticGenerateResult]:
    return synthetic_service.recent_results(limit=limit)


__all__ = ["router"]
