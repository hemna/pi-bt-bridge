"""KISS TNC protocol models and parser."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import IntEnum
from typing import Final

# KISS protocol constants
FEND: Final[int] = 0xC0  # Frame End delimiter
FESC: Final[int] = 0xDB  # Frame Escape character
TFEND: Final[int] = 0xDC  # Transposed Frame End (FESC + TFEND = FEND in data)
TFESC: Final[int] = 0xDD  # Transposed Frame Escape (FESC + TFESC = FESC in data)

MAX_FRAME_SIZE: Final[int] = 4096  # Maximum frame size in bytes
MAX_PORT: Final[int] = 15  # Maximum port number (4-bit value)


class KISSCommand(IntEnum):
    """
    KISS protocol command types.

    The command byte contains port number in high nibble (0-15)
    and command type in low nibble.
    """

    DATA_FRAME = 0x00
    """AX.25 frame data to/from TNC."""

    TX_DELAY = 0x01
    """Transmitter keyup delay in 10ms units."""

    PERSISTENCE = 0x02
    """CSMA persistence parameter (P value, 0-255)."""

    SLOT_TIME = 0x03
    """CSMA slot time interval in 10ms units."""

    TX_TAIL = 0x04
    """Time to hold TX after frame in 10ms units."""

    FULL_DUPLEX = 0x05
    """0=half duplex (default), non-zero=full duplex."""

    SET_HARDWARE = 0x06
    """TNC-specific hardware configuration."""

    RETURN = 0xFF
    """Exit KISS mode, return to TNC command mode."""


@dataclass
class KISSFrame:
    """
    A complete KISS protocol frame.

    Attributes:
        port: TNC port number (0-15).
        command: Frame command type.
        data: Frame payload (unescaped).
        raw: Original escaped frame bytes for passthrough.
        timestamp: Frame creation/reception time (UTC).
    """

    port: int
    command: KISSCommand
    data: bytes
    raw: bytes = field(default=b"", repr=False)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        """Validate frame fields."""
        if not 0 <= self.port <= MAX_PORT:
            raise ValueError(f"Port must be 0-{MAX_PORT}, got {self.port}")
        if len(self.data) > MAX_FRAME_SIZE:
            raise ValueError(f"Data exceeds maximum size ({len(self.data)} > {MAX_FRAME_SIZE})")

    @classmethod
    def from_bytes(cls, data: bytes, port: int = 0) -> KISSFrame:
        """Create a DATA_FRAME from raw payload bytes."""
        return cls(
            port=port,
            command=KISSCommand.DATA_FRAME,
            data=data,
        )

    def encode(self) -> bytes:
        """
        Encode frame to KISS wire format with FEND delimiters and escaping.

        Returns:
            Escaped frame bytes ready for transmission.
        """
        output = bytearray([FEND])

        # Command byte: (port << 4) | command
        cmd_byte = (self.port << 4) | (self.command & 0x0F)
        output.append(cmd_byte)

        # Escape data bytes
        for byte in self.data:
            if byte == FEND:
                output.extend([FESC, TFEND])
            elif byte == FESC:
                output.extend([FESC, TFESC])
            else:
                output.append(byte)

        output.append(FEND)
        return bytes(output)


class KISSParser:
    """
    Stateful parser for KISS frame extraction from byte stream.

    Implements the FEND/FESC state machine for parsing KISS frames
    from a continuous byte stream (e.g., from BLE or SPP).

    Usage:
        parser = KISSParser()
        frames = parser.feed(incoming_bytes)
        for frame in frames:
            process(frame)
    """

    def __init__(self, max_buffer_size: int = MAX_FRAME_SIZE) -> None:
        """
        Initialize the parser.

        Args:
            max_buffer_size: Maximum buffer size before discarding frame.
        """
        self._buffer: bytearray = bytearray()
        self._raw_buffer: bytearray = bytearray()
        self._in_frame: bool = False
        self._escape_next: bool = False
        self._max_buffer_size: int = max_buffer_size

    def reset(self) -> None:
        """Clear parser state (use after protocol errors)."""
        self._buffer.clear()
        self._raw_buffer.clear()
        self._in_frame = False
        self._escape_next = False

    def feed(self, data: bytes) -> list[KISSFrame]:
        """
        Process incoming bytes and return any complete frames.

        Args:
            data: Incoming bytes from connection.

        Returns:
            List of complete KISSFrame objects extracted from the stream.
        """
        frames: list[KISSFrame] = []

        for byte in data:
            frame = self._process_byte(byte)
            if frame is not None:
                frames.append(frame)

        return frames

    def _process_byte(self, byte: int) -> KISSFrame | None:
        """
        Process a single byte through the state machine.

        Returns:
            A complete KISSFrame if one was finished, None otherwise.
        """
        # Track raw bytes for passthrough
        if self._in_frame:
            self._raw_buffer.append(byte)

        # Handle FEND (frame delimiter)
        if byte == FEND:
            if self._in_frame and len(self._buffer) > 0:
                # End of frame - emit it
                frame = self._emit_frame()
                self._start_new_frame()
                return frame
            else:
                # Start of frame (or multiple FENDs for sync)
                self._start_new_frame()
            return None

        # Not in frame yet - ignore bytes until FEND
        if not self._in_frame:
            return None

        # Handle escape sequences
        if self._escape_next:
            self._escape_next = False
            if byte == TFEND:
                self._buffer.append(FEND)
            elif byte == TFESC:
                self._buffer.append(FESC)
            else:
                # Invalid escape - discard byte, log warning would go here
                pass
            return None

        if byte == FESC:
            self._escape_next = True
            return None

        # Regular data byte
        self._buffer.append(byte)

        # Check for buffer overflow
        if len(self._buffer) > self._max_buffer_size:
            # Frame too large - discard and reset
            self.reset()

        return None

    def _start_new_frame(self) -> None:
        """Initialize state for a new frame."""
        self._buffer.clear()
        self._raw_buffer.clear()
        self._raw_buffer.append(FEND)  # Include leading FEND
        self._in_frame = True
        self._escape_next = False

    def _emit_frame(self) -> KISSFrame | None:
        """
        Create a KISSFrame from the current buffer.

        Returns:
            KISSFrame if buffer contains valid frame, None if empty/invalid.
        """
        if len(self._buffer) < 1:
            return None

        # Extract command byte
        cmd_byte = self._buffer[0]
        port = (cmd_byte >> 4) & 0x0F
        command_value = cmd_byte & 0x0F

        # Handle special case for RETURN command (0xFF)
        if cmd_byte == 0xFF:
            command = KISSCommand.RETURN
            port = 0
        else:
            try:
                command = KISSCommand(command_value)
            except ValueError:
                # Unknown command - treat as DATA_FRAME
                command = KISSCommand.DATA_FRAME

        # Extract data (everything after command byte)
        data = bytes(self._buffer[1:])
        raw = bytes(self._raw_buffer)

        try:
            return KISSFrame(
                port=port,
                command=command,
                data=data,
                raw=raw,
            )
        except ValueError:
            # Invalid frame - return None
            return None

    @property
    def in_frame(self) -> bool:
        """Check if parser is currently inside a frame."""
        return self._in_frame

    @property
    def buffer_size(self) -> int:
        """Get current buffer size."""
        return len(self._buffer)
