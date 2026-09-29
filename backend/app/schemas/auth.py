"""Authentication & user schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.core.enums import RoleName
from app.schemas.common import ORMModel


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=2, max_length=160)
    role: RoleName | None = None  # only ADMIN may set a role at registration

    @field_validator("password")
    @classmethod
    def _password_strength(cls, v: str) -> str:
        if not any(ch.islower() for ch in v) or not any(ch.isupper() for ch in v):
            raise ValueError("password must contain upper and lower case letters")
        if not any(ch.isdigit() for ch in v):
            raise ValueError("password must contain at least one digit")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    client_platform: str | None = Field(default=None, max_length=200)


class RefreshRequest(BaseModel):
    refresh_token: str


class Tokens(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int


class RoleSchema(ORMModel):
    name: RoleName
    description: str | None = None
    permissions: list[str] = Field(default_factory=list)


class UserRole(BaseModel):
    model_config = ConfigDict(from_attributes=True, use_enum_values=True)

    name: str
    permissions: list[str]


class UserOut(BaseModel):
    """Public user view (never includes hashed credentials)."""

    model_config = ConfigDict(from_attributes=True, use_enum_values=True)

    id: uuid.UUID
    email: EmailStr
    full_name: str
    is_active: bool
    is_verified: bool
    last_login_at: datetime | None = None
    created_at: datetime
    role: UserRole


class UserMe(UserOut):
    pass


class AssignRoleRequest(BaseModel):
    role: RoleName


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)

    @model_validator(mode="after")
    def _different(self) -> ChangePasswordRequest:
        if self.current_password == self.new_password:
            raise ValueError("new password must differ from current password")
        return self


class LogoutRequest(BaseModel):
    refresh_token: str


__all__ = [
    "AssignRoleRequest",
    "ChangePasswordRequest",
    "LoginRequest",
    "LogoutRequest",
    "RefreshRequest",
    "RegisterRequest",
    "RoleSchema",
    "Tokens",
    "UserMe",
    "UserOut",
]
