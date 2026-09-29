"""Prediction orchestration: the full cash-out prediction lifecycle.

Pipeline steps performed here:

1. assemble the feature bundle for a case
2. compute the predicted cash-out time window (temporal model)
3. select candidate ATM locations (spatial + linked hits)
4. run the hybrid scorer/ranker -> ranked predictions per location
5. attach explanation text and contributing factors
6. persist Prediction + PredictionLocation rows
7. generate alerts (high-risk locations, window-approaching)
8. update the case timeline, risk snapshot and realtime feed
9. audit the run with full provenance (model name/version/feature version)
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.enums import (
    AlertSeverity,
    AlertType,
    AuditAction,
    CaseStatus,
    InvestigationEventType,
    PredictionHorizon,
    PredictionStatus,
    RealtimeEventType,
)
from app.core.errors import PREDICTION_NOT_FOUND, BadRequestError
from app.ml.datasets import build_bundle, candidate_atms
from app.ml.rank_predict import load_ranker_for_case, rank_candidates
from app.ml.temporal import predict_time_window
from app.models import (
    Alert,
    Case,
    Prediction,
    PredictionLocation,
    RiskScore,
    User,
)
from app.schemas.prediction import PredictionRequest
from app.services.alert_service import alert_service
from app.services.audit_service import audit_service
from app.services.case_service import case_service
from app.services.investigation_service import investigation_service
from app.services.realtime_service import event_hub

logger = structlog.get_logger("prediction")


class PredictionService:
    """Runs and records cash-out location/time-window predictions."""

    async def run(
        self,
        session: AsyncSession,
        *,
        case: Case,
        request: PredictionRequest,
        actor: User,
    ) -> Prediction:
        reference = request.reference_time or datetime.now(UTC)

        bundle = await build_bundle(session, case=case, reference_time=reference)

        # ---- temporal model: time-window first so spatial rows can reuse it
        if bundle.case_amount_features.get("hours_since_last_txn") is not None:
            float(bundle.case_amount_features["hours_since_last_txn"])
        horizon_hours = _horizon_to_hours(request.horizon)
        window = predict_time_window(
            bundle.temporal_profile,
            reference=reference,
            horizon_hours=horizon_hours,
            recent_velocity_hours=bundle.case_amount_features.get("velocity_per_hour"),
            window_span_hours=6,
        )
        bundle.predicted_window_start = window.start
        bundle.predicted_window_end = window.end

        # ---- spatial selection + scoring
        candidates = await candidate_atms(
            session, case=case, bundle=bundle, limit=settings.ml_nearest_atms_per_anchor * 4
        )
        ranker = load_ranker_for_case(str(case.id))
        ranked = rank_candidates(bundle, candidates, top_k=request.top_k, ranker=ranker)
        if not ranked:
            raise BadRequestError(
                "No candidate locations could be scored. Ensure the case has geographic "
                "context and ATM infrastructure exists near it.",
                code="NO_PREDICTION_CANDIDATES",
            )

        model_name = ranked[0].model_name if ranked else "cashout-risk"
        model_version = ranked[0].model_version if ranked else "baseline-blend-v1"

        prediction = Prediction(
            case_id=case.id,
            status=PredictionStatus.COMPLETED,
            horizon=request.horizon,
            headline_risk=ranked[0].risk_score if ranked else 0.0,
            predicted_amount=case.amount,
            generated_at=reference,
            completed_at=datetime.now(UTC),
            model_name=model_name,
            model_version=model_version,
            feature_version="1.0",
            requested_by=actor.id,
            metadata_json={
                "reference_time": reference.isoformat(),
                "candidates_considered": len(candidates),
                "scored": len(ranked),
                "warning": bundle.warnings,
                "temporal_profile_samples": bundle.temporal_profile.n_samples,
            },
        )
        session.add(prediction)
        await session.flush()

        for i, item in enumerate(ranked, start=1):
            session.add(
                PredictionLocation(
                    prediction_id=prediction.id,
                    atm_id=uuid.UUID(str(item.candidate.atm_id)),
                    rank=i,
                    risk_score=item.risk_score,
                    confidence=item.confidence,
                    time_window_start=window.start,
                    time_window_end=window.end,
                    contributing_factors=item.factor_impacts[: settings.ml_explanation_top_factors],
                    explanation_text=item.explanation_text,
                )
            )

        # persistent risk snapshot for the case
        session.add(
            RiskScore(
                case_id=case.id,
                score=prediction.headline_risk or 0.0,
                model_version=model_version,
                component_breakdown={},
                computed_at=datetime.now(UTC),
            )
        )
        case.current_risk_score = prediction.headline_risk
        if case.status in {CaseStatus.NEW, CaseStatus.UNDER_ANALYSIS}:
            await case_service.transition(
                session,
                case=case,
                target=CaseStatus.PREDICTION_ACTIVE,
                actor=actor,
                description="Cash-out prediction generated",
            )
        await session.flush()

        # ---- timeline + audit + realtime
        session.add(
            await investigation_service.add_event(
                session,
                case_id=case.id,
                event_type=InvestigationEventType.PREDICTION_GENERATED,
                actor=actor,
                description=f"Prediction {model_name}@{model_version} produced {len(ranked)} ranked locations",
                metadata={
                    "prediction_id": str(prediction.id),
                    "model_version": model_version,
                    "headline_risk": prediction.headline_risk,
                },
            )
        )
        await audit_service.record(
            session,
            action=AuditAction.PREDICTION_RUN,
            actor_id=actor.id,
            actor_email=actor.email,
            actor_role=actor.role_name.value,
            resource="prediction",
            resource_id=prediction.id,
            payload={
                "case_id": str(case.id),
                "model_version": model_version,
                "headline_risk": prediction.headline_risk,
                "n_locations": len(ranked),
            },
        )
        await session.flush()

        await event_hub.publish(
            RealtimeEventType.PREDICTION_CREATED,
            {
                "case_id": str(case.id),
                "prediction_id": str(prediction.id),
                "model_version": model_version,
                "headline_risk": prediction.headline_risk,
            },
        )

        # ---- alerts derived from the prediction
        await self._emit_prediction_alerts(session, prediction, case, actor)

        # transactionally commit before returning (route depends)
        await session.commit()
        await session.refresh(prediction)
        return prediction

    async def _emit_prediction_alerts(
        self,
        session: AsyncSession,
        prediction: Prediction,
        case: Case,
        actor: User,
    ) -> list[Alert]:
        """Generate alerts for top risk locations above the threshold."""
        await session.flush()
        locations = list(
            await session.scalars(
                select(PredictionLocation).where(PredictionLocation.prediction_id == prediction.id)
            )
        )
        created: list[Alert] = []
        top = sorted(locations, key=lambda loc: loc.risk_score, reverse=True)
        for loc in top[:3]:
            if loc.risk_score < 0.75:
                continue
            alert = await alert_service.create(
                session,
                alert_type=AlertType.HIGH_RISK_LOCATION,
                severity=AlertSeverity.CRITICAL if loc.risk_score >= 0.85 else AlertSeverity.HIGH,
                title=f"High-risk cash-out location for case {case.case_number}",
                description=loc.explanation_text
                or f"Ranked cash-out candidate with risk {loc.risk_score:.2f}.",
                metadata_json={
                    "prediction_location_id": str(loc.id),
                    "atm_id": str(loc.atm_id),
                    "rank": loc.rank,
                    "time_window_start": loc.time_window_start.isoformat() if loc.time_window_start else None,
                    "time_window_end": loc.time_window_end.isoformat() if loc.time_window_end else None,
                },
                risk_score=loc.risk_score,
                case_id=case.id,
                prediction_id=prediction.id,
                atm_id=loc.atm_id,
            )
            created.append(alert)

        # window approaching alert - informs monitoring for the predicted window
        window_start = locations[0].time_window_start if locations else None
        if window_start:
            created.append(
                await alert_service.create(
                    session,
                    alert_type=AlertType.CASHOUT_WINDOW_APPROACHING,
                    severity=AlertSeverity.MEDIUM,
                    title=f"Cash-out window approaching for case {case.case_number}",
                    description=f"Predicted window begins {window_start.isoformat()}.",
                    metadata_json={
                        "case_id": str(case.id),
                        "prediction_id": str(prediction.id),
                        "window_start": window_start.isoformat(),
                    },
                    risk_score=prediction.headline_risk,
                    case_id=case.id,
                    prediction_id=prediction.id,
                )
            )
        return created

    # ------------------------------------------------------------- reads
    async def get(self, session: AsyncSession, *, prediction_id: uuid.UUID) -> Prediction:
        prediction = await session.get(Prediction, prediction_id)
        if prediction is None:
            raise PREDICTION_NOT_FOUND
        return prediction

    async def list_by_case(
        self, session: AsyncSession, *, case_id: uuid.UUID, limit: int = 10
    ) -> list[Prediction]:
        rows = await session.scalars(
            select(Prediction)
            .where(Prediction.case_id == case_id)
            .order_by(Prediction.created_at.desc())
            .limit(limit)
        )
        return list(rows.all())

    async def latest_location_predictions(
        self, session: AsyncSession, *, case_id: uuid.UUID
    ) -> list[PredictionLocation]:
        pred = (
            await session.scalars(
                select(Prediction)
                .where(Prediction.case_id == case_id, Prediction.status == PredictionStatus.COMPLETED)
                .order_by(Prediction.created_at.desc())
                .limit(1)
            )
        ).first()
        if pred is None:
            return []
        return list(
            (
                await session.scalars(
                    select(PredictionLocation)
                    .where(PredictionLocation.prediction_id == pred.id)
                    .order_by(PredictionLocation.rank)
                )
            ).all()
        )


def _horizon_to_hours(horizon: PredictionHorizon) -> int:
    return {
        PredictionHorizon.H6: 6,
        PredictionHorizon.H12: 12,
        PredictionHorizon.H24: 24,
        PredictionHorizon.H48: 48,
        PredictionHorizon.H72: 72,
    }.get(horizon, 24)


prediction_service: PredictionService = PredictionService()

__all__ = ["PredictionService", "prediction_service"]
