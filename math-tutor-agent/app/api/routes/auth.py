from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm

from app.api.dependencies.auth import CurrentUser
from app.core.config import settings
from app.domain.auth import (
    ActionRequestResponse,
    AuthenticatedUser,
    EmailRequest,
    GuardianLinkRequest,
    GuardianLinkResponse,
    PasswordChangeRequest,
    PasswordResetRequest,
    RegisterRequest,
    RegistrationResponse,
    TokenActionRequest,
    TokenResponse,
)
from app.security.rate_limit import (
    RateLimitExceeded,
    RateLimitUnavailable,
    auth_rate_limiter,
)
from app.services.auth import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=RegistrationResponse, status_code=201)
def register(payload: RegisterRequest, request: Request) -> RegistrationResponse:
    _enforce(lambda: auth_rate_limiter.enforce_register(_client_ip(request), str(payload.email)))
    return auth_service.register(payload)


@router.post("/token", response_model=TokenResponse)
def login(
    request: Request,
    response: Response,
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
) -> TokenResponse:
    ip_address = _client_ip(request)
    _enforce(lambda: auth_rate_limiter.enforce_login(ip_address, form.username))
    issued = auth_service.login(form.username, form.password)
    auth_rate_limiter.reset_login_account_limits(ip_address, form.username)
    _set_refresh_cookie(response, issued.refresh_token)
    return issued.response


@router.post("/refresh", response_model=TokenResponse)
def refresh(request: Request, response: Response) -> TokenResponse:
    token = request.cookies.get(settings.auth_refresh_cookie_name)
    _enforce_account_action("refresh", request, token or "missing")
    issued = auth_service.refresh(token)
    _set_refresh_cookie(response, issued.refresh_token)
    return issued.response


@router.get("/me", response_model=AuthenticatedUser)
def get_me(current_user: CurrentUser) -> AuthenticatedUser:
    return current_user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, response: Response) -> Response:
    auth_service.logout(request.cookies.get(settings.auth_refresh_cookie_name))
    _clear_refresh_cookie(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.post("/email-verification/request", response_model=ActionRequestResponse, status_code=202)
def request_email_verification(payload: EmailRequest, request: Request) -> ActionRequestResponse:
    _enforce_email_action("email-verification-request", request, str(payload.email))
    return auth_service.request_email_verification(str(payload.email))


@router.post("/email-verification/confirm", response_model=AuthenticatedUser)
def confirm_email_verification(
    payload: TokenActionRequest,
    request: Request,
) -> AuthenticatedUser:
    _enforce_account_action("email-verification-confirm", request, payload.token)
    return auth_service.verify_email(payload.token)


@router.post("/password/forgot", response_model=ActionRequestResponse, status_code=202)
def forgot_password(payload: EmailRequest, request: Request) -> ActionRequestResponse:
    _enforce_email_action("password-forgot", request, str(payload.email))
    return auth_service.request_password_reset(str(payload.email))


@router.post("/password/reset", status_code=status.HTTP_204_NO_CONTENT)
def reset_password(payload: PasswordResetRequest, request: Request, response: Response) -> Response:
    _enforce_account_action("password-reset", request, payload.token)
    auth_service.reset_password(payload)
    _clear_refresh_cookie(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.post("/password/change", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    payload: PasswordChangeRequest,
    request: Request,
    response: Response,
    current_user: CurrentUser,
) -> Response:
    _enforce_account_action("password-change", request, current_user.id)
    auth_service.change_password(current_user, payload)
    _clear_refresh_cookie(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.post("/guardian-links", response_model=GuardianLinkResponse, status_code=201)
def create_guardian_link(
    payload: GuardianLinkRequest,
    request: Request,
    current_user: CurrentUser,
) -> GuardianLinkResponse:
    _enforce_guardian("create", request, current_user.id)
    return auth_service.create_guardian_link(current_user, payload)


@router.get("/guardian-links", response_model=list[GuardianLinkResponse])
def list_guardian_links(current_user: CurrentUser) -> list[GuardianLinkResponse]:
    return auth_service.list_guardian_links(current_user)


@router.post("/guardian-links/{link_id}/accept", response_model=GuardianLinkResponse)
def accept_guardian_link(
    link_id: str,
    request: Request,
    current_user: CurrentUser,
) -> GuardianLinkResponse:
    _enforce_guardian("accept", request, current_user.id)
    return auth_service.accept_guardian_link(current_user, link_id)


@router.delete("/guardian-links/{link_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_guardian_link(link_id: str, request: Request, current_user: CurrentUser) -> Response:
    _enforce_guardian("revoke", request, current_user.id)
    auth_service.revoke_guardian_link(current_user, link_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _client_ip(request: Request) -> str:
    return request.client.host if request.client is not None else "unknown"


def _enforce(operation: Callable[[], None]) -> None:
    try:
        operation()
    except RateLimitExceeded as error:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="请求过于频繁，请稍后再试",
            headers={"Retry-After": str(error.retry_after_seconds)},
        ) from error
    except RateLimitUnavailable as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="认证保护服务暂时不可用，请稍后重试",
            headers={"Retry-After": "2"},
        ) from error


def _enforce_guardian(action: str, request: Request, actor_id: str) -> None:
    _enforce(lambda: auth_rate_limiter.enforce_guardian_action(action, _client_ip(request), actor_id))


def _enforce_account_action(action: str, request: Request, account: str) -> None:
    _enforce(lambda: auth_rate_limiter.enforce_account_action(action, _client_ip(request), account))


def _enforce_email_action(action: str, request: Request, email: str) -> None:
    _enforce(lambda: auth_rate_limiter.enforce_email_action(action, _client_ip(request), email))


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=settings.auth_refresh_cookie_name,
        value=token,
        max_age=settings.auth_refresh_token_days * 24 * 60 * 60,
        path="/v1/auth",
        secure=settings.auth_refresh_cookie_secure,
        httponly=True,
        samesite=settings.auth_refresh_cookie_samesite,
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.auth_refresh_cookie_name,
        path="/v1/auth",
        secure=settings.auth_refresh_cookie_secure,
        httponly=True,
        samesite=settings.auth_refresh_cookie_samesite,
    )
