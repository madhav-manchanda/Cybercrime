"""Investigative-assistant explainability endpoint (LLM-gated)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import rate_limit, require_permission
from app.core.config import settings
from app.core.database import get_db
from app.core.enums import AuditAction, Permission
from app.core.rate_limit import Limit
from app.models import User
from app.schemas.analytics import InvestigatorExplanation, InvestigatorQuestion
from app.services.assistant_service import assistant_service
from app.services.audit_service import audit_service

router = APIRouter(prefix="/assistant", tags=["assistant"])

_llm_limit = Limit(key="llm", per=settings.rate_limit_llm_per_minute, unit="minute")


@router.post("/explain", response_model=InvestigatorExplanation)
async def explain(
    payload: InvestigatorQuestion,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[None, Depends(rate_limit("assistant:explain", _llm_limit))],
    user: Annotated[User, Depends(require_permission(Permission.LLM_EXPLAIN))],
) -> InvestigatorExplanation:
    explanation = await assistant_service.explain(
        session, case_id=str(payload.case_id), question=payload.question
    )
    await audit_service.record(
        session,
        action=AuditAction.LLM_EXPLAIN,
        actor_id=user.id,
        actor_email=user.email,
        actor_role=user.role_name.value,
        resource="case",
        resource_id=str(payload.case_id),
        payload={
            "question": payload.question[:200],
            "generated": bool(explanation.get("generated")),
            "model": explanation.get("model"),
        },
        request_id=request.state.request_id or "",
    )
    await session.commit()
    return InvestigatorExplanation.model_validate(explanation)


__all__ = ["router"]
