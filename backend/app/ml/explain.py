"""Explainability for cash-out predictions.

Two complementary outputs are produced for every candidate:

1. **factor impacts** - ordered, signed contributions
   - when a ranker with SHAP values is available, impacts come from the model
   - otherwise a transparent *counterfactual-style* contribution derived from
     the baseline blend (how much each signal moves the score away from the
     neutral prior)
2. **explanation text** - the human-readable "why" sentence

Terminology stays probabilistic ("associated", "historical pattern", "risk
signal"); it never asserts that a withdrawal *will* happen.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np

from app.core.config import settings
from app.ml.features import CandidateAtm
from app.ml.predict_models import RankerBundle

_FACTOR_LABELS = {
    "historical": "historical_cashout_proximity",
    "spatial": "spatial_proximity",
    "temporal": "temporal_similarity",
    "network": "network_proximity",
    "hotspot_intensity": "hotspot_intensity",
    "amount_deviation": "amount_deviation",
}


def baseline_contributions(
    components: dict[str, float],
    row: dict[str, float] | Any,
    candidate: CandidateAtm,
) -> list[dict[str, Any]]:
    """Ordered factor impacts for the interpretable blend.

    Influence of each signal is proportional to its component value multiplied
    by the relative weight of that component in the blend versus a neutral 0.5
    prior, then rescaled so magnitudes reflect contribution to the headline.
    """
    weights = {
        "historical": 0.35,
        "spatial": 0.25,
        "temporal": 0.20,
        "network": 0.20,
    }
    impacts: list[dict[str, Any]] = []
    prior = 0.5
    for key, weight in weights.items():
        value = float(np.clip(components.get(key, 0.0), 0.0, 1.0))
        # signed impact relative to a neutral prior
        impact = weight * (value - prior)
        impacts.append(
            {
                "factor": _FACTOR_LABELS[key],
                "impact": round(float(impact), 4),
                "detail": _factor_detail(key, value, row, candidate),
            }
        )

    # add financial / amount signal when available and material
    amt = _safe(row, "case_amount_deviation_ratio")
    if amt is not None and abs(amt) > 0.3:
        impacts.append(
            {
                "factor": "amount_deviation",
                "impact": round(float(np.clip(amt, -0.5, 0.5)) * 0.1, 4),
                "detail": "transaction amounts deviate strongly from the case-typical value",
            }
        )
    hotspot = _safe(row, "hotspot_intensity")
    if hotspot is not None and hotspot > 0.5:
        impacts.append(
            {
                "factor": "hotspot_intensity",
                "impact": round(float(min(hotspot, 1.0) - 0.5) * 0.08, 4),
                "detail": "location sits inside a concentrated historical cash-out hotspot",
            }
        )

    impacts.sort(key=lambda i: abs(i["impact"]), reverse=True)
    return impacts[: settings.ml_explanation_top_factors]


def ranker_contributions(
    ranker: RankerBundle,
    x: np.ndarray,
    candidate: CandidateAtm,
    components: dict[str, float],
    row: dict[str, float] | Any,
) -> list[dict[str, Any]]:
    """SHAP-based contributions when available; graceful fallback otherwise."""
    shap_values = _try_shap(ranker, x)
    if shap_values is not None:
        return _from_shap(ranker.feature_columns, shap_values, candidate)
    return baseline_contributions(components, row, candidate)


def _try_shap(ranker: RankerBundle, x: np.ndarray) -> np.ndarray | None:
    try:
        import shap

        explainer = shap.TreeExplainer(ranker.model)
        values = explainer.shap_values(x)
        if isinstance(values, list):
            values = values[1] if len(values) > 1 else values[0]
        return np.asarray(values).ravel()
    except Exception:
        return None


def _from_shap(
    feature_columns: list[str],
    shap_row: np.ndarray,
    candidate: CandidateAtm,
) -> list[dict[str, Any]]:
    pairs = sorted(zip(feature_columns, shap_row, strict=False), key=lambda p: abs(float(p[1])), reverse=True)
    grouped: list[dict[str, Any]] = []
    for _name, _value in pairs[: settings.ml_explanation_top_factors]:
        grouped.append(
            {
                "factor": _readable_feature(_name),
                "impact": round(float(_value), 4),
                "detail": _feature_detail(_name),
            }
        )
    return grouped


def _readable_feature(name: str) -> str:
    mapping = {
        "hist_cashout_signal": "historical_cashout_proximity",
        "hist_cashout_count": "historical_cashout_frequency",
        "anchor_attraction": "spatial_proximity",
        "dist_to_nearest_anchor_km": "distance_to_case_activity",
        "cashout_attraction": "historical_cashout_proximity",
        "temporal_similarity": "temporal_similarity",
        "hotspot_intensity": "hotspot_intensity",
        "atm_network_link_count": "network_proximity",
        "net_mule_count": "linked_mule_entities",
        "net_suspicious_cluster_size": "suspicious_cluster_size",
        "atm_is_csp": "csp_location",
        "case_total_amount": "case_exposure_amount",
        "case_velocity_per_hour": "transaction_velocity",
        "amount_deviation": "amount_deviation",
        "cashout_window_hour": "predicted_cashout_window",
    }
    return mapping.get(name, name.replace("_", " "))


def _feature_detail(name: str) -> str:
    details = {
        "hist_cashout_signal": "historic cash-outs of associated entities occurred at/near this location",
        "hist_cashout_count": "the number of historical cash-outs mapped to this location is elevated",
        "anchor_attraction": "location is geographically close to case-linked activity points",
        "dist_to_nearest_anchor_km": "proximity to the nearest case activity point",
        "cashout_attraction": "nearness to historical cash-out events of linked entities",
        "temporal_similarity": "typical withdrawal hour overlaps the case's learned cash-out time profile",
        "hotspot_intensity": "the point sits in a dense historical cash-out hotspot",
        "atm_network_link_count": "this ATM is directly linked to case entities in the graph",
        "net_mule_count": "case graph contains several high-risk associated accounts",
        "net_suspicious_cluster_size": "the case graph shows a dense suspicious cluster",
        "atm_is_csp": "CSP/correspondent locations present distinct cash-out risk profiles",
        "case_total_amount": "large amount exposed in this case",
        "case_velocity_per_hour": "elevated transaction velocity observed for the case",
        "amount_deviation": "amounts deviate strongly from the case-typical value",
        "cashout_window_hour": "this hour falls inside the predicted cash-out window",
    }
    return details.get(name, "model feature")


def _safe(row: dict[str, float] | Any, key: str) -> float | None:
    try:
        value = row.get(key) if hasattr(row, "get") else None
        if value is None:
            return None
        if hasattr(value, "item"):
            value = value.item()
        return float(value)
    except (TypeError, ValueError):
        return None


def _factor_detail(key: str, value: float, row: dict[str, float] | Any, candidate: CandidateAtm) -> str:
    if key == "historical":
        count = _safe(row, "hist_cashout_count") or 0
        return f"{int(count)} historical cash-out(s) recorded at {candidate.name}"
    if key == "spatial":
        return "location overlaps case activity and historical cash-out geography"
    if key == "temporal":
        return "withdrawal timing matches the learned cash-out hour-of-day profile"
    if key == "network":
        return "case graph structure and ATM linkage present elevated association risk"
    return f"component {key} = {round(value, 2)}"


def shorthand_explanation(factors: Sequence[dict[str, Any]], candidate: CandidateAtm) -> str:
    """Human-readable one-paragraph why for a candidate location."""
    if not factors:
        return (
            f"{candidate.name} is ranked from its estimated risk relative to other "
            "candidate locations; no dominant factor was available."
        )
    top = sorted(factors, key=lambda f: abs(f.get("impact", 0.0)), reverse=True)
    reasons = []
    for factor in top[:3]:
        label = factor.get("factor", "").replace("_", " ")
        detail = factor.get("detail")
        reasons.append(label if not detail else f"{label} ({detail})")
    clause = ", ".join(reasons)
    return (
        f"High relative risk for {candidate.name} because {clause.rstrip('.')}. "
        "This is a model estimate from observed associations, not a prediction of certainty."
    )


__all__ = [
    "baseline_contributions",
    "ranker_contributions",
    "shorthand_explanation",
]
