"""Geospatial helpers and the portable spatial-query layer.

The application stores latitude/longitude as indexed `float` columns **and**,
on PostgreSQL, a PostGIS ``geometry(Point,4326)`` column maintained by ORM
events.  Every spatial *query* is funnelled through this module so the same
code runs against:

- **PostGIS** - ST_Distance / ST_DWithin push work into the database (production)
- **SQLite**  - bounding-box pre-filter + haversine in Python (CI/tests)

The two backends never produce materially different *rankings*; the SQLite
path is an approximation used strictly for local development.
"""

from __future__ import annotations

import math
from typing import Any, Protocol, TypeVar

from sqlalchemy.dialects.postgresql import insert as pg_insert


class _LatLonColumns(Protocol):
    """Structural contract for ORM classes carrying lat/lon float columns."""

    latitude: Any
    longitude: Any


ModelT = TypeVar("ModelT", bound=_LatLonColumns)

EARTH_RADIUS_M = 6_371_000.0


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres (Haversine)."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    return haversine_m(lat1, lon1, lat2, lon2) / 1000.0


def bounding_box(center_lat: float, center_lon: float, radius_km: float) -> tuple[float, float, float, float]:
    """Approximate lat/lon bounding box for a radius (in degrees)."""
    dlat = radius_km / 111.0
    dlon = radius_km / (111.0 * max(math.cos(math.radians(center_lat)), 0.05))
    return (center_lat - dlat, center_lon - dlon, center_lat + dlat, center_lon + dlon)


def bbox_lat_lon_filter[ModelT: _LatLonColumns](
    query: Any,
    model: type[ModelT],
    *,
    min_lat: float | None = None,
    max_lat: float | None = None,
    min_lon: float | None = None,
    max_lon: float | None = None,
) -> Any:
    """Add an efficient, index-friendly bounding-box filter to a query."""
    if min_lat is not None:
        query = query.where(model.latitude >= min_lat)
    if max_lat is not None:
        query = query.where(model.latitude <= max_lat)
    if min_lon is not None:
        query = query.where(model.longitude >= min_lon)
    if max_lon is not None:
        query = query.where(model.longitude <= max_lon)
    return query


def point_from_latlon(lat: float, lon: float) -> Any:
    """Build a WKBElement for the PostGIS column (import cost deferred)."""
    from shapely.geometry import Point
    from sqlalchemy import func

    st_makepoint = getattr(func, "ST_MakePoint", None)
    if st_makepoint is not None:
        return st_makepoint(lon, lat, 4326)
    pt = Point(lon, lat)
    import geoalchemy2.elements as el

    return el.WKTElement(pt.wkt, srid=4326)


def force_postgis_column_update[ModelT: _LatLonColumns](
    model: type[ModelT],
    obj: Any,
    *,
    dialect_name: str,
    lon: float | None = None,
    lat: float | None = None,
) -> None:
    """Populate the PostGIS ``location`` column from lat/lon (ORM side effect).

    Called from an ORM ``before_insert``/``before_update`` listener only when
    the target database is PostgreSQL.
    """
    geo_col = getattr(model, "location", None)
    if geo_col is None or dialect_name in ("sqlite", "sqlite3"):
        return
    longitude = lon if lon is not None else getattr(obj, "longitude", None)
    latitude = lat if lat is not None else getattr(obj, "latitude", None)
    if longitude is None or latitude is None:
        return
    try:
        import geoalchemy2.elements as el
        from shapely.geometry import Point

        obj.location = el.WKTElement(Point(longitude, latitude).wkt, srid=4326)
    except Exception:  # pragma: no cover - defensive
        obj.location = None


def sqlite_dist_expr(lat1_col: Any, lon1_col: Any, lat2: float, lon2: float) -> Any:
    """SQLite approximation of distance (metres) for ORDER BY."""
    from sqlalchemy import func, literal

    # Haversine expressed in SQL terms (fixed point; usable in ORDER BY).
    to_rad = 3.141592653589793 / 180.0
    dlat = (lat1_col - literal(lat2)) * to_rad
    dlon = (lon1_col - literal(lon2)) * to_rad
    lat1r = lat1_col * to_rad
    lat2r = literal(lat2) * to_rad
    a = func.pow(func.sin(dlat / 2), 2) + func.cos(lat1r) * func.cos(lat2r) * func.pow(func.sin(dlon / 2), 2)
    return 2 * EARTH_RADIUS_M * func.atan2(func.sqrt(a), func.sqrt(1 - a))


def pg_upsert(statement: Any) -> Any:
    """Expose the PostgreSQL ``INSERT ... ON CONFLICT`` helper."""
    return pg_insert(statement)


__all__ = [
    "bbox_lat_lon_filter",
    "bounding_box",
    "distance_km",
    "force_postgis_column_update",
    "haversine_m",
    "pg_upsert",
    "point_from_latlon",
    "sqlite_dist_expr",
]
