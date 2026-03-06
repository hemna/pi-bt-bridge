"""Bridge service for bidirectional KISS frame forwarding.

Supports TNCs that use standard KISS framing (0xC0) as well as
radios that use HDLC-style framing (0x7E), with automatic protocol
detection.  Fans out received TNC frames to all connected clients
(BLE and TCP KISS).
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from src.models.hdlc import HDLCFrame, HDLCParser, detect_protocol
from src.models.kiss import KISSFrame, KISSParser
from src.models.state import BridgeState
from src.models.tnc_history import TNCProtocol
from src.services.ble_service import BLEService
from src.services.classic_service import ClassicService

if TYPE_CHECKING:
    from src.services.tcp_kiss_service import TcpKissService

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
        tcp_service: TcpKissService | None = None,
    ) -> None:
        """
        Initialize bridge service.

        Args:
            ble_service: BLE GATT service.
            classic_service: Classic SPP service.
            state: Bridge state container.
            tnc_protocol: Protocol the TNC uses (KISS, HDLC, or AUTO).
            tcp_service: Optional TCP KISS server for desktop clients.
        """
        self._ble = ble_service
        self._classic = classic_service
        self._tcp = tcp_service

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

        # Register TCP KISS callback if service is available
        if self._tcp:
            self._tcp.set_data_callback(self._handle_tcp_data)

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

    @property
    def tcp_service(self) -> TcpKissService | None:
        """Get the TCP KISS service if available."""
        return self._tcp

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

        # Start both BLE and Classic services
        await asyncio.gather(
            self._ble.start(),
            self._classic.start(),
        )

        # Start TCP KISS server if available
        if self._tcp:
            await self._tcp.start()
            logger.info("TCP KISS server started on port %d", self._tcp.port)

        logger.info("Bridge service started")

    async def stop(self) -> None:
        """Stop the bridge service."""
        logger.info("Stopping bridge service")
        self._running = False

        # Stop TCP KISS server first (clients should disconnect cleanly)
        if self._tcp:
            await self._tcp.stop()

        # Stop BLE and Classic services
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
            self._forward_to_classic(frame, source="BLE")

    # --- TCP KISS side ---

    def _handle_tcp_data(self, data: bytes) -> None:
        """Handle data received from a TCP KISS client (TCP -> TNC).

        TCP clients send KISS frames. If the TNC expects HDLC
        framing, we translate before forwarding.
        """
        tcp_parser = KISSParser()
        frames = tcp_parser.feed(data)

        for frame in frames:
            logger.debug(
                "Received TCP KISS frame: %d bytes (port=%d cmd=%s)",
                len(frame.data),
                frame.port,
                frame.command.name,
            )
            self._forward_to_classic(frame, source="TCP")

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
        """Parse Classic data as KISS and forward to all clients."""
        frames = self._state.classic_parser.feed(data)
        for frame in frames:
            self._forward_to_clients(frame)

    def _handle_classic_hdlc(self, data: bytes) -> None:
        """Parse Classic data as HDLC and forward to all clients as KISS."""
        hdlc_frames = self._hdlc_parser.feed(data)
        for hdlc_frame in hdlc_frames:
            kiss_frame = hdlc_frame.to_kiss_frame()
            self._forward_to_clients(kiss_frame)

    # --- Forwarding ---

    def _forward_to_classic(self, frame: KISSFrame, source: str = "BLE") -> None:
        """Forward a KISS frame to the Classic connection.

        If the TNC uses HDLC, translates the frame first.

        Args:
            frame: KISS frame to forward.
            source: Origin of the frame ("BLE" or "TCP") for logging.
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
            "Bridged frame %s->Classic [%s]: %d bytes (port=%d cmd=%s)",
            source,
            proto_label,
            len(frame.data),
            frame.port,
            frame.command.name,
        )

    def _forward_to_clients(self, frame: KISSFrame) -> None:
        """Forward a KISS frame to all clients (BLE and TCP).

        Sends to BLE if connected, and broadcasts to all TCP clients.
        Errors on one destination do not affect others.
        """
        encoded = frame.encode()

        # Forward to BLE client
        if self._ble.is_connected:

            async def _send_ble() -> None:
                try:
                    await self._ble.send_data(encoded)
                except Exception:
                    logger.exception("Error sending data to BLE")

            asyncio.create_task(_send_ble())

        # Broadcast to all TCP KISS clients
        if self._tcp and self._tcp.client_count > 0:

            async def _send_tcp() -> None:
                try:
                    await self._tcp.broadcast(encoded)  # type: ignore[union-attr]
                except Exception:
                    logger.exception("Error broadcasting to TCP clients")

            asyncio.create_task(_send_tcp())

        self._state.frames_bridged += 1

        # Build destination list for logging
        destinations = []
        if self._ble.is_connected:
            destinations.append("BLE")
        if self._tcp and self._tcp.client_count > 0:
            destinations.append(f"TCP({self._tcp.client_count})")
        dest_str = "+".join(destinations) if destinations else "none"

        logger.debug(
            "Bridged frame Classic->%s [KISS]: %d bytes (port=%d cmd=%s)",
            dest_str,
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
