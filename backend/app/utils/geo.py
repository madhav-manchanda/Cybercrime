"""Geospatial utilities shared by services and the geospatial API."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.geo import bbox_lat_lon_filter, bounding_box, distance_km
from app.models import AtmLocation


def geojson_point(lat: float | None, lon: float | None, properties: dict[str, Any]) -> dict[str, Any]:
    """Build a GeoJSON Feature, skipping empty geometry."""
    if lat is None or lon is None:
        return {"type": "Feature", "geometry": {"type": "Point", "coordinates": []}, "properties": properties}
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
        "properties": properties,
    }


def geojson_feature_collection(
    features: list[dict[str, Any]], meta: dict[str, Any] | None = None
) -> dict[str, Any]:
    return {
        "type": "FeatureCollection",
        "features": features,
        "meta": meta or {},
    }


def nearest_atms(
    session: Session,
    lat: float,
    lon: float,
    *,
    radius_km: float,
    limit: int = 50,
    exclude_ids: list[Any] | None = None,
) -> list[tuple[AtmLocation, float]]:
    """Return up to ``limit`` ATMs within ``radius_km`` sorted by distance.

    Uses a bounding-box pre-filter (index friendly) followed by an exact
    haversine pass. The bbox filter is what keeps the query cheap on both
    PostgreSQL and SQLite.
    """
    query = bbox_lat_lon_filter(
        session.query(AtmLocation),
        AtmLocation,
        min_lat=bounding_box(lat, lon, radius_km)[0],
        max_lat=bounding_box(lat, lon, radius_km)[2],
        min_lon=bounding_box(lat, lon, radius_km)[1],
        max_lon=bounding_box(lat, lon, radius_km)[3],
    ).filter(AtmLocation.latitude.is_not(None), AtmLocation.longitude.is_not(None))
    if exclude_ids:
        query = query.filter(AtmLocation.id.not_in(exclude_ids))

    candidates = query.limit(max(limit * 8, 2000)).all()
    result: list[tuple[AtmLocation, float]] = []
    for atm in candidates:
        d = atm_distance_km(atm, lat, lon)
        if d <= radius_km:
            result.append((atm, d))
    result.sort(key=lambda item: item[1])
    return result[:limit]


def atm_distance_km(atm: AtmLocation, lat: float, lon: float) -> float:
    if atm.latitude is None or atm.longitude is None:
        return float("inf")
    return distance_km(atm.latitude, atm.longitude, lat, lon)


__all__ = [
    "atm_distance_km",
    "geojson_feature_collection",
    "geojson_point",
    "nearest_atms",
]
