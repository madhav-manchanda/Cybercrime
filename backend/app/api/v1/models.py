"""Model registry + training endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.database import get_db
from app.core.enums import AuditAction, Permission
from app.models import User
from app.schemas.model import ModelInfo, ModelRunOut, TrainModelRequest
from app.services.audit_service import audit_service
from app.services.model_service import model_service

router = APIRouter(prefix="/models", tags=["models"])


@router.get("", response_model=list[ModelInfo])
@router.get("/", response_model=list[ModelInfo], include_in_schema=False)
async def list_models(
    session: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, Depends(require_permission(Permission.MODEL_READ))],
) -> list[ModelInfo]:
    return await model_service.list_models(session)


@router.get("/{model_name}", response_model=ModelInfo)
async def get_model(
    model_name: str,
    session: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, Depends(require_permission(Permission.MODEL_READ))],
) -> ModelInfo:
    return await model_service.get_model(session, model_name=model_name)


@router.post("/train", response_model=ModelRunOut, status_code=202)
async def train_model(
    payload: TrainModelRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(Permission.MODEL_TRAIN))],
) -> ModelRunOut:
    run = await model_service.train(session, model_name=payload.model_name, force=payload.force, actor=user)
    await audit_service.record(
        session,
        action=AuditAction.MODEL_TRAIN,
        actor_id=user.id,
        actor_email=user.email,
        actor_role=user.role_name.value,
        resource="model",
        resource_id=run.id,
        payload={
            "model_name": run.model_name,
            "version": run.model_version,
            "status": run.status.value if hasattr(run.status, "value") else str(run.status),
            "provenance": "synthetic",
        },
        request_id=request.state.request_id or "",
    )
    await session.commit()
    await session.refresh(run)
    return ModelRunOut.model_validate(run)


__all__ = ["router"]
