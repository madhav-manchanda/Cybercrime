"""ATM inventory + cash-out risk endpoints (drives geo risk / hotspot ops)."""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission, require_roles
from app.core.database import get_db
from app.core.enums import AtmStatus, Permission, RoleName
from app.core.errors import ATM_NOT_FOUND, BadRequestError
from app.models import AtmLocation, User
from app.schemas.atm import (
    AtmCreateRequest,
    AtmOut,
    AtmRiskOut,
    AtmRiskRankingItem,
    RiskFactor,
)
from app.schemas.common import Page
from app.services.risk_service import risk_service

router = APIRouter(prefix="/atms", tags=["atms"])

# -- helper ------------------------------------------------------------------


def _risk_out(item: dict[str, Any], rank: int | None = None) -> AtmRiskRankingItem:
    factors = [
        RiskFactor(
            factor=str(f.get("factor", "")),
            impact=float(f.get("impact", 0.0)),
            detail=f.get("detail") or f.get("details"),
        )
        for f in (item.get("contributing_factors") or [])
    ]
    try:
        status = AtmStatus(item.get("status") or AtmStatus.ACTIVE)
    except ValueError:
        status = AtmStatus.ACTIVE
    base: dict[str, Any] = {
        "atm_id": item["atm_id"],
        "code": item["code"],
        "name": item["name"],
        "latitude": item.get("latitude"),
        "longitude": item.get("longitude"),
        "risk_score": float(item.get("risk_score", 0.0)),
        "confidence": float(item.get("confidence", 0.0)),
        "status": status,
        "contributing_factors": factors,
        "as_of": item["as_of"],
    }
    if rank is not None:
        base["rank"] = rank
    return AtmRiskRankingItem.model_validate(base)


# -- inventory ---------------------------------------------------------------


@router.post("", response_model=AtmOut, status_code=201)
@router.post("/", response_model=AtmOut, include_in_schema=False)
async def create_atm(
    payload: AtmCreateRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, Depends(require_roles(RoleName.ADMIN, RoleName.BANK_ANALYST))],
) -> AtmOut:
    existing = await session.scalar(select(AtmLocation).where(AtmLocation.code == payload.code))
    if existing is not None:
        raise BadRequestError(
            f"An ATM with code {payload.code!r} already exists.",
            code="DUPLICATE_ATM",
        )
    atm = AtmLocation(
        code=payload.code,
        name=payload.name,
        bank_name=payload.bank_name,
        status=payload.status,
        is_csp=payload.is_csp,
        address=payload.address,
        city=payload.city,
        state=payload.state,
        service_hours=payload.service_hours,
        latitude=payload.latitude,
        longitude=payload.longitude,
        base_load=payload.base_load,
        zone_type=payload.zone_type,
    )
    session.add(atm)
    await session.commit()
    await session.refresh(atm)
    return AtmOut.model_validate(atm)


@router.get("", response_model=Page[AtmOut])
@router.get("/", response_model=Page[AtmOut], include_in_schema=False)
async def list_atms(
    session: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, Depends(require_permission(Permission.ATM_READ))],
    page: int = 1,
    page_size: int = 50,
    state: str | None = None,
    code: str | None = None,
) -> Page[AtmOut]:
    page = max(page, 1)
    page_size = min(max(page_size, 1), 200)
    stmt = select(AtmLocation)
    count_stmt = select(func.count()).select_from(AtmLocation)
    if state:
        stmt = stmt.where(AtmLocation.state == state)
        count_stmt = count_stmt.where(AtmLocation.state == state)
    if code:
        stmt = stmt.where(AtmLocation.code.ilike(f"%{code}%"))
        count_stmt = count_stmt.where(AtmLocation.code.ilike(f"%{code}%"))
    total = int((await session.scalar(count_stmt)) or 0)
    rows = list(
        (
            await session.scalars(
                stmt.order_by(AtmLocation.code).offset((page - 1) * page_size).limit(page_size)
            )
        ).all()
    )
    items = [AtmOut.model_validate(a) for a in rows]
    pages = max((total + page_size - 1) // page_size, 1) if total else 0
    return Page[AtmOut](
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
        has_next=page < pages,
    )


@router.get("/rank", response_model=list[AtmRiskRankingItem])
async def rank_atms(
    session: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, Depends(require_permission(Permission.ATM_READ))],
    min_lat: float | None = None,
    max_lat: float | None = None,
    min_lon: float | None = None,
    max_lon: float | None = None,
    top_n: int = 50,
) -> list[AtmRiskRankingItem]:
    rows = await risk_service.rank_atms(
        session,
        min_lat=min_lat,
        max_lat=max_lat,
        min_lon=min_lon,
        max_lon=max_lon,
        top_n=min(max(top_n, 1), 100),
    )
    return [_risk_out(item, rank=i + 1) for i, item in enumerate(rows)]


@router.get("/{atm_id}/risk", response_model=AtmRiskOut)
async def atm_risk(
    atm_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, Depends(require_permission(Permission.ATM_READ))],
    recent_hours: int = 2160,
) -> AtmRiskOut:
    atm = await session.get(AtmLocation, atm_id)
    if atm is None:
        raise ATM_NOT_FOUND
    item = await risk_service.atm_risk(session, atm=atm, recent_hours=min(max(recent_hours, 1), 24 * 365))
    return _risk_out(item)


@router.get("/{atm_id}", response_model=AtmOut)
async def get_atm(
    atm_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, Depends(require_permission(Permission.ATM_READ))],
) -> AtmOut:
    atm = await session.get(AtmLocation, atm_id)
    if atm is None:
        raise ATM_NOT_FOUND
    return AtmOut.model_validate(atm)


__all__ = ["router"]
