"""BLE GATT server service using bless library."""

from __future__ import annotations

import asyncio
import logging
import subprocess
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

    def _setup_adapter_discoverable(self) -> None:
        """Make the Bluetooth adapter discoverable so iOS can see it."""
        try:
            # Set adapter alias to our device name
            subprocess.run(
                ["bluetoothctl", "system-alias", self._device_name],
                capture_output=True,
                timeout=5,
            )
            # Make adapter discoverable (for BR/EDR discovery in iOS Settings)
            subprocess.run(
                ["bluetoothctl", "discoverable", "on"],
                capture_output=True,
                timeout=5,
            )
            # Make adapter pairable
            subprocess.run(
                ["bluetoothctl", "pairable", "on"],
                capture_output=True,
                timeout=5,
            )
            logger.info("Bluetooth adapter set discoverable as '%s'", self._device_name)
        except Exception as e:
            logger.warning("Could not set adapter discoverable: %s", e)

    def _enable_ble_advertising(self) -> None:
        """
        Enable BLE advertising via btmgmt.

        The bless library registers advertisements with BlueZ's LEAdvertisingManager,
        but on some configurations this doesn't automatically enable the adapter's
        advertising flag. We need to explicitly enable it.
        """
        try:
            # Enable BLE advertising at the adapter level
            result = subprocess.run(
                ["sudo", "btmgmt", "advertising", "on"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                logger.info("BLE advertising enabled via btmgmt")
            else:
                logger.warning("btmgmt advertising on failed: %s", result.stderr)
        except FileNotFoundError:
            logger.warning("btmgmt not found, trying hciconfig")
            try:
                # Fallback: use hciconfig leadv
                subprocess.run(
                    ["sudo", "hciconfig", "hci0", "leadv", "0"],
                    capture_output=True,
                    timeout=5,
                )
                logger.info("BLE advertising enabled via hciconfig leadv")
            except Exception as e:
                logger.warning("Could not enable BLE advertising: %s", e)
        except Exception as e:
            logger.warning("Could not enable BLE advertising: %s", e)

    def _set_advertising_data_with_name(self) -> None:
        """
        Set BLE advertising data to include the local name.

        The bless library's BlueZ backend doesn't include the local name in the
        actual advertisement packet by default. We use direct HCI commands to
        set the advertising data with flags and complete local name, which iOS
        CoreBluetooth needs to discover the device during scanning.
        """
        try:
            name_bytes = self._device_name.encode("utf-8")[:20]  # Max 20 bytes for name

            # Build advertising data
            adv_data = bytearray()
            # Flags: LE General Discoverable (0x02) + BR/EDR Not Supported (0x04) = 0x06
            adv_data += bytes([0x02, 0x01, 0x06])
            # Complete Local Name (AD Type 0x09)
            adv_data += bytes([len(name_bytes) + 1, 0x09]) + name_bytes

            total_len = len(adv_data)
            adv_data = adv_data.ljust(31, b"\x00")

            # HCI LE Set Advertising Data (OGF=0x08, OCF=0x0008)
            cmd_params = bytes([total_len]) + bytes(adv_data)
            result = subprocess.run(
                ["sudo", "hcitool", "cmd", "0x08", "0x0008"] + [f"0x{b:02x}" for b in cmd_params],
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode == 0 and "00" in result.stdout:
                logger.info("BLE advertising data set with name '%s'", self._device_name)
            else:
                logger.warning("Failed to set advertising data: %s", result.stderr or result.stdout)

            # Set scan response with service UUID
            uuid_bytes = bytes.fromhex(NUS_SERVICE_UUID.replace("-", ""))[::-1]  # Little-endian
            scan_rsp = bytes([len(uuid_bytes) + 1, 0x07]) + uuid_bytes  # 128-bit Service UUIDs
            scan_rsp = scan_rsp.ljust(31, b"\x00")

            cmd_params2 = bytes([len(uuid_bytes) + 2]) + bytes(scan_rsp)
            subprocess.run(
                ["sudo", "hcitool", "cmd", "0x08", "0x0009"] + [f"0x{b:02x}" for b in cmd_params2],
                capture_output=True,
                timeout=5,
            )
            logger.debug("BLE scan response set with NUS service UUID")

        except Exception as e:
            logger.warning("Could not set advertising data: %s", e)

    def _restore_adapter_settings(self) -> None:
        """Restore adapter settings on shutdown."""
        try:
            subprocess.run(
                ["bluetoothctl", "discoverable", "off"],
                capture_output=True,
                timeout=5,
            )
        except Exception:
            pass

    async def start(self) -> None:
        """
        Start the BLE GATT server and begin advertising.

        Creates the NUS service and characteristics, then starts advertising.
        The bless library should include the local name in the BLE advertisement
        via the LocalName D-Bus property on the LEAdvertisement1 interface.

        Also makes the Bluetooth adapter discoverable so iOS can see it in Settings.
        """
        try:
            from bless import BlessServer, GATTCharacteristicProperties, GATTAttributePermissions

            logger.info("Starting BLE service", extra={"device_name": self._device_name})

            # Create server with explicit name - bless will set LocalName in advertisement
            self._server = BlessServer(name=self._device_name, loop=None)

            # Set up callbacks
            self._server.read_request_func = self._handle_read_request
            self._server.write_request_func = self._handle_write_request

            # Define the GATT tree BEFORE starting
            # This is required for BlueZ backend
            gatt = {
                NUS_SERVICE_UUID: {
                    NUS_TX_CHAR_UUID: {
                        "Properties": (
                            GATTCharacteristicProperties.write
                            | GATTCharacteristicProperties.write_without_response
                        ),
                        "Permissions": (GATTAttributePermissions.writeable),
                        "Value": bytearray(b""),
                    },
                    NUS_RX_CHAR_UUID: {
                        "Properties": (
                            GATTCharacteristicProperties.read | GATTCharacteristicProperties.notify
                        ),
                        "Permissions": (GATTAttributePermissions.readable),
                        "Value": bytearray(b""),
                    },
                }
            }

            logger.info(
                "Starting BLE GATT server with NUS service: %s",
                NUS_SERVICE_UUID,
            )

            # Start server with GATT tree
            await self._server.add_gatt(gatt)
            await self._server.start()

            # Configure adapter AFTER bless starts (bless may reset some settings)
            # This ensures discoverable/pairable flags are properly set for iOS
            self._setup_adapter_discoverable()

            # Explicitly enable BLE advertising at the adapter level
            # This is needed because bless's LEAdvertisingManager registration
            # doesn't always enable the adapter's advertising flag
            self._enable_ble_advertising()

            # Set advertising data with local name via HCI commands
            # This ensures iOS CoreBluetooth can see the device name during scanning
            self._set_advertising_data_with_name()

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
            try:
                await self._server.stop()
            except Exception as e:
                logger.warning("Error stopping BLE server: %s", e)
            self._server = None

        # Restore adapter settings
        self._restore_adapter_settings()

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
