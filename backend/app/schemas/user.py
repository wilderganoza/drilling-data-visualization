from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=100)
    password: str = Field(..., min_length=6)
    full_name: Optional[str] = None
    email: Optional[str] = None
    is_admin: bool = False


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[str] = None
    is_active: Optional[bool] = None
    is_admin: Optional[bool] = None


class UserPasswordUpdate(BaseModel):
    new_password: str = Field(..., min_length=6)


class UserResponse(BaseModel):
    id: int
    username: str
    full_name: Optional[str]
    email: Optional[str]
    is_active: bool
    is_admin: bool
    created_at: Optional[datetime]

    class Config:
        from_attributes = True


class UserListResponse(BaseModel):
    total: int
    users: list[UserResponse]
