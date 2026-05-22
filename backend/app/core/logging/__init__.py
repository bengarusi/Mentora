"""Centralized logging layer for the Mentora backend.

Public surface:
    setup_logging()    -- configure console + rotating-file logging (call once at startup).
    LoggingMiddleware  -- per-request logging middleware (request_id, timing, status).

Note: this package is named ``app.core.logging`` but does NOT shadow the stdlib
``logging`` module — Python 3 absolute imports resolve a bare ``import logging``
to the top-level stdlib module, not to this package.
"""

from app.core.logging.config import setup_logging
from app.core.logging.middleware import LoggingMiddleware

__all__ = ["setup_logging", "LoggingMiddleware"]
