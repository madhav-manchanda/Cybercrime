"""Artifact wrapper types shared by inference and training."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RankerBundle:
    """A trained ranker plus the context needed to run it."""

    model: Any
    feature_columns: list[str]
    calibrator: Any | None = None
    model_name: str = "cashout-risk-ranker"
    model_version: str = "0.0.0"
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class ComponentModelScores:
    historical: float = 0.0
    spatial: float = 0.0
    temporal: float = 0.0
    network: float = 0.0

    def as_dict(self) -> dict[str, float]:
        return {
            "historical": self.historical,
            "spatial": self.spatial,
            "temporal": self.temporal,
            "network": self.network,
        }


__all__ = ["ComponentModelScores", "RankerBundle"]
