from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class Admin(BaseModel):
    """Admin user model for database storage"""
    user_id: str = Field(..., description="Unique admin user ID")
    email: str = Field(..., description="Admin email address")
    password_hash: str = Field(..., description="Hashed password")
    full_name: str = Field(..., description="Admin full name")
    role: str = Field(default="admin", description="User role")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_login: Optional[datetime] = Field(default=None, description="Last login timestamp")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
