"""Temporal modelling: withdrawal-hour distributions and time windows.

The temporal component learns the *when* of cash-outs from historical
withdrawal timestamps belonging to entities associated with a case, then maps
the predicted window onto candidate ATMs.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import numpy as np

HOUR_BINS = 24


@dataclass
class WithdrawalTimeProfile:
    """A temporal distribution of cash-out activity."""

    hour_weights: np.ndarray = field(default_factory=lambda: np.ones(HOUR_BINS) / HOUR_BINS)
    day_weights: np.ndarray = field(default_factory=lambda: np.ones(7) / 7)
    n_samples: int = 0


def _hour_weights(hours: Sequence[int], *, sigma_hours: float = 2.0) -> np.ndarray:
    """Smooth histogram of hours-of-day using a wrapped Gaussian kernel."""
    weights = np.zeros(HOUR_BINS)
    hours = list(hours)
    if not hours:
        return np.ones(HOUR_BINS) / HOUR_BINS
    for h in hours:
        weights[np.arange(HOUR_BINS)] += np.exp(-((np.arange(HOUR_BINS) - h) ** 2) / (2.0 * sigma_hours**2))
    # circular smooth (wrap)
    weights = weights + np.roll(weights, 1) * 0.25 + np.roll(weights, -1) * 0.25
    total = weights.sum()
    return weights / total if total > 0 else np.ones(HOUR_BINS) / HOUR_BINS


def _day_weights(days: Sequence[int]) -> np.ndarray:
    weights = np.zeros(7)
    for d in days:
        weights[d % 7] += 1.0
    total = weights.sum()
    return weights / total if total > 0 else np.ones(7) / 7


def build_profile(
    timestamps: Sequence[datetime],
    *,
    reference: datetime | None = None,
    half_life_days: float = 90.0,
) -> WithdrawalTimeProfile:
    """Build a decaying-memory temporal profile from historical timestamps."""
    if not timestamps:
        return WithdrawalTimeProfile()
    reference = reference or datetime.now(UTC)
    hours: list[int] = []
    days: list[int] = []
    for ts in timestamps:
        if ts is None:
            continue
        hours.append(ts.hour)
        days.append(ts.weekday())
    return WithdrawalTimeProfile(
        hour_weights=_hour_weights(hours),
        day_weights=_day_weights(days),
        n_samples=len(hours),
    )


@dataclass
class PredictedWindow:
    """Highest-density continuous window from an hourly distribution."""

    start: datetime
    end: datetime
    peak_hour: int
    coverage: float  # fraction of probability mass inside the window
    density: float = 0.0


def predict_time_window(
    profile: WithdrawalTimeProfile,
    *,
    reference: datetime,
    horizon_hours: int = 24,
    recent_velocity_hours: float | None = None,
    window_span_hours: int = 6,
) -> PredictedWindow:
    """Pick the highest-density ``window_span_hours`` inside the horizon.

    When a recent transaction burst is detected (short inter-transaction gap)
    the window is shifted earlier to reflect faster cash-out cadence.
    """
    weights = profile.hour_weights
    span = min(window_span_hours, HOUR_BINS)
    best_start = 0
    best_energy = -1.0
    for candidate_start in range(HOUR_BINS):
        cand_end = candidate_start + span
        if cand_end <= HOUR_BINS:
            energy = float(weights[candidate_start:cand_end].sum())
        else:
            energy = float(weights[candidate_start:].sum() + weights[: cand_end - HOUR_BINS].sum())
        if energy > best_energy:
            best_energy = energy
            best_start = candidate_start

    coverage = min(best_energy, 1.0)

    # temporal bias: shuffle window forward when velocity is high
    bias_hours = 0.0
    if recent_velocity_hours is not None and recent_velocity_hours > 1.0:
        bias_hours = min(6.0, recent_velocity_hours)

    center_hour_local = (best_start + span / 2.0) % 24
    start_dt = _align_to_hour(reference) + timedelta(hours=bias_hours)
    candidate = start_dt.replace(hour=int(center_hour_local) % 24, minute=0, second=0, microsecond=0)
    if candidate < start_dt:
        candidate = candidate + timedelta(days=1)
    start: datetime = candidate
    end_dt: datetime = start + timedelta(hours=span)

    # cap within horizon
    horizon_end = start_dt + timedelta(hours=horizon_hours)
    if end_dt > horizon_end:
        end_dt = horizon_end
        start = end_dt - timedelta(hours=span)
        if start < start_dt:
            start = start_dt

    return PredictedWindow(
        start=start,
        end=end_dt,
        peak_hour=int(center_hour_local) % 24,
        coverage=coverage,
        density=best_energy / span,
    )


def _align_to_hour(dt: datetime) -> datetime:
    return dt.replace(minute=0, second=0, microsecond=0)


def temporal_similarity(
    profile: WithdrawalTimeProfile,
    atm_hour_of_day: float | None,
    *,
    isotonic: bool = True,
) -> float:
    """Probability density at the ATM's typical withdrawal hour."""
    if atm_hour_of_day is None:
        return 0.5
    hour = int(atm_hour_of_day) % 24
    density = float(profile.hour_weights[hour])
    if isotonic:
        # scale [0,max] to [0,1] opinionatedly for interpretability
        density /= float(profile.hour_weights.max()) if profile.hour_weights.max() > 0 else 1.0
    return min(1.0, max(0.0, density))


__all__ = [
    "PredictedWindow",
    "WithdrawalTimeProfile",
    "build_profile",
    "predict_time_window",
    "temporal_similarity",
]
