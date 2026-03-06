"""Structured logging setup for the BT bridge daemon."""

from __future__ import annotations

import asyncio
import logging
import sys
import threading
from collections import deque
from datetime import UTC, datetime
from typing import Any

# Custom log format with structured fields
LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Singleton SSE log handler, set by setup_logging() when called with sse=True
_sse_log_handler: SSELogHandler | None = None


def get_sse_log_handler() -> SSELogHandler | None:
    """Get the global SSE log handler instance (if configured)."""
    return _sse_log_handler


class SSELogHandler(logging.Handler):
    """
    Logging handler that stores entries in a ring buffer and pushes to SSE consumers.

    Keeps the last ``maxlen`` formatted log entries in memory so that new
    SSE clients can receive recent history, and publishes each new entry to
    all registered async queues so they can be streamed in real time.
    """

    def __init__(self, maxlen: int = 500, level: int = logging.DEBUG) -> None:
        """
        Initialize the SSE log handler.

        Args:
            maxlen: Maximum number of log entries to retain.
            level: Minimum log level to capture.
        """
        super().__init__(level)
        self._buffer: deque[dict[str, str]] = deque(maxlen=maxlen)
        self._subscribers: list[asyncio.Queue[dict[str, str]]] = []
        self._lock = threading.Lock()

    def emit(self, record: logging.LogRecord) -> None:
        """
        Process a log record.

        Stores the formatted entry in the ring buffer and pushes it
        to all active SSE subscriber queues.
        """
        try:
            entry = self._format_entry(record)
            with self._lock:
                self._buffer.append(entry)
                for queue in self._subscribers:
                    try:
                        queue.put_nowait(entry)
                    except asyncio.QueueFull:
                        # Drop oldest entry to make room
                        try:
                            queue.get_nowait()
                        except asyncio.QueueEmpty:
                            pass
                        try:
                            queue.put_nowait(entry)
                        except asyncio.QueueFull:
                            pass
        except Exception:  # noqa: BLE001
            self.handleError(record)

    def _format_entry(self, record: logging.LogRecord) -> dict[str, str]:
        """Format a log record into a dict suitable for JSON serialisation."""
        # Use getMessage() for the raw message text (without timestamp/level prefix)
        # so the UI can format display using the structured fields.
        msg = record.getMessage()
        # Append structured data if present (mirrors StructuredFormatter behaviour)
        if hasattr(record, "structured_data") and record.structured_data:
            pairs = " ".join(f"{k}={v}" for k, v in record.structured_data.items())
            msg = f"{msg} | {pairs}"
        return {
            "timestamp": datetime.now(UTC).strftime(DATE_FORMAT),
            "level": record.levelname,
            "logger": record.name,
            "message": msg,
        }

    def get_recent(self, count: int | None = None) -> list[dict[str, str]]:
        """
        Return recent log entries from the ring buffer.

        Args:
            count: Max entries to return. ``None`` means all buffered.

        Returns:
            List of log entry dicts, oldest first.
        """
        with self._lock:
            if count is None:
                return list(self._buffer)
            return list(self._buffer)[-count:]

    def subscribe(self) -> asyncio.Queue[dict[str, str]]:
        """
        Create a new subscriber queue for real-time log streaming.

        Returns:
            An asyncio.Queue that will receive new log entries.
        """
        queue: asyncio.Queue[dict[str, str]] = asyncio.Queue(maxsize=200)
        with self._lock:
            self._subscribers.append(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[dict[str, str]]) -> None:
        """
        Remove a subscriber queue.

        Args:
            queue: The queue previously returned by ``subscribe()``.
        """
        with self._lock:
            if queue in self._subscribers:
                self._subscribers.remove(queue)


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
    sse: bool = False,
) -> logging.Logger:
    """
    Configure logging for the daemon.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR).
        log_file: Optional log file path. None for stdout only.
        name: Logger name.
        sse: If True, attach an SSELogHandler for real-time web streaming.

    Returns:
        Configured logger instance.
    """
    global _sse_log_handler  # noqa: PLW0603

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

    # SSE handler for real-time web log streaming
    if sse:
        _sse_log_handler = SSELogHandler(maxlen=500, level=logging.DEBUG)
        _sse_log_handler.setFormatter(formatter)
        logger.addHandler(_sse_log_handler)

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
