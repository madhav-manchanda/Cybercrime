"""Model training: XGBoost ranker + calibration on synthetic ground truth.

Training is a **background job**. The pipeline:

1. Assemble the labelled feature frame (see :mod:`app.ml.datasets`).
2. Split by case to avoid leakage: train cases vs. held-out cases.
3. Fit an XGBoost ranker on the feature matrix.
4. Fit a Platt/isotonic calibrator on the held-out split.
5. Persist artifact + metrics + a :class:`ModelRun` journal row.

Metrics produced here are *synthetic-data evaluation metrics* and are stored
with that provenance attached.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import numpy as np
import pandas as pd
import structlog
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from xgboost import XGBClassifier

from app.core.config import settings
from app.core.enums import ModelKind, ModelStatus, TrainingStatus
from app.ml.model_registry import registry
from app.ml.predict_models import RankerBundle

logger = structlog.get_logger("ml.train")


@dataclass
class TrainingResult:
    model_name: str
    model_version: str
    metrics: dict[str, float] = field(default_factory=dict)
    artifact_path: str | None = None
    sample_count: int = 0
    status: str = TrainingStatus.SUCCEEDED.value
    error: str | None = None


def _next_version() -> str:
    now = datetime.now(UTC)
    return f"{now.year}.{now.month}.{now.day}-{now.strftime('%H%M%S')}"


def train_ranker_on_frame(
    frame: pd.DataFrame,
    *,
    tune: bool = True,
    random_state: int | None = None,
) -> TrainingResult:
    """Train the ranker on an already-assembled labelled DataFrame."""
    random_state = random_state or settings.ml_random_seed
    if frame.empty or "label" not in frame.columns:
        return TrainingResult(
            model_name="cashout-risk-ranker",
            model_version="none",
            status=TrainingStatus.SKIPPED.value,
            error="no training data available",
        )

    pos = int((frame["label"] == 1).sum())
    neg = int((frame["label"] == 0).sum())
    if pos < settings.ml_min_train_samples:
        return TrainingResult(
            model_name="cashout-risk-ranker",
            model_version="none",
            status=TrainingStatus.SKIPPED.value,
            error=f"only {pos} positives - below minimum {settings.ml_min_train_samples}",
        )

    feature_cols = list(feature_columns_if_available(frame))
    X = frame[feature_cols].values.astype(np.float64)
    y = frame["label"].values.astype(int)

    case_ids = frame["case_id"].unique()
    rng = np.random.default_rng(random_state)
    rng.shuffle(case_ids)
    n_train_cases = max(int(len(case_ids) * 0.8), 1)
    train_cases = set(case_ids[:n_train_cases])
    mask_train = frame["case_id"].isin(train_cases).values
    X_train, y_train = X[mask_train], y[mask_train]
    X_val, y_val = X[~mask_train], y[~mask_train]

    params = {
        "n_estimators": 200,
        "max_depth": 5,
        "learning_rate": 0.08,
        "subsample": 0.8,
        "colsample_bytree": 0.8,
        "min_child_weight": 2,
        "reg_lambda": 1.0,
        "objective": "binary:logistic",
        "eval_metric": "logloss",
        "random_state": random_state,
        "n_jobs": 2,
        "base_score": np.clip(pos / max(len(y), 1), 1e-4, 0.99),
    }
    scale_pos_weight = max(len(y_train[y_train == 0]) / max(int((y_train == 1).sum()), 1), 1.0)
    params["scale_pos_weight"] = float(np.clip(scale_pos_weight, 1.0, 40.0))

    model = XGBClassifier(**params)
    model.fit(X_train, y_train)

    # calibrate on validation split when present enough
    calibrator = None
    val_proba = None
    if len(X_val) > 0 and int((y_val == 1).sum()) >= 10:
        calibrator = CalibratedClassifierCV(model, method="isotonic", cv=3)
        calibrator.fit(X_val, y_val)
        val_proba = calibrator.predict_proba(X_val)[:, 1]
    else:
        val_proba = model.predict_proba(X_val)[:, 1] if len(X_val) else None

    metrics = _metrics(y_val, val_proba, model, X_val) if val_proba is not None else {}

    version = _next_version()
    feature_version = "1.0"
    bundle = RankerBundle(
        model=model,
        feature_columns=feature_cols,
        calibrator=calibrator,
        model_name="cashout-risk-ranker",
        model_version=version,
        params=params,
    )
    artifact = registry.save(
        bundle,
        model_name="cashout-risk-ranker",
        model_version=version,
        feature_version=feature_version,
        model_kind=ModelKind.RANKER,
        feature_columns=feature_cols,
        metadata={"status": ModelStatus.ACTIVE.value, "trained_on": "synthetic"},
        params=params,
    )
    # persist calibrator artifact too
    if calibrator is not None:
        import joblib

        joblib.dump(
            calibrator,
            registry.model_dir("cashout-risk-ranker", version) / "calibrator.joblib",
        )

    metrics.update(
        {
            "train_positives": int(pos),
            "train_negatives": int(neg),
            "train_cases": len(train_cases),
            "eval_cases": len(set(case_ids) - train_cases),
            "feature_count": len(feature_cols),
            "provenance": 2.0,  # marker: synthetic
        }
    )
    logger.info(
        "ranker_trained",
        version=version,
        metrics={k: round(v, 4) for k, v in metrics.items() if isinstance(v, (int, float))},
    )
    return TrainingResult(
        model_name="cashout-risk-ranker",
        model_version=version,
        metrics=metrics,
        artifact_path=str(artifact),
        sample_count=len(frame),
    )


def _metrics(y_true: np.ndarray, y_proba: np.ndarray, model: Any, X_val: np.ndarray) -> dict[str, float]:
    y_pred = (y_proba >= 0.5).astype(int)
    n = len(y_true)
    metrics: dict[str, float] = {}
    if n == 0:
        return metrics
    metrics["precision"] = float(precision_score(y_true, y_pred, zero_division=0))
    metrics["recall"] = float(recall_score(y_true, y_pred, zero_division=0))
    metrics["f1"] = float(f1_score(y_true, y_pred, zero_division=0))
    metrics["accuracy"] = float(accuracy_score(y_true, y_pred))
    try:
        if len(np.unique(y_true)) > 1:
            metrics["roc_auc"] = float(roc_auc_score(y_true, y_proba))
            metrics["average_precision"] = float(average_precision_score(y_true, y_proba))
    except ValueError:
        pass
    metrics["sample_size"] = float(n)
    return metrics


def feature_columns_if_available(frame: pd.DataFrame) -> list[str]:
    cols = feature_columns_from_frame(frame)
    if cols:
        return cols
    from app.ml.features import feature_columns

    return feature_columns()


def feature_columns_from_frame(frame: pd.DataFrame) -> list[str]:
    expected = set(frame.columns)
    from app.ml.features import feature_columns

    return [c for c in feature_columns() if c in expected]


__all__ = ["TrainingResult", "train_ranker_on_frame"]
