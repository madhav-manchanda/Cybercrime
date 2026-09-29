"""Analytics + geospatial (GeoJSON) endpoints."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.database import get_db
from app.core.enums import Permission
from app.models import User
from app.schemas.analytics import (
    AnalyticsOverview,
    CaseSeriesPoint,
    GeoJSONFeature,
    GeoJSONFeatureCollection,
    HotspotSummary,
    RiskDistribution,
)
from app.services.analytics_service import analytics_service

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/overview", response_model=AnalyticsOverview)
async def overview(
    session: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, Depends(require_permission(Permission.ANALYTICS_READ))],
) -> AnalyticsOverview:
    return await analytics_service.overview(session)


@router.get("/cases-over-time", response_model=list[CaseSeriesPoint])
async def cases_over_time(
    session: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, Depends(require_permission(Permission.ANALYTICS_READ))],
    days: int = 30,
) -> list[CaseSeriesPoint]:
    rows = await analytics_service.cases_over_time(session, days=max(min(days, 365), 1))
    return [CaseSeriesPoint.model_validate(r) for r in rows]


@router.get("/risk-distribution", response_model=RiskDistribution)
async def risk_distribution(
    session: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, Depends(require_permission(Permission.ANALYTICS_READ))],
) -> RiskDistribution:
    data = await analytics_service.risk_distribution(session)
    return RiskDistribution.model_validate(data)


@router.get("/outcomes-summary", response_model=dict)
async def outcomes_summary(
    session: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, Depends(require_permission(Permission.ANALYTICS_READ))],
) -> dict:
    return await analytics_service.outcomes_summary(session)


@router.get("/cases/{case_id}/risk-history", response_model=list[dict])
async def case_risk_history(
    case_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, Depends(require_permission(Permission.ANALYTICS_READ))],
) -> list[dict]:
    return await analytics_service.case_risk_history(session, case_id=case_id)


@router.get("/hotspots", response_model=list[HotspotSummary])
async def hotspots(
    session: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, Depends(require_permission(Permission.ANALYTICS_READ))],
    min_lat: float | None = None,
    max_lat: float | None = None,
    min_lon: float | None = None,
    max_lon: float | None = None,
) -> list[HotspotSummary]:
    rows = await analytics_service.hotspots(
        session,
        min_lat=min_lat,
        max_lat=max_lat,
        min_lon=min_lon,
        max_lon=max_lon,
    )
    return [HotspotSummary.model_validate(r) for r in rows]


@router.get("/geojson", response_model=GeoJSONFeatureCollection)
async def geojson(
    session: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, Depends(require_permission(Permission.ANALYTICS_READ))],
) -> GeoJSONFeatureCollection:
    rows = await analytics_service.hotspots(session)
    features: list[GeoJSONFeature] = []
    for row in rows:
        features.append(
            GeoJSONFeature(
                geometry={
                    "type": "Point",
                    "coordinates": [row["longitude"], row["latitude"]],
                },
                properties={
                    "id": row["id"],
                    "label": row["label"],
                    "risk_score": row["risk_score"],
                    "case_count": row["case_count"],
                    "predicted_amount": row["predicted_amount"],
                },
            )
        )
    return GeoJSONFeatureCollection(
        features=features,
        meta={
            "source_scope": "synthetic",
            "disclaimer": "Derived from synthetic records only; not real-world intelligence.",
        },
    )


__all__ = ["router"]
