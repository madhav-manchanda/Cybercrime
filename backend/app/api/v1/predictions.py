"""Prediction endpoints: run, list, latest-locations, single view."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import rate_limit, require_permission
from app.core.config import settings
from app.core.database import get_db
from app.core.enums import AuditAction, Permission
from app.core.rate_limit import Limit
from app.models import AtmLocation, Prediction, PredictionLocation, User
from app.schemas.common import FactorContribution, TimeWindowBound
from app.schemas.prediction import (
    PredictionLocationOut,
    PredictionOut,
    PredictionRequest,
    RunPredictionResponse,
)
from app.services.audit_service import audit_service
from app.services.case_service import case_service
from app.services.prediction_service import prediction_service

router = APIRouter(prefix="/cases", tags=["predictions"])

_predict_limit = Limit(key="predict", per=settings.rate_limit_predict_per_minute, unit="minute")


def _location_out(location: PredictionLocation, atm: AtmLocation | None) -> PredictionLocationOut:
    window = (
        TimeWindowBound(start=location.time_window_start, end=location.time_window_end)
        if location.time_window_start and location.time_window_end
        else None
    )
    factors: list[FactorContribution] = []
    for item in location.contributing_factors or []:
        factors.append(
            FactorContribution(
                factor=str(item.get("factor", "")),
                impact=float(item.get("impact", 0.0)),
                details=item.get("detail") or item.get("details"),
            )
        )
    return PredictionLocationOut(
        location_id=location.id,
        atm_id=location.atm_id,
        rank=location.rank,
        risk_score=location.risk_score,
        confidence=location.confidence,
        time_window=window,
        contributing_factors=factors,
        explanation_text=location.explanation_text,
        latitude=atm.latitude if atm else None,
        longitude=atm.longitude if atm else None,
        atm_code=atm.code if atm else None,
        atm_name=atm.name if atm else None,
    )


async def _prediction_out(session: AsyncSession, prediction: Prediction) -> PredictionOut:
    locations = list(
        await session.scalars(
            select(PredictionLocation)
            .where(PredictionLocation.prediction_id == prediction.id)
            .order_by(PredictionLocation.rank)
        )
    )
    atm_ids = [loc.atm_id for loc in locations]
    atms: dict[uuid.UUID, AtmLocation] = {}
    if atm_ids:
        rows = (await session.scalars(select(AtmLocation).where(AtmLocation.id.in_(atm_ids)))).all()
        atms = {a.id: a for a in rows}
    return PredictionOut(
        id=prediction.id,
        created_at=prediction.created_at,
        updated_at=prediction.updated_at,
        case_id=prediction.case_id,
        status=prediction.status,
        horizon=prediction.horizon,
        headline_risk=prediction.headline_risk,
        predicted_amount=prediction.predicted_amount,
        generated_at=prediction.generated_at,
        completed_at=prediction.completed_at,
        model_name=prediction.model_name,
        model_version=prediction.model_version,
        feature_version=prediction.feature_version,
        locations=[_location_out(loc, atms.get(loc.atm_id)) for loc in locations],
        metadata_json=prediction.metadata_json or {},
    )


@router.post("/{case_id}/predict", response_model=RunPredictionResponse, status_code=201)
async def run_prediction(
    case_id: uuid.UUID,
    payload: PredictionRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[None, Depends(rate_limit("prediction:run", _predict_limit))],
    user: Annotated[User, Depends(require_permission(Permission.PREDICTION_RUN))],
) -> RunPredictionResponse:
    case = await case_service.get(session, case_id=case_id)
    prediction = await prediction_service.run(session, case=case, request=payload, actor=user)
    await audit_service.record(
        session,
        action=AuditAction.PREDICTION_RUN,
        actor_id=user.id,
        actor_email=user.email,
        actor_role=user.role_name.value,
        resource="prediction",
        resource_id=prediction.id,
        payload={"horizon": payload.horizon, "top_k": payload.top_k},
        request_id=request.state.request_id or "",
    )
    await session.commit()
    out = await _prediction_out(session, prediction)
    return RunPredictionResponse(
        case_id=str(case_id),
        prediction_id=str(prediction.id),
        queued=False,
        completed=True,
        result=out,
    )


@router.get("/{case_id}/predictions", response_model=list[PredictionOut])
async def list_predictions(
    case_id: uuid.UUID,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(require_permission(Permission.PREDICTION_READ))],
    limit: int = 10,
) -> list[PredictionOut]:
    await case_service.get(session, case_id=case_id)
    rows = await prediction_service.list_by_case(session, case_id=case_id, limit=min(max(limit, 1), 50))
    await audit_service.record(
        session,
        action=AuditAction.PREDICTION_READ,
        actor_id=user.id,
        actor_email=user.email,
        actor_role=user.role_name.value,
        resource="prediction",
        resource_id=case_id,
        request_id=request.state.request_id or "",
    )
    await session.commit()
    return [await _prediction_out(session, p) for p in rows]


@router.get("/{case_id}/predictions/latest-locations", response_model=list[PredictionLocationOut])
async def latest_locations(
    case_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, Depends(require_permission(Permission.PREDICTION_READ))],
) -> list[PredictionLocationOut]:
    locations = await prediction_service.latest_location_predictions(session, case_id=case_id)
    atm_ids = [loc.atm_id for loc in locations]
    atms: dict[uuid.UUID, AtmLocation] = {}
    if atm_ids:
        rows = (await session.scalars(select(AtmLocation).where(AtmLocation.id.in_(atm_ids)))).all()
        atms = {a.id: a for a in rows}
    return [_location_out(loc, atms.get(loc.atm_id)) for loc in locations]


@router.get("/{case_id}/predictions/{prediction_id}", response_model=PredictionOut)
async def get_prediction(
    case_id: uuid.UUID,
    prediction_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, Depends(require_permission(Permission.PREDICTION_READ))],
) -> PredictionOut:
    await case_service.get(session, case_id=case_id)
    prediction = await prediction_service.get(session, prediction_id=prediction_id)
    return await _prediction_out(session, prediction)


__all__ = ["router"]
