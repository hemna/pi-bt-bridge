"""Bluetooth Classic SPP service using dbus-python."""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Callable
from typing import TYPE_CHECKING, Final

from src.models.connection import ClassicConnection
from src.models.state import ConnectionState

if TYPE_CHECKING:
    import dbus


# SPP Service UUID
SPP_SERVICE_UUID: Final[str] = "00001101-0000-1000-8000-00805F9B34FB"

# D-Bus paths
BLUEZ_SERVICE: Final[str] = "org.bluez"
ADAPTER_PATH: Final[str] = "/org/bluez/hci0"
PROFILE_PATH: Final[str] = "/org/bluez/profile/spp"

logger = logging.getLogger("bt-bridge.classic")


class ClassicService:
    """
    Bluetooth Classic SPP client service using D-Bus/BlueZ.

    Connects to a target TNC device over Serial Port Profile (SPP)
    and provides a byte stream interface for KISS frame communication.
    """

    def __init__(
        self,
        target_address: str,
        target_pin: str = "0000",
        reconnect_max_delay: int = 30,
        connection: ClassicConnection | None = None,
    ) -> None:
        """
        Initialize Classic SPP service.

        Args:
            target_address: Target device MAC address.
            target_pin: Pairing PIN.
            reconnect_max_delay: Maximum reconnect delay in seconds.
            connection: Connection state object.
        """
        self._target_address = target_address
        self._target_pin = target_pin
        self._reconnect_max_delay = reconnect_max_delay
        self._connection = connection or ClassicConnection(target_address=target_address)

        self._bus: dbus.SystemBus | None = None
        self._fd: int | None = None
        self._reader_task: asyncio.Task[None] | None = None
        self._on_data_received: Callable[[bytes], None] | None = None
        self._on_state_changed: Callable[[ConnectionState], None] | None = None
        self._running = False

    @property
    def connection(self) -> ClassicConnection:
        """Get the connection state object."""
        return self._connection

    @property
    def is_connected(self) -> bool:
        """Check if connected to TNC."""
        return self._connection.is_connected

    def set_data_callback(self, callback: Callable[[bytes], None]) -> None:
        """Set callback for received data."""
        self._on_data_received = callback

    def set_state_callback(self, callback: Callable[[ConnectionState], None]) -> None:
        """Set callback for state changes."""
        self._on_state_changed = callback

    async def start(self) -> None:
        """
        Start the Classic SPP service and connect to target.

        Registers SPP profile with BlueZ and initiates connection.
        """
        try:
            import dbus
            import dbus.mainloop.glib

            logger.info(
                "Starting Classic service, target: %s",
                self._target_address,
            )

            # Initialize D-Bus
            dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
            self._bus = dbus.SystemBus()

            # Register SPP profile
            await self._register_profile()

            # Start connection
            self._running = True
            await self._connect()

        except ImportError:
            logger.error("dbus-python library not installed")
            raise
        except Exception as e:
            logger.error("Failed to start Classic service: %s", e)
            self._update_state(ConnectionState.ERROR)
            raise

    async def stop(self) -> None:
        """Stop the Classic service and disconnect."""
        logger.info("Stopping Classic service")
        self._running = False

        # Cancel reader task
        if self._reader_task:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
            self._reader_task = None

        # Close file descriptor
        if self._fd is not None:
            try:
                os.close(self._fd)
            except OSError:
                pass
            self._fd = None

        self._connection.set_disconnected()
        self._update_state(ConnectionState.IDLE)

    async def send_data(self, data: bytes) -> None:
        """
        Send data to connected TNC.

        Args:
            data: Data to send.
        """
        if not self.is_connected or self._fd is None:
            logger.warning("Cannot send: not connected")
            return

        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, os.write, self._fd, data)
            self._connection.record_tx(len(data))
            logger.debug("Sent %d bytes via SPP", len(data))
        except OSError as e:
            logger.error("SPP write error: %s", e)
            self._handle_disconnect(str(e))

    async def _register_profile(self) -> None:
        """Register SPP profile with BlueZ."""
        import dbus

        if not self._bus:
            return

        try:
            manager = dbus.Interface(
                self._bus.get_object(BLUEZ_SERVICE, "/org/bluez"),
                "org.bluez.ProfileManager1",
            )

            profile_options = {
                "Name": dbus.String("Serial Port"),
                "Service": dbus.String(SPP_SERVICE_UUID),
                "Role": dbus.String("client"),
                "Channel": dbus.UInt16(0),  # Auto-select via SDP
                "RequireAuthentication": dbus.Boolean(True),
                "RequireAuthorization": dbus.Boolean(False),
            }

            # Create profile handler
            # In production, this would be a proper D-Bus object
            manager.RegisterProfile(PROFILE_PATH, SPP_SERVICE_UUID, profile_options)

            logger.info("SPP profile registered")

        except dbus.exceptions.DBusException as e:
            if "AlreadyExists" not in str(e):
                raise
            logger.debug("SPP profile already registered")

    async def _connect(self) -> None:
        """Initiate connection to target device."""
        import dbus

        if not self._bus:
            return

        self._update_state(ConnectionState.SCANNING)

        try:
            # Get device proxy
            device_path = f"{ADAPTER_PATH}/dev_{self._target_address.replace(':', '_')}"
            device = dbus.Interface(
                self._bus.get_object(BLUEZ_SERVICE, device_path),
                "org.bluez.Device1",
            )

            self._update_state(ConnectionState.CONNECTING)

            # Connect (this will use the registered profile)
            device.Connect()

            # Connection handling is done via NewConnection callback
            logger.info("Connection initiated to %s", self._target_address)

        except dbus.exceptions.DBusException as e:
            error_name = e.get_dbus_name() if hasattr(e, "get_dbus_name") else str(e)
            logger.error("Connection failed: %s", error_name)
            self._connection.last_error = str(e)
            self._update_state(ConnectionState.ERROR)

            # Schedule reconnection
            if self._running:
                await self._schedule_reconnect()

    async def _schedule_reconnect(self) -> None:
        """Schedule reconnection with exponential backoff."""
        self._connection.record_reconnect_attempt()
        delay = self._connection.get_backoff_delay(self._reconnect_max_delay)

        logger.info(
            "Scheduling reconnect in %.1f seconds (attempt %d)",
            delay,
            self._connection.reconnect_attempts,
        )

        await asyncio.sleep(delay)

        if self._running and not self.is_connected:
            await self._connect()

    def handle_new_connection(self, fd: int, properties: dict[str, object]) -> None:
        """
        Handle new SPP connection from BlueZ.

        Called by BlueZ Profile1 when connection is established.

        Args:
            fd: File descriptor for the connection.
            properties: Connection properties.
        """
        self._fd = fd

        # Extract device info
        device_name = properties.get("Name")

        # Discover channel from properties or default to 1
        channel = int(properties.get("Channel", 1))

        self._connection.set_connected(channel, device_name)  # type: ignore[arg-type]
        self._update_state(ConnectionState.CONNECTED)

        logger.info(
            "SPP connected: %s (%s) on channel %d",
            self._target_address,
            device_name or "unknown",
            channel,
        )

        # Start reader task
        self._reader_task = asyncio.create_task(self._read_loop())

    def handle_request_disconnection(self) -> None:
        """Handle disconnection request from BlueZ."""
        self._handle_disconnect("Remote disconnection requested")

    def _handle_disconnect(self, reason: str) -> None:
        """Handle disconnection event."""
        old_address = self._target_address
        self._connection.set_disconnected(reason)
        self._update_state(ConnectionState.IDLE)

        if self._fd is not None:
            try:
                os.close(self._fd)
            except OSError:
                pass
            self._fd = None

        logger.info("SPP disconnected: %s (%s)", old_address, reason)

        # Schedule reconnection if still running
        if self._running:
            asyncio.create_task(self._schedule_reconnect())

    async def _read_loop(self) -> None:
        """Read data from SPP connection."""
        if self._fd is None:
            return

        loop = asyncio.get_event_loop()

        try:
            while self._running and self._fd is not None:
                try:
                    # Read with timeout
                    data = await asyncio.wait_for(
                        loop.run_in_executor(None, os.read, self._fd, 4096),
                        timeout=1.0,
                    )

                    if not data:
                        # EOF - connection closed
                        self._handle_disconnect("Connection closed")
                        break

                    self._connection.record_rx(len(data))
                    logger.debug("Received %d bytes via SPP", len(data))

                    if self._on_data_received:
                        self._on_data_received(data)

                except TimeoutError:
                    continue
                except OSError as e:
                    self._handle_disconnect(str(e))
                    break

        except asyncio.CancelledError:
            pass

    def _update_state(self, new_state: ConnectionState) -> None:
        """Update connection state and notify callback."""
        old_state = self._connection.state
        self._connection.state = new_state

        if self._on_state_changed and old_state != new_state:
            self._on_state_changed(new_state)

        logger.info(
            "Classic state changed: %s -> %s",
            old_state.value,
            new_state.value,
        )
