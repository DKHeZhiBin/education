from dataclasses import dataclass
import hashlib
import hmac
import logging

from redis import Redis
from redis.exceptions import RedisError

from app.core.config import settings
from app.core.redis import get_redis_client

logger = logging.getLogger(__name__)


FIXED_WINDOW_SCRIPT = """
local current = redis.call('INCR', KEYS[1])
if current == 1 then
  redis.call('EXPIRE', KEYS[1], ARGV[2])
end
local ttl = redis.call('TTL', KEYS[1])
if current > tonumber(ARGV[1]) then
  return {0, ttl, current}
end
return {1, ttl, current}
"""


class RateLimitExceeded(Exception):
    def __init__(self, retry_after_seconds: int) -> None:
        self.retry_after_seconds = retry_after_seconds
        super().__init__("Authentication request rate limit exceeded")


class RateLimitUnavailable(Exception):
    pass


@dataclass(frozen=True)
class RateLimitPolicy:
    scope: str
    identifier: str
    attempts: int
    window_seconds: int


class AuthRateLimiter:
    """Redis-backed fixed-window limits for security-sensitive auth routes."""

    def __init__(self, client: Redis | None) -> None:
        self.client = client
        self.script = client.register_script(FIXED_WINDOW_SCRIPT) if client is not None else None

    def enforce_login(self, ip_address: str, email: str) -> None:
        self._enforce(
            "login",
            ip_address,
            email,
            settings.auth_rate_limit_login_window_seconds,
            settings.auth_rate_limit_login_ip_attempts,
            settings.auth_rate_limit_login_account_attempts,
            settings.auth_rate_limit_login_combined_attempts,
        )

    def reset_login_account_limits(self, ip_address: str, email: str) -> None:
        """Clear failed-attempt pressure after success while retaining the IP-wide limit."""
        if not settings.auth_rate_limit_enabled or self.client is None:
            return
        keys = [
            self._key("login", "account", self._normalize_account(email)),
            self._key("login", "combined", self._normalize_ip(ip_address), self._normalize_account(email)),
        ]
        try:
            self.client.delete(*keys)
        except RedisError:
            logger.warning("Unable to reset successful login rate limits", exc_info=True)

    def enforce_register(self, ip_address: str, email: str) -> None:
        self._enforce(
            "register",
            ip_address,
            email,
            settings.auth_rate_limit_register_window_seconds,
            settings.auth_rate_limit_register_ip_attempts,
            settings.auth_rate_limit_register_account_attempts,
            settings.auth_rate_limit_register_combined_attempts,
        )

    def enforce_guardian_action(self, action: str, ip_address: str, actor_id: str) -> None:
        self._enforce(
            f"guardian-{action}",
            ip_address,
            actor_id,
            settings.auth_rate_limit_guardian_window_seconds,
            settings.auth_rate_limit_guardian_ip_attempts,
            settings.auth_rate_limit_guardian_account_attempts,
            settings.auth_rate_limit_guardian_combined_attempts,
        )

    def enforce_account_action(self, action: str, ip_address: str, account: str) -> None:
        self._enforce(
            action,
            ip_address,
            account,
            settings.auth_rate_limit_login_window_seconds,
            settings.auth_rate_limit_login_ip_attempts,
            settings.auth_rate_limit_login_account_attempts,
            settings.auth_rate_limit_login_combined_attempts,
        )

    def enforce_email_action(self, action: str, ip_address: str, email: str) -> None:
        self._enforce(
            action,
            ip_address,
            email,
            settings.auth_rate_limit_register_window_seconds,
            settings.auth_rate_limit_register_ip_attempts,
            settings.auth_rate_limit_register_account_attempts,
            settings.auth_rate_limit_register_combined_attempts,
        )

    def _enforce(
        self,
        action: str,
        ip_address: str,
        account: str,
        window_seconds: int,
        ip_attempts: int,
        account_attempts: int,
        combined_attempts: int,
    ) -> None:
        if not settings.auth_rate_limit_enabled:
            return
        if self.script is None:
            self._unavailable()
            return

        normalized_ip = self._normalize_ip(ip_address)
        normalized_account = self._normalize_account(account)
        policies = (
            RateLimitPolicy("ip", normalized_ip, ip_attempts, window_seconds),
            RateLimitPolicy("account", normalized_account, account_attempts, window_seconds),
            RateLimitPolicy(
                "combined",
                f"{normalized_ip}\0{normalized_account}",
                combined_attempts,
                window_seconds,
            ),
        )
        for policy in policies:
            self._apply(action, policy)

    def _apply(self, action: str, policy: RateLimitPolicy) -> None:
        key = self._key(action, policy.scope, policy.identifier)
        try:
            result = self.script(
                keys=[key],
                args=[policy.attempts, policy.window_seconds],
            )
        except RedisError:
            logger.warning(
                "Redis unavailable while enforcing authentication rate limit",
                extra={"action": action, "scope": policy.scope},
                exc_info=True,
            )
            self._unavailable()
            return

        allowed = int(result[0]) == 1
        if not allowed:
            ttl = int(result[1])
            raise RateLimitExceeded(max(1, ttl if ttl > 0 else policy.window_seconds))

    def _key(self, action: str, scope: str, *identifiers: str) -> str:
        value = "\0".join(identifiers)
        digest = hmac.new(
            settings.auth_jwt_secret.encode("utf-8"),
            value.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return f"{settings.redis_key_prefix}:rate-limit:auth:{action}:{scope}:{digest}"

    @staticmethod
    def _normalize_ip(value: str) -> str:
        return value.strip() or "unknown"

    @staticmethod
    def _normalize_account(value: str) -> str:
        return value.strip().casefold()

    @staticmethod
    def _unavailable() -> None:
        if settings.auth_rate_limit_fail_closed:
            raise RateLimitUnavailable("Authentication rate limiting is unavailable")


auth_rate_limiter = AuthRateLimiter(get_redis_client() if settings.redis_enabled else None)
