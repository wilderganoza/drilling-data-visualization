from pydantic import BaseModel


class LoginRequest(BaseModel):
    username: str
    password: str


class UserInfo(BaseModel):
    id: int
    username: str
    full_name: str | None
    email: str | None
    is_admin: bool

    class Config:
        from_attributes = True


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserInfo
