"""BLE GATT server service using bless library."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Final

from src.models.connection import BLEConnection
from src.models.state import ConnectionState

if TYPE_CHECKING:
    from bless import BlessGATTCharacteristic, BlessServer


# Nordic UART Service UUIDs
NUS_SERVICE_UUID: Final[str] = "6E400001-B5A3-F393-E0A9-E50E24DCCA9E"
NUS_TX_CHAR_UUID: Final[str] = "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"  # Write
NUS_RX_CHAR_UUID: Final[str] = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"  # Notify

# BLE GATT properties
GATT_PROP_READ: Final[int] = 0x02
GATT_PROP_WRITE: Final[int] = 0x08
GATT_PROP_WRITE_NO_RESP: Final[int] = 0x04
GATT_PROP_NOTIFY: Final[int] = 0x10

logger = logging.getLogger("bt-bridge.ble")


class BLEService:
    """
    BLE GATT server service for Nordic UART Service (NUS).

    Provides a serial-like interface over BLE for iOS apps to communicate
    with the bridge. Uses the bless library for cross-platform BLE support.
    """

    def __init__(
        self,
        device_name: str = "PiBTBridge",
        connection: BLEConnection | None = None,
    ) -> None:
        """
        Initialize BLE service.

        Args:
            device_name: Name to advertise.
            connection: Connection state object.
        """
        self._device_name = device_name
        self._connection = connection or BLEConnection()
        self._server: BlessServer | None = None
        self._is_advertising = False
        self._on_data_received: Callable[[bytes], None] | None = None
        self._on_state_changed: Callable[[ConnectionState], None] | None = None

    @property
    def connection(self) -> BLEConnection:
        """Get the connection state object."""
        return self._connection

    @property
    def is_advertising(self) -> bool:
        """Check if currently advertising."""
        return self._is_advertising

    @property
    def is_connected(self) -> bool:
        """Check if a device is connected."""
        return self._connection.is_connected

    def set_data_callback(self, callback: Callable[[bytes], None]) -> None:
        """Set callback for received data."""
        self._on_data_received = callback

    def set_state_callback(self, callback: Callable[[ConnectionState], None]) -> None:
        """Set callback for state changes."""
        self._on_state_changed = callback

    async def start(self) -> None:
        """
        Start the BLE GATT server and begin advertising.

        Creates the NUS service and characteristics, then starts advertising.
        """
        try:
            from bless import BlessServer

            logger.info("Starting BLE service", extra={"device_name": self._device_name})

            # Create server
            self._server = BlessServer(name=self._device_name)

            # Set up callbacks
            self._server.read_request_func = self._handle_read_request
            self._server.write_request_func = self._handle_write_request

            # Start server
            await self._server.start()

            # Add NUS service
            await self._server.add_new_service(NUS_SERVICE_UUID)

            # Add TX characteristic (iPhone writes to this)
            await self._server.add_new_characteristic(
                NUS_SERVICE_UUID,
                NUS_TX_CHAR_UUID,
                GATT_PROP_WRITE | GATT_PROP_WRITE_NO_RESP,
                None,
                [],
            )

            # Add RX characteristic (Bridge notifies through this)
            await self._server.add_new_characteristic(
                NUS_SERVICE_UUID,
                NUS_RX_CHAR_UUID,
                GATT_PROP_READ | GATT_PROP_NOTIFY,
                None,
                [],
            )

            # Begin advertising
            self._is_advertising = True
            self._update_state(ConnectionState.SCANNING)

            logger.info("BLE service started, advertising as '%s'", self._device_name)

        except ImportError:
            logger.error("bless library not installed")
            raise
        except Exception as e:
            logger.error("Failed to start BLE service: %s", e)
            self._update_state(ConnectionState.ERROR)
            raise

    async def stop(self) -> None:
        """Stop the BLE server and advertising."""
        if self._server:
            logger.info("Stopping BLE service")
            await self._server.stop()
            self._server = None

        self._is_advertising = False
        self._update_state(ConnectionState.IDLE)

    async def send_data(self, data: bytes) -> None:
        """
        Send data to connected device via notification.

        Args:
            data: Data to send (will be fragmented if > MTU-3).
        """
        if not self.is_connected:
            logger.warning("Cannot send: not connected")
            return

        if not self._server:
            return

        # Fragment data to MTU size
        payload_size = self._connection.payload_size
        for i in range(0, len(data), payload_size):
            chunk = data[i : i + payload_size]
            self._server.update_value(NUS_SERVICE_UUID, NUS_RX_CHAR_UUID)
            self._connection.record_tx(len(chunk))

        logger.debug("Sent %d bytes via BLE", len(data))

    def _handle_read_request(
        self,
        characteristic: BlessGATTCharacteristic,
        **kwargs: object,  # noqa: ARG002
    ) -> bytearray:
        """Handle GATT read request."""
        logger.debug("Read request for characteristic %s", characteristic.uuid)
        return bytearray()

    def _handle_write_request(
        self,
        characteristic: BlessGATTCharacteristic,
        value: bytes,
        **kwargs: object,  # noqa: ARG002
    ) -> None:
        """Handle GATT write request (data from iPhone)."""
        if characteristic.uuid.upper() == NUS_TX_CHAR_UUID.upper():
            self._connection.record_rx(len(value))
            logger.debug("Received %d bytes via BLE", len(value))

            if self._on_data_received:
                self._on_data_received(value)

    def _update_state(self, new_state: ConnectionState) -> None:
        """Update connection state and notify callback."""
        old_state = self._connection.state
        self._connection.state = new_state

        if self._on_state_changed and old_state != new_state:
            self._on_state_changed(new_state)

        logger.info(
            "BLE state changed: %s -> %s",
            old_state.value,
            new_state.value,
        )

    def handle_connection(self, device_address: str, device_name: str | None = None) -> None:
        """
        Handle incoming BLE connection.

        Args:
            device_address: Connected device MAC address.
            device_name: Device name (optional).
        """
        self._connection.set_connected(device_address, device_name)
        self._update_state(ConnectionState.CONNECTED)
        self._is_advertising = False

        logger.info(
            "BLE device connected: %s (%s)",
            device_address,
            device_name or "unknown",
        )

    def handle_disconnection(self) -> None:
        """Handle BLE disconnection."""
        old_address = self._connection.device_address
        self._connection.set_disconnected()
        self._update_state(ConnectionState.IDLE)

        logger.info("BLE device disconnected: %s", old_address)

    def handle_mtu_change(self, new_mtu: int) -> None:
        """
        Handle MTU negotiation result.

        Args:
            new_mtu: Negotiated MTU value.
        """
        old_mtu = self._connection.mtu
        self._connection.update_mtu(new_mtu)

        logger.info("BLE MTU changed: %d -> %d", old_mtu, new_mtu)
