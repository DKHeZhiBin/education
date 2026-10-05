from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt
from jwt.exceptions import InvalidTokenError
from pwdlib import PasswordHash
import hashlib
import secrets

from app.core.config import settings


password_hash = PasswordHash.recommended()
DUMMY_PASSWORD_HASH = password_hash.hash("dummy-password-for-timing-equalization")


class InvalidAccessToken(Exception):
    pass


def create_opaque_token() -> tuple[str, str]:
    token = secrets.token_urlsafe(48)
    return token, hash_opaque_token(token)


def hash_opaque_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, encoded_hash: str | None) -> bool:
    candidate = encoded_hash if encoded_hash and encoded_hash != "!" else DUMMY_PASSWORD_HASH
    try:
        valid = password_hash.verify(password, candidate)
    except Exception:
        password_hash.verify(password, DUMMY_PASSWORD_HASH)
        return False
    return valid and candidate == encoded_hash


def create_access_token(user_id: str, role: str, token_version: int) -> tuple[str, int]:
    now = datetime.now(timezone.utc)
    expires = now + timedelta(minutes=settings.auth_access_token_minutes)
    payload = {
        "sub": user_id,
        "role": role,
        "ver": token_version,
        "iss": settings.auth_jwt_issuer,
        "aud": settings.auth_jwt_audience,
        "iat": now,
        "exp": expires,
        "jti": str(uuid4()),
    }
    token = jwt.encode(payload, settings.auth_jwt_secret, algorithm=settings.auth_jwt_algorithm)
    return token, int((expires - now).total_seconds())


def decode_access_token(token: str) -> dict:
    try:
        return jwt.decode(
            token,
            settings.auth_jwt_secret,
            algorithms=[settings.auth_jwt_algorithm],
            audience=settings.auth_jwt_audience,
            issuer=settings.auth_jwt_issuer,
            options={"require": ["sub", "role", "ver", "iss", "aud", "iat", "exp", "jti"]},
        )
    except InvalidTokenError as error:
        raise InvalidAccessToken from error
