"""Shared ORM mixins: UUID PKs, audit timestamps, GeoPoint columns."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from geoalchemy2 import Geometry
from sqlalchemy import DateTime, Float, String, event, inspect
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.core.config import settings
from app.core.geo import force_postgis_column_update


def utcnow() -> datetime:
    return datetime.now(UTC)


class UUIDPrimaryKeyMixin:
    """UUID primary key with a server-side-safe default."""

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4, index=True)


class TimestampMixin:
    """created_at / updated_at maintained by the ORM."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class GeoPointMixin:
    """Latitude/longitude columns plus an optional PostGIS point.

    ``location`` is populated through ``before_insert``/``before_update``
    listeners **only when the dialect is PostgreSQL** (see
    :func:`app.core.database.is_postgres`).  On SQLite-based test setups it
    stays ``NULL`` and the float columns are the source of truth.
    """

    latitude: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)

    #: PostGIS geometry(Point, 4326) with a GiST index (production backend).
    #: On SQLite the column degrades to a plain string carrier so DDL and the
    #: GeoAlchemy2 metadata-recovery statements do not break local dev.
    location: Mapped[object | None] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326, spatial_index=True)
        if (settings.async_database_url or "").startswith("postgresql")
        else String(64),
        nullable=True,
    )


def install_geo_listeners(
    mapper: type,
    *,
    lat_attr: str = "latitude",
    lon_attr: str = "longitude",
    geo_attr: str = "location",
) -> None:
    """Bind the lat/lon -> PostGIS-point population events to an ORM class.

    Examples of use: ``install_geo_listeners(AtmLocation)`` after the class is
    defined; harmless on SQLite.
    """

    def _sync(mapper_cls: type, connection, target: object) -> None:
        dialect = getattr(connection, "dialect", None)
        dialect_name = getattr(dialect, "name", "") if dialect is not None else ""
        lat = getattr(target, lat_attr, None)
        lon = getattr(target, lon_attr, None)
        force_postgis_column_update(
            mapper_cls,
            target,
            dialect_name=dialect_name,
            lat=lat,
            lon=lon,
        )

    event.listen(mapper, "before_insert", _sync)
    event.listen(mapper, "before_update", _sync)


def has_geo_dialect(connection: object) -> bool:
    dialect = getattr(getattr(connection, "dialect", None), "name", "")
    return dialect.startswith("postgresql")


class JSONTypeMixin:
    """No-op marker: imported at model level for readability."""


def model_table_name(cls: type) -> str:
    """Return the actual table name for an ORM class (useful in listeners)."""
    return str(inspect(cls).local_table)  # type: ignore[union-attr]


__all__ = [
    "GeoPointMixin",
    "JSONTypeMixin",
    "TimestampMixin",
    "UUIDPrimaryKeyMixin",
    "has_geo_dialect",
    "install_geo_listeners",
    "model_table_name",
    "utcnow",
]
