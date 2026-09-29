"""API v1 router aggregator."""

from fastapi import APIRouter

from app.api.v1 import (
    alerts,
    analytics,
    assistant,
    atms,
    audit,
    auth,
    cases,
    complaints,
    entities,
    investigations,
    models,
    outcomes,
    predictions,
    realtime,
    synthetic,
    transactions,
    users,
)

api_v1_router = APIRouter()

api_v1_router.include_router(auth.router)
api_v1_router.include_router(users.router)
api_v1_router.include_router(cases.router)
api_v1_router.include_router(complaints.router)
api_v1_router.include_router(transactions.router)
api_v1_router.include_router(entities.router)
api_v1_router.include_router(predictions.router)
api_v1_router.include_router(atms.router)
api_v1_router.include_router(alerts.router)
api_v1_router.include_router(investigations.router)
api_v1_router.include_router(outcomes.router)
api_v1_router.include_router(analytics.router)
api_v1_router.include_router(audit.router)
api_v1_router.include_router(assistant.router)
api_v1_router.include_router(realtime.router)
api_v1_router.include_router(models.router)
api_v1_router.include_router(synthetic.router)

__all__ = ["api_v1_router"]
