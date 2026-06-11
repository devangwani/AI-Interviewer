from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime


class UserBase(BaseModel):
    email: EmailStr
    display_name: Optional[str] = None
    photo_url: Optional[str] = None


class UserCreate(UserBase):
    firebase_uid: str


class UserInDB(UserBase):
    id: Optional[str] = Field(default=None, alias="_id")
    firebase_uid: str
    role: Optional[str] = None   # "candidate" | "recruiter" | None (unset = first login)
    role_switch_count: int = 0   # max 1 — one correction allowed
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {"populate_by_name": True}


class UserResponse(UserBase):
    id: str
    firebase_uid: str
    role: Optional[str] = None
    role_switch_count: int = 0
    created_at: datetime
