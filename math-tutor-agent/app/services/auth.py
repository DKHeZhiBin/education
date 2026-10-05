from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
from uuid import uuid4

from fastapi import HTTPException, status

from app.core.config import settings
from app.core.database import create_mysql_engine, create_session_factory
from app.core.security import (
    InvalidAccessToken,
    create_access_token,
    create_opaque_token,
    decode_access_token,
    hash_opaque_token,
    hash_password,
    verify_password,
)
from app.domain.auth import (
    AuthenticatedUser,
    ActionRequestResponse,
    GuardianLinkRequest,
    GuardianLinkResponse,
    PasswordChangeRequest,
    PasswordResetRequest,
    RegisterRequest,
    RegistrationResponse,
    TokenResponse,
)
from app.providers.email import EmailDeliveryError, email_sender
from app.repositories.auth import (
    AuthRepository,
    EmailAlreadyRegistered,
    GuardianLinkAlreadyExists,
)


@dataclass(frozen=True)
class IssuedSession:
    response: TokenResponse
    refresh_token: str


class AuthService:
    def __init__(self) -> None:
        engine = create_mysql_engine()
        self.repository = AuthRepository(engine, create_session_factory(engine))

    def register(self, request: RegisterRequest) -> RegistrationResponse:
        if request.role == "student" and request.grade_band is None:
            raise HTTPException(status_code=422, detail="学生账号必须选择学段")
        if not request.display_name.strip():
            raise HTTPException(status_code=422, detail="显示名称不能为空")
        try:
            user = self.repository.create_user(
                email=self._email(request.email),
                password_hash=hash_password(request.password),
                role=request.role,
                display_name=request.display_name.strip(),
                grade_band=request.grade_band,
            )
        except EmailAlreadyRegistered as error:
            raise HTTPException(status_code=409, detail="该邮箱已经注册") from error
        action = self._send_action_email(user, "email_verification")
        return RegistrationResponse(
            user=user,
            message=action.message,
            development_verification_url=action.development_action_url,
        )

    def login(self, email: str, password: str) -> IssuedSession:
        user = self.repository.get_user_by_email(self._email(email))
        encoded_hash = user.password_hash if user is not None else None
        if not verify_password(password, encoded_hash):
            raise self._credentials_error()
        if user is None or user.account_status != "active":
            raise self._credentials_error()
        if user.email_verified_at is None:
            raise HTTPException(status_code=403, detail="请先完成邮箱验证")
        identity = self.repository.to_identity(user)
        issued = self._issue_session(identity)
        self.repository.mark_login(user.id)
        return issued

    def refresh(self, refresh_token: str | None) -> IssuedSession:
        if not refresh_token:
            raise self._credentials_error()
        replacement, replacement_hash = create_opaque_token()
        expires_at = self._now() + timedelta(days=settings.auth_refresh_token_days)
        rotation_status, identity = self.repository.rotate_refresh_session(
            hash_opaque_token(refresh_token),
            replacement_hash,
            expires_at,
        )
        if rotation_status != "rotated" or identity is None:
            raise self._credentials_error()
        access_token, expires_in = create_access_token(
            identity.id, identity.role, identity.token_version
        )
        return IssuedSession(
            response=TokenResponse(
                access_token=access_token,
                expires_in=expires_in,
                user=identity,
            ),
            refresh_token=replacement,
        )

    def authenticate_token(self, token: str) -> AuthenticatedUser:
        try:
            claims = decode_access_token(token)
        except InvalidAccessToken as error:
            raise self._credentials_error() from error
        user = self.repository.get_user_by_id(str(claims["sub"]))
        if (
            user is None
            or user.account_status != "active"
            or user.role != claims.get("role")
            or user.token_version != claims.get("ver")
        ):
            raise self._credentials_error()
        return self.repository.to_identity(user)

    def logout(self, refresh_token: str | None = None) -> None:
        if refresh_token:
            self.repository.revoke_refresh_family(hash_opaque_token(refresh_token))

    def request_email_verification(self, email: str) -> ActionRequestResponse:
        user = self.repository.get_user_by_email(self._email(email))
        if user is None or user.account_status != "active" or user.email_verified_at is not None:
            return self._generic_verification_response()
        return self._send_action_email(self.repository.to_identity(user), "email_verification")

    def verify_email(self, token: str) -> AuthenticatedUser:
        user = self.repository.verify_email(hash_opaque_token(token))
        if user is None:
            raise HTTPException(status_code=400, detail="验证链接无效或已经过期")
        return user

    def request_password_reset(self, email: str) -> ActionRequestResponse:
        user = self.repository.get_user_by_email(self._email(email))
        if user is None or user.account_status != "active":
            return self._generic_password_reset_response()
        result = self._send_action_email(self.repository.to_identity(user), "password_reset")
        return ActionRequestResponse(
            message=self._generic_password_reset_response().message,
            development_action_url=result.development_action_url,
        )

    def reset_password(self, request: PasswordResetRequest) -> None:
        if not self.repository.reset_password(
            hash_opaque_token(request.token),
            hash_password(request.new_password),
        ):
            raise HTTPException(status_code=400, detail="密码重置链接无效或已经过期")

    def change_password(self, actor: AuthenticatedUser, request: PasswordChangeRequest) -> None:
        user = self.repository.get_user_by_id(actor.id)
        if user is None or not verify_password(request.current_password, user.password_hash):
            raise HTTPException(status_code=400, detail="当前密码不正确")
        if verify_password(request.new_password, user.password_hash):
            raise HTTPException(status_code=422, detail="新密码不能与当前密码相同")
        if not self.repository.change_password(actor.id, hash_password(request.new_password)):
            raise self._credentials_error()

    def create_guardian_link(
        self,
        actor: AuthenticatedUser,
        request: GuardianLinkRequest,
    ) -> GuardianLinkResponse:
        self.require_role(actor, "guardian")
        try:
            link = self.repository.create_guardian_link(
                actor.id,
                self._email(request.student_email),
                request.relationship.strip(),
            )
        except GuardianLinkAlreadyExists as error:
            raise HTTPException(status_code=409, detail="关联申请已经存在") from error
        if link is None:
            raise HTTPException(status_code=404, detail="没有找到对应的学生账号")
        return link

    def accept_guardian_link(
        self,
        actor: AuthenticatedUser,
        link_id: str,
    ) -> GuardianLinkResponse:
        self.require_role(actor, "student")
        link = self.repository.accept_guardian_link(link_id, actor.id)
        if link is None:
            raise HTTPException(status_code=404, detail="待确认的关联申请不存在")
        return link

    def revoke_guardian_link(self, actor: AuthenticatedUser, link_id: str) -> None:
        if actor.role not in {"student", "guardian"}:
            raise HTTPException(status_code=403, detail="无权解除该关联")
        if not self.repository.revoke_guardian_link(link_id, actor.id):
            raise HTTPException(status_code=404, detail="关联不存在")

    def list_guardian_links(self, actor: AuthenticatedUser) -> list[GuardianLinkResponse]:
        if actor.role not in {"student", "guardian"}:
            return []
        return self.repository.list_guardian_links(actor.id, actor.role)

    def can_read_student(self, actor: AuthenticatedUser, student_user_id: str) -> bool:
        if actor.role == "admin":
            return True
        if actor.role == "student":
            return actor.id == student_user_id
        return self.repository.guardian_can_access(actor.id, student_user_id)

    @staticmethod
    def require_role(actor: AuthenticatedUser, role: str) -> None:
        if actor.role != role:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前账号无权执行此操作")

    @staticmethod
    def _email(value) -> str:
        return str(value).strip().casefold()

    @staticmethod
    def _credentials_error() -> HTTPException:
        return HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="登录信息无效或已经过期",
            headers={"WWW-Authenticate": "Bearer"},
        )

    def _issue_session(self, identity: AuthenticatedUser) -> IssuedSession:
        access_token, expires_in = create_access_token(
            identity.id, identity.role, identity.token_version
        )
        refresh_token, refresh_hash = create_opaque_token()
        self.repository.create_refresh_session(
            identity.id,
            str(uuid4()),
            refresh_hash,
            self._now() + timedelta(days=settings.auth_refresh_token_days),
        )
        return IssuedSession(
            response=TokenResponse(
                access_token=access_token,
                expires_in=expires_in,
                user=identity,
            ),
            refresh_token=refresh_token,
        )

    def _send_action_email(
        self,
        user: AuthenticatedUser,
        purpose: str,
    ) -> ActionRequestResponse:
        raw_token, token_hash = create_opaque_token()
        minutes = (
            settings.auth_email_verification_minutes
            if purpose == "email_verification"
            else settings.auth_password_reset_minutes
        )
        self.repository.create_action_token(
            user.id,
            purpose,
            token_hash,
            self._now() + timedelta(minutes=minutes),
        )
        query_name = "verify_token" if purpose == "email_verification" else "reset_token"
        url = f"{settings.auth_frontend_url.rstrip('/')}/auth?{urlencode({query_name: raw_token})}"
        subject = "验证你的数知伙伴邮箱" if purpose == "email_verification" else "重置你的数知伙伴密码"
        text = (
            f"你好，{user.display_name}：\n\n请在 {minutes} 分钟内打开下面的链接：\n{url}\n\n如果不是你发起的操作，可以忽略这封邮件。"
        )
        delivered = True
        try:
            email_sender.send(str(user.email), subject, text)
        except EmailDeliveryError:
            delivered = False
        development_url = (
            url
            if settings.app_env == "development" and settings.auth_expose_development_tokens
            else None
        )
        if purpose == "email_verification":
            message = "验证邮件已发送，请检查邮箱"
            if not delivered:
                message = "验证邮件暂未发送，请稍后重新发送"
        else:
            message = self._generic_password_reset_response().message
        return ActionRequestResponse(message=message, development_action_url=development_url)

    @staticmethod
    def _generic_verification_response() -> ActionRequestResponse:
        return ActionRequestResponse(message="如果账号需要验证，我们会发送一封验证邮件")

    @staticmethod
    def _generic_password_reset_response() -> ActionRequestResponse:
        return ActionRequestResponse(message="如果该邮箱已注册，我们会发送密码重置邮件")

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc).replace(tzinfo=None)


auth_service = AuthService()
