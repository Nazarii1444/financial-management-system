from typing import Optional
from pydantic import BaseModel, EmailStr, ConfigDict, Field
from src.models import UserStatus


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    email: EmailStr
    password: str = Field(min_length=8)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    """Unified response for both signup and login."""
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    token_type: str = "bearer"
    requires_2fa: bool = False
    temp_token: Optional[str] = None   # present only when requires_2fa=True


# Kept for backward compatibility
class UserLoginResponse(LoginResponse):
    pass


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)


class TwoFACompleteRequest(BaseModel):
    """Sent after login when requires_2fa=True."""
    temp_token: str
    code: str = Field(min_length=6, max_length=6)


class UserEmail(BaseModel):
    email: EmailStr


class UserResponse(BaseModel):
    username: str
    email: EmailStr
    is_admin: UserStatus
    is_active: bool = True
    model_config = ConfigDict(from_attributes=True)
