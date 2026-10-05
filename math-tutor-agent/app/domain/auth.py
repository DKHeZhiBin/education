from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field


UserRoleValue = Literal["student", "guardian", "admin"]


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    role: Literal["student", "guardian"]
    display_name: str = Field(min_length=1, max_length=40)
    grade_band: Literal["primary_lower", "primary_upper", "middle", "high"] | None = None


class AuthenticatedUser(BaseModel):
    id: str
    email: EmailStr
    role: UserRoleValue
    account_status: str
    token_version: int
    display_name: str
    grade_band: str | None = None
    email_verified: bool


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: AuthenticatedUser


class RegistrationResponse(BaseModel):
    user: AuthenticatedUser
    message: str
    development_verification_url: str | None = None


class ActionRequestResponse(BaseModel):
    message: str
    development_action_url: str | None = None


class EmailRequest(BaseModel):
    email: EmailStr


class TokenActionRequest(BaseModel):
    token: str = Field(min_length=32, max_length=512)


class PasswordResetRequest(TokenActionRequest):
    new_password: str = Field(min_length=8, max_length=128)


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class GuardianLinkRequest(BaseModel):
    student_email: EmailStr
    relationship: str = Field(min_length=1, max_length=20)


class GuardianLinkResponse(BaseModel):
    id: str
    guardian_user_id: str
    student_user_id: str
    guardian_name: str
    student_name: str
    relationship: str
    status: str
    consented_at: datetime | None = None
    created_at: datetime
