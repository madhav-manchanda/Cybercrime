"""Application settings loaded from environment / ``.env`` file.

All configuration is immutable and validated once at import time.  Nothing in
this module performs I/O beyond reading the environment.
"""

from __future__ import annotations

import functools
from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]


class AppEnv(StrEnum):
    """Deployment environment."""

    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class GeoBackend(StrEnum):
    """Spatial storage / query strategy."""

    AUTO = "auto"
    POSTGIS = "postgis"
    SQLITE = "sqlite"


class LogFormat(StrEnum):
    JSON = "json"
    CONSOLE = "console"


class PasswordHashAlgorithm(StrEnum):
    ARGON2 = "argon2"
    BCRYPT = "bcrypt"


class Settings(BaseSettings):
    """Root settings object."""

    model_config = SettingsConfigDict(
        env_file=(BACKEND_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---------------------------------------------------------------- app
    app_name: str = "Cybercrime Cash-Out Intelligence API"
    app_slug: str = "cybercrime-intel"
    app_version: str = "1.0.0"
    app_env: AppEnv = AppEnv.DEVELOPMENT
    debug: bool = False
    api_v1_prefix: str = "/api/v1"
    timezone: str = "Asia/Kolkata"
    cors_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ]
    )

    # ----------------------------------------------------------- security
    secret_key: SecretStr = SecretStr("insecure-development-key-do-not-use-in-production")
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7
    jwt_issuer: str = "cybercrime-intel-api"
    jwt_audience: str = "cybercrime-intel-clients"

    password_hash_algorithm: PasswordHashAlgorithm = PasswordHashAlgorithm.ARGON2
    argon2_time_cost: int = 3
    argon2_memory_cost: int = 65536
    argon2_parallelism: int = 4
    bcrypt_rounds: int = 12

    bootstrap_admin_email: str = "admin@cybercrime.local"
    bootstrap_admin_password: SecretStr = SecretStr("ChangeMe!Admin#2026")
    demo_user_password: SecretStr = SecretStr("Demo#Passw0rd")

    # ------------------------------------------------------------- database
    postgres_user: str = "cybercrime"
    postgres_password: SecretStr = SecretStr("cybercrime")
    postgres_db: str = "cybercrime"
    postgres_host: str = "postgres"
    postgres_port: int = 5432
    database_url: str | None = None
    db_echo: bool = False
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_pool_timeout: int = 30
    db_pool_recycle: int = 1800
    db_statement_timeout_ms: int = 30000
    db_connect_retries: int = 5
    db_connect_retry_delay: int = 2
    geo_backend: GeoBackend = GeoBackend.AUTO

    # --------------------------------------------------------------- redis
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str | None = None
    celery_result_backend: str | None = None
    celery_task_always_eager: bool = False
    celery_task_serializer: str = "json"
    celery_result_serializer: str = "json"
    celery_worker_concurrency: int = 4
    celery_beat_schedule_minutes: int = 15

    # ------------------------------------------------------- rate limiting
    rate_limit_enabled: bool = True
    rate_limit_backend: Literal["memory", "redis"] = "memory"
    rate_limit_default_per_minute: int = 120
    rate_limit_login_per_minute: int = 10
    rate_limit_write_per_minute: int = 60
    rate_limit_predict_per_minute: int = 12
    rate_limit_synthetic_per_hour: int = 20
    rate_limit_llm_per_minute: int = 30

    # -------------------------------------------------------------- cache
    cache_enabled: bool = True
    cache_ttl_dashboard_seconds: int = 60
    cache_ttl_atm_risk_seconds: int = 300
    cache_ttl_hotspots_seconds: int = 600
    cache_ttl_model_meta_seconds: int = 1800

    # ----------------------------------------------------------- logging
    log_level: str = "INFO"
    log_format: LogFormat = LogFormat.JSON
    log_sensitive_fields: list[str] = Field(
        default_factory=lambda: [
            "password",
            "token",
            "access_token",
            "refresh_token",
            "authorization",
            "account_number",
            "api_key",
            "secret",
            "private_key",
            "card_number",
            "upi_id",
        ]
    )
    request_logging: bool = True
    slow_request_ms: int = 1500

    # ----------------------------------------------------------------- ML
    ml_artifact_dir: str = "var/ml"
    ml_random_seed: int = 42
    ml_train_limit_cases: int = 100
    ml_min_train_samples: int = 40
    ml_predict_top_k: int = 10
    ml_nearest_atms_per_anchor: int = 60
    ml_max_distance_km: float = 75.0
    ml_negative_sampling_ratio: float = 6.0
    ml_retrain_min_cases: int = 25
    ml_explanation_top_factors: int = 8

    # ----------------------------------------------------------------- LLM
    llm_enabled: bool = False
    llm_provider: str = "openai_compatible"
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: SecretStr = SecretStr("")
    llm_model: str = "gpt-4o-mini"
    llm_timeout_seconds: int = 45
    llm_max_context_chars: int = 12000

    # -------------------------------------------------------------- domain
    default_city: str = "Lucknow"
    default_city_lat: float = 26.8467
    default_city_lon: float = 80.9462
    default_timezone: str = "Asia/Kolkata"
    demo_cases: int = 60
    demo_atms: int = 140

    # --------------------------------------------------------- validators
    @field_validator("cors_origins", "log_sensitive_fields", mode="before")
    @classmethod
    def _split_csv(cls, value: object) -> object:
        """Accept either a JSON array or a comma separated string."""
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return []
            if stripped.startswith("["):
                return value
            return [item.strip() for item in stripped.split(",") if item.strip()]
        return value

    @field_validator("log_level")
    @classmethod
    def _validate_log_level(cls, value: str) -> str:
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = value.upper()
        if upper not in allowed:
            raise ValueError(f"LOG_LEVEL must be one of {sorted(allowed)}")
        return upper

    @model_validator(mode="after")
    def _production_hardening(self) -> Settings:
        """Refuse obviously unsafe production configuration."""
        if self.app_env is AppEnv.PRODUCTION:
            secret = self.secret_key.get_secret_value()
            if len(secret) < 32:
                raise ValueError("SECRET_KEY must be at least 32 characters in production")
            if "insecure" in secret.lower() or "change-me" in secret.lower():
                raise ValueError("SECRET_KEY must be rotated before running in production")
            if "*" in self.cors_origins:
                raise ValueError("CORS_ORIGINS must not be '*' in production")
        return self

    # --------------------------------------------------------- properties
    @property
    def is_production(self) -> bool:
        return self.app_env is AppEnv.PRODUCTION

    @property
    def is_development(self) -> bool:
        return self.app_env is AppEnv.DEVELOPMENT

    @property
    def async_database_url(self) -> str:
        """Async SQLAlchemy DSN used by the application."""
        if self.database_url:
            return self._normalise_dsn(self.database_url)
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password.get_secret_value()}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def sync_database_url(self) -> str:
        """Blocking DSN used by Alembic, Celery workers and CLI scripts."""
        if self.database_url:
            return self._normalise_dsn(self.database_url, driver_override="psycopg2")
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password.get_secret_value()}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @staticmethod
    def _normalise_dsn(dsn: str, driver_override: str | None = None) -> str:
        """Force an async/sync driver and escape credentials."""
        from sqlalchemy.engine import make_url

        url = make_url(dsn)
        if driver_override:
            backend = url.get_backend_name()
            if backend == "postgresql":
                url = url.set(drivername=f"postgresql+{driver_override}")
            elif backend == "sqlite":
                url = url.set(drivername="sqlite+pysqlite")
        if url.password:
            url = url.set(password=url.password)
        return str(url.render_as_string(hide_password=False))

    @property
    def broker_url(self) -> str:
        return self.celery_broker_url or self.redis_url

    @property
    def result_backend(self) -> str:
        if self.celery_result_backend:
            return self.celery_result_backend
        base = self.redis_url.rstrip("/")
        return f"{base}/1" if not base.endswith("/1") else base

    @property
    def artifact_path(self) -> Path:
        path = Path(self.ml_artifact_dir)
        if not path.is_absolute():
            path = BACKEND_ROOT / path
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def sqlalchemy_echo(self) -> bool:
        return self.db_echo or self.debug


@functools.lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings singleton."""
    return Settings()


settings = get_settings()

__all__ = [
    "BACKEND_ROOT",
    "AppEnv",
    "GeoBackend",
    "LogFormat",
    "PasswordHashAlgorithm",
    "Settings",
    "get_settings",
    "settings",
]
