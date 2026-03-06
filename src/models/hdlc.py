"""HDLC frame parser for TNC radios that use AX.25 flag-byte framing.

Some radios (e.g. VGC VR-N7600) send raw HDLC-framed data over
Bluetooth SPP using 0x7E flag bytes instead of KISS 0xC0 framing.
This module provides an HDLCParser that extracts frames delimited by
0x7E flags, and utilities to translate between KISS and HDLC framing.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Final

from src.models.kiss import FEND, KISSCommand, KISSFrame

# HDLC flag byte (AX.25 frame delimiter)
HDLC_FLAG: Final[int] = 0x7E

# Maximum frame size (same limit as KISS)
MAX_FRAME_SIZE: Final[int] = 4096

logger = logging.getLogger("bt-bridge.hdlc")


@dataclass
class HDLCFrame:
    """A raw HDLC-framed data unit.

    Attributes:
        data: Frame payload between 0x7E delimiters (may include
              a leading command/type byte depending on the radio).
        timestamp: Frame reception time (UTC).
    """

    data: bytes
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    def encode(self) -> bytes:
        """Encode frame with 0x7E flag delimiters.

        Returns:
            Bytes ready for transmission: 7E [data] 7E.
        """
        return bytes([HDLC_FLAG]) + self.data + bytes([HDLC_FLAG])

    def to_kiss_frame(self) -> KISSFrame:
        """Convert this HDLC frame to a KISS frame for the BLE side.

        The HDLC payload is treated as an opaque data blob and wrapped
        in a KISS DATA_FRAME on port 0.  If the first byte of the HDLC
        payload is 0x00 (which matches KISS port-0 DATA_FRAME), we keep
        it as-is inside the KISS data so the phone sees the original
        bytes.

        Returns:
            KISSFrame suitable for sending over BLE to the phone.
        """
        return KISSFrame(
            port=0,
            command=KISSCommand.DATA_FRAME,
            data=self.data,
        )

    @classmethod
    def from_kiss_frame(cls, frame: KISSFrame) -> HDLCFrame:
        """Create an HDLC frame from a KISS frame (phone -> radio direction).

        Takes the KISS payload (the AX.25 data) and wraps it for HDLC
        transmission.  The KISS command byte (port/type) is included
        as the first byte of the HDLC payload so the radio sees the
        same leading byte the phone intended.

        Args:
            frame: KISSFrame received from the phone via BLE.

        Returns:
            HDLCFrame ready to send to the radio via SPP.
        """
        # Re-create the command byte the phone sent: (port << 4) | cmd
        cmd_byte = (frame.port << 4) | (frame.command & 0x0F)
        return cls(data=bytes([cmd_byte]) + frame.data)


class HDLCParser:
    """Stateful parser for extracting frames delimited by 0x7E flags.

    Works like KISSParser but uses 0x7E as the frame delimiter.
    No escape-sequence handling is needed because HDLC over serial
    (non-RF) links does not use bit-stuffing.

    Usage:
        parser = HDLCParser()
        frames = parser.feed(incoming_bytes)
        for frame in frames:
            process(frame)
    """

    def __init__(self, max_buffer_size: int = MAX_FRAME_SIZE) -> None:
        """Initialize the parser.

        Args:
            max_buffer_size: Maximum buffer size before discarding frame.
        """
        self._buffer: bytearray = bytearray()
        self._in_frame: bool = False
        self._max_buffer_size: int = max_buffer_size

    def reset(self) -> None:
        """Clear parser state."""
        self._buffer.clear()
        self._in_frame = False

    def feed(self, data: bytes) -> list[HDLCFrame]:
        """Process incoming bytes and return any complete frames.

        Args:
            data: Incoming bytes from the TNC connection.

        Returns:
            List of complete HDLCFrame objects.
        """
        frames: list[HDLCFrame] = []

        for byte in data:
            frame = self._process_byte(byte)
            if frame is not None:
                frames.append(frame)

        return frames

    def _process_byte(self, byte: int) -> HDLCFrame | None:
        """Process a single byte through the state machine.

        Returns:
            An HDLCFrame if a complete frame was extracted, else None.
        """
        if byte == HDLC_FLAG:
            if self._in_frame and len(self._buffer) > 0:
                # End of frame
                frame_data = bytes(self._buffer)
                self._buffer.clear()
                # Stay in-frame (next flag is start of next frame)
                return HDLCFrame(data=frame_data)
            else:
                # Start of frame (or consecutive flags for sync)
                self._buffer.clear()
                self._in_frame = True
            return None

        if not self._in_frame:
            return None

        self._buffer.append(byte)

        if len(self._buffer) > self._max_buffer_size:
            logger.warning("HDLC frame exceeds max size, discarding")
            self.reset()

        return None

    @property
    def in_frame(self) -> bool:
        """Check if parser is currently inside a frame."""
        return self._in_frame

    @property
    def buffer_size(self) -> int:
        """Get current buffer size."""
        return len(self._buffer)


def detect_protocol(data: bytes | bytearray) -> str:
    """Auto-detect whether incoming data uses KISS or HDLC framing.

    Examines the first meaningful byte to determine the framing protocol.

    Args:
        data: First chunk of data received from the TNC.

    Returns:
        "kiss" if KISS framing detected, "hdlc" if HDLC detected,
        "unknown" if not enough data or ambiguous.
    """
    if not data:
        return "unknown"

    # Look for the first delimiter byte
    for byte in data:
        if byte == FEND:  # 0xC0 = KISS
            return "kiss"
        if byte == HDLC_FLAG:  # 0x7E = HDLC
            return "hdlc"

    return "unknown"
