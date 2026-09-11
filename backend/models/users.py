from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId
from pydantic import BaseModel, EmailStr, Field


class User(BaseModel):
    id: Optional[ObjectId] = Field(default=None, alias="_id")
    email: EmailStr
    username: str
    password: str
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    refresh_token: Optional[str] = None
