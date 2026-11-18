"""Opt-in console logging composition; importing this facade changes nothing."""

import logging
import sys

from platform_kit_runtime.infrastructure.console import ConsoleFormatter
from platform_kit_runtime.infrastructure.telemetry import RequestContextFilter

__all__ = ["ConsoleFormatter", "configure_console_logging"]


def configure_console_logging() -> None:
    """Replace console handlers with one INFO JSON stdout sink; never export logs.

    Repeated calls do not accumulate handlers. Call during process startup, not
    during requests. Owns root, ``app``, runtime and Uvicorn logging configuration;
    disables raw Uvicorn access records. Health access events remain DEBUG.
    Third-party loggers report WARNING and above: their messages are dropped by
    the formatter, so their INFO records (such as per-request client lines) are noise.
    """
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.INFO)
    handler.setFormatter(ConsoleFormatter())
    handler.addFilter(RequestContextFilter())
    for name in ("", "app", "platform_kit_runtime", "uvicorn", "uvicorn.error"):
        logger = logging.getLogger(name)
        logger.handlers = [handler]
        logger.setLevel(logging.WARNING if name == "" else logging.INFO)
        logger.propagate = False
    access = logging.getLogger("uvicorn.access")
    access.handlers = []
    access.propagate = False
    access.disabled = True
