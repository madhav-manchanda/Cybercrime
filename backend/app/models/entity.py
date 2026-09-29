"""Entity resolution graph: entities and typed relationships."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON, Uuid

from app.core.database import Base
from app.core.enums import DataSource, EntityType, RelationshipType
from app.models.mixins import (
    GeoPointMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    install_geo_listeners,
)

if TYPE_CHECKING:
    from app.models.account import Account, Device, PhoneNumber, UpiId
    from app.models.atm import AtmLocation
    from app.models.case import Case


class Entity(Base, UUIDPrimaryKeyMixin, TimestampMixin, GeoPointMixin):
    """A resolved entity participating in one or more cases.

    ``external_id`` is the stable business identifier of the underlying record
    (e.g. an account hash) - the unique key is ``(entity_type, external_id)``.
    """

    __tablename__ = "entities"
    __table_args__ = (
        UniqueConstraint("entity_type", "external_id", name="uq_entities_type_external"),
        Index("ix_entities_type", "entity_type"),
        Index("ix_entities_resolved", "is_resolved"),
        Index("ix_entities_label", "label"),
    )

    entity_type: Mapped[EntityType] = mapped_column(String(32), nullable=False)
    external_id: Mapped[str] = mapped_column(String(160), nullable=False)
    label: Mapped[str | None] = mapped_column(String(240), nullable=True)
    risk_score: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)
    is_resolved: Mapped[bool] = mapped_column(default=True, nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    data_source: Mapped[DataSource] = mapped_column(String(16), default=DataSource.SYNTHETIC)

    case_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("cases.id", ondelete="CASCADE"), nullable=True, index=True
    )
    account_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    phone_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("phone_numbers.id", ondelete="SET NULL"), nullable=True, index=True
    )
    device_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("devices.id", ondelete="SET NULL"), nullable=True, index=True
    )
    upi_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("upi_ids.id", ondelete="SET NULL"), nullable=True, index=True
    )
    atm_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("atm_locations.id", ondelete="SET NULL"), nullable=True, index=True
    )

    case: Mapped[Case | None] = relationship(back_populates="entities")
    account: Mapped[Account | None] = relationship(back_populates="entity")
    phone: Mapped[PhoneNumber | None] = relationship(back_populates="entity")
    device: Mapped[Device | None] = relationship(back_populates="entity")
    upi: Mapped[UpiId | None] = relationship(back_populates="entity")
    atm: Mapped[AtmLocation | None] = relationship(back_populates="entities")

    outgoing_relationships: Mapped[list[EntityRelationship]] = relationship(
        back_populates="source_entity", foreign_keys="EntityRelationship.source_entity_id"
    )
    incoming_relationships: Mapped[list[EntityRelationship]] = relationship(
        back_populates="target_entity", foreign_keys="EntityRelationship.target_entity_id"
    )

    @property
    def display_label(self) -> str:
        return self.label or f"{self.entity_type}:{self.external_id[:8]}"


class EntityRelationship(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A typed, evidence-backed association between two entities."""

    __tablename__ = "entity_relationships"
    __table_args__ = (
        Index("ix_assoc_source", "source_entity_id"),
        Index("ix_assoc_target", "target_entity_id"),
        Index("ix_assoc_type", "relationship_type"),
        Index("ix_assoc_ts", "timestamp"),
    )

    source_entity_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("entities.id", ondelete="CASCADE"), nullable=False
    )
    target_entity_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("entities.id", ondelete="CASCADE"), nullable=False
    )
    relationship_type: Mapped[RelationshipType] = mapped_column(String(40), nullable=False)
    weight: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.8, nullable=False)
    timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    source_entity: Mapped[Entity] = relationship(
        back_populates="outgoing_relationships", foreign_keys=[source_entity_id]
    )
    target_entity: Mapped[Entity] = relationship(
        back_populates="incoming_relationships", foreign_keys=[target_entity_id]
    )


install_geo_listeners(Entity)

__all__ = ["Entity", "EntityRelationship"]
