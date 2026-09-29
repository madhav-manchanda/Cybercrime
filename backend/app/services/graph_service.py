"""Fraud-network graph engine (NetworkX over the entity graph).

Builds a weighted undirected graph from stored entity relationships, computes
structural metrics, detects suspicious clusters, and renders React-Flow/D3
friendly JSON.

⚠️ Terminology is deliberately neutral ("suspicious relationship", "associated
entity", "risk signal"). A graph edge records an *observed association*, not a
proof of criminal activity.
"""

from __future__ import annotations

import uuid
from typing import Any

import networkx as nx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import RelationshipType
from app.models import Entity, EntityRelationship
from app.utils.validators import as_str

_SUSPICIOUS_RELATIONSHIPS = {
    RelationshipType.FUNDS_TRANSFERRED_TO,
    RelationshipType.FUNDS_TRANSFERRED_FROM,
    RelationshipType.WITHDREW_AT,
    RelationshipType.CO_OCCURRED,
}


class GraphService:
    """Builds and analyses per-case entity graphs."""

    async def load(self, session: AsyncSession, *, case_id: uuid.UUID) -> nx.Graph:
        """Load a case graph into memory (nodes + weighted edges)."""
        entities = await session.scalars(
            select(Entity).where(
                (Entity.case_id == case_id)
                | (
                    Entity.id.in_(
                        select(EntityRelationship.source_entity_id)
                        .join(Entity, Entity.id == EntityRelationship.source_entity_id)
                        .where(Entity.case_id == case_id)
                    )
                )
            )
        )
        graph = nx.Graph()
        entity_list = list(entities.all())
        for entity in entity_list:
            risk = float(entity.risk_score or 0.0)
            graph.add_node(
                str(entity.id),
                entity_type=as_str(entity.entity_type),
                label=entity.display_label,
                risk=risk,
                metadata={
                    "external_id": entity.external_id,
                    "is_resolved": entity.is_resolved,
                },
            )

        relations = await session.scalars(
            select(EntityRelationship).where(
                EntityRelationship.source_entity_id.in_([e.id for e in entity_list])
                | EntityRelationship.target_entity_id.in_([e.id for e in entity_list])
            )
        )
        for rel in relations.all():
            source = str(rel.source_entity_id)
            target = str(rel.target_entity_id)
            if source not in graph or target not in graph:
                continue
            graph.add_edge(
                source,
                target,
                relationship=as_str(rel.relationship_type),
                weight=float(rel.weight),
                confidence=float(rel.confidence),
                timestamp=rel.timestamp.isoformat() if rel.timestamp else None,
            )
        return graph

    def metrics(self, graph: nx.Graph) -> dict[str, Any]:
        """Structural metrics + suspicious cluster detection for a graph."""
        if graph.number_of_nodes() == 0:
            return self._empty_metrics()

        degrees = dict(graph.degree())
        weighted = dict(graph.degree(weight="weight"))
        degrees_by_node = {
            n: {"degree": d, "weighted_degree": round(weighted.get(n, 0.0), 3)} for n, d in degrees.items()
        }
        components = list(nx.connected_components(graph))
        diameters: list[int] = []
        for comp in components:
            sub = graph.subgraph(comp)
            if len(comp) > 1:
                try:
                    diameters.append(nx.diameter(sub))
                except nx.NetworkXError:
                    diameters.append(0)

        # centrality (bounded work: only for reasonable graphs)
        try:
            betweenness = nx.betweenness_centrality(graph, weight="weight")
        except Exception:  # pragma: no cover
            betweenness = dict.fromkeys(graph.nodes, 0.0)

        central_nodes = sorted(
            (
                {
                    "id": n,
                    "label": graph.nodes[n].get("label", n),
                    "entity_type": graph.nodes[n].get("entity_type"),
                    "degree": degrees_by_node[n]["degree"],
                    "weighted_degree": degrees_by_node[n]["weighted_degree"],
                    "betweenness": round(betweenness.get(n, 0.0), 4),
                    "risk": graph.nodes[n].get("risk", 0.0),
                }
                for n in graph.nodes
            ),
            key=lambda x: (x["betweenness"], x["weighted_degree"]),
            reverse=True,
        )[:15]

        suspicious_clusters = self._suspicious_clusters(graph)

        return {
            "nodes": graph.number_of_nodes(),
            "edges": graph.number_of_edges(),
            "connected_components": len(components),
            "diameter": max(diameters) if diameters else None,
            "mean_degree": round(sum(d for d in degrees.values()) / graph.number_of_nodes(), 3),
            "max_degree": max(degrees.values()) if degrees else 0,
            "density": round(nx.density(graph), 4),
            "clustering_coefficient": round(nx.average_clustering(graph), 4),
            "central_nodes": central_nodes,
            "suspicious_clusters": suspicious_clusters,
            "node_stats": degrees_by_node,
        }

    def _suspicious_clusters(self, graph: nx.Graph) -> list[dict[str, Any]]:
        """Identify dense components dominated by risk edges (radar, not verdict)."""
        clusters: list[dict[str, Any]] = []
        for component in nx.connected_components(graph):
            sub = graph.subgraph(component)
            if len(component) < 3:
                continue
            risky = sum(
                1
                for _, _, data in sub.edges(data=True)
                if data.get("relationship") in {r.value for r in _SUSPICIOUS_RELATIONSHIPS}
            )
            risk_ratio = risky / max(sub.number_of_edges(), 1)
            mean_risk = sum(float(graph.nodes[n].get("risk", 0.0)) for n in sub.nodes) / len(sub)
            if risk_ratio >= 0.5 or mean_risk >= 0.5:
                clusters.append(
                    {
                        "cluster_id": "-".join(sorted(str(n) for n in component)[:4]),
                        "size": len(component),
                        "mean_risk": round(mean_risk, 3),
                        "risk_edge_ratio": round(risk_ratio, 3),
                        "entity_types": sorted({graph.nodes[n].get("entity_type") for n in component}),
                        "member_ids": [str(n) for n in component],
                    }
                )
        clusters.sort(key=lambda c: (c["mean_risk"], c["size"]), reverse=True)
        return clusters[:10]

    async def render(self, session: AsyncSession, *, case_id: uuid.UUID) -> dict[str, Any]:
        """Return the React-Flow/D3 graph payload with metrics + warnings."""
        graph = await self.load(session, case_id=case_id)
        metrics = self.metrics(graph)

        nodes = [
            {
                "id": n,
                "type": graph.nodes[n].get("entity_type", "ENTITY"),
                "label": graph.nodes[n].get("label", n)[:80],
                "risk": round(graph.nodes[n].get("risk", 0.0), 3),
                "metadata": graph.nodes[n].get("metadata", {}),
            }
            for n in graph.nodes
        ]
        edges = [
            {
                "source": u,
                "target": v,
                "relationship": data.get("relationship", "ASSOCIATED"),
                "weight": data.get("weight", 1.0),
                "confidence": data.get("confidence", 0.8),
                "timestamp": data.get("timestamp"),
            }
            for u, v, data in graph.edges(data=True)
        ]
        warnings = [
            "Graph edges record observed associations, not proof of criminal activity.",
            "Risk values are model estimates and never stand-alone accusations.",
        ]
        if graph.number_of_nodes() == 0:
            warnings.append("No entities have been resolved for this case yet.")

        return {
            "case_id": str(case_id),
            "nodes": nodes,
            "edges": edges,
            "metrics": metrics,
            "warnings": warnings,
        }

    @staticmethod
    def _empty_metrics() -> dict[str, Any]:
        return {
            "nodes": 0,
            "edges": 0,
            "connected_components": 0,
            "diameter": None,
            "mean_degree": 0.0,
            "max_degree": 0,
            "density": 0.0,
            "clustering_coefficient": 0.0,
            "central_nodes": [],
            "suspicious_clusters": [],
        }


graph_service: GraphService = GraphService()

__all__ = ["GraphService", "graph_service"]
