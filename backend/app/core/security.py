"""Security primitives: password hashing, JWT tokens, mask utilities.

This module exposes **no credentials of its own** - secrets come exclusively
from :mod:`app.core.config` (environment).  Never log objects returned here.
"""

from __future__ import annotations

import datetime as dt
import hmac
import uuid
from typing import Any, Literal

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from passlib.context import CryptContext

from app.core.config import settings
from app.core.errors import AuthenticationError

# ------------------------------------------------------------------ hashing

_argon2 = PasswordHasher(
    time_cost=settings.argon2_time_cost,
    memory_cost=settings.argon2_memory_cost,
    parallelism=settings.argon2_parallelism,
    hash_len=32,
    salt_len=16,
)

_bcrypt = CryptContext(schemes=["bcrypt"], bcrypt__rounds=settings.bcrypt_rounds)


def hash_password(plain: str) -> str:
    """Hash a password with the configured algorithm."""
    if settings.password_hash_algorithm.value == "argon2":
        return _argon2.hash(plain)
    return _bcrypt.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Safely verify a password against its stored hash."""
    try:
        if hashed.startswith("$argon2"):
            result = _argon2.verify(hashed, plain)
            if _argon2.check_needs_rehash(hashed):  # pragma: no cover
                # caller may re-hash; we just report success
                pass
            return result
        return bool(_bcrypt.verify(plain, hashed))
    except (VerificationError, InvalidHashError, ValueError):
        return False


# -------------------------------------------------------------------- JWT

_TOKEN_TYPE = Literal["access", "refresh"]


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def create_token(
    subject: str,
    token_type: _TOKEN_TYPE,
    *,
    role: str,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    """Issue a signed JWT.

    ``jti`` is a unique id so refresh tokens can be rotated/rejected.
    """
    now = _now()
    lifetime = (
        dt.timedelta(minutes=settings.access_token_expire_minutes)
        if token_type == "access"
        else dt.timedelta(days=settings.refresh_token_expire_days)
    )
    claims: dict[str, Any] = {
        "sub": str(subject),
        "typ": token_type,
        "role": role,
        "jti": str(uuid.uuid4()),
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": now,
        "exp": now + lifetime,
    }
    if extra_claims:
        claims.update(extra_claims)
    return jwt.encode(
        claims,
        settings.secret_key.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )


def decode_token(token: str, expected_type: _TOKEN_TYPE) -> dict[str, Any]:
    """Validate signature/expiry/issuer/type and return the claims.

    Raises :class:`AuthenticationError` with stable codes for every failure.
    """
    try:
        payload = jwt.decode(
            token,
            settings.secret_key.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
            options={"verify_exp": True, "require": ["sub", "exp", "iat", "jti"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise AuthenticationError("Access token has expired.", code="TOKEN_EXPIRED") from exc
    except jwt.InvalidAudienceError as exc:
        raise AuthenticationError("Invalid token audience.", code="TOKEN_INVALID") from exc
    except jwt.InvalidIssuerError as exc:
        raise AuthenticationError("Invalid token issuer.", code="TOKEN_INVALID") from exc
    except jwt.InvalidTokenError as exc:
        raise AuthenticationError("Invalid or malformed token.", code="TOKEN_INVALID") from exc

    if payload.get("typ") != expected_type:
        raise AuthenticationError("Unexpected token type.", code="TOKEN_TYPE_MISMATCH")
    return payload


# ------------------------------------------------------------- security
def constant_time_compare(a: str, b: str) -> bool:
    """Constant-time string comparison."""
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def generate_refresh_token_hash(refresh_token: str) -> str:
    """Stable identifier used to revoke/rotate refresh tokens."""
    from app.utils.hashing import sha256_hex

    return sha256_hex(refresh_token)


# --------------------------------------------------------------- masking
def mask(value: str | None, keep_last: int = 4, placeholder: str = "*") -> str:
    """Mask ``value`` showing the last ``keep_last`` characters.

    ``123456789012`` -> ``********9012`` ; short strings are fully masked.
    """
    if not value:
        return ""
    if len(value) <= keep_last:
        return placeholder * len(value)
    return placeholder * (len(value) - keep_last) + value[-keep_last:]


def mask_phone(value: str | None) -> str:
    """Mask a phone number keeping the last 4 digits: ``******1234``."""
    if not value:
        return ""
    digits = "".join(ch for ch in value if ch.isdigit())
    if not digits:
        return mask(value)
    return "*" * 6 + digits[-4:]


def mask_email(value: str | None) -> str:
    """Mask an email keeping the domain and first character."""
    if not value or "@" not in value:
        return mask(value)
    local, domain = value.split("@", 1)
    if len(local) <= 2:
        local_masked = "*"
    else:
        local_masked = local[0] + "*" * (len(local) - 2) + local[-1]
    return f"{local_masked}@{domain}"


def mask_upi(value: str | None) -> str:
    """Mask a UPI id: ``raj****@okhdfcbank``."""
    if not value or "@" not in value:
        return mask(value)
    local, handle = value.split("@", 1)
    return f"{local[:3]}{'*' * max(len(local) - 3, 1)}@{handle}"


__all__ = [
    "constant_time_compare",
    "create_token",
    "decode_token",
    "generate_refresh_token_hash",
    "hash_password",
    "mask",
    "mask_email",
    "mask_phone",
    "mask_upi",
    "verify_password",
]
