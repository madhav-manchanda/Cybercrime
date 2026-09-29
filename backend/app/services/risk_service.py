"""ATM & case risk scoring (non-prediction risk surface).

Each ATM gets a static risk profile combining:

    historical cash-out signal + current case proximity
    + temporal similarity + network proximity + local hotspot intensity

The result is a probability-like score (0..1) with per-factor contributions,
identical philosophy to prediction risk with SHAP-style explainable factors.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.enums import CaseStatus, EntityType, RelationshipType
from app.core.geo import bbox_lat_lon_filter
from app.ml.spatial import hotspot_intensity
from app.ml.temporal import build_profile, temporal_similarity
from app.models import (
    AtmLocation,
    Case,
    CashWithdrawal,
    Entity,
    EntityRelationship,
)
from app.utils.geo import distance_km


class RiskService:
    """Computes ATM/case risk with transparent factor contributions."""

    async def atm_risk(
        self,
        session: AsyncSession,
        *,
        atm: AtmLocation,
        recent_hours: int = 24 * 90,
        as_of: datetime | None = None,
    ) -> dict[str, Any]:
        as_of = as_of or datetime.now(UTC)
        cutoff = as_of - timedelta(hours=recent_hours)
        lat = float(atm.latitude or 0.0)
        lon = float(atm.longitude or 0.0)

        # ---- historical cash-out signal at this ATM
        hist = list(
            (
                await session.scalars(
                    select(CashWithdrawal).where(
                        CashWithdrawal.atm_id == atm.id,
                        CashWithdrawal.timestamp >= cutoff,
                    )
                )
            ).all()
        )
        hist_count = len(hist)
        hist_amount = sum(w.amount for w in hist)
        hist_signal = min(
            1.0,
            (0.35 * min(hist_count / 5.0, 1.0)) + (0.25 * min(hist_amount / 100_000.0, 1.0)),
        )

        # ---- current case proximity: open cases whose entities sit nearby
        nearby_cases = await self._nearby_case_pressure(session, atm)
        case_proximity = 0.0
        nearest_case_km: float | None = None
        nearest_case_id: str | None = None
        if nearby_cases:
            d = distance_km(
                lat,
                lon,
                nearby_cases[0]["lat"],
                nearby_cases[0]["lon"],
            )
            nearest_case_km = round(d, 2)
            nearest_case_id = nearby_cases[0]["case_id"]
            case_proximity = float(np.exp(-((d / 5.0) ** 2)))

        # ---- temporal similarity for the ATM
        global_profile = build_profile([w.timestamp for w in hist], reference=as_of)
        if hist:
            hours = [w.timestamp.hour for w in hist]
            atm_hour = float(max(set(hours), key=hours.count))
        else:
            atm_hour = 12.0
        temporal = temporal_similarity(global_profile, atm_hour)

        # ---- network proximity: WITHDREW_AT links targeting this ATM
        network_links = await self._network_link_count(session, atm)
        network = min(1.0, network_links / 4.0)

        # ---- regional hotspot intensity (recent 30 days of withdrawals)
        region = list(
            (
                await session.scalars(
                    select(CashWithdrawal)
                    .join(AtmLocation, AtmLocation.id == CashWithdrawal.atm_id)
                    .where(CashWithdrawal.timestamp >= as_of - timedelta(days=30))
                    .options(selectinload(CashWithdrawal.atm))
                )
            ).all()
        )
        region_pts = [
            (w.atm.latitude, w.atm.longitude)
            for w in region
            if w.atm and w.atm.latitude is not None and w.atm.longitude is not None
        ]
        hotspot = (
            hotspot_intensity(
                lat,
                lon,
                [p[0] for p in region_pts],
                [p[1] for p in region_pts],
            )
            if region_pts
            else 0.0
        )

        weights = {
            "historical_cashout_proximity": 0.30,
            "current_case_proximity": 0.25,
            "temporal_similarity": 0.20,
            "network_proximity": 0.15,
            "local_hotspot_intensity": 0.10,
        }
        parts = {
            "historical_cashout_proximity": hist_signal,
            "current_case_proximity": case_proximity,
            "temporal_similarity": temporal,
            "network_proximity": network,
            "local_hotspot_intensity": hotspot,
        }
        risk = sum(weights[k] * parts[k] for k in weights)

        factors: list[dict[str, Any]] = [
            {
                "factor": k,
                "impact": round(weights[k] * (parts[k] - 0.5), 4),
                "detail": _factor_detail(k, parts[k], hist_count, nearest_case_km, network_links),
            }
            for k in weights
        ]
        factors.sort(key=lambda f: abs(f["impact"]), reverse=True)

        spread = (max(parts.values()) - min(parts.values())) if parts else 0.0
        confidence = float(np.clip(0.5 + 0.5 * (1.0 - spread / 0.8), 0.1, 0.97))
        return {
            "atm_id": atm.id,
            "code": atm.code,
            "name": atm.name,
            "latitude": atm.latitude,
            "longitude": atm.longitude,
            "risk_score": round(float(np.clip(risk, 0.0, 1.0)), 4),
            "confidence": round(confidence, 4),
            "status": atm.status,
            "contributing_factors": factors,
            "as_of": as_of,
            "extra": {
                "nearest_case_km": nearest_case_km,
                "nearest_case_id": nearest_case_id,
                "historical_withdrawals": hist_count,
                "historical_amount": round(hist_amount, 2),
                "network_links": network_links,
            },
        }

    async def rank_atms(
        self,
        session: AsyncSession,
        *,
        min_lat: float | None = None,
        max_lat: float | None = None,
        min_lon: float | None = None,
        max_lon: float | None = None,
        top_n: int = 50,
    ) -> list[dict[str, Any]]:
        query = select(AtmLocation)
        if any(x is not None for x in (min_lat, max_lat, min_lon, max_lon)):
            query = bbox_lat_lon_filter(
                query,
                AtmLocation,
                min_lat=min_lat,
                max_lat=max_lat,
                min_lon=min_lon,
                max_lon=max_lon,
            )
        rows = (await session.scalars(query)).all()
        bounded = rows[: min(max(top_n * 4, 60), 500)]
        ranked = [await self.atm_risk(session, atm=atm) for atm in bounded]
        ranked.sort(key=lambda r: r["risk_score"], reverse=True)
        return ranked[:top_n]

    async def _nearby_case_pressure(self, session: AsyncSession, atm: AtmLocation) -> list[dict[str, Any]]:
        """Open-case entities with coords within ~25km of this ATM."""
        if atm.latitude is None or atm.longitude is None:
            return []
        open_statuses = [s.value for s in CaseStatus.open_states()]
        rows = await session.execute(
            select(Entity, Case.case_number)
            .join(Case, Case.id == Entity.case_id)
            .where(
                Case.status.in_(open_statuses),
                Entity.latitude.is_not(None),
                Entity.longitude.is_not(None),
                Entity.case_id.is_not(None),
            )
        )
        pressure: list[dict[str, Any]] = []
        for entity, case_number in rows.all():
            if entity.latitude is None or entity.longitude is None:
                continue
            d = distance_km(entity.latitude, entity.longitude, atm.latitude, atm.longitude)
            if d <= 25.0:
                pressure.append(
                    {
                        "lat": entity.latitude,
                        "lon": entity.longitude,
                        "case_id": str(entity.case_id),
                        "case_number": case_number,
                        "distance_km": d,
                    }
                )
        pressure.sort(key=lambda p: p["distance_km"])
        return pressure

    async def _network_link_count(self, session: AsyncSession, atm: AtmLocation) -> int:
        """Count WITHDREW_AT edges whose target ATM entity == this location."""
        rows = await session.scalars(
            select(EntityRelationship)
            .join(Entity, Entity.id == EntityRelationship.target_entity_id)
            .where(
                EntityRelationship.relationship_type == RelationshipType.WITHDREW_AT.value,
                Entity.entity_type == EntityType.ATM.value,
                Entity.atm_id == atm.id,
            )
        )
        return len(list(rows.all()))


def _factor_detail(
    key: str, value: float, hist_count: int, nearest_case_km: float | None, network_links: int
) -> str:
    if key == "historical_cashout_proximity":
        return f"{hist_count} historical withdrawals recorded at this ATM"
    if key == "current_case_proximity":
        return (
            f"{nearest_case_km:.1f} km from nearest open-case activity"
            if nearest_case_km is not None
            else "no nearby open case"
        )
    if key == "temporal_similarity":
        return "withdrawal hour overlaps the region's cash-out time profile"
    if key == "network_proximity":
        return f"{network_links} network links to case entities"
    if key == "local_hotspot_intensity":
        return "within a dense regional cash-out hotspot"
    return ""


risk_service: RiskService = RiskService()

__all__ = ["RiskService", "risk_service"]
