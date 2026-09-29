"""Shared Pydantic schemas: pagination, envelope, geo primitives."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.enums import DataSource

T = TypeVar("T")


class ORMModel(BaseModel):
    """Base for schemas assembled from ORM objects (id + timestamps)."""

    model_config = ConfigDict(from_attributes=True, use_enum_values=True)

    id: uuid.UUID
    created_at: datetime
    updated_at: datetime | None = None


class WritableModel(BaseModel):
    """Base for request payloads; enums are *validated* and kept as enums."""

    model_config = ConfigDict(use_enum_values=True)


class ErrorDetail(BaseModel):
    code: str
    message: str
    request_id: str = ""
    details: dict[str, Any] | None = None


class ErrorEnvelope(BaseModel):
    error: ErrorDetail


class Page[T](BaseModel):
    """Standard paginated response envelope."""

    items: list[T]
    total: int
    page: int
    page_size: int
    pages: int
    has_next: bool


class GeoPoint(BaseModel):
    """Latitude/longitude pair used across request payloads."""

    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)

    @field_validator("latitude", "longitude")
    @classmethod
    def _finite(cls, v: float) -> float:
        if v != v or v in (float("inf"), float("-inf")):
            raise ValueError("coordinates must be finite")
        return v


class BoundingBox(BaseModel):
    min_lat: float = Field(ge=-90, le=90)
    max_lat: float = Field(ge=-90, le=90)
    min_lon: float = Field(ge=-180, le=180)
    max_lon: float = Field(ge=-180, le=180)

    @field_validator("max_lat")
    @classmethod
    def _lat_ordering(cls, v: float, info: Any) -> float:
        min_lat = info.data.get("min_lat")
        if min_lat is not None and v < min_lat:
            raise ValueError("max_lat must be >= min_lat")
        return v

    @field_validator("max_lon")
    @classmethod
    def _lon_ordering(cls, v: float, info: Any) -> float:
        min_lon = info.data.get("min_lon")
        if min_lon is not None and v < min_lon:
            raise ValueError("max_lon must be >= min_lon")
        return v


class TimeWindow(BaseModel):
    start: datetime | None = None
    end: datetime | None = None


class TimeWindowBound(BaseModel):
    start: datetime
    end: datetime


class Provenance(BaseModel):
    """Read-only provenance marker attached to generated records."""

    data_source: DataSource = DataSource.SYNTHETIC


class FactorContribution(BaseModel):
    """One explainability factor with its signed impact."""

    factor: str
    impact: float = Field(ge=-1.0, le=1.0)
    details: str | None = None


class Message(BaseModel):
    message: str
    detail: str | None = None


__all__ = [
    "BoundingBox",
    "DataSource",
    "ErrorDetail",
    "ErrorEnvelope",
    "FactorContribution",
    "GeoPoint",
    "ORMModel",
    "Page",
    "Provenance",
    "TimeWindow",
    "TimeWindowBound",
    "WritableModel",
]
