from __future__ import annotations

import hashlib
import json
import logging
import re
import sys
import time
import uuid
from datetime import datetime, timezone
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Any

from flask import Flask, g, has_request_context, request


SENSITIVE_KEYWORDS = (
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "authorization",
    "cookie",
    "set-cookie",
    "razorpay_key_secret",
    "stripe_secret_key",
)
TOKEN_PATTERN = re.compile(r"(?i)(token|secret|password|api[_-]?key)=([^&\s]+)")
EMAIL_PATTERN = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
LONG_SECRET_PATTERN = re.compile(r"\b[A-Za-z0-9_\-]{32,}\b")


class SensitiveDataFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, dict):
            record.args = {key: _redact_if_sensitive(key, value) for key, value in record.args.items()}
        elif isinstance(record.args, tuple):
            record.args = tuple(_sanitize_value(value) for value in record.args)
        return True


class RequestContextFilter(logging.Filter):
    def __init__(self, app: Flask) -> None:
        super().__init__()
        self.app = app

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = None
        record.remote_addr_hash = None
        record.method = None
        record.path = None
        record.endpoint = None
        record.user_id = None

        if has_request_context():
            request_id = getattr(g, "request_id", None)
            record.request_id = request_id
            record.method = request.method
            record.path = _route_pattern()
            record.endpoint = request.endpoint
            record.remote_addr_hash = _hash_remote_addr(self.app, request.headers.get("X-Forwarded-For", request.remote_addr))
            record.user_id = _current_user_id()

        return True


class JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": _sanitize_value(record.getMessage()),
            "module": record.module,
            "line": record.lineno,
            "process": record.process,
            "thread": record.threadName,
        }

        for attr in ("request_id", "remote_addr_hash", "method", "path", "endpoint", "user_id"):
            value = getattr(record, attr, None)
            if value is not None:
                payload[attr] = value

        extras = _record_extras(record)
        if extras:
            payload["extra"] = extras

        if record.exc_info:
            payload["exception"] = _sanitize_value(self.formatException(record.exc_info))

        if record.stack_info:
            payload["stack"] = _sanitize_value(self.formatStack(record.stack_info))

        return json.dumps(payload, ensure_ascii=True, separators=(",", ":"))


def setup_logging(app: Flask) -> None:
    if getattr(app, "_paswan_logging_configured", False):
        return

    log_dir = Path(app.config["LOG_DIR"])
    log_dir.mkdir(parents=True, exist_ok=True)

    level = logging.getLevelName(app.config.get("LOG_LEVEL", "INFO").upper())
    if not isinstance(level, int):
        level = logging.INFO

    formatter = JsonLogFormatter()
    request_filter = RequestContextFilter(app)
    sensitive_filter = SensitiveDataFilter()

    app_handler = _rotating_file_handler(
        app.config["APP_LOG_FILE"],
        level,
        formatter,
        app.config["LOG_BACKUP_COUNT"],
    )
    error_handler = _rotating_file_handler(
        app.config["ERROR_LOG_FILE"],
        logging.ERROR,
        formatter,
        app.config["LOG_BACKUP_COUNT"],
    )
    security_handler = _rotating_file_handler(
        app.config["SECURITY_LOG_FILE"],
        logging.INFO,
        formatter,
        app.config["LOG_BACKUP_COUNT"],
    )
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)

    for handler in (app_handler, error_handler, security_handler, console_handler):
        handler.addFilter(request_filter)
        handler.addFilter(sensitive_filter)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.handlers.clear()
    root_logger.addHandler(app_handler)
    root_logger.addHandler(error_handler)
    root_logger.addHandler(console_handler)

    security_logger = logging.getLogger("paswan.security")
    security_logger.setLevel(logging.INFO)
    security_logger.handlers.clear()
    security_logger.addHandler(security_handler)
    security_logger.propagate = False

    app.logger.handlers.clear()
    app.logger.setLevel(level)
    app.logger.propagate = True

    _register_request_logging(app)
    app._paswan_logging_configured = True
    app.logger.info(
        "logging_configured",
        extra={
            "event": "logging_configured",
            "environment": app.config.get("ENVIRONMENT"),
            "log_level": logging.getLevelName(level),
        },
    )


def get_security_logger() -> logging.Logger:
    return logging.getLogger("paswan.security")


def _register_request_logging(app: Flask) -> None:
    @app.before_request
    def assign_request_context() -> None:
        g.request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        g.request_started_at = time.perf_counter()

    @app.after_request
    def log_request_summary(response):
        duration_ms = None
        started_at = getattr(g, "request_started_at", None)
        if started_at is not None:
            duration_ms = round((time.perf_counter() - started_at) * 1000, 2)

        response.headers["X-Request-ID"] = getattr(g, "request_id", "")
        app.logger.info(
            "request_completed",
            extra={
                "event": "request_completed",
                "status_code": response.status_code,
                "duration_ms": duration_ms,
                "content_length": response.calculate_content_length(),
            },
        )
        return response


def _rotating_file_handler(
    filename: str,
    level: int,
    formatter: logging.Formatter,
    backup_count: int,
) -> TimedRotatingFileHandler:
    path = Path(filename)
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = TimedRotatingFileHandler(
        filename=path,
        when="midnight",
        interval=1,
        backupCount=backup_count,
        encoding="utf-8",
        utc=True,
    )
    handler.setLevel(level)
    handler.setFormatter(formatter)
    return handler


def _route_pattern() -> str | None:
    if request.url_rule is not None:
        return request.url_rule.rule
    return _sanitize_value(request.path)


def _current_user_id() -> int | None:
    try:
        from flask_login import current_user
    except ModuleNotFoundError:
        return None

    if getattr(current_user, "is_authenticated", False):
        user_id = getattr(current_user, "id", None)
        return int(user_id) if user_id is not None else None
    return None


def _hash_remote_addr(app: Flask, remote_addr: str | None) -> str | None:
    if not remote_addr:
        return None
    first_addr = remote_addr.split(",", 1)[0].strip()
    salt = app.config.get("SECRET_KEY", "")
    digest = hashlib.sha256(f"{salt}:{first_addr}".encode("utf-8")).hexdigest()
    return digest[:24]


def _record_extras(record: logging.LogRecord) -> dict[str, Any]:
    standard = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__)
    standard.update({"request_id", "remote_addr_hash", "method", "path", "endpoint", "user_id"})
    extras: dict[str, Any] = {}
    for key, value in record.__dict__.items():
        if key in standard or key.startswith("_"):
            continue
        sanitized = _redact_if_sensitive(key, value)
        extras[key] = _json_safe(sanitized)
    return extras


def _redact_if_sensitive(key: str, value: Any) -> Any:
    lowered = key.lower()
    if any(keyword in lowered for keyword in SENSITIVE_KEYWORDS):
        return "[REDACTED]"
    return _sanitize_value(value)


def _sanitize_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, dict):
        return {str(key): _redact_if_sensitive(str(key), item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_sanitize_value(item) for item in value]

    text = str(value)
    text = TOKEN_PATTERN.sub(r"\1=[REDACTED]", text)
    text = EMAIL_PATTERN.sub("[EMAIL_REDACTED]", text)
    text = LONG_SECRET_PATTERN.sub("[SECRET_REDACTED]", text)
    return text


def _json_safe(value: Any) -> Any:
    try:
        json.dumps(value)
    except (TypeError, ValueError):
        return str(value)
    return value
