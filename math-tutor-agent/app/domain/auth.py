from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field


UserRoleValue = Literal["student", "guardian", "admin", "teacher_reviewer"]


class RegisterRequest(BaseModel):
    """中文：定义“register·请求”类，封装该职责相关的数据与行为。
    English: Defines the register request class and encapsulates data and behavior for that responsibility.
    """
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    role: Literal["student", "guardian"]
    display_name: str = Field(min_length=1, max_length=40)


class AuthenticatedUser(BaseModel):
    """中文：定义“authenticated·用户”类，封装该职责相关的数据与行为。
    English: Defines the authenticated user class and encapsulates data and behavior for that responsibility.
    """
    id: str
    email: EmailStr
    role: UserRoleValue
    account_status: str
    token_version: int
    display_name: str
    email_verified: bool


class TokenResponse(BaseModel):
    """中文：定义“令牌·响应”类，封装该职责相关的数据与行为。
    English: Defines the token response class and encapsulates data and behavior for that responsibility.
    """
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: AuthenticatedUser


class RegistrationResponse(BaseModel):
    """中文：定义“registration·响应”类，封装该职责相关的数据与行为。
    English: Defines the registration response class and encapsulates data and behavior for that responsibility.
    """
    user: AuthenticatedUser
    message: str
    development_verification_url: str | None = None


class ActionRequestResponse(BaseModel):
    """中文：定义“action·请求·响应”类，封装该职责相关的数据与行为。
    English: Defines the action request response class and encapsulates data and behavior for that responsibility.
    """
    message: str
    development_action_url: str | None = None


class EmailRequest(BaseModel):
    """中文：定义“邮箱·请求”类，封装该职责相关的数据与行为。
    English: Defines the email request class and encapsulates data and behavior for that responsibility.
    """
    email: EmailStr


class TokenActionRequest(BaseModel):
    """中文：定义“令牌·action·请求”类，封装该职责相关的数据与行为。
    English: Defines the token action request class and encapsulates data and behavior for that responsibility.
    """
    token: str = Field(min_length=32, max_length=512)


class PasswordResetRequest(TokenActionRequest):
    """中文：定义“密码·重置·请求”类，封装该职责相关的数据与行为。
    English: Defines the password reset request class and encapsulates data and behavior for that responsibility.
    """
    new_password: str = Field(min_length=8, max_length=128)


class PasswordChangeRequest(BaseModel):
    """中文：定义“密码·change·请求”类，封装该职责相关的数据与行为。
    English: Defines the password change request class and encapsulates data and behavior for that responsibility.
    """
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class GuardianLinkRequest(BaseModel):
    """中文：定义“家长·link·请求”类，封装该职责相关的数据与行为。
    English: Defines the guardian link request class and encapsulates data and behavior for that responsibility.
    """
    student_email: EmailStr
    relationship: str = Field(min_length=1, max_length=20)


class GuardianLinkResponse(BaseModel):
    """中文：定义“家长·link·响应”类，封装该职责相关的数据与行为。
    English: Defines the guardian link response class and encapsulates data and behavior for that responsibility.
    """
    id: str
    guardian_user_id: str
    student_user_id: str
    guardian_name: str
    student_name: str
    relationship: str
    status: str
    consented_at: datetime | None = None
    created_at: datetime
