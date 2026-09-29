"""Feature engineering for cash-out candidate ranking.

Everything here is a **pure function** over a :class:`FeatureBundle` so the
spatio-temporal-network-financial feature pipeline can be unit tested without a
database.  The bundle is assembled by :func:`build_case_bundle` inside
:class:`app.services.prediction_service`.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd

from app.ml.graph_features import CaseNetworkFeatures
from app.ml.spatial import atm_density, hotspot_intensity
from app.ml.temporal import WithdrawalTimeProfile, temporal_similarity
from app.utils.geo import distance_km

_SENTINEL = -999.0

# Default coupling decline distance for anchors / cash-out halos.
_ANCHOR_SCALE_KM = 3.0
_CASHOUT_SCALE_KM = 5.0


@dataclass
class AnchorPoint:
    """A geo point where case activity concentrates."""

    lat: float
    lon: float
    weight: float = 1.0
    kind: str = "transaction"


@dataclass
class HistoricalCashout:
    lat: float
    lon: float
    amount: float
    timestamp: datetime
    linked: bool = True
    atm_id: str | None = None


@dataclass
class CandidateAtm:
    atm_id: str
    code: str
    name: str
    latitude: float
    longitude: float
    bank_name: str | None = None
    is_csp: bool = False
    base_load: float = 0.5
    monthly_withdrawals: int = 0
    zone_type: str | None = None
    typical_withdrawal_hour: float | None = None
    historical_withdrawals: list[HistoricalCashout] = field(default_factory=list)
    network_link_count: int = 0


@dataclass
class FeatureBundle:
    """Per-case context used to score every candidate ATM."""

    case_id: str
    anchor_points: list[AnchorPoint] = field(default_factory=list)
    historical_cashouts: list[HistoricalCashout] = field(default_factory=list)
    temporal_profile: WithdrawalTimeProfile = field(default_factory=WithdrawalTimeProfile)
    network: CaseNetworkFeatures = field(default_factory=CaseNetworkFeatures)
    case_amount_features: dict[str, float] = field(default_factory=dict)
    predicted_window_start: datetime | None = None
    predicted_window_end: datetime | None = None
    reference_time: datetime | None = None
    warnings: list[str] = field(default_factory=list)


def _attraction(
    points: Sequence[AnchorPoint] | Sequence[HistoricalCashout],
    lat: float,
    lon: float,
    scale_km: float,
    *,
    weight_attr: str | None = None,
) -> float:
    """Attention-weighted decaying influence of all points on a candidate."""
    acc = 0.0
    wsum = 0.0
    for point in points:
        if weight_attr:
            weight = getattr(point, weight_attr, 1.0)
        else:
            weight = getattr(point, "weight", 1.0)
        d = distance_km(point.lat, point.lon, lat, lon)
        w = max(0.0, np.exp(-((d / scale_km) ** 2)))
        acc += weight * w
        wsum += abs(weight)
    return float(acc / max(wsum, 1e-9))


def _nearest_distance(
    lat: float, lon: float, points: Sequence[Any], attr_lat: str = "lat", attr_lon: str = "lon"
) -> float:
    if not points:
        return _SENTINEL
    return min(distance_km(getattr(p, attr_lat), getattr(p, attr_lon), lat, lon) for p in points)


class FeatureResolver:
    """Resolves spatial features given a bundle and a candidate set."""

    def __init__(self, bundle: FeatureBundle, candidates: list[CandidateAtm]) -> None:
        self.bundle = bundle
        self.candidates = candidates
        self._atm_lats = [
            c.latitude for c in candidates if c.latitude is not None and c.longitude is not None
        ]
        self._atm_lons = [
            c.longitude for c in candidates if c.latitude is not None and c.longitude is not None
        ]

    def vector(self, atm: CandidateAtm) -> dict[str, float]:
        b = self.bundle
        lat, lon = atm.latitude, atm.longitude
        if lat is None or lon is None:
            missing_row = dict.fromkeys(feature_columns(), _SENTINEL)
            return missing_row

        case_lat = self._case_lat()
        case_lon = self._case_lon()

        anchor_attraction = _attraction(b.anchor_points, lat, lon, _ANCHOR_SCALE_KM, weight_attr="weight")
        cashout_attraction = _attraction(
            b.historical_cashouts, lat, lon, _CASHOUT_SCALE_KM, weight_attr="amount"
        )
        dist_nearest_anchor = _nearest_distance(lat, lon, b.anchor_points)
        dist_case = (
            distance_km(case_lat, case_lon, lat, lon)
            if case_lat is not None and case_lon is not None
            else _SENTINEL
        )
        dist_cashout = _nearest_distance(lat, lon, b.historical_cashouts, attr_lat="lat", attr_lon="lon")

        hist_wd = atm.historical_withdrawals
        hist_signal = sum(min(c.amount / 10_000.0, 1.0) for c in hist_wd) / 5.0
        temporal = temporal_similarity(b.temporal_profile, atm.typical_withdrawal_hour)

        net = b.network
        row: dict[str, float] = {
            "dist_to_case_km": dist_case,
            "dist_to_nearest_anchor_km": dist_nearest_anchor,
            "anchor_attraction": anchor_attraction,
            "dist_to_cashout_km": dist_cashout,
            "cashout_attraction": cashout_attraction,
            "hotspot_intensity": hotspot_intensity(lat, lon, *(self._case_points())),
            "atm_density_4km": atm_density(lat, lon, self._atm_lats, self._atm_lons, 4.0),
            "hist_cashout_signal": min(hist_signal, 1.0),
            "hist_cashout_count": len(hist_wd),
            "hist_cashout_amount": sum(c.amount for c in hist_wd) / 1000.0,
            "is_withdrawal_atm": 1.0 if len(hist_wd) > 0 else 0.0,
            "temporal_similarity": temporal,
            "cashout_window_hour": (b.predicted_window_start.hour if b.predicted_window_start else _SENTINEL),
            "net_entity_count": net.entity_count,
            "net_relationship_count": net.relationship_count,
            "net_mule_count": net.mule_count,
            "net_avg_degree": net.avg_degree,
            "net_risky_edge_ratio": net.risky_edge_ratio,
            "net_suspicious_cluster_size": net.suspicious_cluster_size,
            "atm_network_link_count": atm.network_link_count,
            "atm_is_csp": 1.0 if atm.is_csp else 0.0,
            "atm_base_load": atm.base_load,
            "atm_monthly_withdrawals": atm.monthly_withdrawals / 1000.0,
            "zone_business": 1.0 if (atm.zone_type or "city") in {"city", "commercial", "business"} else 0.0,
            "zone_rural": 1.0 if atm.zone_type == "rural" else 0.0,
        }
        row.update(
            {f"case_{k}": float(v) for k, v in b.case_amount_features.items() if isinstance(v, (int, float))}
        )
        return row

    def _case_points(self) -> tuple[list[float], list[float]]:
        pool: list[tuple[float, float]] = []
        for a in self.bundle.anchor_points:
            pool.append((a.lat, a.lon))
        for c in self.bundle.historical_cashouts:
            pool.append((c.lat, c.lon))
        if not pool:
            lat = self._case_lat()
            lon = self._case_lon()
            if lat is not None and lon is not None:
                pool.append((lat, lon))
        lats = [p[0] for p in pool] or [0.0]
        lons = [p[1] for p in pool] or [0.0]
        return lats, lons

    def _case_lat(self) -> float | None:
        for a in self.bundle.anchor_points:
            if a.kind == "case":
                return a.lat
        return self.bundle.anchor_points[0].lat if self.bundle.anchor_points else None

    def _case_lon(self) -> float | None:
        for a in self.bundle.anchor_points:
            if a.kind == "case":
                return a.lon
        return self.bundle.anchor_points[0].lon if self.bundle.anchor_points else None


def feature_columns() -> list[str]:
    """Canonical ordered feature names (must match persisted manifests)."""
    base = [
        "dist_to_case_km",
        "dist_to_nearest_anchor_km",
        "anchor_attraction",
        "dist_to_cashout_km",
        "cashout_attraction",
        "hotspot_intensity",
        "atm_density_4km",
        "hist_cashout_signal",
        "hist_cashout_count",
        "hist_cashout_amount",
        "is_withdrawal_atm",
        "temporal_similarity",
        "cashout_window_hour",
        "net_entity_count",
        "net_relationship_count",
        "net_mule_count",
        "net_avg_degree",
        "net_risky_edge_ratio",
        "net_suspicious_cluster_size",
        "atm_network_link_count",
        "atm_is_csp",
        "atm_base_load",
        "atm_monthly_withdrawals",
        "zone_business",
        "zone_rural",
    ]
    case_feats = [
        "case_" + c
        for c in [
            "transaction_count",
            "total_amount",
            "mean_amount",
            "max_amount",
            "std_amount",
            "amount_deviation_ratio",
            "velocity_per_hour",
            "time_span_hours",
            "withdrawal_count",
            "withdrawal_total",
            "withdrawal_mean_amount",
            "hours_since_last_txn",
            "distinct_dest",
            "distinct_src",
        ]
    ]
    return base + case_feats


def build_feature_matrix(
    bundle: FeatureBundle, candidates: list[CandidateAtm]
) -> tuple[pd.DataFrame, FeatureResolver]:
    """Return a DataFrame of feature rows for the candidate set."""
    resolver = FeatureResolver(bundle, candidates)
    rows: list[dict[str, Any]] = []
    for atm in candidates:
        rows.append({"atm_id": atm.atm_id, **resolver.vector(atm)})
    df = pd.DataFrame(rows)
    # make sure missing columns are materialised so train/predict agree
    for col in feature_columns():
        if col not in df.columns:
            df[col] = _SENTINEL
    df = df[["atm_id", *feature_columns()]]
    return df, resolver


def component_scores(row: pd.Series | dict[str, float]) -> dict[str, float]:
    """Decay-style interpretable sub-scores (0..1) for the hybrid model.

    These are the *model components*:

    - ``spatial``   : proximity to case + anchor/cash-out attracration
    - ``temporal``  : overlap with the learned cash-out time profile
    - ``network``   : structural risk of the case graph + ATM linkage
    - ``historical``: prior cash-out signal at this exact ATM
    """

    def get(k: str, default: float = 0.0) -> float:
        if isinstance(row, pd.Series):
            if k not in row.index or pd.isna(row[k]):
                return default
            return float(row[k])
        value = row.get(k, default)
        return default if value is None else float(value)

    anchor = clip01(get("anchor_attraction"))
    cashout = clip01(get("cashout_attraction"))
    hotspot = clip01(get("hotspot_intensity"))
    spatial = clip01(0.45 * anchor + 0.35 * cashout + 0.20 * hotspot)

    historical = clip01(0.6 * get("hist_cashout_signal") + 0.4 * min(get("hist_cashout_count") / 4.0, 1.0))
    temporal = clip01(get("temporal_similarity"))

    risky = clip01(get("net_risky_edge_ratio"))
    mule = clip01(get("net_mule_count") / 5.0)
    cluster = clip01(get("net_suspicious_cluster_size") / 10.0)
    atm_link = clip01(get("atm_network_link_count") / 3.0)
    network = clip01(0.4 * risky + 0.3 * mule + 0.2 * cluster + 0.1 * atm_link)
    return {"spatial": spatial, "temporal": temporal, "network": network, "historical": historical}


def clip01(x: float) -> float:
    return float(max(0.0, min(1.0, x)))


__all__ = [
    "AnchorPoint",
    "CandidateAtm",
    "FeatureBundle",
    "FeatureResolver",
    "HistoricalCashout",
    "build_feature_matrix",
    "component_scores",
    "feature_columns",
]
