"""TCP KISS server service.

Provides a standard KISS-over-TCP interface (de facto standard used by
Direwolf, APRSIS32, Xastir, PinPoint APRS) so traditional ham radio
apps can connect to the bridge alongside BLE clients.

Protocol: Raw TCP with KISS framing (0xC0 delimiters), no handshake.
Default port: 8001 (Direwolf convention).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from src.models.connection import TcpKissConnection
from src.models.kiss import KISSParser

if TYPE_CHECKING:
    from src.models.state import BridgeState

logger = logging.getLogger("bt-bridge.tcp-kiss")


class TcpKissService:
    """
    TCP KISS server for KISS-over-TCP clients.

    Accepts TCP connections from ham radio software, parses incoming
    KISS frames, and broadcasts TNC data to all connected clients.
    Each client gets its own KISSParser for stream reassembly.
    """

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 8001,
        max_clients: int = 5,
        bridge_state: BridgeState | None = None,
    ) -> None:
        """
        Initialize TCP KISS service.

        Args:
            host: Address to bind to.
            port: TCP port to listen on (0 for OS-assigned).
            max_clients: Maximum simultaneous TCP clients.
            bridge_state: Bridge state container for tracking clients.
        """
        self._host = host
        self._port = port
        self._max_clients = max_clients
        self._bridge_state = bridge_state

        self._server: asyncio.Server | None = None
        self._running = False

        # Per-client state: remote_address -> (reader, writer, parser, connection)
        self._clients: dict[
            str,
            tuple[asyncio.StreamReader, asyncio.StreamWriter, KISSParser, TcpKissConnection],
        ] = {}

        # Callback for forwarding parsed frames to BridgeService
        self._on_data_received: Callable[[bytes], None] | None = None

    @property
    def is_running(self) -> bool:
        """Check if the TCP server is running."""
        return self._running

    @property
    def port(self) -> int:
        """Get the actual listening port (useful when port=0)."""
        if self._server and self._server.sockets:
            return self._server.sockets[0].getsockname()[1]
        return self._port

    @property
    def client_count(self) -> int:
        """Get number of connected clients."""
        return len(self._clients)

    @property
    def is_at_capacity(self) -> bool:
        """Check if max_clients has been reached."""
        return len(self._clients) >= self._max_clients

    def set_data_callback(self, callback: Callable[[bytes], None]) -> None:
        """
        Set callback for received KISS frame data.

        The callback receives the raw encoded KISS frame bytes
        (including FEND delimiters) from any TCP client.

        Args:
            callback: Function to call with KISS frame bytes.
        """
        self._on_data_received = callback

    async def start(self) -> None:
        """Start the TCP KISS server."""
        if self._running:
            logger.warning("TCP KISS server already running")
            return

        self._server = await asyncio.start_server(
            self._handle_client,
            host=self._host,
            port=self._port,
        )
        self._running = True

        addr = self._server.sockets[0].getsockname() if self._server.sockets else ("?", "?")
        logger.info("TCP KISS server listening on %s:%s", addr[0], addr[1])

    async def stop(self) -> None:
        """Stop the TCP KISS server and disconnect all clients."""
        if not self._running and self._server is None:
            return

        self._running = False

        # Close all client connections
        for _addr, (_reader, writer, _parser, _conn) in list(self._clients.items()):
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

        self._clients.clear()
        if self._bridge_state:
            self._bridge_state.tcp_clients.clear()

        # Close the server
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

        logger.info("TCP KISS server stopped")

    async def broadcast(self, data: bytes) -> None:
        """
        Send data to all connected TCP clients.

        Handles per-client write errors without affecting other clients.
        Failed clients are removed.

        Args:
            data: Raw KISS frame bytes to send (including FEND delimiters).
        """
        if not self._clients:
            return

        failed_clients: list[str] = []

        for addr, (_reader, writer, _parser, conn) in self._clients.items():
            if writer.is_closing():
                failed_clients.append(addr)
                continue

            try:
                writer.write(data)
                await writer.drain()
                conn.record_tx(len(data))
            except (ConnectionResetError, BrokenPipeError, OSError) as e:
                logger.warning("Write error for TCP client %s: %s", addr, e)
                failed_clients.append(addr)

        # Remove failed clients
        for addr in failed_clients:
            self._remove_client(addr)

    async def send_data(self, data: bytes) -> None:
        """
        Send data to all connected TCP clients.

        Alias for broadcast() to match the interface of BLEService/ClassicService.

        Args:
            data: Raw KISS frame bytes to send.
        """
        await self.broadcast(data)

    def _add_client(
        self,
        remote_address: str,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """
        Register a new TCP client.

        Args:
            remote_address: Remote IP:port string.
            reader: Client stream reader.
            writer: Client stream writer.
        """
        parser = KISSParser()
        conn = TcpKissConnection()
        conn.set_connected(remote_address)

        self._clients[remote_address] = (reader, writer, parser, conn)

        if self._bridge_state:
            self._bridge_state.tcp_clients.append(conn)

        logger.info(
            "TCP KISS client connected: %s (%d/%d)",
            remote_address,
            len(self._clients),
            self._max_clients,
        )

    def _remove_client(self, remote_address: str) -> None:
        """
        Unregister a TCP client.

        Args:
            remote_address: Remote IP:port string.
        """
        client = self._clients.pop(remote_address, None)
        if client is None:
            return

        _, writer, _, conn = client

        # Remove from bridge state
        if self._bridge_state:
            try:
                self._bridge_state.tcp_clients.remove(conn)
            except ValueError:
                pass

        # Close the writer
        try:
            if not writer.is_closing():
                writer.close()
        except Exception:
            pass

        logger.info(
            "TCP KISS client disconnected: %s (%d/%d)",
            remote_address,
            len(self._clients),
            self._max_clients,
        )

    def _handle_client_data(self, remote_address: str, data: bytes) -> None:
        """
        Process raw bytes received from a TCP client.

        Feeds data through the client's KISSParser. For each complete
        frame, calls the data callback.

        Args:
            remote_address: Remote IP:port of the sending client.
            data: Raw bytes from the TCP socket.
        """
        client = self._clients.get(remote_address)
        if client is None:
            return

        _, _, parser, conn = client
        conn.record_rx(len(data))

        frames = parser.feed(data)
        for frame in frames:
            if self._on_data_received:
                # Re-encode the frame for the bridge (consistent interface)
                self._on_data_received(frame.encode())

    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """
        Handle a new TCP client connection.

        This is the asyncio server callback for each new connection.

        Args:
            reader: Client stream reader.
            writer: Client stream writer.
        """
        peername = writer.get_extra_info("peername")
        remote_address = f"{peername[0]}:{peername[1]}" if peername else "unknown"

        # Check capacity
        if self.is_at_capacity:
            logger.warning(
                "TCP KISS client rejected (at capacity %d/%d): %s",
                len(self._clients),
                self._max_clients,
                remote_address,
            )
            writer.close()
            await writer.wait_closed()
            return

        self._add_client(remote_address, reader, writer)

        try:
            while self._running:
                data = await reader.read(4096)
                if not data:
                    break  # Client disconnected

                self._handle_client_data(remote_address, data)

        except (ConnectionResetError, BrokenPipeError, OSError) as e:
            logger.debug("TCP client %s connection error: %s", remote_address, e)
        except asyncio.CancelledError:
            pass
        finally:
            self._remove_client(remote_address)
