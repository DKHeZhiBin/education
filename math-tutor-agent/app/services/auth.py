from contextlib import ExitStack
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
from app.domain.data_privacy import (
    StudentAccountDeletionRequest,
    StudentDataExport,
)
from app.cache.base import RuntimeCoordinationUnavailable, SessionLockBusy
from app.cache.factory import build_runtime_cache
from app.providers.problem_image_storage import problem_image_storage
from app.repositories.data_privacy import StudentDataNotFound, StudentDataRepository
from app.providers.email import EmailDeliveryError, email_sender
from app.repositories.auth import (
    AuthRepository,
    EmailAlreadyRegistered,
    GuardianLinkAlreadyExists,
)


@dataclass(frozen=True)
class IssuedSession:
    """中文：定义“issued·会话”类，封装该职责相关的数据与行为。
    English: Defines the issued session class and encapsulates data and behavior for that responsibility.
    """
    response: TokenResponse
    refresh_token: str


class AuthService:
    """中文：定义“auth·服务”类，封装该职责相关的数据与行为。
    English: Defines the auth service class and encapsulates data and behavior for that responsibility.
    """
    def __init__(self) -> None:
        """中文：初始化当前对象及其依赖。
        English: Initializes the current object and its dependencies.
        """
        engine = create_mysql_engine()
        session_factory = create_session_factory(engine)
        self.repository = AuthRepository(engine, session_factory)
        self.data_repository = StudentDataRepository(engine, session_factory)
        self.runtime_cache = build_runtime_cache()

    def register(self, request: RegisterRequest) -> RegistrationResponse:
        """中文：处理“register”相关操作。
        English: Handles the register operation.
        """
        if not request.display_name.strip():
            raise HTTPException(status_code=422, detail="显示名称不能为空")
        try:
            user = self.repository.create_user(
                email=self._email(request.email),
                password_hash=hash_password(request.password),
                role=request.role,
                display_name=request.display_name.strip(),
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
        """中文：处理“登录”相关操作。
        English: Handles the login operation.
        """
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
        """中文：处理“刷新”相关操作。
        English: Handles the refresh operation.
        """
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
        """中文：处理“认证·令牌”相关操作。
        English: Handles the authenticate token operation.
        """
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
        """中文：处理“退出登录”相关操作。
        English: Handles the logout operation.
        """
        if refresh_token:
            self.repository.revoke_refresh_family(hash_opaque_token(refresh_token))

    def request_email_verification(self, email: str) -> ActionRequestResponse:
        """中文：处理“请求·邮箱·校验”相关操作。
        English: Handles the request email verification operation.
        """
        user = self.repository.get_user_by_email(self._email(email))
        if user is None or user.account_status != "active" or user.email_verified_at is not None:
            return self._generic_verification_response()
        return self._send_action_email(self.repository.to_identity(user), "email_verification")

    def verify_email(self, token: str) -> AuthenticatedUser:
        """中文：处理“校验·邮箱”相关操作。
        English: Handles the verify email operation.
        """
        user = self.repository.verify_email(hash_opaque_token(token))
        if user is None:
            raise HTTPException(status_code=400, detail="验证链接无效或已经过期")
        return user

    def request_password_reset(self, email: str) -> ActionRequestResponse:
        """中文：处理“请求·密码·重置”相关操作。
        English: Handles the request password reset operation.
        """
        user = self.repository.get_user_by_email(self._email(email))
        if user is None or user.account_status != "active":
            return self._generic_password_reset_response()
        result = self._send_action_email(self.repository.to_identity(user), "password_reset")
        return ActionRequestResponse(
            message=self._generic_password_reset_response().message,
            development_action_url=result.development_action_url,
        )

    def reset_password(self, request: PasswordResetRequest) -> None:
        """中文：处理“重置·密码”相关操作。
        English: Handles the reset password operation.
        """
        if not self.repository.reset_password(
            hash_opaque_token(request.token),
            hash_password(request.new_password),
        ):
            raise HTTPException(status_code=400, detail="密码重置链接无效或已经过期")

    def change_password(self, actor: AuthenticatedUser, request: PasswordChangeRequest) -> None:
        """中文：处理“change·密码”相关操作。
        English: Handles the change password operation.
        """
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
        """中文：处理“创建·家长·link”相关操作。
        English: Handles the create guardian link operation.
        """
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
        """中文：处理“accept·家长·link”相关操作。
        English: Handles the accept guardian link operation.
        """
        self.require_role(actor, "student")
        link = self.repository.accept_guardian_link(link_id, actor.id)
        if link is None:
            raise HTTPException(status_code=404, detail="待确认的关联申请不存在")
        return link

    def revoke_guardian_link(self, actor: AuthenticatedUser, link_id: str) -> None:
        """中文：处理“revoke·家长·link”相关操作。
        English: Handles the revoke guardian link operation.
        """
        if actor.role not in {"student", "guardian"}:
            raise HTTPException(status_code=403, detail="无权解除该关联")
        if not self.repository.revoke_guardian_link(link_id, actor.id):
            raise HTTPException(status_code=404, detail="关联不存在")

    def list_guardian_links(self, actor: AuthenticatedUser) -> list[GuardianLinkResponse]:
        """中文：处理“列出·家长·links”相关操作。
        English: Handles the list guardian links operation.
        """
        if actor.role not in {"student", "guardian"}:
            return []
        return self.repository.list_guardian_links(actor.id, actor.role)

    def export_student_data(self, actor: AuthenticatedUser) -> StudentDataExport:
        """中文：处理“export·学生·data”相关操作。
        English: Handles the export student data operation.
        """
        self.require_role(actor, "student")
        try:
            return self.data_repository.export(actor.id)
        except StudentDataNotFound as error:
            raise HTTPException(status_code=404, detail="学生数据不存在") from error

    def delete_student_account(
        self,
        actor: AuthenticatedUser,
        request: StudentAccountDeletionRequest,
    ) -> None:
        """中文：处理“删除·学生·account”相关操作。
        English: Handles the delete student account operation.
        """
        self.require_role(actor, "student")
        user = self.repository.get_user_by_id(actor.id)
        if user is None or not verify_password(request.current_password, user.password_hash):
            raise HTTPException(status_code=400, detail="当前密码不正确")
        try:
            targets = self.data_repository.deletion_targets(actor.id)
        except StudentDataNotFound as error:
            raise HTTPException(status_code=404, detail="学生数据不存在") from error
        try:
            with ExitStack() as session_locks:
                for session_id in sorted(targets.deleted_session_ids):
                    session_locks.enter_context(self.runtime_cache.lock_session(session_id))
                for session_id in targets.deleted_session_ids:
                    self.runtime_cache.purge_session(session_id)
                try:
                    problem_image_storage.delete_owner(actor.id)
                except OSError as error:
                    raise HTTPException(
                        status_code=503,
                        detail="暂时无法清除已上传的题目图片，请稍后重试删除操作",
                        headers={"Retry-After": "2"},
                    ) from error
                self.data_repository.delete_student_data(actor.id)
        except SessionLockBusy as error:
            raise HTTPException(
                status_code=409,
                detail="学习会话正在处理，请稍后重试删除操作",
                headers={"Retry-After": "2"},
            ) from error
        except RuntimeCoordinationUnavailable as error:
            raise HTTPException(
                status_code=503,
                detail="暂时无法清除缓存中的学习数据，请稍后重试删除操作",
                headers={"Retry-After": "2"},
            ) from error

    def close(self) -> None:
        """中文：处理“关闭”相关操作。
        English: Handles the close operation.
        """
        self.runtime_cache.close()
        self.repository.engine.dispose()

    def can_read_student(self, actor: AuthenticatedUser, student_user_id: str) -> bool:
        """中文：处理“can·读取·学生”相关操作。
        English: Handles the can read student operation.
        """
        if actor.role == "admin":
            return True
        if actor.role == "student":
            return actor.id == student_user_id
        return self.repository.guardian_can_access(actor.id, student_user_id)

    @staticmethod
    def require_role(actor: AuthenticatedUser, role: str) -> None:
        """中文：处理“require·role”相关操作。
        English: Handles the require role operation.
        """
        if actor.role != role:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前账号无权执行此操作")

    @staticmethod
    def _email(value) -> str:
        """中文：处理“邮箱”相关操作。
        English: Handles the email operation.
        """
        return str(value).strip().casefold()

    @staticmethod
    def _credentials_error() -> HTTPException:
        """中文：处理“credentials·error”相关操作。
        English: Handles the credentials error operation.
        """
        return HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="登录信息无效或已经过期",
            headers={"WWW-Authenticate": "Bearer"},
        )

    def _issue_session(self, identity: AuthenticatedUser) -> IssuedSession:
        """中文：处理“issue·会话”相关操作。
        English: Handles the issue session operation.
        """
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
        """中文：处理“send·action·邮箱”相关操作。
        English: Handles the send action email operation.
        """
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
        """中文：处理“generic·校验·响应”相关操作。
        English: Handles the generic verification response operation.
        """
        return ActionRequestResponse(message="如果账号需要验证，我们会发送一封验证邮件")

    @staticmethod
    def _generic_password_reset_response() -> ActionRequestResponse:
        """中文：处理“generic·密码·重置·响应”相关操作。
        English: Handles the generic password reset response operation.
        """
        return ActionRequestResponse(message="如果该邮箱已注册，我们会发送密码重置邮件")

    @staticmethod
    def _now() -> datetime:
        """中文：处理“now”相关操作。
        English: Handles the now operation.
        """
        return datetime.now(timezone.utc).replace(tzinfo=None)


auth_service = AuthService()
