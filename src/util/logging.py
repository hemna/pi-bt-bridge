"""Structured logging setup for the BT bridge daemon."""

from __future__ import annotations

import logging
import sys
from datetime import UTC, datetime
from typing import Any

# Custom log format with structured fields
LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


class StructuredFormatter(logging.Formatter):
    """
    Custom formatter that adds structured context to log messages.

    Supports adding key=value pairs to log messages for easier parsing.
    """

    def format(self, record: logging.LogRecord) -> str:
        """Format the log record with structured fields."""
        # Add UTC timestamp
        record.asctime = datetime.now(UTC).strftime(DATE_FORMAT)

        # Format structured data if present
        if hasattr(record, "structured_data") and record.structured_data:
            data = record.structured_data
            pairs = " ".join(f"{k}={v}" for k, v in data.items())
            record.msg = f"{record.msg} | {pairs}"

        return super().format(record)


def setup_logging(
    level: str = "INFO",
    log_file: str | None = None,
    name: str = "bt-bridge",
) -> logging.Logger:
    """
    Configure logging for the daemon.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR).
        log_file: Optional log file path. None for stdout only.
        name: Logger name.

    Returns:
        Configured logger instance.
    """
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Remove existing handlers
    logger.handlers.clear()

    # Create formatter
    formatter = StructuredFormatter(LOG_FORMAT, DATE_FORMAT)

    # Console handler (always enabled)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler (optional)
    if log_file:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    # Don't propagate to root logger
    logger.propagate = False

    return logger


def get_logger(name: str = "bt-bridge") -> logging.Logger:
    """
    Get a logger instance by name.

    Args:
        name: Logger name (will be prefixed with 'bt-bridge.' if not already).

    Returns:
        Logger instance.
    """
    if not name.startswith("bt-bridge"):
        name = f"bt-bridge.{name}"
    return logging.getLogger(name)


def log_with_context(
    logger: logging.Logger,
    level: int,
    message: str,
    **context: Any,
) -> None:
    """
    Log a message with structured context data.

    Args:
        logger: Logger instance.
        level: Log level (e.g., logging.INFO).
        message: Log message.
        **context: Key-value pairs to include in log.
    """
    record = logger.makeRecord(
        logger.name,
        level,
        "(unknown file)",
        0,
        message,
        (),
        None,
    )
    record.structured_data = context  # type: ignore[attr-defined]
    logger.handle(record)


# Convenience functions for structured logging
def log_frame_bridged(
    logger: logging.Logger,
    direction: str,
    size: int,
    latency_ms: float | None = None,
) -> None:
    """Log a frame bridging event."""
    context: dict[str, Any] = {
        "direction": direction,
        "size": size,
    }
    if latency_ms is not None:
        context["latency_ms"] = f"{latency_ms:.2f}"

    log_with_context(logger, logging.INFO, "Frame bridged", **context)


def log_connection_state(
    logger: logging.Logger,
    connection_type: str,
    old_state: str,
    new_state: str,
    device: str | None = None,
) -> None:
    """Log a connection state change."""
    context: dict[str, Any] = {
        "type": connection_type,
        "old_state": old_state,
        "new_state": new_state,
    }
    if device:
        context["device"] = device

    log_with_context(logger, logging.INFO, "Connection state changed", **context)


def log_error_with_remediation(
    logger: logging.Logger,
    error_type: str,
    message: str,
    remediation: str | None = None,
    source: str | None = None,
) -> None:
    """Log an error with remediation suggestion."""
    context: dict[str, Any] = {
        "error_type": error_type,
    }
    if source:
        context["source"] = source
    if remediation:
        context["remediation"] = remediation

    log_with_context(logger, logging.ERROR, message, **context)
