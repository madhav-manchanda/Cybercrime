"""Input validation helpers reused across services and routes."""

from __future__ import annotations

import ipaddress
import re
from datetime import UTC, datetime
from typing import Any

from app.core.errors import BadRequestError

_PHONE_RE = re.compile(r"^\+?[0-9\- ]{8,20}$")
_UPI_RE = re.compile(r"^[a-zA-Z0-9._\-]{2,120}@[a-zA-Z]{2,60}$")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def validate_phone(phone: str) -> str:
    """Return the digits-only normalised phone or raise."""
    digits = "".join(c for c in phone if c.isdigit())
    if not _PHONE_RE.match(phone) or len(digits) < 10:
        raise BadRequestError("Invalid phone number.", code="INVALID_PHONE")
    return digits


def validate_upi(upi: str) -> str:
    if not _UPI_RE.match(upi):
        raise BadRequestError("Invalid UPI identifier.", code="INVALID_UPI")
    return upi.lower()


def validate_email(email: str) -> str:
    if not _EMAIL_RE.match(email):
        raise BadRequestError("Invalid email address.", code="INVALID_EMAIL")
    return email.lower()


def validate_ip(address: str) -> str:
    try:
        return str(ipaddress.ip_address(address.strip()))
    except ValueError as exc:
        raise BadRequestError("Invalid IP address.", code="INVALID_IP") from exc


def utc_aware(value: datetime) -> datetime:
    """Normalise a datetime to UTC-aware (naive values treated as UTC)."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def ensure_iso8601(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise BadRequestError("Invalid timestamp. Expected ISO-8601.", code="INVALID_TIMESTAMP") from exc
    return utc_aware(parsed)


def bounded(value: Any, minimum: float, maximum: float, field: str) -> float:
    """Sanity bound for monetary values."""
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise BadRequestError(f"{field} must be numeric.", code="INVALID_NUMBER") from exc
    if not minimum <= number <= maximum:
        raise BadRequestError(f"{field} must be between {minimum} and {maximum}.", code="OUT_OF_RANGE")
    return number


def non_empty(value: str, field: str, *, max_len: int = 1000) -> str:
    cleaned = (value or "").strip()
    if not cleaned:
        raise BadRequestError(f"{field} must not be empty.", code="EMPTY_VALUE")
    if len(cleaned) > max_len:
        raise BadRequestError(f"{field} is longer than {max_len} characters.", code="TOO_LONG")
    return cleaned


def page_params(page: int, page_size: int, *, max_size: int = 100) -> tuple[int, int]:
    page = max(page, 1)
    page_size = max(min(page_size, max_size), 1)
    return page, page_size


__all__ = [
    "as_enum",
    "as_str",
    "bounded",
    "ensure_iso8601",
    "non_empty",
    "page_params",
    "utc_aware",
    "validate_email",
    "validate_ip",
    "validate_phone",
    "validate_upi",
]


def as_enum(value: Any, enum_type: type) -> Any:
    """Coerce a schema field into its declared enum.

    Schemas sometimes flatten enums into plain strings (``use_enum_values``);
    services rely on real enum objects for ``.value`` access.  No-op when the
    value already is an instance of ``enum_type``.
    """
    return enum_type(value) if isinstance(value, str) else value


def as_str(value: Any) -> str:
    """Return the persisted string form of an enum-like value."""
    return getattr(value, "value", value)
