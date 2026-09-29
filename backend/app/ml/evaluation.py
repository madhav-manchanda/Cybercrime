"""Model evaluation metrics for cash-out location prediction.

Metrics implemented:

- precision / recall / F1 / ROC-AUC (binary, calibrated threshold)
- top-K location hit rate
- mean/median spatial error (km between predicted and actual ATM)
- time-window hit rate (actual withdrawal inside the predicted window)
- calibration diagnostics (ECE)

⚠️ All metrics computed here are evaluated on **synthetic data** only unless
the caller passes ``scope="operational"`` explicitly.
"""

from __future__ import annotations

import itertools
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

Threshold = 0.5


@dataclass
class LocationEvaluation:
    """Record computed from recorded outcomes vs. the prediction."""

    outcomes: list[dict[str, Any]] = field(default_factory=list)
    scope: str = "synthetic"

    @property
    def sample_size(self) -> int:
        return len(self.outcomes)

    def evaluate(self) -> dict[str, float]:
        n = self.sample_size
        if n == 0:
            return {"sample_size": 0.0, "note": 1.0}

        predicted_id = [o.get("predicted_atm_id") for o in self.outcomes]
        actual_id = [o.get("actual_atm_id", o.get("actual_location_id")) for o in self.outcomes]
        [bool(o.get("was_cashout", False)) for o in self.outcomes]
        outcome_type = [o.get("outcome_type", "UNKNOWN") for o in self.outcomes]

        # location hit = predicted top location id equals actual (per outcome)
        hit = []
        for p, a in zip(predicted_id, actual_id, strict=False):
            if p and a:
                hit.append(int(str(p) == str(a)))
            else:
                hit.append(0)

        distance_error = [
            float(o["distance_error_km"]) for o in self.outcomes if o.get("distance_error_km") is not None
        ]
        distance_error = [d for d in distance_error if d >= 0]
        time_error = [
            float(o["time_error_hours"]) for o in self.outcomes if o.get("time_error_hours") is not None
        ]
        time_window_hit = [
            int(bool(o.get("time_window_hit"))) for o in self.outcomes if "time_window_hit" in o
        ]

        confirmed = sum(t == "PREDICTION_CONFIRMED" for t in outcome_type)
        partial = sum(t == "PREDICTION_PARTIAL" for t in outcome_type)
        incorrect = sum(t == "PREDICTION_INCORRECT" for t in outcome_type)

        base: dict[str, float] = {
            "sample_size": float(n),
            "top1_hit_rate": float(np.mean(hit)) if hit else 0.0,
            "confirmed": float(confirmed),
            "partial": float(partial),
            "incorrect": float(incorrect),
            "sqrt": 0.0,  # placeholder replaced below
        }
        if distance_error:
            base["mean_location_error_km"] = float(np.mean(distance_error))
            base["median_location_error_km"] = float(np.median(distance_error))
            base["within_5km_rate"] = float(np.mean([1.0 if d <= 5.0 else 0.0 for d in distance_error]))
        if time_error:
            base["mean_time_error_hours"] = float(np.mean(time_error))
        if time_window_hit:
            base["time_window_hit_rate"] = float(np.mean(time_window_hit))

        base.pop("sqrt", None)
        base["scope"] = 1.0 if self.scope == "operational" else 0.0
        return {k: round(float(v), 4) for k, v in base.items()}


def binary_metrics(
    labels: np.ndarray, scores: np.ndarray, *, threshold: float = Threshold
) -> dict[str, float]:
    """Binary classification metrics for the ranker's held-out split."""
    labels = np.asarray(labels, dtype=int)
    scores = np.asarray(scores, dtype=float)
    out: dict[str, float] = {}
    if len(labels) == 0 or len(np.unique(labels)) < 2:
        return out
    pred = (scores >= threshold).astype(int)
    out["precision"] = float(precision_score(labels, pred, zero_division=0))
    out["recall"] = float(recall_score(labels, pred, zero_division=0))
    out["f1"] = float(f1_score(labels, pred, zero_division=0))
    try:
        out["roc_auc"] = float(roc_auc_score(labels, scores))
        out["average_precision"] = float(average_precision_score(labels, scores))
        out["brier_score"] = float(brier_score_loss(labels, scores))
        out["ece"] = _expected_calibration_error(labels, scores)
    except ValueError:
        pass
    return {k: round(float(v), 4) for k, v in out.items()}


def top_k_hit_rate(predictions: Sequence[Sequence[Any]], actuals: Sequence[Any]) -> float:
    """Fraction where the true ATM appears among the model's top-k for a case."""
    if not predictions:
        return 0.0
    hits = 0
    total = 0
    for predicted, actual in zip(predictions, actuals, strict=False):
        if actual is None:
            continue
        total += 1
        if actual in predicted:
            hits += 1
    return round(hits / max(total, 1), 4)


def time_window_hit_rate(windows: Sequence[tuple[Any, Any]], actual_times: Sequence[Any]) -> float:
    hits = 0
    total = 0
    for (start, end), actual in zip(windows, actual_times, strict=False):
        if actual is None or start is None or end is None:
            continue
        total += 1
        if start <= actual <= end:
            hits += 1
    return round(hits / max(total, 1), 4)


def _expected_calibration_error(labels: np.ndarray, scores: np.ndarray, bins: int = 10) -> float:
    bin_edges = np.linspace(0.0, 1.0, bins + 1)
    ece = 0.0
    n = len(scores)
    for lo, hi in itertools.pairwise(bin_edges):
        mask = (scores >= lo) & (scores < hi)
        if not np.any(mask):
            continue
        bin_acc = float(np.mean(labels[mask]))
        bin_conf = float(np.mean(scores[mask]))
        ece += (len(np.where(mask)[0]) / n) * abs(bin_acc - bin_conf)
    return float(ece)


__all__ = [
    "LocationEvaluation",
    "binary_metrics",
    "time_window_hit_rate",
    "top_k_hit_rate",
]
