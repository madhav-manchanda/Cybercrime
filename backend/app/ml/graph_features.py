"""Network features extracted from the case entity graph."""

from __future__ import annotations

from dataclasses import dataclass, field

import networkx as nx

from app.core.enums import EntityType, RelationshipType


@dataclass
class CaseNetworkFeatures:
    """Structural risk signals from the associated-entity graph."""

    entity_count: int = 0
    relationship_count: int = 0
    account_count: int = 0
    phone_count: int = 0
    mule_count: int = 0
    complaint_count: int = 0
    atm_count: int = 0
    connected_components: int = 0
    max_component_size: int = 0
    avg_degree: float = 0.0
    risky_edge_ratio: float = 0.0
    victim_center_centrality: float = 0.0
    suspicious_cluster_size: int = 0
    density: float = 0.0
    raw: dict = field(default_factory=dict)

    def as_dict(self, prefix: str = "net_") -> dict[str, float]:
        skip = {"raw"}
        return {
            f"{prefix}{k}": float(v)
            for k, v in self.__dict__.items()
            if k not in skip and isinstance(v, (int, float))
        }


def extract_features(graph: nx.Graph) -> CaseNetworkFeatures:
    """Compute a feature vector from a case graph."""
    features = CaseNetworkFeatures(
        entity_count=graph.number_of_nodes(),
        relationship_count=graph.number_of_edges(),
    )
    if graph.number_of_nodes() == 0:
        return features

    for _node, data in graph.nodes(data=True):
        etype = data.get("entity_type")
        if etype == EntityType.ACCOUNT.value:
            features.account_count += 1
            if data.get("metadata", {}).get("is_mule"):
                features.mule_count += 1
        elif etype == EntityType.PHONE.value:
            features.phone_count += 1
        elif etype == EntityType.COMPLAINT.value:
            features.complaint_count += 1
        elif etype in {EntityType.ATM.value, EntityType.CSP.value}:
            features.atm_count += 1

    components = list(nx.connected_components(graph))
    features.connected_components = len(components)
    features.max_component_size = max((len(c) for c in components), default=0)

    degrees = [d for _, d in graph.degree()]
    features.avg_degree = sum(degrees) / len(degrees) if degrees else 0.0

    risky = 0
    for _, _, data in graph.edges(data=True):
        if data.get("relationship") in {r.value for r in _RISKY_RELS}:
            risky += 1
    features.risky_edge_ratio = risky / max(graph.number_of_edges(), 1)
    features.density = nx.density(graph)

    # centralisation around the victim (if identifiable)
    victim_nodes = [n for n, d in graph.nodes(data=True) if d.get("metadata", {}).get("is_victim")]
    if victim_nodes:
        try:
            betweenness = nx.betweenness_centrality(graph)
            features.victim_center_centrality = max(betweenness.get(n, 0.0) for n in victim_nodes)
        except Exception:  # pragma: no cover
            features.victim_center_centrality = 0.0

    # largest "suspicious" component: dominated by money/co-occurrence edges
    largest = max(components, key=len)
    sub = graph.subgraph(largest)
    suspicious_edges = sum(
        1 for _, _, d in sub.edges(data=True) if d.get("relationship") in {r.value for r in _RISKY_RELS}
    )
    if suspicious_edges / max(sub.number_of_edges(), 1) >= 0.5:
        features.suspicious_cluster_size = len(largest)

    features.raw = {
        "components": [sorted(c)[:20] for c in components[:5]],
    }
    return features


_RISKY_RELS = {
    RelationshipType.FUNDS_TRANSFERRED_TO,
    RelationshipType.FUNDS_TRANSFERRED_FROM,
    RelationshipType.WITHDREW_AT,
    RelationshipType.CO_OCCURRED,
}

__all__ = ["CaseNetworkFeatures", "extract_features"]
