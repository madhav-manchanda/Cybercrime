"""Analytics aggregation: dashboards, trends, risk distribution, hotspots."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.enums import AlertSeverity, AlertStatus, CaseStatus
from app.models import (
    Alert,
    Case,
    CashWithdrawal,
    Outcome,
    Prediction,
    PredictionLocation,
    RiskScore,
    Transaction,
)
from app.schemas.analytics import (
    AnalyticsOverview,
    HotspotSummary,
    RiskDistributionBucket,
)
from app.utils.validators import as_str


class AnalyticsService:
    """Read-only aggregate views for the analytics endpoints."""

    async def overview(self, session: AsyncSession) -> AnalyticsOverview:
        open_states = [s.value for s in CaseStatus.open_states()]
        active_cases = (
            await session.scalar(
                select(func.count())
                .select_from(Case)
                .where(Case.status.in_([*open_states, CaseStatus.RESOLVED.value]))
            )
            or 0
        )
        open_cases = (
            await session.scalar(select(func.count()).select_from(Case).where(Case.status.in_(open_states)))
            or 0
        )
        high_risk = (
            await session.scalar(select(func.count()).select_from(Case).where(Case.current_risk_score >= 0.7))
            or 0
        )
        active_alerts = (
            await session.scalar(
                select(func.count())
                .select_from(Alert)
                .where(Alert.status.in_([AlertStatus.OPEN.value, AlertStatus.ACKNOWLEDGED.value]))
            )
            or 0
        )
        critical_alerts = (
            await session.scalar(
                select(func.count())
                .select_from(Alert)
                .where(
                    Alert.status == AlertStatus.OPEN.value,
                    Alert.severity == AlertSeverity.CRITICAL.value,
                )
            )
            or 0
        )
        predicted_locations = await session.scalar(select(func.count()).select_from(PredictionLocation)) or 0
        total_volume = await session.scalar(select(func.coalesce(func.sum(Transaction.amount), 0.0))) or 0.0
        transaction_count = await session.scalar(select(func.count()).select_from(Transaction)) or 0
        prediction_count = await session.scalar(select(func.count()).select_from(Prediction)) or 0
        active_investigations = (
            await session.scalar(
                select(func.count())
                .select_from(Case)
                .where(Case.status == CaseStatus.INVESTIGATION_ACTIVE.value)
            )
            or 0
        )
        resolved_cases = (
            await session.scalar(
                select(func.count())
                .select_from(Case)
                .where(Case.status.in_([CaseStatus.RESOLVED.value, CaseStatus.CLOSED.value]))
            )
            or 0
        )

        # optimistic but honest accuracy estimate only when outcomes exist
        prediction_accuracy = await self._prediction_accuracy(session)

        return AnalyticsOverview(
            active_cases=int(active_cases),
            open_cases=int(open_cases),
            high_risk_cases=int(high_risk),
            active_alerts=int(active_alerts),
            critical_alerts=int(critical_alerts),
            predicted_locations=int(predicted_locations),
            total_transaction_volume=float(total_volume),
            transaction_count=int(transaction_count),
            prediction_count=int(prediction_count),
            prediction_accuracy=prediction_accuracy,
            active_investigations=int(active_investigations),
            resolved_cases=int(resolved_cases),
            total_exposure=float(total_volume),
            generated_at=datetime.now(UTC),
        )

    async def cases_over_time(self, session: AsyncSession, days: int = 30) -> list[dict[str, Any]]:
        since = datetime.now(UTC) - timedelta(days=days)
        cases = (await session.scalars(select(Case).where(Case.opened_at >= since))).all()
        buckets: dict[str, dict[str, int]] = {}
        for case in cases:
            key = case.opened_at.strftime("%Y-%m-%d")
            b = buckets.get(key)
            if b is None:
                b = {"period": 0, "opened": 0, "resolved": 0}
                buckets[key] = b
            b["opened"] += 1
            if case.status in {CaseStatus.RESOLVED.value, CaseStatus.CLOSED.value}:
                b["resolved"] += 1
        return [{**buckets[k], "period": k} for k in sorted(buckets, reverse=True)[: min(days, 90)]]

    async def risk_distribution(self, session: AsyncSession) -> dict[str, Any]:
        cases = (await session.scalars(select(Case))).all()
        buckets: dict[str, int] = {"0-0.2": 0, "0.2-0.4": 0, "0.4-0.6": 0, "0.6-0.8": 0, "0.8-1.0": 0}
        for case in cases:
            risk = case.current_risk_score or 0.0
            if risk < 0.2:
                buckets["0-0.2"] += 1
            elif risk < 0.4:
                buckets["0.2-0.4"] += 1
            elif risk < 0.6:
                buckets["0.4-0.6"] += 1
            elif risk < 0.8:
                buckets["0.6-0.8"] += 1
            else:
                buckets["0.8-1.0"] += 1
        return {
            "buckets": [RiskDistributionBucket(bucket=k, count=v).model_dump() for k, v in buckets.items()],
            "source_scope": "synthetic",
        }

    async def hotspots(
        self,
        session: AsyncSession,
        *,
        min_lat: float | None = None,
        max_lat: float | None = None,
        min_lon: float | None = None,
        max_lon: float | None = None,
    ) -> list[dict[str, Any]]:
        query = select(CashWithdrawal).options(
            selectinload(CashWithdrawal.atm),
            selectinload(CashWithdrawal.account_entity),
        )
        if any(x is not None for x in (min_lat, max_lat, min_lon, max_lon)):
            from app.core.geo import bbox_lat_lon_filter
            from app.models import AtmLocation

            query = query.join(AtmLocation, AtmLocation.id == CashWithdrawal.atm_id)
            query = bbox_lat_lon_filter(
                query,
                AtmLocation,
                min_lat=min_lat,
                max_lat=max_lat,
                min_lon=min_lon,
                max_lon=max_lon,
            )
        withdrawals = (await session.scalars(query)).all()

        # cluster by rounded coordinates into cell summaries
        cells: dict[tuple[float, float], dict[str, Any]] = {}
        for w in withdrawals:
            if w.atm_id is None or w.atm is None:
                continue
            if w.atm.latitude is None or w.atm.longitude is None:
                continue
            key = (round(w.atm.latitude * 4) / 4.0, round(w.atm.longitude * 4) / 4.0)
            cell = cells.setdefault(
                key,
                {
                    "latitude": key[0],
                    "longitude": key[1],
                    "risk_score": 0.0,
                    "case_count": 0,
                    "predicted_amount": 0.0,
                    "_cases": set(),
                    "_amount": 0.0,
                },
            )
            cell["_amount"] += w.amount
            if w.account_entity and w.account_entity.case_id:
                cell["_cases"].add(str(w.account_entity.case_id))

        hotspots: list[dict[str, Any]] = []
        for cell in cells.values():
            case_count = len(cell["_cases"])
            amount = cell["_amount"]
            # simple heuristic escalation: bigger number of linked cases & volume => higher risk
            risk = min(0.95, 0.2 + 0.15 * case_count + amount / 5_000_000.0)
            hotspots.append(
                HotspotSummary(
                    id=f"hotspot-{cell['latitude']:.4f}-{cell['longitude']:.4f}",
                    label=f"Cluster @ {cell['latitude']:.2f},{cell['longitude']:.2f}",
                    latitude=cell["latitude"],
                    longitude=cell["longitude"],
                    risk_score=round(float(min(risk, 1.0)), 4),
                    case_count=case_count,
                    predicted_amount=round(amount, 2),
                ).model_dump()
            )
        hotspots.sort(key=lambda h: h["risk_score"], reverse=True)
        return hotspots

    async def case_risk_history(self, session: AsyncSession, *, case_id: Any) -> list[dict[str, Any]]:
        rows = (
            await session.scalars(
                select(RiskScore).where(RiskScore.case_id == case_id).order_by(RiskScore.computed_at)
            )
        ).all()
        return [
            {
                "score": r.score,
                "model_version": r.model_version,
                "computed_at": r.computed_at.isoformat(),
                "component_breakdown": r.component_breakdown,
            }
            for r in rows
        ]

    async def outcomes_summary(self, session: AsyncSession) -> dict[str, Any]:
        rows = (await session.scalars(select(Outcome))).all()
        by_type: dict[str, int] = {}
        distance_errors: list[float] = []
        for o in rows:
            by_type[o.outcome_type.value if hasattr(o.outcome_type, "value") else str(o.outcome_type)] = (
                by_type.get(
                    o.outcome_type.value if hasattr(o.outcome_type, "value") else str(o.outcome_type), 0
                )
                + 1
            )
            if o.distance_error_km is not None:
                distance_errors.append(o.distance_error_km)
        return {
            "total": len(rows),
            "by_type": by_type,
            "mean_location_error_km": round(sum(distance_errors) / len(distance_errors), 2)
            if distance_errors
            else None,
            "median_location_error_km": round(sorted(distance_errors)[len(distance_errors) // 2], 2)
            if distance_errors
            else None,
        }

    async def _prediction_accuracy(self, session: AsyncSession) -> float | None:
        outcomes = (await session.scalars(select(Outcome))).all()
        if not outcomes:
            return None
        hits = sum(1 for o in outcomes if as_str(o.outcome_type) == "PREDICTION_CONFIRMED")
        return round(hits / len(outcomes), 4)


analytics_service: AnalyticsService = AnalyticsService()

__all__ = ["AnalyticsService", "analytics_service"]
