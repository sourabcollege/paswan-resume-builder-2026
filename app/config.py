from __future__ import annotations

import os
import secrets
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv


# ✅ FIX: Project root (one level UP from app/)
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        return default
    return int(value)


def _env_csv(name: str, default: tuple[str, ...] = ()) -> tuple[str, ...]:
    value = os.environ.get(name)
    if not value:
        return default
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _path_from_env(name: str, default: str) -> str:
    raw_path = os.environ.get(name, default)
    path = Path(raw_path)
    if not path.is_absolute():
        path = BASE_DIR / path
    return str(path)


def _sqlite_uri(filename: str) -> str:
    return f"sqlite:///{BASE_DIR / 'instance' / filename}"


def _runtime_secret() -> str:
    return os.environ.get("SECRET_KEY") or secrets.token_urlsafe(64)


class BaseConfig:
    # ── ADZUNA JOB API ──
    ADZUNA_APP_ID = os.environ.get("ADZUNA_APP_ID", "")
    ADZUNA_APP_KEY = os.environ.get("ADZUNA_APP_KEY", "")
    ADZUNA_COUNTRY = os.environ.get("ADZUNA_COUNTRY", "in")
    ADZUNA_MAX_RESULTS = _env_int("ADZUNA_MAX_RESULTS", 20)
    
    # ── ADMIN ──
    ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "")

    APP_NAME = os.environ.get("APP_NAME", "Paswan Resume Builder")
    ENVIRONMENT = os.environ.get("FLASK_ENV", "production")
    DEBUG = False
    TESTING = False

    SECRET_KEY = _runtime_secret()
    WTF_CSRF_SECRET_KEY = os.environ.get("WTF_CSRF_SECRET_KEY") or SECRET_KEY
    WTF_CSRF_TIME_LIMIT = _env_int("WTF_CSRF_TIME_LIMIT", 3600)

    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL",
        _sqlite_uri("paswan_resume_builder.sqlite3"),
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": _env_int("DB_POOL_RECYCLE_SECONDS", 280),
    }

    MAX_CONTENT_LENGTH = _env_int("MAX_UPLOAD_BYTES", 5 * 1024 * 1024)
    ALLOWED_RESUME_EXTENSIONS = frozenset(_env_csv("ALLOWED_RESUME_EXTENSIONS", ("pdf", "docx")))
    ALLOWED_RESUME_MIME_TYPES = frozenset(
        _env_csv(
            "ALLOWED_RESUME_MIME_TYPES",
            (
                "application/pdf",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ),
        )
    )

    UPLOAD_ROOT = _path_from_env("UPLOAD_ROOT", "uploads")
    RESUME_UPLOAD_FOLDER = _path_from_env("RESUME_UPLOAD_FOLDER", "uploads/resumes")
    AVATAR_UPLOAD_FOLDER = _path_from_env("AVATAR_UPLOAD_FOLDER", "uploads/avatars")
    GENERATED_RESUME_FOLDER = _path_from_env("GENERATED_RESUME_FOLDER", "generated_resumes")
    STORAGE_BACKEND = os.environ.get("STORAGE_BACKEND", "local")
    S3_ENDPOINT_URL = os.environ.get("S3_ENDPOINT_URL")
    S3_BUCKET_NAME = os.environ.get("S3_BUCKET_NAME")
    S3_REGION_NAME = os.environ.get("S3_REGION_NAME", "ap-south-1")
    S3_ACCESS_KEY_ID = os.environ.get("S3_ACCESS_KEY_ID")
    S3_SECRET_ACCESS_KEY = os.environ.get("S3_SECRET_ACCESS_KEY")

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = os.environ.get("SESSION_COOKIE_SAMESITE", "Lax")
    SESSION_COOKIE_SECURE = _env_bool("SESSION_COOKIE_SECURE", False)
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SECURE = _env_bool("REMEMBER_COOKIE_SECURE", False)
    PERMANENT_SESSION_LIFETIME = timedelta(days=_env_int("SESSION_LIFETIME_DAYS", 7))

    SECURITY_HEADERS = {
        "X-Frame-Options": os.environ.get("X_FRAME_OPTIONS", "DENY"),
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": os.environ.get("REFERRER_POLICY", "strict-origin-when-cross-origin"),
        "Permissions-Policy": os.environ.get(
            "PERMISSIONS_POLICY",
            "camera=(), microphone=(), geolocation=()",
        ),
    }
    
    CONTENT_SECURITY_POLICY = os.environ.get(
     "CONTENT_SECURITY_POLICY",
     "default-src 'self'; "
     "script-src 'self' 'unsafe-inline' 'unsafe-eval' "
     "https://cdn.jsdelivr.net https://cdn.jsdelivr.net/npm/; "
     "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
     "font-src 'self' https://fonts.gstatic.com; "
     "img-src 'self' data:; "
     "connect-src 'self' https://cdn.jsdelivr.net; "
     "frame-ancestors 'none'; "
     "base-uri 'self'; "
     "form-action 'self'",
    )

    RATELIMIT_STORAGE_URI = os.environ.get("RATELIMIT_STORAGE_URI", "memory://")
    RATELIMIT_DEFAULT = os.environ.get("RATELIMIT_DEFAULT", "200 per day;50 per hour")
    AUTH_LOGIN_RATE_LIMIT = os.environ.get("AUTH_LOGIN_RATE_LIMIT", "5 per minute")
    AI_RATE_LIMIT = os.environ.get("AI_RATE_LIMIT", "20 per hour")

    REDIS_URL = os.environ.get("REDIS_URL", "memory://")
    CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", "memory://")
    CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", "memory://")
    CELERY_TASK_ALWAYS_EAGER = _env_bool("CELERY_TASK_ALWAYS_EAGER", True)  # No worker needed
    CELERY_TASK_TIME_LIMIT = _env_int("CELERY_TASK_TIME_LIMIT", 300)
    CELERY_TASK_SOFT_TIME_LIMIT = _env_int("CELERY_TASK_SOFT_TIME_LIMIT", 240)

    MAIL_SERVER = os.environ.get("MAIL_SERVER", "localhost")
    MAIL_PORT = _env_int("MAIL_PORT", 1025)
    MAIL_USE_TLS = _env_bool("MAIL_USE_TLS", False)
    MAIL_USE_SSL = _env_bool("MAIL_USE_SSL", False)
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD")
    MAIL_DEFAULT_SENDER = os.environ.get("MAIL_DEFAULT_SENDER", "noreply@paswan-resume-builder.local")
    MAIL_SUPPRESS_SEND = _env_bool("MAIL_SUPPRESS_SEND", False)

    EMAIL_VERIFICATION_TOKEN_MAX_AGE_SECONDS = _env_int(
        "EMAIL_VERIFICATION_TOKEN_MAX_AGE_SECONDS",
        24 * 60 * 60,
    )
    PASSWORD_RESET_TOKEN_MAX_AGE_SECONDS = _env_int(
        "PASSWORD_RESET_TOKEN_MAX_AGE_SECONDS",
        60 * 60,
    )

    AI_ENABLED = _env_bool("AI_ENABLED", False)
    AI_PROVIDER = os.environ.get("AI_PROVIDER", "openrouter")
    AI_API_KEY = os.environ.get("AI_API_KEY")
    AI_BASE_URL = os.environ.get("AI_BASE_URL", "https://openrouter.ai/api/v1")
    AI_MODEL = os.environ.get("AI_MODEL", "openai/gpt-4o-mini")
    GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
    AI_TIMEOUT_SECONDS = _env_int("AI_TIMEOUT_SECONDS", 45)
    AI_CACHE_TTL_SECONDS = _env_int("AI_CACHE_TTL_SECONDS", 30 * 24 * 60 * 60)

    RAZORPAY_KEY_ID = os.environ.get("RAZORPAY_KEY_ID")
    RAZORPAY_KEY_SECRET = os.environ.get("RAZORPAY_KEY_SECRET")
    RAZORPAY_WEBHOOK_SECRET = os.environ.get("RAZORPAY_WEBHOOK_SECRET")
    STRIPE_PUBLISHABLE_KEY = os.environ.get("STRIPE_PUBLISHABLE_KEY")
    STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY")
    STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET")
    PAYMENT_CURRENCY = os.environ.get("PAYMENT_CURRENCY", "INR")

    # ── GOOGLE OAUTH ──
    GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
    GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")

    FREE_PLAN_RESUME_LIMIT = _env_int("FREE_PLAN_RESUME_LIMIT", 3)
    FREE_PLAN_VERSION_LIMIT = _env_int("FREE_PLAN_VERSION_LIMIT", 3)
    PRO_PLAN_RESUME_LIMIT = _env_int("PRO_PLAN_RESUME_LIMIT", 0)
    PRO_PLAN_VERSION_LIMIT = _env_int("PRO_PLAN_VERSION_LIMIT", 0)

    JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY") or SECRET_KEY
    JWT_ALGORITHM = os.environ.get("JWT_ALGORITHM", "HS256")
    JWT_ISSUER = os.environ.get("JWT_ISSUER", "paswan-resume-builder")
    JWT_AUDIENCE = os.environ.get("JWT_AUDIENCE", "paswan-resume-builder-api")
    JWT_EXPIRATION_MINUTES = _env_int("JWT_EXPIRATION_MINUTES", 30)

    LOG_DIR = _path_from_env("LOG_DIR", "logs")
    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
    APP_LOG_FILE = _path_from_env("APP_LOG_FILE", "logs/app.log")
    ERROR_LOG_FILE = _path_from_env("ERROR_LOG_FILE", "logs/error.log")
    SECURITY_LOG_FILE = _path_from_env("SECURITY_LOG_FILE", "logs/security.log")
    LOG_RETENTION_DAYS = _env_int("LOG_RETENTION_DAYS", 14)
    LOG_BACKUP_COUNT = _env_int("LOG_BACKUP_COUNT", 30)

    HEALTH_CHECK_DATABASE_TIMEOUT_SECONDS = _env_int("HEALTH_CHECK_DATABASE_TIMEOUT_SECONDS", 2)

    @classmethod
    def init_app(cls, app) -> None:
        Path(app.instance_path).mkdir(parents=True, exist_ok=True)
        for directory in (
            cls.LOG_DIR,
            cls.UPLOAD_ROOT,
            cls.RESUME_UPLOAD_FOLDER,
            cls.AVATAR_UPLOAD_FOLDER,
            cls.GENERATED_RESUME_FOLDER,
        ):
            Path(directory).mkdir(parents=True, exist_ok=True)


class DevelopmentConfig(BaseConfig):
    ENVIRONMENT = "development"
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL",
        _sqlite_uri("paswan_resume_builder_dev.sqlite3"),
    )
    MAIL_SUPPRESS_SEND = _env_bool("MAIL_SUPPRESS_SEND", True)
    # ✅ AI enabled by default for local testing
    AI_ENABLED = True


class TestingConfig(BaseConfig):
    ENVIRONMENT = "testing"
    TESTING = True
    WTF_CSRF_ENABLED = _env_bool("WTF_CSRF_ENABLED", False)
    SQLALCHEMY_DATABASE_URI = os.environ.get("TEST_DATABASE_URL", "sqlite:///:memory:")
    CELERY_TASK_ALWAYS_EAGER = True
    MAIL_SUPPRESS_SEND = True
    RATELIMIT_ENABLED = _env_bool("RATELIMIT_ENABLED", False)
    SERVER_NAME = os.environ.get("TEST_SERVER_NAME", "localhost.test")


class ProductionConfig(BaseConfig):
    ENVIRONMENT = "production"
    SESSION_COOKIE_SECURE = False
    REMEMBER_COOKIE_SECURE = True
    PREFERRED_URL_SCHEME = "https"
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL")
    RATELIMIT_STORAGE_URI = os.environ.get("RATELIMIT_STORAGE_URI", "memory://")

    @classmethod
    def init_app(cls, app) -> None:
        super().init_app(app)
        required_env = (
            "SECRET_KEY",
            "DATABASE_URL",
            "MAIL_SERVER",
            "MAIL_DEFAULT_SENDER",
        )
        missing = [name for name in required_env if not os.environ.get(name)]
        if missing:
            joined = ", ".join(sorted(missing))
            raise RuntimeError(f"Missing required production environment variables: {joined}")


config_by_name = {
    "development": DevelopmentConfig,
    "dev": DevelopmentConfig,
    "testing": TestingConfig,
    "test": TestingConfig,
    "production": ProductionConfig,
    "prod": ProductionConfig,
    "default": DevelopmentConfig,
}


def get_config(config_name: str | None = None) -> type[BaseConfig]:
    selected = config_name or os.environ.get("FLASK_CONFIG") or os.environ.get("FLASK_ENV") or "default"
    return config_by_name.get(selected.lower(), DevelopmentConfig)