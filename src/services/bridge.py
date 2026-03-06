"""Bridge service for bidirectional KISS frame forwarding."""

from __future__ import annotations

import asyncio
import logging

from src.models.kiss import KISSFrame, KISSParser
from src.models.state import BridgeState
from src.services.ble_service import BLEService
from src.services.classic_service import ClassicService

logger = logging.getLogger("bt-bridge.bridge")


class BridgeService:
    """
    Main bridge service coordinating BLE and Classic connections.

    Forwards KISS frames bidirectionally between the iPhone (BLE)
    and TNC (Classic) connections.
    """

    def __init__(
        self,
        ble_service: BLEService,
        classic_service: ClassicService,
        state: BridgeState | None = None,
    ) -> None:
        """
        Initialize bridge service.

        Args:
            ble_service: BLE GATT service.
            classic_service: Classic SPP service.
            state: Bridge state container.
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

        # Set up data callbacks
        self._ble.set_data_callback(self._handle_ble_data)
        self._classic.set_data_callback(self._handle_classic_data)

    @property
    def state(self) -> BridgeState:
        """Get bridge state."""
        return self._state

    @property
    def is_fully_connected(self) -> bool:
        """Check if both connections are active."""
        return self._state.is_fully_connected

    async def start(self) -> None:
        """Start the bridge service."""
        logger.info("Starting bridge service")
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

    def _handle_ble_data(self, data: bytes) -> None:
        """
        Handle data received from BLE (iPhone -> TNC).

        Parses KISS frames and forwards to Classic connection.
        """
        frames = self._state.ble_parser.feed(data)

        for frame in frames:
            self._forward_to_classic(frame)

    def _handle_classic_data(self, data: bytes) -> None:
        """
        Handle data received from Classic (TNC -> iPhone).

        Parses KISS frames and forwards to BLE connection.
        """
        frames = self._state.classic_parser.feed(data)

        for frame in frames:
            self._forward_to_ble(frame)

    def _forward_to_classic(self, frame: KISSFrame) -> None:
        """Forward a KISS frame to the Classic connection."""
        if not self._classic.is_connected:
            logger.warning("Cannot forward to Classic: not connected")
            return

        encoded = frame.encode()

        async def _send_with_error_handling() -> None:
            try:
                await self._classic.send_data(encoded)
            except Exception:
                logger.exception("Error sending data to Classic")

        asyncio.create_task(_send_with_error_handling())
        self._state.frames_bridged += 1

        logger.debug(
            "Bridged frame BLE->Classic: %d bytes",
            len(frame.data),
        )

    def _forward_to_ble(self, frame: KISSFrame) -> None:
        """Forward a KISS frame to the BLE connection."""
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
            "Bridged frame Classic->BLE: %d bytes",
            len(frame.data),
        )

    def get_status(self) -> dict[str, object]:
        """Get current bridge status as dictionary."""
        return self._state.to_status_dict()
