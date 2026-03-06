"""Bluetooth Classic SPP service using direct RFCOMM socket."""

from __future__ import annotations

import asyncio
import logging
import socket
from collections.abc import Callable
from typing import Final

from src.models.connection import ClassicConnection
from src.models.state import ConnectionState

# SPP Service UUID
SPP_SERVICE_UUID: Final[str] = "00001101-0000-1000-8000-00805F9B34FB"

# Default RFCOMM channel for SPP (TH-D74 uses channel 2 for Serial Port service)
DEFAULT_RFCOMM_CHANNEL: Final[int] = 2

# KISS Protocol Constants
KISS_FEND: Final[int] = 0xC0  # Frame End
KISS_CMD_TXDELAY: Final[int] = 0x01  # TX delay command (in 10ms units)
KISS_CMD_SLOT_TIME: Final[int] = 0x03  # Slot time command (in 10ms units)
KISS_CMD_TX_TAIL: Final[int] = 0x04  # TX tail command (in 10ms units)

# Default KISS parameters (matching Android app values)
DEFAULT_TXDELAY_MS: Final[int] = 500  # 500ms = 50 units
DEFAULT_SLOT_TIME_MS: Final[int] = 100  # 100ms = 10 units
DEFAULT_TX_TAIL_MS: Final[int] = 50  # 50ms = 5 units
KISS_COMMAND_DELAY_S: Final[float] = 0.05  # 50ms delay between commands

logger = logging.getLogger("bt-bridge.classic")


class ClassicService:
    """
    Bluetooth Classic SPP client service using direct RFCOMM socket.

    Connects to a target TNC device over Serial Port Profile (SPP)
    and provides a byte stream interface for KISS frame communication.

    Uses Python's socket module with BTPROTO_RFCOMM for direct connection,
    which is more reliable than the D-Bus profile approach for many devices.
    """

    def __init__(
        self,
        target_address: str,
        target_pin: str = "0000",
        reconnect_max_delay: int = 30,
        rfcomm_channel: int = DEFAULT_RFCOMM_CHANNEL,
        connection: ClassicConnection | None = None,
    ) -> None:
        """
        Initialize Classic SPP service.

        Args:
            target_address: Target device MAC address.
            target_pin: Pairing PIN (used for reference, pairing should be done beforehand).
            reconnect_max_delay: Maximum reconnect delay in seconds.
            rfcomm_channel: RFCOMM channel to connect to (default: 1).
            connection: Connection state object.
        """
        self._target_address = target_address
        self._target_pin = target_pin
        self._reconnect_max_delay = reconnect_max_delay
        self._rfcomm_channel = rfcomm_channel
        self._connection = connection or ClassicConnection(target_address=target_address)

        self._socket: socket.socket | None = None
        self._reader_task: asyncio.Task[None] | None = None
        self._reconnect_task: asyncio.Task[None] | None = None
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
        return self._connection.is_connected and self._socket is not None

    def set_data_callback(self, callback: Callable[[bytes], None]) -> None:
        """Set callback for received data."""
        self._on_data_received = callback

    def set_state_callback(self, callback: Callable[[ConnectionState], None]) -> None:
        """Set callback for state changes."""
        self._on_state_changed = callback

    async def start(self) -> None:
        """
        Start the Classic SPP service and connect to target.

        Uses direct RFCOMM socket connection.
        """
        logger.info(
            "Starting Classic service, target: %s channel: %d",
            self._target_address,
            self._rfcomm_channel,
        )

        self._running = True
        await self._connect()

    async def stop(self) -> None:
        """Stop the Classic service and disconnect."""
        logger.info("Stopping Classic service")
        self._running = False

        # Cancel reconnect task
        if self._reconnect_task:
            self._reconnect_task.cancel()
            try:
                await self._reconnect_task
            except asyncio.CancelledError:
                pass
            self._reconnect_task = None

        # Cancel reader task
        if self._reader_task:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
            self._reader_task = None

        # Close socket
        if self._socket:
            try:
                self._socket.close()
            except OSError:
                pass
            self._socket = None

        self._connection.set_disconnected()
        self._update_state(ConnectionState.IDLE)

    async def switch_target(self, address: str, rfcomm_channel: int | None = None) -> None:
        """
        Switch to a different target TNC device.

        Disconnects from the current device (if connected), updates the
        target address/channel, resets reconnect state, and initiates a
        new connection — all without restarting the daemon.

        Args:
            address: New target device MAC address.
            rfcomm_channel: RFCOMM channel (None keeps current channel).
        """
        old_target = self._target_address
        logger.info(
            "Switching target from %s to %s (channel %s)",
            old_target,
            address,
            rfcomm_channel or self._rfcomm_channel,
        )

        # Stop current connection (cancel reconnect loop, close socket)
        await self.stop()

        # Update target
        self._target_address = address
        if rfcomm_channel is not None:
            self._rfcomm_channel = rfcomm_channel

        # Reset connection state in-place so BridgeState.classic stays
        # pointed at the same object and status API reflects the new target.
        self._connection.target_address = address
        self._connection.bytes_rx = 0
        self._connection.bytes_tx = 0
        self._connection.reconnect_attempts = 0
        self._connection.last_error = None

        # Restart connection to new target
        await self.start()

    async def send_data(self, data: bytes) -> None:
        """
        Send data to connected TNC.

        Args:
            data: Data to send.
        """
        if not self.is_connected or self._socket is None:
            logger.warning("Cannot send: not connected")
            return

        try:
            loop = asyncio.get_event_loop()
            await asyncio.wait_for(
                loop.run_in_executor(None, self._socket.send, data),
                timeout=10.0,
            )
            self._connection.record_tx(len(data))
            logger.debug("Sent %d bytes via SPP", len(data))
        except TimeoutError:
            logger.error("SPP write timed out")
            await self._handle_disconnect("Write timed out")
        except OSError as e:
            logger.error("SPP write error: %s", e)
            await self._handle_disconnect(str(e))

    async def _connect(self) -> None:
        """Initiate RFCOMM connection to target device."""
        self._update_state(ConnectionState.CONNECTING)

        try:
            # Create RFCOMM socket
            loop = asyncio.get_event_loop()

            def create_and_connect() -> socket.socket:
                sock = socket.socket(
                    socket.AF_BLUETOOTH,
                    socket.SOCK_STREAM,
                    socket.BTPROTO_RFCOMM,
                )
                sock.settimeout(10.0)  # 10 second connection timeout
                sock.connect((self._target_address, self._rfcomm_channel))
                sock.settimeout(5.0)  # 5 second timeout for send/recv
                return sock

            logger.info(
                "Connecting to %s on RFCOMM channel %d...",
                self._target_address,
                self._rfcomm_channel,
            )

            self._socket = await loop.run_in_executor(None, create_and_connect)

            # Connection successful
            self._connection.set_connected(self._rfcomm_channel, None)
            self._update_state(ConnectionState.CONNECTED)

            logger.info(
                "SPP connected: %s on channel %d",
                self._target_address,
                self._rfcomm_channel,
            )

            # NOTE: Do NOT send KISS parameter commands to TH-D74!
            # Testing showed that sending TXDELAY/SLOT_TIME/TX_TAIL commands
            # prevents the TH-D74 from transmitting packets. The radio works
            # correctly without these configuration commands.
            # await self._configure_kiss_parameters()

            # Start reader task
            self._reader_task = asyncio.create_task(self._read_loop())

        except OSError as e:
            logger.error("Connection failed: %s", e)
            self._connection.last_error = str(e)
            self._update_state(ConnectionState.ERROR)

            if self._socket:
                try:
                    self._socket.close()
                except OSError:
                    pass
                self._socket = None

            # Schedule reconnection
            if self._running:
                self._reconnect_task = asyncio.create_task(self._schedule_reconnect())

    async def _configure_kiss_parameters(self) -> None:
        """
        Configure TNC with KISS parameters after connection.

        Sends TX delay, slot time, and TX tail settings. This may be required
        for some TNCs (like TH-D74) to properly recognize the Bluetooth connection.
        Based on Android app's configureKissParameters() function.
        """
        if self._socket is None:
            return

        loop = asyncio.get_event_loop()

        try:
            logger.info("Configuring KISS parameters...")

            # Set TX delay (time to wait after keying before sending data)
            # 500ms = 50 units (in 10ms units)
            txdelay_units = DEFAULT_TXDELAY_MS // 10
            txdelay_cmd = bytes([KISS_FEND, KISS_CMD_TXDELAY, txdelay_units, KISS_FEND])
            logger.debug(
                "Setting TXDELAY to %dms (%d units)",
                DEFAULT_TXDELAY_MS,
                txdelay_units,
            )
            await loop.run_in_executor(None, self._socket.send, txdelay_cmd)
            await asyncio.sleep(KISS_COMMAND_DELAY_S)

            # Set slot time (interval between channel checks)
            # 100ms = 10 units (in 10ms units)
            slot_time_units = DEFAULT_SLOT_TIME_MS // 10
            slot_time_cmd = bytes([KISS_FEND, KISS_CMD_SLOT_TIME, slot_time_units, KISS_FEND])
            logger.debug(
                "Setting SLOT_TIME to %dms (%d units)",
                DEFAULT_SLOT_TIME_MS,
                slot_time_units,
            )
            await loop.run_in_executor(None, self._socket.send, slot_time_cmd)
            await asyncio.sleep(KISS_COMMAND_DELAY_S)

            # Set TX tail (time to keep transmitter keyed after data)
            # 50ms = 5 units (in 10ms units)
            tx_tail_units = DEFAULT_TX_TAIL_MS // 10
            tx_tail_cmd = bytes([KISS_FEND, KISS_CMD_TX_TAIL, tx_tail_units, KISS_FEND])
            logger.debug(
                "Setting TX_TAIL to %dms (%d units)",
                DEFAULT_TX_TAIL_MS,
                tx_tail_units,
            )
            await loop.run_in_executor(None, self._socket.send, tx_tail_cmd)
            await asyncio.sleep(KISS_COMMAND_DELAY_S)

            logger.info("KISS parameters configured successfully")

        except OSError as e:
            logger.warning("Failed to configure KISS parameters: %s", e)
            # Don't fail the connection, some TNCs may not support all commands

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

    async def _handle_disconnect(self, reason: str) -> None:
        """Handle disconnection event."""
        self._connection.set_disconnected(reason)
        self._update_state(ConnectionState.IDLE)

        if self._socket:
            try:
                self._socket.close()
            except OSError:
                pass
            self._socket = None

        logger.info("SPP disconnected: %s (%s)", self._target_address, reason)

        # Schedule reconnection if still running
        if self._running:
            self._reconnect_task = asyncio.create_task(self._schedule_reconnect())

    async def _read_loop(self) -> None:
        """Read data from SPP connection."""
        if self._socket is None:
            return

        loop = asyncio.get_event_loop()

        try:
            while self._running and self._socket is not None:
                try:
                    data = await asyncio.wait_for(
                        loop.run_in_executor(None, self._socket.recv, 4096),
                        timeout=10.0,
                    )

                    if not data:
                        # EOF - connection closed
                        await self._handle_disconnect("Connection closed by remote")
                        break

                    self._connection.record_rx(len(data))
                    logger.debug("Received %d bytes via SPP", len(data))

                    if self._on_data_received:
                        self._on_data_received(data)

                except TimeoutError:
                    # Socket or asyncio timeout - just keep polling
                    continue
                except OSError as e:
                    await self._handle_disconnect(str(e))
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
