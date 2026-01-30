"""Logging configuration."""

from __future__ import annotations

import logging
import sys
from typing import Optional

from rich.logging import RichHandler


_loggers: dict[str, logging.Logger] = {}


def setup_logger(name: str, level: str = "INFO") -> logging.Logger:
    """
    Configure logger with Rich handler.

    Args:
        name: Logger name
        level: Logging level

    Returns:
        Configured logger
    """
    if name in _loggers:
        return _loggers[name]

    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True)],
    )

    logger = logging.getLogger(name)
    _loggers[name] = logger

    return logger


def get_logger(name: str, level: Optional[str] = None) -> logging.Logger:
    """
    Get or create a logger.

    Args:
        name: Logger name
        level: Optional logging level

    Returns:
        Logger instance
    """
    if name in _loggers:
        return _loggers[name]

    return setup_logger(name, level or "INFO")


def setup_logging(level: str = "INFO") -> None:
    """
    Set up global logging configuration.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR)
    """
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True)],
        force=True
    )

    # Update all existing loggers
    for logger in _loggers.values():
        logger.setLevel(getattr(logging, level.upper()))
