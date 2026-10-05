from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""
    llm_timeout_seconds: float = 30.0
    llm_readiness_path: str = "/models"
    llm_required_for_readiness: bool = False
    readiness_timeout_seconds: float = 2.0
    database_url: str = "mysql+pymysql://math_tutor:math_tutor@localhost:3306/math_tutor?charset=utf8mb4"
    database_pool_size: int = 10
    database_max_overflow: int = 20
    database_pool_recycle_seconds: int = 1800
    database_echo: bool = False
    auth_jwt_secret: str = "development-only-change-this-secret"
    auth_jwt_algorithm: str = "HS256"
    auth_jwt_issuer: str = "math-tutor-agent"
    auth_jwt_audience: str = "math-tutor-web"
    auth_access_token_minutes: int = 30
    auth_refresh_token_days: int = 30
    auth_refresh_cookie_name: str = "math_tutor_refresh"
    auth_refresh_cookie_secure: bool = False
    auth_refresh_cookie_samesite: str = "lax"
    auth_email_verification_minutes: int = 1440
    auth_password_reset_minutes: int = 30
    auth_frontend_url: str = "http://localhost:5173"
    auth_expose_development_tokens: bool = False
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_email: str = ""
    smtp_starttls: bool = True
    auth_rate_limit_enabled: bool = True
    auth_rate_limit_fail_closed: bool = True
    auth_rate_limit_login_window_seconds: int = 900
    auth_rate_limit_login_ip_attempts: int = 20
    auth_rate_limit_login_account_attempts: int = 8
    auth_rate_limit_login_combined_attempts: int = 5
    auth_rate_limit_register_window_seconds: int = 3600
    auth_rate_limit_register_ip_attempts: int = 5
    auth_rate_limit_register_account_attempts: int = 3
    auth_rate_limit_register_combined_attempts: int = 2
    auth_rate_limit_guardian_window_seconds: int = 3600
    auth_rate_limit_guardian_ip_attempts: int = 20
    auth_rate_limit_guardian_account_attempts: int = 10
    auth_rate_limit_guardian_combined_attempts: int = 6
    redis_enabled: bool = True
    redis_coordination_fail_closed: bool = True
    redis_url: str = "redis://localhost:6379/0"
    redis_key_prefix: str = "math-tutor:v1"
    redis_session_ttl_seconds: int = 3600
    redis_idempotency_ttl_seconds: int = 86400
    redis_lock_ttl_seconds: int = 120
    redis_lock_wait_seconds: float = 3.0
    redis_socket_timeout_seconds: float = 0.5
    redis_max_connections: int = 20
    harness_max_agent_calls: int = 8
    harness_max_duration_ms: int = 60_000
    solution_max_revision_attempts: int = 2
    knowledge_problem_max_revision_attempts: int = 2
    rag_enabled: bool = False
    rag_provider: str = ""
    rag_top_k: int = 5
    rag_timeout_seconds: float = 3.0
    rag_max_context_chars: int = 12_000
    rag_required_for_readiness: bool = False
    rag_hybrid_rrf_k: int = 60
    rag_hybrid_vector_weight: float = 1.0
    rag_hybrid_keyword_weight: float = 1.0
    rag_rerank_fusion_weight: float = 0.55
    rag_rerank_condition_weight: float = 0.20
    rag_rerank_target_weight: float = 0.15
    rag_rerank_solution_weight: float = 0.10
    rag_cache_enabled: bool = True
    rag_cache_ttl_seconds: int = 900
    rag_cache_no_results_ttl_seconds: int = 60
    rag_cache_schema_version: str = "v1"
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str = ""
    qdrant_collection: str = "math_tutor_knowledge_v1"
    qdrant_vector_name: str = "dense"
    qdrant_score_threshold: float = 0.25
    qdrant_oversampling_factor: int = 4
    embedding_base_url: str = ""
    embedding_api_key: str = ""
    embedding_model: str = ""
    embedding_dimensions: int = 1024
    embedding_timeout_seconds: float = 15.0
    embedding_readiness_path: str = "/models"
    production_index_version: str = "v1"
    production_index_sync_limit: int = 100
    production_embedding_batch_size: int = 32
    production_index_timeout_seconds: float = 30.0
    production_index_maintenance_max_attempts: int = 5
    production_index_maintenance_lease_seconds: int = 300
    quality_max_erroneous_admission_rate: float = 0.0
    quality_release_min_auto_admissions: int = 1

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @model_validator(mode="after")
    def validate_auth_secret(self):
        if self.auth_jwt_algorithm != "HS256":
            raise ValueError("AUTH_JWT_ALGORITHM currently supports HS256 only")
        weak_secret = (
            len(self.auth_jwt_secret) < 32
            or self.auth_jwt_secret == "development-only-change-this-secret"
            or self.auth_jwt_secret.startswith("replace-with-")
        )
        if self.app_env != "development" and weak_secret:
            raise ValueError("AUTH_JWT_SECRET must be a unique secret of at least 32 characters")
        if self.auth_refresh_cookie_samesite not in {"lax", "strict", "none"}:
            raise ValueError("AUTH_REFRESH_COOKIE_SAMESITE must be lax, strict or none")
        if self.auth_refresh_cookie_samesite == "none" and not self.auth_refresh_cookie_secure:
            raise ValueError("SameSite=None requires AUTH_REFRESH_COOKIE_SECURE=true")
        if self.app_env != "development":
            if not self.auth_refresh_cookie_secure:
                raise ValueError("AUTH_REFRESH_COOKIE_SECURE must be true outside development")
            if not self.smtp_host or not self.smtp_from_email:
                raise ValueError("SMTP_HOST and SMTP_FROM_EMAIL are required outside development")
            if self.auth_expose_development_tokens:
                raise ValueError("AUTH_EXPOSE_DEVELOPMENT_TOKENS must be false outside development")
        if self.app_env != "development" and self.auth_rate_limit_enabled:
            if not self.redis_enabled:
                raise ValueError("REDIS_ENABLED must be true when auth rate limiting is enabled")
            if not self.auth_rate_limit_fail_closed:
                raise ValueError("AUTH_RATE_LIMIT_FAIL_CLOSED must be true outside development")
        if self.app_env != "development":
            if not self.redis_enabled:
                raise ValueError("REDIS_ENABLED must be true outside development")
            if not self.redis_coordination_fail_closed:
                raise ValueError("REDIS_COORDINATION_FAIL_CLOSED must be true outside development")
        positive_values = {
            "AUTH_RATE_LIMIT_LOGIN_WINDOW_SECONDS": self.auth_rate_limit_login_window_seconds,
            "AUTH_RATE_LIMIT_LOGIN_IP_ATTEMPTS": self.auth_rate_limit_login_ip_attempts,
            "AUTH_RATE_LIMIT_LOGIN_ACCOUNT_ATTEMPTS": self.auth_rate_limit_login_account_attempts,
            "AUTH_RATE_LIMIT_LOGIN_COMBINED_ATTEMPTS": self.auth_rate_limit_login_combined_attempts,
            "AUTH_RATE_LIMIT_REGISTER_WINDOW_SECONDS": self.auth_rate_limit_register_window_seconds,
            "AUTH_RATE_LIMIT_REGISTER_IP_ATTEMPTS": self.auth_rate_limit_register_ip_attempts,
            "AUTH_RATE_LIMIT_REGISTER_ACCOUNT_ATTEMPTS": self.auth_rate_limit_register_account_attempts,
            "AUTH_RATE_LIMIT_REGISTER_COMBINED_ATTEMPTS": self.auth_rate_limit_register_combined_attempts,
            "AUTH_RATE_LIMIT_GUARDIAN_WINDOW_SECONDS": self.auth_rate_limit_guardian_window_seconds,
            "AUTH_RATE_LIMIT_GUARDIAN_IP_ATTEMPTS": self.auth_rate_limit_guardian_ip_attempts,
            "AUTH_RATE_LIMIT_GUARDIAN_ACCOUNT_ATTEMPTS": self.auth_rate_limit_guardian_account_attempts,
            "AUTH_RATE_LIMIT_GUARDIAN_COMBINED_ATTEMPTS": self.auth_rate_limit_guardian_combined_attempts,
            "AUTH_REFRESH_TOKEN_DAYS": self.auth_refresh_token_days,
            "AUTH_EMAIL_VERIFICATION_MINUTES": self.auth_email_verification_minutes,
            "AUTH_PASSWORD_RESET_MINUTES": self.auth_password_reset_minutes,
            "READINESS_TIMEOUT_SECONDS": self.readiness_timeout_seconds,
            "HARNESS_MAX_AGENT_CALLS": self.harness_max_agent_calls,
            "HARNESS_MAX_DURATION_MS": self.harness_max_duration_ms,
            "RAG_TOP_K": self.rag_top_k,
            "RAG_TIMEOUT_SECONDS": self.rag_timeout_seconds,
            "RAG_MAX_CONTEXT_CHARS": self.rag_max_context_chars,
            "RAG_HYBRID_RRF_K": self.rag_hybrid_rrf_k,
            "RAG_HYBRID_VECTOR_WEIGHT": self.rag_hybrid_vector_weight,
            "RAG_HYBRID_KEYWORD_WEIGHT": self.rag_hybrid_keyword_weight,
            "RAG_CACHE_TTL_SECONDS": self.rag_cache_ttl_seconds,
            "RAG_CACHE_NO_RESULTS_TTL_SECONDS": self.rag_cache_no_results_ttl_seconds,
            "QDRANT_OVERSAMPLING_FACTOR": self.qdrant_oversampling_factor,
            "EMBEDDING_DIMENSIONS": self.embedding_dimensions,
            "EMBEDDING_TIMEOUT_SECONDS": self.embedding_timeout_seconds,
            "PRODUCTION_INDEX_SYNC_LIMIT": self.production_index_sync_limit,
            "PRODUCTION_EMBEDDING_BATCH_SIZE": self.production_embedding_batch_size,
            "PRODUCTION_INDEX_TIMEOUT_SECONDS": self.production_index_timeout_seconds,
            "PRODUCTION_INDEX_MAINTENANCE_MAX_ATTEMPTS": self.production_index_maintenance_max_attempts,
            "PRODUCTION_INDEX_MAINTENANCE_LEASE_SECONDS": self.production_index_maintenance_lease_seconds,
        }
        invalid_values = [name for name, value in positive_values.items() if value <= 0]
        if invalid_values:
            raise ValueError(f"Configuration values must be greater than zero: {', '.join(invalid_values)}")
        rerank_weights = {
            "RAG_RERANK_FUSION_WEIGHT": self.rag_rerank_fusion_weight,
            "RAG_RERANK_CONDITION_WEIGHT": self.rag_rerank_condition_weight,
            "RAG_RERANK_TARGET_WEIGHT": self.rag_rerank_target_weight,
            "RAG_RERANK_SOLUTION_WEIGHT": self.rag_rerank_solution_weight,
        }
        if any(value < 0 for value in rerank_weights.values()):
            raise ValueError("RAG rerank weights must not be negative")
        if sum(rerank_weights.values()) <= 0:
            raise ValueError("At least one RAG rerank weight must be greater than zero")
        if self.llm_readiness_path and not self.llm_readiness_path.startswith("/"):
            raise ValueError("LLM_READINESS_PATH must start with /")
        if not 0 <= self.solution_max_revision_attempts <= 3:
            raise ValueError("SOLUTION_MAX_REVISION_ATTEMPTS must be between 0 and 3")
        minimum_agent_calls = 4 + 2 * self.solution_max_revision_attempts
        if self.harness_max_agent_calls < minimum_agent_calls:
            raise ValueError(
                "HARNESS_MAX_AGENT_CALLS must be at least "
                f"{minimum_agent_calls} for the configured solution revision limit"
            )
        if not 1 <= self.knowledge_problem_max_revision_attempts <= 2:
            raise ValueError(
                "KNOWLEDGE_PROBLEM_MAX_REVISION_ATTEMPTS must be between 1 and 2"
            )
        if self.rag_top_k > 20:
            raise ValueError("RAG_TOP_K must be no greater than 20")
        if self.rag_max_context_chars > 24_000:
            raise ValueError("RAG_MAX_CONTEXT_CHARS must be no greater than 24000")
        if not self.rag_cache_schema_version.strip():
            raise ValueError("RAG_CACHE_SCHEMA_VERSION must not be empty")
        if not 0 <= self.qdrant_score_threshold <= 1:
            raise ValueError("QDRANT_SCORE_THRESHOLD must be between 0 and 1")
        if self.qdrant_oversampling_factor > 20:
            raise ValueError("QDRANT_OVERSAMPLING_FACTOR must be no greater than 20")
        if not self.qdrant_url.startswith(("http://", "https://")):
            raise ValueError("QDRANT_URL must use http or https")
        allowed_name_chars = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-")
        if not self.qdrant_collection or not set(self.qdrant_collection) <= allowed_name_chars:
            raise ValueError("QDRANT_COLLECTION contains unsupported characters")
        if not self.qdrant_vector_name or not set(self.qdrant_vector_name) <= allowed_name_chars:
            raise ValueError("QDRANT_VECTOR_NAME contains unsupported characters")
        if self.embedding_readiness_path and not self.embedding_readiness_path.startswith("/"):
            raise ValueError("EMBEDDING_READINESS_PATH must start with /")
        if not self.production_index_version.strip():
            raise ValueError("PRODUCTION_INDEX_VERSION must not be empty")
        if not 0 <= self.quality_max_erroneous_admission_rate <= 1:
            raise ValueError("QUALITY_MAX_ERRONEOUS_ADMISSION_RATE must be between 0 and 1")
        if self.quality_release_min_auto_admissions < 1:
            raise ValueError("QUALITY_RELEASE_MIN_AUTO_ADMISSIONS must be at least 1")
        if self.rag_enabled and not self.rag_provider.strip():
            raise ValueError("RAG_PROVIDER is required when RAG_ENABLED=true")
        if self.rag_enabled and self.rag_provider.strip().lower() in {
            "qdrant",
            "hybrid",
        }:
            required_qdrant = {
                "QDRANT_URL": self.qdrant_url,
                "QDRANT_COLLECTION": self.qdrant_collection,
                "QDRANT_VECTOR_NAME": self.qdrant_vector_name,
                "EMBEDDING_BASE_URL": self.embedding_base_url,
                "EMBEDDING_MODEL": self.embedding_model,
            }
            missing = [name for name, value in required_qdrant.items() if not value.strip()]
            if missing:
                raise ValueError(
                    "Qdrant RAG configuration is incomplete: " + ", ".join(missing)
                )
        if not self.rag_enabled and self.rag_required_for_readiness:
            raise ValueError("RAG_REQUIRED_FOR_READINESS requires RAG_ENABLED=true")
        return self


settings = Settings()
