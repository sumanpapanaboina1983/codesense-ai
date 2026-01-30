"""Enhanced logging configuration with structured output and progress tracking."""

from __future__ import annotations

import logging
import sys
import time
import json
from contextlib import contextmanager
from datetime import datetime
from typing import Optional, Any, Generator
from functools import wraps

from rich.logging import RichHandler
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

# Global console for rich output
console = Console()

_loggers: dict[str, logging.Logger] = {}

# ANSI color codes for non-rich environments
COLORS = {
    "RESET": "\033[0m",
    "BOLD": "\033[1m",
    "RED": "\033[31m",
    "GREEN": "\033[32m",
    "YELLOW": "\033[33m",
    "BLUE": "\033[34m",
    "MAGENTA": "\033[35m",
    "CYAN": "\033[36m",
}


class StructuredFormatter(logging.Formatter):
    """Custom formatter that outputs structured log messages."""

    def format(self, record: logging.LogRecord) -> str:
        # Add timestamp
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

        # Get level color
        level_colors = {
            "DEBUG": COLORS["CYAN"],
            "INFO": COLORS["GREEN"],
            "WARNING": COLORS["YELLOW"],
            "ERROR": COLORS["RED"],
            "CRITICAL": COLORS["RED"] + COLORS["BOLD"],
        }
        level_color = level_colors.get(record.levelname, "")

        # Format the message
        base_msg = f"{timestamp} | {level_color}{record.levelname:8}{COLORS['RESET']} | {record.name} | {record.getMessage()}"

        # Add extra context if available
        if hasattr(record, 'extra_context') and record.extra_context:
            context_str = json.dumps(record.extra_context, default=str)
            base_msg += f" | {COLORS['CYAN']}{context_str}{COLORS['RESET']}"

        return base_msg


class ProgressLogger:
    """Logger wrapper with progress tracking capabilities."""

    def __init__(self, logger: logging.Logger, component: str):
        self.logger = logger
        self.component = component
        self._start_times: dict[str, float] = {}
        self._step_counts: dict[str, int] = {}

    def start_operation(self, operation: str, details: str = "") -> None:
        """Log the start of an operation and track timing."""
        self._start_times[operation] = time.time()
        msg = f"[START] {operation}"
        if details:
            msg += f" - {details}"
        self.logger.info(msg)

    def end_operation(self, operation: str, success: bool = True, details: str = "") -> None:
        """Log the end of an operation with duration."""
        duration = 0.0
        if operation in self._start_times:
            duration = time.time() - self._start_times[operation]
            del self._start_times[operation]

        status = "DONE" if success else "FAILED"
        msg = f"[{status}] {operation} ({duration:.2f}s)"
        if details:
            msg += f" - {details}"

        if success:
            self.logger.info(msg)
        else:
            self.logger.error(msg)

    def step(self, operation: str, step_name: str, current: int = None, total: int = None) -> None:
        """Log a step within an operation."""
        if operation not in self._step_counts:
            self._step_counts[operation] = 0
        self._step_counts[operation] += 1

        progress = ""
        if current is not None and total is not None:
            pct = (current / total) * 100
            progress = f"[{current}/{total} - {pct:.0f}%] "

        self.logger.info(f"  {progress}{step_name}")

    def progress(self, message: str, current: int, total: int) -> None:
        """Log progress with percentage."""
        pct = (current / total) * 100
        bar_len = 20
        filled = int(bar_len * current / total)
        bar = "=" * filled + "-" * (bar_len - filled)
        self.logger.info(f"  [{bar}] {pct:5.1f}% | {message}")

    def debug(self, msg: str, **context) -> None:
        """Log debug message with optional context."""
        self._log_with_context(logging.DEBUG, msg, context)

    def info(self, msg: str, **context) -> None:
        """Log info message with optional context."""
        self._log_with_context(logging.INFO, msg, context)

    def warning(self, msg: str, **context) -> None:
        """Log warning message with optional context."""
        self._log_with_context(logging.WARNING, msg, context)

    def error(self, msg: str, **context) -> None:
        """Log error message with optional context."""
        self._log_with_context(logging.ERROR, msg, context)

    def exception(self, msg: str, **context) -> None:
        """Log exception with traceback."""
        self._log_with_context(logging.ERROR, msg, context, exc_info=True)

    def _log_with_context(self, level: int, msg: str, context: dict, exc_info: bool = False) -> None:
        """Log with optional context dictionary."""
        extra = {"extra_context": context} if context else {}
        self.logger.log(level, msg, extra=extra, exc_info=exc_info)


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
        handlers=[RichHandler(rich_tracebacks=True, show_path=False)],
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


def get_progress_logger(name: str, component: str = "") -> ProgressLogger:
    """
    Get a progress-aware logger.

    Args:
        name: Logger name
        component: Component identifier for context

    Returns:
        ProgressLogger instance
    """
    logger = get_logger(name)
    return ProgressLogger(logger, component or name)


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
        handlers=[RichHandler(rich_tracebacks=True, show_path=False)],
        force=True
    )

    # Update all existing loggers
    for logger in _loggers.values():
        logger.setLevel(getattr(logging, level.upper()))


@contextmanager
def log_operation(logger: logging.Logger, operation: str, details: str = "") -> Generator[None, None, None]:
    """
    Context manager for logging operation start/end with timing.

    Usage:
        with log_operation(logger, "Processing BRD", "section: Executive Summary"):
            # do work
            pass
    """
    start_time = time.time()
    logger.info(f"[START] {operation}" + (f" - {details}" if details else ""))
    try:
        yield
        duration = time.time() - start_time
        logger.info(f"[DONE] {operation} ({duration:.2f}s)")
    except Exception as e:
        duration = time.time() - start_time
        logger.error(f"[FAILED] {operation} ({duration:.2f}s) - {str(e)}")
        raise


def log_function_call(logger: logging.Logger = None):
    """
    Decorator to log function entry/exit with arguments and timing.

    Usage:
        @log_function_call(logger)
        def my_function(arg1, arg2):
            pass
    """
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            nonlocal logger
            if logger is None:
                logger = get_logger(func.__module__)

            func_name = func.__qualname__
            # Truncate args for display
            args_str = ", ".join([str(a)[:50] for a in args[1:]])  # Skip self
            kwargs_str = ", ".join([f"{k}={str(v)[:30]}" for k, v in kwargs.items()])
            params = ", ".join(filter(None, [args_str, kwargs_str]))

            logger.debug(f"[CALL] {func_name}({params[:100]})")
            start = time.time()
            try:
                result = await func(*args, **kwargs)
                duration = time.time() - start
                result_str = str(result)[:100] if result else "None"
                logger.debug(f"[RETURN] {func_name} ({duration:.2f}s) -> {result_str}")
                return result
            except Exception as e:
                duration = time.time() - start
                logger.error(f"[EXCEPTION] {func_name} ({duration:.2f}s) - {type(e).__name__}: {e}")
                raise

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            nonlocal logger
            if logger is None:
                logger = get_logger(func.__module__)

            func_name = func.__qualname__
            args_str = ", ".join([str(a)[:50] for a in args[1:]])
            kwargs_str = ", ".join([f"{k}={str(v)[:30]}" for k, v in kwargs.items()])
            params = ", ".join(filter(None, [args_str, kwargs_str]))

            logger.debug(f"[CALL] {func_name}({params[:100]})")
            start = time.time()
            try:
                result = func(*args, **kwargs)
                duration = time.time() - start
                result_str = str(result)[:100] if result else "None"
                logger.debug(f"[RETURN] {func_name} ({duration:.2f}s) -> {result_str}")
                return result
            except Exception as e:
                duration = time.time() - start
                logger.error(f"[EXCEPTION] {func_name} ({duration:.2f}s) - {type(e).__name__}: {e}")
                raise

        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    return decorator


class LogContext:
    """Context manager for adding contextual information to logs."""

    _context: dict[str, Any] = {}

    @classmethod
    def set(cls, **kwargs) -> None:
        """Set context values."""
        cls._context.update(kwargs)

    @classmethod
    def get(cls, key: str, default: Any = None) -> Any:
        """Get a context value."""
        return cls._context.get(key, default)

    @classmethod
    def clear(cls) -> None:
        """Clear all context."""
        cls._context.clear()

    @classmethod
    @contextmanager
    def scope(cls, **kwargs) -> Generator[None, None, None]:
        """Temporarily set context values."""
        old_values = {k: cls._context.get(k) for k in kwargs}
        cls._context.update(kwargs)
        try:
            yield
        finally:
            for k, v in old_values.items():
                if v is None:
                    cls._context.pop(k, None)
                else:
                    cls._context[k] = v
