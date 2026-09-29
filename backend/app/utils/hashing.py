"""Deterministic hashing helpers for entity resolution and audit chaining."""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any


def sha256_hex(data: str | bytes = "", *, binary: bytes | None = None) -> str:
    """Hex-encoded SHA-256 of a string or raw bytes."""
    if binary is not None:
        return hashlib.sha256(binary).hexdigest()
    if isinstance(data, bytes):
        return hashlib.sha256(data).hexdigest()
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def canonical_json(obj: Any) -> str:
    """Deterministic JSON serialisation (stable ordering) for hashing."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def hmaci(key: str, message: str) -> str:
    """Hex HMAC-SHA256 over message using key (for opaque identifiers)."""
    return hmac.new(key.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).hexdigest()


def account_hash(account_number: str, salt: str) -> str:
    """Hash an account number so plaintext is never stored."""
    return sha256_hex(f"acct:{account_number.strip()}:{salt}")


def phone_hash(phone: str, salt: str) -> str:
    """Hash a phone number for deterministic entity resolution."""
    digits = "".join(c for c in phone if c.isdigit())
    return sha256_hex(f"phone:{digits}:{salt}")


def upi_hash(upi: str, salt: str) -> str:
    return sha256_hex(f"upi:{upi.strip().lower()}:{salt}")


def device_hash(fingerprint: str, salt: str) -> str:
    return sha256_hex(f"device:{fingerprint.strip()}:{salt}")


def audit_chain_hash(event_payload: dict[str, Any], prev_hash: str | None) -> str:
    """Compute the hash-chaining record hash for the audit log.

    ``hash = SHA256(canonical(event_payload) || prev_hash)``
    """
    body = canonical_json(event_payload) + (prev_hash or "")
    return sha256_hex(body)


__all__ = [
    "account_hash",
    "audit_chain_hash",
    "canonical_json",
    "device_hash",
    "hmaci",
    "phone_hash",
    "sha256_hex",
    "upi_hash",
]
