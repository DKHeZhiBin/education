from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from app.domain.auth import AuthenticatedUser
from app.services.auth import auth_service


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/v1/auth/token")


def get_current_user(token: Annotated[str, Depends(oauth2_scheme)]) -> AuthenticatedUser:
    return auth_service.authenticate_token(token)


CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]


def get_admin_user(current_user: CurrentUser) -> AuthenticatedUser:
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="当前账号无权访问题库管理接口",
        )
    return current_user


AdminUser = Annotated[AuthenticatedUser, Depends(get_admin_user)]
