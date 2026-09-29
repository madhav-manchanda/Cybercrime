"""Structured logging built on :mod:`structlog`.

Design goals:
- single consistent JSON line format in production, pretty console in dev
- context (request_id, user, route) attached automatically via middlewares
- sensitive fields redacted **before** anything hits the sink
- async-capable through the structlog filter-based processors
"""

from __future__ import annotations

import logging
import re
import sys
from typing import Any

import structlog

from app.core.config import settings

_REDACTION_PATTERN = re.compile(
    r"((" + "|".join(settings.log_sensitive_fields) + r")\s*[=:]\s*)([^\s,\"}]+)",
    flags=re.IGNORECASE,
)


def _redact_fields(_logger: Any, method_name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    """Replace values of known sensitive keys in logs."""
    for field in settings.log_sensitive_fields:
        if field in event_dict:
            event_dict[field] = "[REDACTED]"
    # redact inline `key=value` fragments hiding inside flat messages
    if isinstance(event_dict.get("event"), str):
        event_dict["event"] = _REDACTION_PATTERN.sub(r"\1[REDACTED]", event_dict["event"])
    return event_dict


def _mask_account_numbers(_logger: Any, method_name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    """Best-effort masking of long numeric strings that look like account ids."""
    event = event_dict.get("event")
    if isinstance(event, str):
        event_dict["event"] = re.sub(r"\b\d{12,}\b", "***", event)
    return event_dict


def build_processors() -> list[Any]:
    shared: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
    ]
    if settings.debug:
        shared.append(structlog.processors.format_exc_info)
    shared.extend([_redact_fields, _mask_account_numbers])
    return shared


def configure_logging() -> None:
    """Configure structlog and the stdlib root logger."""
    level = getattr(logging, settings.log_level, logging.INFO)
    logging.basicConfig(level=level, format="%(message)s")

    structlog.configure(
        processors=[
            *build_processors(),
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            (
                structlog.dev.ConsoleRenderer()
                if settings.log_format.value == "console"
                else structlog.processors.JSONRenderer(ensure_ascii=False)
            ),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=True,
    )

    # Silence noisy library loggers
    for noisy in ("uvicorn.access", "httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine.Engine").setLevel(
        logging.DEBUG if settings.sqlalchemy_echo else logging.WARNING
    )


def get_logger(name: str) -> Any:
    return structlog.get_logger(name)


configure_logging()

__all__ = ["build_processors", "configure_logging", "get_logger"]
