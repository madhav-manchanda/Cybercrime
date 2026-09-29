"""Cash-out prediction: hybrid scoring ensemble + ranking.

Four component signals feed the predictor:

1. **historical** - prior cash-out signal at the candidate ATM
2. **spatial**    - proximity to case/anchor/cash-out geography + hotspot
3. **temporal**   - overlap with the learned cash-out hour-of-day profile
4. **network**    - structural risk of the case graph + ATM linkage

When a trained ranker artifact is available, its calibrated probability is used
as the headline risk; otherwise a documented transparent fallback blend runs.
Both paths emit per-ATM risk, confidence and ordered factor contributions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from app.core.config import settings
from app.ml.explain import (
    baseline_contributions,
    ranker_contributions,
    shorthand_explanation,
)
from app.ml.features import (
    CandidateAtm,
    FeatureBundle,
    build_feature_matrix,
    component_scores,
    feature_columns,
)
from app.ml.model_registry import registry
from app.ml.predict_models import RankerBundle

_BASELINE_WEIGHTS = {
    "historical": 0.35,
    "spatial": 0.25,
    "temporal": 0.20,
    "network": 0.20,
}


@dataclass
class RankedPrediction:
    """One scored candidate ATM."""

    candidate: CandidateAtm
    risk_score: float
    confidence: float
    components: dict[str, float]
    factor_impacts: list[dict[str, Any]]
    explanation_text: str
    model_name: str
    model_version: str


def _agreement_confidence(components: dict[str, float]) -> float:
    arr = np.array(list(components.values()), dtype=np.float64)
    if arr.size == 0:
        return 0.5
    arr = np.clip(arr, 0.0, 1.0)
    spread = float(arr.max() - arr.min())
    agreement = 1.0 - min(1.0, spread / 0.75)
    return float(np.clip(0.45 + 0.55 * agreement, 0.1, 0.97))


def rank_candidates(
    bundle: FeatureBundle,
    candidates: list[CandidateAtm],
    *,
    top_k: int | None = None,
    ranker: RankerBundle | None = None,
) -> list[RankedPrediction]:
    """Score + rank candidates using the active ranker or the fallback blend.

    Never returns raw model logits as if they were certainties - outputs are
    probability-like risk scores gated by a calibration/agreement confidence.
    """
    top_k = top_k or settings.ml_predict_top_k
    if not candidates:
        return []

    feature_df, _resolver = build_feature_matrix(bundle, candidates)
    feature_df = feature_df.fillna(-999.0).replace([np.inf, -np.inf], -999.0)

    model_name = "cashout-risk"
    model_version = "baseline-blend-v1"

    if ranker is not None and ranker.feature_columns is not None:
        can_use_ranker = True
        feature_cols = ranker.feature_columns
    else:
        can_use_ranker = False
        feature_cols = feature_columns()

    ranked: list[RankedPrediction] = []
    for _, row in feature_df.iterrows():
        components = component_scores(row)
        atm_id = row["atm_id"]
        candidate = next((c for c in candidates if c.atm_id == atm_id), None)
        if candidate is None:
            continue

        if can_use_ranker and ranker is not None and all(col in feature_df.columns for col in feature_cols):
            x = feature_df.loc[feature_df["atm_id"] == atm_id, feature_cols].values.reshape(1, -1)
            proba = (
                float(ranker.model.predict_proba(x)[0, 1])
                if hasattr(ranker.model, "predict_proba")
                else float(ranker.model.predict(x)[0])
            )
            risk_score = float(np.clip(proba, 0.0, 1.0))
            confidence = calibration_confidence(ranker, proba)
            model_name = ranker.model_name
            model_version = ranker.model_version
            factors = ranker_contributions(ranker, x, candidate, components, row)
        else:
            proba = sum(_BASELINE_WEIGHTS[k] * components[k] for k in _BASELINE_WEIGHTS)
            risk_score = float(np.clip(proba, 0.0, 1.0))
            confidence = _agreement_confidence(components)
            factors = baseline_contributions(components, row, candidate)

        ranked.append(
            RankedPrediction(
                candidate=candidate,
                risk_score=risk_score,
                confidence=confidence,
                components=components,
                factor_impacts=factors,
                explanation_text=shorthand_explanation(factors, candidate),
                model_name=model_name,
                model_version=model_version,
            )
        )

    ranked.sort(key=lambda p: p.risk_score, reverse=True)
    return ranked[:top_k]


def calibration_confidence(ranker: RankerBundle, proba: float) -> float:
    """Confidence calibrated via Platt mapping when available."""
    if ranker.calibrator is not None:
        conf = float(ranker.calibrator.predict(np.array([[proba]]))[0])
        return float(np.clip(conf, 0.05, 0.99))
    return float(np.clip(0.5 + 0.5 * abs(proba - 0.5), 0.1, 0.97))


def load_ranker_for_case(case_id: str | None = None) -> RankerBundle | None:
    """Load the active ranker artifact if one exists."""
    try:
        version = registry.active_version("cashout-risk-ranker")
        if not version:
            return None
        model = registry.load("cashout-risk-ranker", version)
        meta = registry.load_metadata("cashout-risk-ranker", version)
        feature_cols = registry.load_feature_columns("cashout-risk-ranker", version)
        calibrator = None
        cal_path = registry.model_dir("cashout-risk-ranker", version) / "calibrator.joblib"
        if cal_path.exists():
            import joblib

            calibrator = joblib.load(cal_path)
        return RankerBundle(
            model=model,
            feature_columns=feature_cols,
            calibrator=calibrator,
            model_name=meta.get("model_name", "cashout-risk-ranker"),
            model_version=version,
        )
    except Exception:
        return None


__all__ = [
    "RankedPrediction",
    "calibration_confidence",
    "load_ranker_for_case",
    "rank_candidates",
]
