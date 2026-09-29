"""Preprocessing: feature scaling + frame sanitation.

Serves as the canonical entry point for preparing feature matrices for both
training and inference, keeping NaN/inf handling identical on both paths.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.preprocessing import RobustScaler

_FILL = -999.0


def sanitize_frame(frame: pd.DataFrame, feature_cols: list[str]) -> pd.DataFrame:
    """Materialise missing columns, drop unusable rows, impute inf/NaN."""
    out = frame.copy()
    for col in feature_cols:
        if col not in out.columns:
            out[col] = _FILL
    dtype_map = dict.fromkeys(feature_cols, "float64")
    out = out.astype({k: v for k, v in dtype_map.items() if k in out.columns})
    out = out.replace([np.inf, -np.inf], _FILL)
    out[feature_cols] = out[feature_cols].fillna(_FILL)
    return out


def split_case_stratified(
    frame: pd.DataFrame, *, test_fraction: float = 0.2, seed: int = 42
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Case-aware split (never splits a case across folds)."""
    case_ids = sorted(set(frame["case_id"]))
    merged: list[str] = []
    for case_id in case_ids:
        merged.append(str(case_id))
    rng = np.random.default_rng(seed)
    rng.shuffle(merged)
    n_test = max(int(len(merged) * test_fraction), 1)
    test_cases = set(merged[:n_test])
    train = frame[~frame["case_id"].astype(str).isin(test_cases)].copy()
    test = frame[frame["case_id"].astype(str).isin(test_cases)].copy()
    return train, test


def make_scaler(X: np.ndarray) -> RobustScaler:
    scaler = RobustScaler(quantile_range=(10, 90))
    scaler.fit(X)
    return scaler


__all__ = ["make_scaler", "sanitize_frame", "split_case_stratified"]
