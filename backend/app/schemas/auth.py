from __future__ import annotations

from pydantic import BaseModel, Field


class RegisterAdminRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8, max_length=255)


class LoginRequest(BaseModel):
    username: str
    password: str


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str = Field(min_length=8, max_length=255)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    csrf_token: str


class UserResponse(BaseModel):
    id: str
    username: str
    is_admin: bool

    class Config:
        from_attributes = True
