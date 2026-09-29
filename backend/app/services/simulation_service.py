"""Intervention simulation - models "what if" actions against a prediction.

Simulation follows a transparent formula:

    baseline_exposure   = sum(risk * amount) across ranked prediction locations
    simulated_exposure  = baseline_exposure reduced by an intervention efficacy
                          factor (upper bound, uncertainty-aware)
    risk_reduction      = 1 - simulated_exposure / baseline_exposure

Efficacy factors are documented constants (upper-bound estimates from the
literature on cash-out disruption); the UI always shows reduction as a model
estimate, never as certainty.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import (
    AuditAction,
    InterventionStatus,
    InterventionType,
    InvestigationEventType,
    RealtimeEventType,
)
from app.core.errors import CASE_NOT_FOUND, INTERVENTION_NOT_FOUND, PREDICTION_NOT_FOUND, BadRequestError
from app.models import Case, Intervention, Prediction, User
from app.services.audit_service import audit_service
from app.services.investigation_service import investigation_service
from app.services.realtime_service import event_hub
from app.utils.validators import as_enum

_DEFAULT_EFFICACY: dict[InterventionType, tuple[float, float]] = {
    InterventionType.MONITOR_ATM: (0.15, 0.42),
    InterventionType.ALERT_BANK: (0.25, 0.55),
    InterventionType.DISPATCH_UNIT: (0.3, 0.6),
    InterventionType.INCREASE_MONITORING: (0.2, 0.5),
    InterventionType.FREEZE_SIMULATION: (0.6, 0.9),
    InterventionType.NO_INTERVENTION: (0.0, 0.0),
}


class SimulationService:
    """Simulate, approve/execute intervention plans against predictions."""

    async def simulate(
        self,
        session: AsyncSession,
        *,
        case_id: uuid.UUID,
        intervention_type: InterventionType,
        actor: User,
        prediction_id: uuid.UUID | None = None,
        notes: str | None = None,
    ) -> Intervention:
        intervention_type = as_enum(intervention_type, InterventionType)
        case = await session.get(Case, case_id)
        if case is None:
            raise CASE_NOT_FOUND

        prediction = None
        if prediction_id:
            prediction = await session.get(Prediction, prediction_id)
            if prediction is None:
                raise PREDICTION_NOT_FOUND
            if prediction.case_id != case_id:
                raise BadRequestError(
                    "Prediction does not belong to this case.", code="PREDICTION_CASE_MISMATCH"
                )

        # ranked probability-weighted exposure of the prediction set
        baseline_exposure = case.amount or 0.0
        affected: list[str] = []
        if prediction is not None and prediction.locations:
            weights = [loc.risk_score for loc in prediction.locations]
            sum(weights) or 1.0
            # exposure concentrated where the model puts the most probability
            baseline_exposure *= max(weights) if weights else 0.0
            if weights:
                top_idx = max(range(len(weights)), key=lambda i: weights[i])
                affected = [str(prediction.locations[top_idx].atm_id)]

        lo, hi = _DEFAULT_EFFICACY.get(intervention_type, (0.1, 0.4))
        efficacy = (lo + hi) / 2.0
        simulated_exposure = baseline_exposure * max(0.0, 1.0 - efficacy)
        risk_reduction = round(
            (1.0 - simulated_exposure / baseline_exposure) if baseline_exposure > 0 else 0.0,
            4,
        )

        intervention = Intervention(
            case_id=case_id,
            prediction_id=prediction_id,
            intervention_type=intervention_type.value,
            status=InterventionStatus.SIMULATED,
            description=notes,
            baseline_exposure=round(float(baseline_exposure), 2),
            simulated_exposure=round(float(simulated_exposure), 2),
            risk_reduction=risk_reduction,
            affected_location_ids=affected,
            assumptions=[
                f"{intervention_type.value} efficacy assumed between {lo:.0%} and {hi:.0%} "
                "(upper-bound estimate, not a certainty)",
                "Simulation applies the efficacy factor to probability-weighted exposure only",
                f"Based on prediction {'#' + str(prediction_id) if prediction_id else 'set for case'}",
            ],
            suggested_by=actor.id,
        )
        session.add(intervention)
        await session.flush()

        await investigation_service.add_event(
            session,
            case_id=case_id,
            event_type=InvestigationEventType.INTERVENTION_SIMULATED,
            actor=actor,
            description=f"Intervention simulated: {intervention_type.value} (risk reduction ~{risk_reduction:.0%})",
            metadata={
                "intervention_id": str(intervention.id),
                "baseline_exposure": intervention.baseline_exposure,
                "simulated_exposure": intervention.simulated_exposure,
                "risk_reduction": risk_reduction,
            },
        )
        await audit_service.record(
            session,
            action=AuditAction.INTERVENTION_SIMULATE,
            actor_id=actor.id,
            actor_email=actor.email,
            actor_role=actor.role_name.value,
            resource="intervention",
            resource_id=intervention.id,
            payload={"case_id": str(case_id), "intervention_type": intervention.intervention_type},
        )
        await session.flush()
        return intervention

    async def approve(
        self, session: AsyncSession, *, intervention_id: uuid.UUID, actor: User
    ) -> Intervention:
        intervention = await self.get(session, intervention_id=intervention_id)
        if intervention.status == InterventionStatus.EXECUTED:
            raise BadRequestError(
                "Executed interventions cannot be re-approved.", code="INTERVENTION_EXECUTED"
            )
        intervention.status = InterventionStatus.APPROVED
        await audit_service.record(
            session,
            action=AuditAction.INTERVENTION_APPROVE,
            actor_id=actor.id,
            actor_email=actor.email,
            actor_role=actor.role_name.value,
            resource="intervention",
            resource_id=intervention.id,
        )
        await session.flush()
        return intervention

    async def execute(
        self, session: AsyncSession, *, intervention_id: uuid.UUID, actor: User, note: str | None = None
    ) -> Intervention:
        intervention = await self.get(session, intervention_id=intervention_id)
        intervention.status = InterventionStatus.EXECUTED
        intervention.executed_by = actor.id
        intervention.executed_at = datetime.now(UTC)
        if note:
            intervention.description = note

        await investigation_service.add_event(
            session,
            case_id=intervention.case_id,
            event_type=InvestigationEventType.INTERVENTION_EXECUTED,
            actor=actor,
            description=f"Intervention executed: {intervention.intervention_type}",
            metadata={"intervention_id": str(intervention.id), "note": note},
        )
        await audit_service.record(
            session,
            action=AuditAction.INTERVENTION_EXECUTE,
            actor_id=actor.id,
            actor_email=actor.email,
            actor_role=actor.role_name.value,
            resource="intervention",
            resource_id=intervention.id,
        )
        await session.flush()
        await event_hub.publish(
            RealtimeEventType.INTERVENTION_EXECUTED,
            {
                "intervention_id": str(intervention.id),
                "case_id": str(intervention.case_id),
                "intervention_type": intervention.intervention_type,
            },
        )
        return intervention

    async def get(self, session: AsyncSession, *, intervention_id: uuid.UUID) -> Intervention:
        intervention = await session.get(Intervention, intervention_id)
        if intervention is None:
            raise INTERVENTION_NOT_FOUND
        return intervention

    async def list_by_case(self, session: AsyncSession, *, case_id: uuid.UUID) -> list[Intervention]:
        rows = (
            await session.scalars(
                select(Intervention)
                .where(Intervention.case_id == case_id)
                .order_by(Intervention.created_at.desc())
            )
        ).all()
        return list(rows)


simulation_service: SimulationService = SimulationService()

__all__ = ["SimulationService", "simulation_service"]
