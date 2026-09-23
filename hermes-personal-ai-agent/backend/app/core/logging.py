"""Structured logging with sensitive-data scrubbing.

We never log raw user payloads. Every record passes through the scrubbing
middleware first, and the formatter re-applies scrubbing as a defensive layer.
"""

from __future__ import annotations

import logging
import sys

import structlog

from app.core.config import settings
from app.middleware.scrubbing import scrub_text


def _scrub_processor(_logger, _method_name, event_dict):
    """Defense-in-depth: scrub any string values before emission."""
    for key, value in list(event_dict.items()):
        if isinstance(value, str):
            event_dict[key] = scrub_text(value)
    return event_dict


def configure_logging() -> None:
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
    )

    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        _scrub_processor,
    ]

    renderer = (
        structlog.processors.JSONRenderer()
        if settings.is_production
        else structlog.dev.ConsoleRenderer()
    )

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, settings.log_level.upper(), logging.INFO)
        ),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str):
    return structlog.get_logger(name)
