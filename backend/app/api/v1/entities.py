"""Entity resolution, linking, and fraud-network graph endpoints."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.database import get_db
from app.core.enums import EntityType, Permission, RelationshipType
from app.core.errors import ENTITY_NOT_FOUND, BadRequestError
from app.models import Entity, User
from app.schemas.entity import (
    EntityLinkRequest,
    EntityOut,
    EntityResolutionResult,
    RelationshipOut,
)
from app.services.case_service import case_service
from app.services.entity_service import entity_service
from app.services.graph_service import graph_service

router = APIRouter(prefix="/entities", tags=["entities"])


@router.post("/resolve", response_model=EntityResolutionResult)
async def resolve_entity(
    payload: dict,
    session: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, Depends(require_permission(Permission.NETWORK_WRITE))],
) -> EntityResolutionResult:
    kind = payload.get("entity_type")
    external_id = payload.get("external_id")
    case_id_raw = payload.get("case_id")
    label = payload.get("label")
    if kind not in ("account", "phone", "upi", "device"):
        raise BadRequestError(
            "entity_type must be one of account|phone|upi|device",
            code="UNKNOWN_ENTITY_KIND",
        )
    if not isinstance(external_id, str) or not external_id:
        raise BadRequestError("external_id is required", code="MISSING_EXTERNAL_ID")
    try:
        case_id = uuid.UUID(str(case_id_raw)) if case_id_raw else None
    except ValueError:
        raise BadRequestError("case_id must be a valid UUID", code="INVALID_CASE_ID") from None

    if kind == "account":
        existing = await session.scalar(
            select(Entity).where(
                Entity.external_id == external_id,
                Entity.entity_type == EntityType.ACCOUNT,
            )
        )
        entity = existing or await entity_service.resolve_from_account(
            session, account_number=external_id, case_id=case_id, label=label
        )
    elif kind == "phone":
        existing = await session.scalar(
            select(Entity).where(
                Entity.external_id == external_id,
                Entity.entity_type == EntityType.PHONE,
            )
        )
        entity = existing or await entity_service.resolve_phone(
            session, phone=external_id, case_id=case_id, label=label
        )
    elif kind == "upi":
        existing = await session.scalar(
            select(Entity).where(
                Entity.external_id == external_id,
                Entity.entity_type == EntityType.UPI,
            )
        )
        entity = existing or await entity_service.resolve_upi(session, upi=external_id, case_id=case_id)
    else:
        existing = await session.scalar(
            select(Entity).where(
                Entity.external_id == external_id,
                Entity.entity_type == EntityType.DEVICE,
            )
        )
        entity = existing or await entity_service.resolve_device(
            session, fingerprint=external_id, case_id=case_id
        )
    await session.commit()
    if entity.case_id and case_id and entity.case_id != case_id:
        entity.case_id = case_id
        await session.commit()
    return EntityResolutionResult(
        entity_id=entity.id,
        matched=existing is not None,
        created=existing is None,
        entity_type=entity.entity_type,
        relations_created=0,
    )


@router.get("/{entity_id}", response_model=EntityOut)
async def get_entity(
    entity_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, Depends(require_permission(Permission.ENTITY_READ))],
) -> EntityOut:
    entity = await session.get(Entity, entity_id)
    if entity is None:
        raise ENTITY_NOT_FOUND
    return EntityOut.model_validate(entity)


@router.get("/{entity_id}/relations", response_model=list[RelationshipOut])
async def entity_relations(
    entity_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, Depends(require_permission(Permission.ENTITY_READ))],
) -> list[RelationshipOut]:
    entity = await session.get(Entity, entity_id)
    if entity is None:
        raise ENTITY_NOT_FOUND
    relations = await entity_service.get_relations(session, entity_id=entity_id)
    return [RelationshipOut.model_validate(r) for r in relations]


@router.post("/{source_id}/link", response_model=EntityResolutionResult)
async def link_entity(
    source_id: uuid.UUID,
    payload: EntityLinkRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, Depends(require_permission(Permission.NETWORK_WRITE))],
) -> EntityResolutionResult:
    source = await session.get(Entity, source_id)
    if source is None:
        raise ENTITY_NOT_FOUND

    kind = payload.entity_type
    if kind == EntityType.ACCOUNT:
        target = await entity_service.resolve_from_account(
            session, account_number=payload.external_id, label=payload.label
        )
    elif kind == EntityType.PHONE:
        target = await entity_service.resolve_phone(session, phone=payload.external_id, label=payload.label)
    elif kind == EntityType.UPI:
        target = await entity_service.resolve_upi(session, upi=payload.external_id)
    elif kind == EntityType.DEVICE:
        target = await entity_service.resolve_device(session, fingerprint=payload.external_id)
    else:
        raise BadRequestError(
            "entity_type must be one of ACCOUNT|PHONE|UPI|DEVICE",
            code="UNKNOWN_ENTITY_KIND",
        )
    await entity_service.link(
        session,
        source=source,
        target=target,
        relationship=RelationshipType.SENT_TO,
        confidence=payload.confidence,
        actor=None,
    )
    await session.commit()
    return EntityResolutionResult(
        entity_id=target.id,
        matched=True,
        created=False,
        entity_type=target.entity_type,
        relations_created=1,
    )


@router.get("/cases/{case_id}", response_model=list[EntityOut])
async def case_entities(
    case_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, Depends(require_permission(Permission.ENTITY_READ))],
) -> list[EntityOut]:
    await case_service.get(session, case_id=case_id)
    entities = list(
        (
            await session.scalars(select(Entity).where(Entity.case_id == case_id).order_by(Entity.created_at))
        ).all()
    )
    return [EntityOut.model_validate(e) for e in entities]


@router.get("/cases/{case_id}/network", response_model=dict)
async def case_network(
    case_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, Depends(require_permission(Permission.NETWORK_READ))],
) -> dict:
    await case_service.get(session, case_id=case_id)
    return await graph_service.render(session, case_id=case_id)


__all__ = ["router"]
