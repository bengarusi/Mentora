"""Logging configuration via ``logging.config.dictConfig``.

Logs go to the console (concise format) and a UTF-8 rotating file at
``<LOG_DIR>/mentora.log`` (detailed format with filename:lineno). The level and
directory are env-configurable through ``Settings`` (LOG_LEVEL / LOG_DIR).
"""

from __future__ import annotations

import logging
import logging.config
from pathlib import Path

from app.core.config import settings

# config.py -> logging -> core -> app -> backend
_DEFAULT_LOG_DIR = Path(__file__).resolve().parents[3] / "logs"
_LOG_FILE_NAME = "mentora.log"

# Guard so repeated calls (e.g. test imports of app.main) don't reconfigure.
_CONFIGURED = False


def setup_logging(level: str | None = None, log_dir: str | None = None) -> None:
    """Configure application logging. Idempotent — safe to call more than once.

    Args take precedence over ``settings`` (LOG_LEVEL / LOG_DIR), which fall back
    to ``INFO`` and ``backend/logs/``.
    """
    global _CONFIGURED
    if _CONFIGURED:
        return

    resolved_level = (level or settings.LOG_LEVEL or "INFO").upper()
    resolved_dir = Path(log_dir or settings.LOG_DIR or _DEFAULT_LOG_DIR)
    resolved_dir.mkdir(parents=True, exist_ok=True)
    log_file = resolved_dir / _LOG_FILE_NAME

    config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "standard": {
                "format": "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
            "detailed": {
                "format": (
                    "%(asctime)s | %(levelname)-8s | %(name)s | "
                    "%(filename)s:%(lineno)d | %(message)s"
                ),
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "level": resolved_level,
                "formatter": "standard",
                "stream": "ext://sys.stdout",
            },
            "file": {
                "class": "logging.handlers.RotatingFileHandler",
                "level": resolved_level,
                "formatter": "detailed",
                "filename": str(log_file),
                "maxBytes": 5_242_880,  # 5 MB
                "backupCount": 5,
                "encoding": "utf-8",
            },
        },
        "loggers": {
            # Our application namespace — every app.* logger flows here.
            "app": {
                "handlers": ["console", "file"],
                "level": resolved_level,
                "propagate": False,
            },
            # Uvicorn: keep error/lifecycle logs, mute the per-request access log
            # since LoggingMiddleware already records every request.
            "uvicorn.error": {"level": "INFO"},
            "uvicorn.access": {"level": "WARNING"},
        },
        "root": {
            "handlers": ["console", "file"],
            "level": "WARNING",
        },
    }

    logging.config.dictConfig(config)
    _CONFIGURED = True
