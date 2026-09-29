"""Entity resolution service.

Converts raw identifiers (account numbers, phones, UPIs, devices) into stable
:class:`Entity` nodes and typed, evidence-carrying :class:`EntityRelationship`
edges.  Raw account numbers are hashed with a per-deployment salt; only masked
forms are ever persisted.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.enums import (
    DataSource,
    EntityType,
    RelationshipType,
)
from app.core.errors import BadRequestError
from app.core.security import mask, mask_phone, mask_upi
from app.models import (
    Account,
    Device,
    Entity,
    EntityRelationship,
    PhoneNumber,
    UpiId,
    User,
)
from app.utils.hashing import (
    account_hash,
    device_hash,
    phone_hash,
    sha256_hex,
    upi_hash,
)

_SALT = sha256_hex(settings.secret_key.get_secret_value())[:16]


class EntityService:
    """Resolve identifiers into a typed entity graph."""

    # ----------------------------------------------------- identifier
    async def _ensure_account(self, session: AsyncSession, account_number: str) -> Account:
        hashed = account_hash(account_number, _SALT)
        row = await session.scalar(select(Account).where(Account.account_number_hash == hashed))
        if row is None:
            row = Account(
                account_number_hash=hashed,
                account_number_masked=mask(account_number),
            )
            session.add(row)
            await session.flush()
        return row

    async def _ensure_phone(self, session: AsyncSession, phone: str) -> PhoneNumber:
        digits = "".join(c for c in phone if c.isdigit())
        hashed = phone_hash(digits, _SALT)
        row = await session.scalar(select(PhoneNumber).where(PhoneNumber.phone_hash == hashed))
        if row is None:
            row = PhoneNumber(phone_hash=hashed, phone_masked=mask_phone(phone))
            session.add(row)
            await session.flush()
        return row

    async def _ensure_upi(self, session: AsyncSession, upi: str) -> UpiId:
        hashed = upi_hash(upi, _SALT)
        row = await session.scalar(select(UpiId).where(UpiId.upi_hash == hashed))
        if row is None:
            row = UpiId(upi_hash=hashed, upi_masked=mask_upi(upi))
            session.add(row)
            await session.flush()
        return row

    async def _ensure_device(self, session: AsyncSession, fingerprint: str) -> Device:
        hashed = device_hash(fingerprint, _SALT)
        row = await session.scalar(select(Device).where(Device.device_hash == hashed))
        if row is None:
            row = Device(device_hash=hashed)
            session.add(row)
            await session.flush()
        return row

    async def _ensure_entity(
        self,
        session: AsyncSession,
        *,
        entity_type: EntityType,
        external_id: str,
        label: str | None = None,
        case_id: uuid.UUID | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Entity:
        row = await session.scalar(
            select(Entity).where(
                Entity.entity_type == entity_type.value,
                Entity.external_id == external_id,
            )
        )
        if row is None:
            row = Entity(
                entity_type=entity_type,
                external_id=external_id,
                label=label,
                case_id=case_id,
                metadata_json=metadata or {},
                data_source=DataSource.OPERATIONAL,
            )
            session.add(row)
            await session.flush()
        elif metadata:
            merged = {**row.metadata_json, **metadata}
            row.metadata_json = merged
        return row

    # --------------------------------------------------- resolution API
    async def resolve_from_account(
        self,
        session: AsyncSession,
        *,
        account_number: str,
        case_id: uuid.UUID | None = None,
        label: str | None = None,
    ) -> Entity:
        account = await self._ensure_account(session, account_number)
        entity = await self._ensure_entity(
            session,
            entity_type=EntityType.ACCOUNT,
            external_id=account.account_number_hash,
            label=label or f"Account {mask(account_number)}",
            case_id=case_id,
            metadata={"is_mule": account.is_mule},
        )
        entity.account_id = account.id
        await session.flush()
        return entity

    async def resolve_phone(
        self,
        session: AsyncSession,
        *,
        phone: str,
        case_id: uuid.UUID | None = None,
        label: str | None = None,
    ) -> Entity:
        phone_row = await self._ensure_phone(session, phone)
        entity = await self._ensure_entity(
            session,
            entity_type=EntityType.PHONE,
            external_id=phone_row.phone_hash,
            label=label or f"Phone {mask_phone(phone)}",
            case_id=case_id,
        )
        entity.phone_id = phone_row.id
        await session.flush()
        return entity

    async def resolve_upi(
        self, session: AsyncSession, *, upi: str, case_id: uuid.UUID | None = None
    ) -> Entity:
        upi_row = await self._ensure_upi(session, upi)
        entity = await self._ensure_entity(
            session,
            entity_type=EntityType.UPI,
            external_id=upi_row.upi_hash,
            label=f"UPI {mask_upi(upi)}",
            case_id=case_id,
        )
        entity.upi_id = upi_row.id
        await session.flush()
        return entity

    async def resolve_device(
        self, session: AsyncSession, *, fingerprint: str, case_id: uuid.UUID | None = None
    ) -> Entity:
        device = await self._ensure_device(session, fingerprint)
        entity = await self._ensure_entity(
            session,
            entity_type=EntityType.DEVICE,
            external_id=device.device_hash,
            label="Device",
            case_id=case_id,
        )
        entity.device_id = device.id
        await session.flush()
        return entity

    # ------------------------------------------------------------- link
    async def link(
        self,
        session: AsyncSession,
        *,
        source: Entity,
        target: Entity,
        relationship: RelationshipType | str,
        weight: float = 1.0,
        confidence: float = 0.8,
        timestamp: datetime | None = None,
        evidence: dict[str, Any] | None = None,
        actor: User | None = None,
    ) -> EntityRelationship:
        rel_type = (
            relationship if isinstance(relationship, RelationshipType) else RelationshipType(relationship)
        )
        if source.id == target.id:
            raise BadRequestError("Cannot link an entity to itself.", code="SELF_LINK")
        existing = await session.scalar(
            select(EntityRelationship).where(
                EntityRelationship.source_entity_id == source.id,
                EntityRelationship.target_entity_id == target.id,
                EntityRelationship.relationship_type == rel_type,
            )
        )
        if existing is not None:
            existing.weight = max(existing.weight, weight)
            existing.confidence = max(existing.confidence, confidence)
            if evidence:
                existing.evidence = {**existing.evidence, **evidence}
            await session.flush()
            return existing

        link_row = EntityRelationship(
            source_entity_id=source.id,
            target_entity_id=target.id,
            relationship_type=rel_type,
            weight=weight,
            confidence=confidence,
            timestamp=timestamp or datetime.now(UTC),
            evidence=evidence or {},
        )
        session.add(link_row)
        await session.flush()
        return link_row

    async def attach_account_identifiers(
        self,
        session: AsyncSession,
        *,
        account: Entity,
        phone: str | None = None,
        upi: str | None = None,
        device_fingerprint: str | None = None,
        case_id: uuid.UUID | None = None,
    ) -> list[EntityRelationship]:
        """Create ACCOUNT->PHONE / ACCOUNT->UPI / ACCOUNT->DEVICE edges."""
        created: list[EntityRelationship] = []
        if phone:
            phone_entity = await self.resolve_phone(session, phone=phone, case_id=case_id)
            created.append(
                await self.link(
                    session,
                    source=account,
                    target=phone_entity,
                    relationship=RelationshipType.REGISTERED_WITH,
                    evidence={"medium": "phone"},
                )
            )
        if upi:
            upi_entity = await self.resolve_upi(session, upi=upi, case_id=case_id)
            created.append(
                await self.link(
                    session,
                    source=account,
                    target=upi_entity,
                    relationship=RelationshipType.REGISTERED_WITH,
                    evidence={"medium": "upi"},
                )
            )
        if device_fingerprint:
            device_entity = await self.resolve_device(
                session, fingerprint=device_fingerprint, case_id=case_id
            )
            created.append(
                await self.link(
                    session,
                    source=account,
                    target=device_entity,
                    relationship=RelationshipType.USES,
                    evidence={"medium": "device"},
                )
            )
        return created

    async def link_victim_entities(
        self,
        session: AsyncSession,
        *,
        case_id: uuid.UUID,
        victim_account: str | None,
        victim_phone: str | None,
        complaint_id: uuid.UUID | None = None,
    ) -> dict[str, Entity]:
        """Resolve and persist the victim's identifiers as graph nodes."""
        from app.models import Complaint

        entities: dict[str, Entity] = {}
        if victim_account:
            entities["account"] = await self.resolve_from_account(
                session, account_number=victim_account, case_id=case_id, label="Victim account"
            )
        if victim_phone:
            entities["phone"] = await self.resolve_phone(
                session, phone=victim_phone, case_id=case_id, label="Victim phone"
            )

        complaint_entity = None
        if complaint_id:
            complaint = await session.get(Complaint, complaint_id)
            if complaint:
                complaint_entity = await self._ensure_entity(
                    session,
                    entity_type=EntityType.COMPLAINT,
                    external_id=str(complaint.id),
                    label=f"Complaint {complaint.complaint_number}",
                    case_id=case_id,
                )
                entities["complaint"] = complaint_entity
                for key in ("account", "phone"):
                    if key in entities:
                        await self.link(
                            session,
                            source=entities[key],
                            target=complaint_entity,
                            relationship=RelationshipType.COMPLAINTS_ABOUT,
                            evidence={"complaint_id": str(complaint.id), "role": "victim"},
                        )
        return entities

    async def get_relations(
        self,
        session: AsyncSession,
        *,
        entity_id: uuid.UUID,
    ) -> list[EntityRelationship]:
        rows = await session.scalars(
            select(EntityRelationship).where(
                (EntityRelationship.source_entity_id == entity_id)
                | (EntityRelationship.target_entity_id == entity_id)
            )
        )
        return list(rows.all())


entity_service: EntityService = EntityService()

__all__ = ["EntityService", "entity_service"]
