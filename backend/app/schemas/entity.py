"""Entity resolution + fraud-network graph schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.core.enums import DataSource, EntityType, RelationshipType
from app.schemas.common import ORMModel


class EntityLinkRequest(BaseModel):
    """Request to associate a resolved entity to a case."""

    entity_type: EntityType
    external_id: str = Field(min_length=1, max_length=160)
    label: str | None = None
    confidence: float = Field(default=0.8, ge=0, le=1)


class EntityOut(ORMModel):
    entity_type: EntityType
    external_id: str
    label: str | None = None
    risk_score: float | None = None
    is_resolved: bool
    case_id: uuid.UUID | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    data_source: DataSource
    latitude: float | None = None
    longitude: float | None = None


class RelationshipOut(ORMModel):
    source_entity_id: uuid.UUID
    target_entity_id: uuid.UUID
    relationship_type: RelationshipType
    weight: float
    confidence: float
    timestamp: datetime | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)


class GraphNode(BaseModel):
    id: str
    type: EntityType
    label: str
    risk: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class GraphEdge(BaseModel):
    source: str
    target: str
    relationship: RelationshipType
    weight: float = 1.0
    timestamp: datetime | None = None
    confidence: float = 0.8


class FraudNetworkGraph(BaseModel):
    case_id: str
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    metrics: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class NetworkMetrics(BaseModel):
    nodes: int
    edges: int
    connected_components: int
    diameter: int | None = None
    mean_degree: float
    max_degree: int
    density: float
    clustering_coefficient: float = 0.0
    central_nodes: list[dict[str, Any]] = []
    suspicious_clusters: list[dict[str, Any]] = []


class EntityResolutionResult(BaseModel):
    entity_id: uuid.UUID
    matched: bool
    created: bool
    entity_type: EntityType
    relations_created: int = 0


__all__ = [
    "EntityLinkRequest",
    "EntityOut",
    "EntityResolutionResult",
    "FraudNetworkGraph",
    "GraphEdge",
    "GraphNode",
    "NetworkMetrics",
    "RelationshipOut",
]
