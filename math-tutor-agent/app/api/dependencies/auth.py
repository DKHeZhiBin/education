from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from app.domain.auth import AuthenticatedUser
from app.services.auth import auth_service


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/v1/auth/token")


def get_current_user(token: Annotated[str, Depends(oauth2_scheme)]) -> AuthenticatedUser:
    """中文：处理“获取·current·用户”相关操作。
    English: Handles the get current user operation.
    """
    return auth_service.authenticate_token(token)


CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]


def get_admin_user(current_user: CurrentUser) -> AuthenticatedUser:
    """中文：处理“获取·admin·用户”相关操作。
    English: Handles the get admin user operation.
    """
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="当前账号无权访问题库管理接口",
        )
    return current_user


AdminUser = Annotated[AuthenticatedUser, Depends(get_admin_user)]


def get_review_user(current_user: CurrentUser) -> AuthenticatedUser:
    """中文：处理“获取·复核·用户”相关操作。
    English: Handles the get review user operation.
    """
    if current_user.role not in {"admin", "teacher_reviewer"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="当前账号无权访问人工抽检工作台",
        )
    return current_user


ReviewUser = Annotated[AuthenticatedUser, Depends(get_review_user)]
