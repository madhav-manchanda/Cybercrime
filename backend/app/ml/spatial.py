"""Spatial signals: kernel hotspot intensity, ATM density, distances."""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np
from numpy.typing import ArrayLike

EARTH_R = 6371.0
_HOTSPOT_BANDWIDTH_KM = 2.0
_DENSITY_RADIUS_KM = 4.0


def _haversine_km(lat1: np.ndarray, lon1: np.ndarray, lat2: float, lon2: float) -> np.ndarray:
    phi1 = np.radians(lat1)
    phi2 = np.radians(lat2)
    dphi = np.radians(lat2 - lat1)
    dlambda = np.radians(lon2 - lon1)
    a = np.sin(dphi / 2) ** 2 + np.cos(phi1) * np.cos(phi2) * np.sin(dlambda / 2) ** 2
    return 2 * EARTH_R * np.arcsin(np.clip(np.sqrt(a), 0.0, 1.0))


def hotspot_intensity(
    lat: float,
    lon: float,
    points_lat: ArrayLike,
    points_lon: ArrayLike,
    bandwidth_km: float = _HOTSPOT_BANDWIDTH_KM,
    weights: ArrayLike | None = None,
) -> float:
    """Weighted Gaussian-kernel density estimate at a query point."""
    lats = np.asarray(points_lat, dtype=float)
    lons = np.asarray(points_lon, dtype=float)
    if lats.size == 0 or lons.size == 0:
        return 0.0
    d = _haversine_km(lats, lons, lat, lon)
    kernel = np.exp(-((d / bandwidth_km) ** 2))
    if weights is not None:
        kernel = kernel * np.asarray(weights, dtype=float)
    value = float(np.sum(kernel))
    # normalise by a single point at zero distance == 1.0, capped for display
    return min(value, 20.0) / 20.0


def atm_density(
    lat: float,
    lon: float,
    atm_lats: Sequence[float],
    atm_lons: Sequence[float],
    radius_km: float = _DENSITY_RADIUS_KM,
) -> int:
    """Count of ATMs within ``radius_km`` (self-inclusive per caller input)."""
    if not atm_lats:
        return 0
    d = _haversine_km(
        np.asarray(atm_lats, dtype=float),
        np.asarray(atm_lons, dtype=float),
        lat,
        lon,
    )
    return int(np.sum(d <= radius_km))


def hotspot_peaks(
    points_lat: Sequence[float],
    points_lon: Sequence[float],
    *,
    grid_cell_km: float = 1.0,
) -> list[dict[str, float]]:
    """Coarse grid peak detection over points for map hot-spot rendering."""
    if len(points_lat) < 3:
        return []
    from app.core.geo import bounding_box

    min_lat, min_lon, max_lat, max_lon = bounding_box(
        float(np.mean(points_lat)), float(np.mean(points_lon)), 30.0
    )
    lat_steps = int((max_lat - min_lat) / grid_cell_km * 100) + 1
    lon_steps = int((max_lon - min_lon) / (grid_cell_km * 100)) + 1
    lat_steps = max(lat_steps, 1)
    lon_steps = max(lon_steps, 1)
    lat_bins = np.linspace(min_lat, max_lat, lat_steps)
    lon_bins = np.linspace(min_lon, max_lon, lon_steps)
    grid = np.zeros((lat_steps, lon_steps))
    # vectorised density computation over the grid
    lats = np.asarray(points_lat, dtype=float)
    lons = np.asarray(points_lon, dtype=float)
    for i in range(lat_steps):
        for j in range(lon_steps):
            grid[i, j] = hotspot_intensity(lat_bins[i], lon_bins[j], lats, lons, bandwidth_km=grid_cell_km)
    grid.flatten()
    local_max = (
        (grid >= np.roll(grid, 1, 0))
        & (grid >= np.roll(grid, -1, 0))
        & (grid >= np.roll(grid, 1, 1))
        & (grid >= np.roll(grid, -1, 1))
    )
    peaks = []
    for i in range(lat_steps):
        for j in range(lon_steps):
            if local_max[i, j] and grid[i, j] >= 0.25:
                peaks.append(
                    {
                        "latitude": float(lat_bins[i]),
                        "longitude": float(lon_bins[j]),
                        "intensity": round(min(float(grid[i, j]), 1.0), 4),
                    }
                )
    peaks.sort(key=lambda p: p["intensity"], reverse=True)
    # de-duplicate adjacent peaks
    kept: list[dict[str, float]] = []
    for peak in peaks:
        if any(
            math.hypot(peak["latitude"] - k["latitude"], peak["longitude"] - k["longitude"]) < 0.12
            for k in kept
        ):
            continue
        kept.append(peak)
        if len(kept) >= 10:
            break
    return kept[:10]


__all__ = [
    "atm_density",
    "hotspot_intensity",
    "hotspot_peaks",
]
