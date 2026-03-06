"""Bridge service for bidirectional KISS frame forwarding.

Supports TNCs that use standard KISS framing (0xC0) as well as
radios that use HDLC-style framing (0x7E), with automatic protocol
detection.
"""

from __future__ import annotations

import asyncio
import logging

from src.models.hdlc import HDLCFrame, HDLCParser, detect_protocol
from src.models.kiss import KISSFrame, KISSParser
from src.models.state import BridgeState
from src.models.tnc_history import TNCProtocol
from src.services.ble_service import BLEService
from src.services.classic_service import ClassicService

logger = logging.getLogger("bt-bridge.bridge")


class BridgeService:
    """
    Main bridge service coordinating BLE and Classic connections.

    Forwards frames bidirectionally between the iPhone (BLE, always KISS)
    and TNC (Classic, KISS or HDLC depending on the radio).

    When the TNC uses HDLC framing the bridge translates:
        BLE->Classic: KISS frame -> strip KISS delimiters -> wrap in HDLC (7E)
        Classic->BLE: HDLC frame -> strip HDLC flags -> wrap in KISS (C0)
    """

    def __init__(
        self,
        ble_service: BLEService,
        classic_service: ClassicService,
        state: BridgeState | None = None,
        tnc_protocol: TNCProtocol = TNCProtocol.AUTO,
    ) -> None:
        """
        Initialize bridge service.

        Args:
            ble_service: BLE GATT service.
            classic_service: Classic SPP service.
            state: Bridge state container.
            tnc_protocol: Protocol the TNC uses (KISS, HDLC, or AUTO).
        """
        self._ble = ble_service
        self._classic = classic_service

        # Create state if not provided
        if state is None:
            self._state = BridgeState(
                ble=ble_service.connection,
                classic=classic_service.connection,
                ble_parser=KISSParser(),
                classic_parser=KISSParser(),
            )
        else:
            self._state = state

        self._running = False

        # Protocol handling for the TNC (Classic) side.
        # BLE side is ALWAYS KISS (phone app uses KISS).
        self._tnc_protocol = tnc_protocol
        self._resolved_protocol: TNCProtocol | None = (
            None if tnc_protocol == TNCProtocol.AUTO else tnc_protocol
        )
        self._hdlc_parser = HDLCParser()
        # Buffer for auto-detect: accumulate bytes until we see a delimiter
        self._detect_buffer: bytearray = bytearray()

        # Set up data callbacks
        self._ble.set_data_callback(self._handle_ble_data)
        self._classic.set_data_callback(self._handle_classic_data)

    @property
    def state(self) -> BridgeState:
        """Get bridge state."""
        return self._state

    @property
    def tnc_protocol(self) -> TNCProtocol | None:
        """Get the resolved TNC protocol (None if not yet detected)."""
        return self._resolved_protocol

    @property
    def is_fully_connected(self) -> bool:
        """Check if both connections are active."""
        return self._state.is_fully_connected

    def set_tnc_protocol(self, protocol: TNCProtocol) -> None:
        """Change the TNC protocol mode.

        Resets parsers and auto-detect state.

        Args:
            protocol: New protocol to use.
        """
        self._tnc_protocol = protocol
        self._resolved_protocol = None if protocol == TNCProtocol.AUTO else protocol
        self._detect_buffer.clear()
        self._hdlc_parser.reset()
        self._state.classic_parser.reset()
        logger.info("TNC protocol set to %s", protocol.value)

    async def start(self) -> None:
        """Start the bridge service."""
        logger.info("Starting bridge service (TNC protocol: %s)", self._tnc_protocol.value)
        self._running = True

        # Start both services
        await asyncio.gather(
            self._ble.start(),
            self._classic.start(),
        )

        logger.info("Bridge service started")

    async def stop(self) -> None:
        """Stop the bridge service."""
        logger.info("Stopping bridge service")
        self._running = False

        # Stop both services
        await asyncio.gather(
            self._ble.stop(),
            self._classic.stop(),
        )

        logger.info("Bridge service stopped")

    # --- BLE (phone) side: always KISS ---

    def _handle_ble_data(self, data: bytes) -> None:
        """Handle data received from BLE (iPhone -> TNC).

        The phone always sends KISS frames. If the TNC expects HDLC
        framing, we translate before forwarding.
        """
        frames = self._state.ble_parser.feed(data)

        for frame in frames:
            self._forward_to_classic(frame)

    # --- Classic (TNC) side: KISS or HDLC ---

    def _handle_classic_data(self, data: bytes) -> None:
        """Handle data received from Classic (TNC -> iPhone).

        If auto-detect is pending, buffer data until we can determine
        the protocol. Then parse with the appropriate parser.
        """
        # Auto-detect if needed
        if self._resolved_protocol is None:
            self._detect_buffer.extend(data)
            detected = detect_protocol(self._detect_buffer)
            if detected == "unknown":
                # Need more data
                if len(self._detect_buffer) > 1024:
                    # Too much data without a delimiter - default to KISS
                    logger.warning(
                        "Could not auto-detect TNC protocol after %d bytes, defaulting to KISS",
                        len(self._detect_buffer),
                    )
                    self._resolved_protocol = TNCProtocol.KISS
                else:
                    return
            elif detected == "kiss":
                self._resolved_protocol = TNCProtocol.KISS
                logger.info("Auto-detected TNC protocol: KISS (0xC0 framing)")
            else:
                self._resolved_protocol = TNCProtocol.HDLC
                logger.info("Auto-detected TNC protocol: HDLC (0x7E framing)")

            # Feed the buffered data through the correct parser
            buffered = bytes(self._detect_buffer)
            self._detect_buffer.clear()
            self._handle_classic_data(buffered)
            return

        # Parse with the resolved protocol
        if self._resolved_protocol == TNCProtocol.HDLC:
            self._handle_classic_hdlc(data)
        else:
            self._handle_classic_kiss(data)

    def _handle_classic_kiss(self, data: bytes) -> None:
        """Parse Classic data as KISS and forward to BLE."""
        frames = self._state.classic_parser.feed(data)
        for frame in frames:
            self._forward_to_ble_kiss(frame)

    def _handle_classic_hdlc(self, data: bytes) -> None:
        """Parse Classic data as HDLC and forward to BLE as KISS."""
        hdlc_frames = self._hdlc_parser.feed(data)
        for hdlc_frame in hdlc_frames:
            kiss_frame = hdlc_frame.to_kiss_frame()
            self._forward_to_ble_kiss(kiss_frame)

    # --- Forwarding ---

    def _forward_to_classic(self, frame: KISSFrame) -> None:
        """Forward a KISS frame from BLE to the Classic connection.

        If the TNC uses HDLC, translates the frame first.
        """
        if not self._classic.is_connected:
            logger.warning("Cannot forward to Classic: not connected")
            return

        protocol = self._resolved_protocol or TNCProtocol.KISS

        if protocol == TNCProtocol.HDLC:
            hdlc_frame = HDLCFrame.from_kiss_frame(frame)
            encoded = hdlc_frame.encode()
            proto_label = "HDLC"
        else:
            encoded = frame.encode()
            proto_label = "KISS"

        async def _send_with_error_handling() -> None:
            try:
                await self._classic.send_data(encoded)
            except Exception:
                logger.exception("Error sending data to Classic")

        asyncio.create_task(_send_with_error_handling())
        self._state.frames_bridged += 1

        logger.debug(
            "Bridged frame BLE->Classic [%s]: %d bytes (port=%d cmd=%s)",
            proto_label,
            len(frame.data),
            frame.port,
            frame.command.name,
        )

    def _forward_to_ble_kiss(self, frame: KISSFrame) -> None:
        """Forward a KISS frame to the BLE connection (always KISS)."""
        if not self._ble.is_connected:
            logger.warning("Cannot forward to BLE: not connected")
            return

        encoded = frame.encode()

        async def _send_with_error_handling() -> None:
            try:
                await self._ble.send_data(encoded)
            except Exception:
                logger.exception("Error sending data to BLE")

        asyncio.create_task(_send_with_error_handling())
        self._state.frames_bridged += 1

        logger.debug(
            "Bridged frame Classic->BLE [KISS]: %d bytes (port=%d cmd=%s)",
            len(frame.data),
            frame.port,
            frame.command.name,
        )

    def get_status(self) -> dict[str, object]:
        """Get current bridge status as dictionary."""
        status = self._state.to_status_dict()
        status["tnc_protocol"] = (
            self._resolved_protocol.value if self._resolved_protocol else "detecting"
        )
        return status
