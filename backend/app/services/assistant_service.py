"""Investigator assistant: structured, evidence-grounded explainability.

Generates human-readable answers about a case from **stored structured data**
(predictions, alerts, entities, outcomes, timeline) rather than freeform
inference.  An optional LLM re-writes the structured summary when
``LLM_ENABLED=true``; by default the assistant returns a deterministic
template so the feature works offline and never hallucinates.

The assistant is explicitly assistive: it never determines criminality and
always appends a disclaimer.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import (
    Alert,
    Case,
    Entity,
    InvestigationEvent,
    Outcome,
    Prediction,
    PredictionLocation,
    Transaction,
)


class AssistantService:
    """Generate evidence-grounded explanations for investigators."""

    async def explain(
        self,
        session: AsyncSession,
        *,
        case_id: str,
        question: str,
    ) -> dict[str, Any]:
        case = await session.get(Case, uuid(case_id))
        if case is None:
            from app.core.errors import CASE_NOT_FOUND

            raise CASE_NOT_FOUND

        evidence = await self._collect_evidence(session, case)
        if settings.llm_enabled:
            answer = await self._llm_answer(question, evidence)
            generated = True
            model = settings.llm_model
        else:
            answer = self._template_answer(question, evidence)
            generated = False
            model = None
        return {
            "case_id": case_id,
            "question": question,
            "evidence": evidence,
            "answer": answer,
            "generated": generated,
            "model": model,
            "disclaimer": (
                "This explanation summarises structured evidence already stored in the platform. "
                "It is an assistive summary and never a determination of criminality."
            ),
        }

    async def _collect_evidence(self, session: AsyncSession, case: Case) -> list[dict[str, Any]]:
        evidence: list[dict[str, Any]] = []
        txns = list((await session.scalars(select(Transaction).where(Transaction.case_id == case.id))).all())
        if txns:
            total = sum(t.amount for t in txns)
            evidence.append(
                {
                    "kind": "economy",
                    "source": "transactions",
                    "content": f"{len(txns)} transactions totalling ₹{total:,.0f}",
                }
            )

        entities = list((await session.scalars(select(Entity).where(Entity.case_id == case.id))).all())
        if entities:
            evidence.append(
                {
                    "kind": "entity",
                    "source": "entity-resolution",
                    "content": f"{len(entities)} linked entities "
                    f"({', '.join(sorted({e.entity_type for e in entities}))})",
                }
            )

        predictions = list(
            (
                await session.scalars(
                    select(Prediction)
                    .where(Prediction.case_id == case.id)
                    .order_by(Prediction.created_at.desc())
                )
            ).all()
        )
        if predictions:
            top = predictions[0]
            locations = list(
                (
                    await session.scalars(
                        select(PredictionLocation)
                        .where(PredictionLocation.prediction_id == top.id)
                        .order_by(PredictionLocation.rank)
                    )
                ).all()
            )[:3]
            loc_text = "; ".join(f"#{loc.rank} risk={loc.risk_score:.2f}" for loc in locations)
            evidence.append(
                {
                    "kind": "prediction",
                    "source": f"model {top.model_name}@{top.model_version}",
                    "content": (
                        f"headline risk {top.headline_risk:.2f} within {top.horizon} : {loc_text} "
                        if top.headline_risk is not None
                        else f"prediction {top.model_version} (no headline risk) : {loc_text}"
                    ),
                }
            )

        alerts = list((await session.scalars(select(Alert).where(Alert.case_id == case.id))).all())
        if alerts:
            open_alerts = [a for a in alerts if str(a.status) in {"OPEN", "ACKNOWLEDGED"}]
            evidence.append(
                {
                    "kind": "alerts",
                    "source": "alerting",
                    "content": f"{len(open_alerts)}/{len(alerts)} alerts still open",
                }
            )

        timeline = list(
            (
                await session.scalars(
                    select(InvestigationEvent)
                    .where(InvestigationEvent.case_id == case.id)
                    .order_by(InvestigationEvent.occurred_at.desc())
                )
            ).all()
        )[:5]
        if timeline:
            evidence.append(
                {
                    "kind": "timeline",
                    "source": "investigation",
                    "content": " | ".join(e.description or "" for e in timeline[:3]),
                }
            )

        outcomes = list((await session.scalars(select(Outcome).where(Outcome.case_id == case.id))).all())
        if outcomes:
            evidence.append(
                {
                    "kind": "outcome",
                    "source": "feedback-loop",
                    "content": "; ".join(o.outcome_type for o in outcomes),
                }
            )
        return evidence

    async def _llm_answer(self, question: str, evidence: list[dict[str, Any]]) -> str:
        # Keep the LLM call hermetic: no raw PII leaves the platform context
        # This is a pull-based call to openai-compatible /chat/completions.
        import httpx

        context_chars = settings.llm_max_context_chars
        context = "\n".join(f"[{e['kind']}] {e['content']}" for e in evidence)[:context_chars]
        payload = {
            "model": settings.llm_model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are an assistive cybercrime investigator. Answer ONLY from the "
                        "structured evidence provided. Do not speculate, do not determine "
                        "criminality, and flag any uncertainty explicitly. Prefer concise "
                        "bullet points with the supporting evidence type."
                    ),
                },
                {"role": "user", "content": f"QUESTION: {question}\n\nEVIDENCE:\n{context}"},
            ],
            "temperature": 0.2,
            "max_tokens": 500,
        }
        async with httpx.AsyncClient(timeout=settings.llm_timeout_seconds) as client:
            r = await client.post(
                f"{settings.llm_base_url.rstrip('/')}/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.llm_api_key.get_secret_value()}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            r.raise_for_status()
            data = r.json()
            return data["choices"][0]["message"]["content"]

    def _template_answer(self, question: str, evidence: list[dict[str, Any]]) -> str:
        lines = [
            "Evidence-grounded summary (structured data, no generative model):",
            "",
        ]
        for e in evidence[:8]:
            lines.append(f"- [{e['kind']}] {e['content']}")
        lines.append("")
        lines.append(
            "Recommendation: review the signals above; the answer reflects stored platform "
            "evidence only and is not a determination."
        )
        return "\n".join(lines)


def uuid(value: str) -> Any:
    import uuid as _uuid

    return _uuid.UUID(value)


assistant_service: AssistantService = AssistantService()

__all__ = ["AssistantService", "assistant_service"]
