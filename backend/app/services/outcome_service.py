"""Outcome recording - the closed-loop feedback for the prediction pipeline.

Fields like ``distance_error_km`` / ``time_error_hours`` are computed from the
inputs when possible; the system never claims an outcome that was not recorded.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import AuditAction, InvestigationEventType
from app.core.errors import CASE_NOT_FOUND, BadRequestError
from app.models import AtmLocation, Case, Outcome, Prediction, User
from app.schemas.outcome import OutcomeCreateRequest
from app.services.audit_service import audit_service
from app.services.investigation_service import investigation_service
from app.utils.geo import distance_km
from app.utils.validators import as_str


def _utc_aware(dt: datetime | None) -> datetime | None:
    """Normalize a possibly-naive UTC stamp so comparisons never mix tz info."""
    if dt is None or dt.tzinfo is not None:
        return dt
    return dt.replace(tzinfo=UTC)


class OutcomeService:
    """Records ground-truth outcomes for predictions."""

    async def record(
        self,
        session: AsyncSession,
        *,
        case_id: uuid.UUID,
        payload: OutcomeCreateRequest,
        actor: User,
    ) -> Outcome:
        case = await session.get(Case, case_id)
        if case is None:
            raise CASE_NOT_FOUND

        prediction = None
        if payload.prediction_id:
            prediction = await session.get(Prediction, payload.prediction_id)
            if prediction is not None and prediction.case_id != case_id:
                raise BadRequestError(
                    "Prediction does not belong to this case.", code="PREDICTION_CASE_MISMATCH"
                )

        distance_error: float | None = None
        time_error: float | None = None
        actual_time = _utc_aware(payload.actual_time)
        predicted_start = _utc_aware(payload.predicted_time_start)
        predicted_end = _utc_aware(payload.predicted_time_end)
        if payload.predicted_atm_id and payload.actual_atm_id:
            pred_atm = await session.get(AtmLocation, payload.predicted_atm_id)
            act_atm = await session.get(AtmLocation, payload.actual_atm_id)
            if (
                pred_atm
                and act_atm
                and pred_atm.latitude
                and act_atm.latitude
                and pred_atm.longitude
                and act_atm.longitude
                and pred_atm.id != act_atm.id
            ):
                distance_error = round(
                    distance_km(
                        pred_atm.latitude,
                        pred_atm.longitude,
                        act_atm.latitude,
                        act_atm.longitude,
                    ),
                    2,
                )
        if (
            predicted_start
            and predicted_end
            and actual_time
            and predicted_end >= predicted_start
        ):
            if actual_time < predicted_start:
                time_error = round((predicted_start - actual_time).total_seconds() / 3600.0, 2)
            else:
                time_error = round(
                    max(0.0, (actual_time - predicted_end).total_seconds() / 3600.0),
                    2,
                )

        outcome = Outcome(
            outcome_type=as_str(payload.outcome_type)
            if hasattr(payload.outcome_type, "value")
            else payload.outcome_type,
            predicted_atm_id=payload.predicted_atm_id,
            actual_atm_id=payload.actual_atm_id,
            predicted_time_start=predicted_start,
            predicted_time_end=predicted_end,
            actual_time=actual_time,
            distance_error_km=distance_error,
            time_error_hours=time_error,
            was_cashout=payload.was_cashout,
            amount_withdrawn=payload.amount_withdrawn,
            notes=payload.notes,
            case_id=case_id,
            prediction_id=payload.prediction_id,
            recorded_by=actor.id,
            recorded_at=datetime.now(UTC),
        )
        session.add(outcome)
        await session.flush()

        await investigation_service.add_event(
            session,
            case_id=case_id,
            event_type=InvestigationEventType.OUTCOME_RECORDED,
            actor=actor,
            description=f"Outcome recorded: {outcome.outcome_type}",
            metadata={
                "outcome_id": str(outcome.id),
                "distance_error_km": distance_error,
                "time_error_hours": time_error,
            },
        )
        await audit_service.record(
            session,
            action=AuditAction.OUTCOME_RECORD,
            actor_id=actor.id,
            actor_email=actor.email,
            actor_role=actor.role_name.value,
            resource="outcome",
            resource_id=outcome.id,
            payload={
                "case_id": str(case_id),
                "outcome_type": outcome.outcome_type,
                "prediction_id": str(outcome.prediction_id) if outcome.prediction_id else None,
            },
        )
        await session.flush()
        return outcome

    async def list_by_case(self, session: AsyncSession, *, case_id: uuid.UUID) -> list[Outcome]:
        rows = await session.scalars(
            select(Outcome).where(Outcome.case_id == case_id).order_by(Outcome.recorded_at.desc())
        )
        return list(rows.all())


outcome_service: OutcomeService = OutcomeService()

__all__ = ["OutcomeService", "outcome_service"]
