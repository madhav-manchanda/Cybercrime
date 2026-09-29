"""Utilities: masking / enum-norm helpers / sanity bounds."""

from __future__ import annotations

import pytest

from app.core.enums import CaseStatus, FraudType
from app.core.errors import BadRequestError
from app.core.security import mask, mask_email, mask_phone, mask_upi
from app.utils.validators import as_enum, as_str, bounded, validate_phone, validate_upi


def test_mask_keeps_tail() -> None:
    assert mask("9876543210", keep_last=4) == "******3210"


def test_mask_short_fully_hidden() -> None:
    assert mask("ab") == "**"


def test_mask_phone() -> None:
    assert mask_phone("+91 98765 43210") == "******3210"


def test_mask_email_keeps_domain() -> None:
    assert mask_email("alice@example.gov.in") == "a***e@example.gov.in"


def test_mask_upi() -> None:
    assert mask_upi("rajesh@okhdfcbank") == "raj***@okhdfcbank"


def test_validate_phone_normalises() -> None:
    assert validate_phone("+91-98765-43210") == "919876543210"


def test_validate_phone_rejects_short() -> None:
    with pytest.raises(BadRequestError):
        validate_phone("1234")


def test_validate_upi_lowercases() -> None:
    assert validate_upi("Raju@OKHDFCBANK") == "raju@okhdfcbank"


def test_as_enum_from_string() -> None:
    assert as_enum("UNDER_ANALYSIS", CaseStatus) is CaseStatus.UNDER_ANALYSIS


def test_as_enum_passthrough_enum() -> None:
    assert as_enum(CaseStatus.UNDER_ANALYSIS, CaseStatus) is CaseStatus.UNDER_ANALYSIS


def test_as_enum_unknown_raises() -> None:
    with pytest.raises(ValueError):
        as_enum("BOGUS", CaseStatus)


def test_as_str_from_enum() -> None:
    assert as_str(FraudType.UPI_FRAUD) == "UPI_FRAUD"


def test_as_str_from_string() -> None:
    assert as_str("UPI_FRAUD") == "UPI_FRAUD"


def test_bounded_in_range() -> None:
    assert bounded(5, 0.0, 10.0, "x") == 5.0


def test_bounded_rejects_out_of_range() -> None:
    with pytest.raises(BadRequestError):
        bounded(50, 0.0, 10.0, "x")


def test_bounded_rejects_non_numeric() -> None:
    with pytest.raises(BadRequestError):
        bounded("not-a-number", 0.0, 10.0, "x")