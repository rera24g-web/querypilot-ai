"""Pydantic schemas for authentication endpoints."""
from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime


class UserCreate(BaseModel):
    """Schema for user registration."""
    email: EmailStr = Field(..., description="User's email address")
    password: str = Field(
        ...,
        min_length=8,
        max_length=128,
        description="Password (min 8 characters)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "email": "user@example.com",
                "password": "securepassword123"
            }
        }


class UserResponse(BaseModel):
    """Schema for user response (without sensitive data)."""
    id: str
    email: str
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class LoginRequest(BaseModel):
    """Schema for login request."""
    email: EmailStr = Field(..., description="User's email address")
    password: str = Field(..., description="Password")

    class Config:
        json_schema_extra = {
            "example": {
                "email": "user@example.com",
                "password": "securepassword123"
            }
        }


class TokenResponse(BaseModel):
    """Schema for successful login/registration response."""
    user: UserResponse
    message: str


class UserMeResponse(BaseModel):
    """Schema for /auth/me endpoint response."""
    id: str
    email: str
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class ErrorResponse(BaseModel):
    """Schema for error responses."""
    detail: str