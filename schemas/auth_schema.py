from pydantic import BaseModel, Field
from typing import Optional


class LoginRequest(BaseModel):
    """Login request schema"""
    email: str = Field(..., description="Admin email")
    password: str = Field(..., min_length=6, description="Admin password")


class CreateAdminRequest(BaseModel):
    """Create admin request schema with all fields"""
    email: str = Field(..., description="Admin email")
    password: str = Field(..., min_length=6, description="Admin password")
    full_name: str = Field(..., description="Admin full name")
    role: str = Field(default="admin", description="User role")


class LoginResponse(BaseModel):
    """Login response schema"""
    access_token: str = Field(..., description="JWT access token")
    token_type: str = Field(default="bearer", description="Token type")
    expires_in: int = Field(..., description="Token expiration in seconds")
    user_info: dict = Field(..., description="Basic user information")
    success: bool = Field(default=True, description="Login success status")
    message: str = Field(default="Login successful", description="Response message")


class TokenData(BaseModel):
    """Token payload schema"""
    user_id: str = Field(..., description="User ID from token")
    email: str = Field(..., description="Email from token")
    role: str = Field(..., description="User role")
    exp: int = Field(..., description="Token expiration timestamp")
