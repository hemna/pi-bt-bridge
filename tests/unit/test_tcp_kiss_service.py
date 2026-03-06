"""Unit tests for TcpKissService: start/stop, accept client, receive data, send data, disconnect."""

from __future__ import annotations

import asyncio
from datetime import datetime
from unittest.mock import MagicMock

import pytest

from src.models.connection import TcpKissConnection
from src.models.kiss import KISSCommand, KISSFrame, KISSParser
from tests.conftest import make_mock_tcp_writer

# =============================================================================
# TcpKissConnection dataclass tests
# =============================================================================


class TestTcpKissConnection:
    """Unit tests for TcpKissConnection dataclass."""

    def test_default_values(self) -> None:
        """TcpKissConnection has sensible defaults."""
        conn = TcpKissConnection()
        assert conn.remote_address == ""
        assert conn.connected_at is None
        assert conn.bytes_rx == 0
        assert conn.bytes_tx == 0

    def test_set_connected(self) -> None:
        """set_connected sets address and timestamp."""
        conn = TcpKissConnection()
        conn.set_connected("192.168.1.100:54321")

        assert conn.remote_address == "192.168.1.100:54321"
        assert conn.connected_at is not None
        assert isinstance(conn.connected_at, datetime)

    def test_record_rx(self) -> None:
        """record_rx increments byte counter."""
        conn = TcpKissConnection()
        conn.record_rx(100)
        conn.record_rx(50)
        assert conn.bytes_rx == 150

    def test_record_tx(self) -> None:
        """record_tx increments byte counter."""
        conn = TcpKissConnection()
        conn.record_tx(200)
        conn.record_tx(75)
        assert conn.bytes_tx == 275


# =============================================================================
# TcpKissService lifecycle tests
# =============================================================================


class TestTcpKissServiceLifecycle:
    """Tests for TcpKissService start/stop lifecycle."""

    @pytest.mark.asyncio
    async def test_start_creates_server(self) -> None:
        """start() should create an asyncio TCP server."""
        from src.services.tcp_kiss_service import TcpKissService

        service = TcpKissService(port=0)  # port=0 lets OS pick
        await service.start()

        assert service.is_running
        assert service.port > 0  # OS assigned a port

        await service.stop()

    @pytest.mark.asyncio
    async def test_stop_closes_server(self) -> None:
        """stop() should shut down the TCP server."""
        from src.services.tcp_kiss_service import TcpKissService

        service = TcpKissService(port=0)
        await service.start()
        await service.stop()

        assert not service.is_running

    @pytest.mark.asyncio
    async def test_stop_before_start_is_safe(self) -> None:
        """stop() on a never-started service should not raise."""
        from src.services.tcp_kiss_service import TcpKissService

        service = TcpKissService(port=0)
        await service.stop()  # Should not raise

    @pytest.mark.asyncio
    async def test_start_twice_is_safe(self) -> None:
        """Calling start() twice should not create duplicate servers."""
        from src.services.tcp_kiss_service import TcpKissService

        service = TcpKissService(port=0)
        await service.start()
        _ = service.port  # Verify port was assigned

        await service.start()  # Should be no-op or restart cleanly
        assert service.is_running

        await service.stop()


# =============================================================================
# Client connection tests
# =============================================================================


class TestTcpKissServiceClientManagement:
    """Tests for TCP client connection/disconnection handling."""

    @pytest.mark.asyncio
    async def test_add_client_tracked(self) -> None:
        """Adding a client updates client count."""
        from src.services.tcp_kiss_service import TcpKissService

        service = TcpKissService(port=0)

        writer = make_mock_tcp_writer()
        service._add_client("192.168.1.1:5000", asyncio.StreamReader(), writer)

        assert service.client_count == 1

    @pytest.mark.asyncio
    async def test_remove_client_tracked(self) -> None:
        """Removing a client updates client count."""
        from src.services.tcp_kiss_service import TcpKissService

        service = TcpKissService(port=0)

        writer = make_mock_tcp_writer()
        service._add_client("192.168.1.1:5000", asyncio.StreamReader(), writer)
        service._remove_client("192.168.1.1:5000")

        assert service.client_count == 0

    @pytest.mark.asyncio
    async def test_remove_nonexistent_client_is_safe(self) -> None:
        """Removing a client that doesn't exist should not raise."""
        from src.services.tcp_kiss_service import TcpKissService

        service = TcpKissService(port=0)
        service._remove_client("nonexistent:9999")  # Should not raise

    @pytest.mark.asyncio
    async def test_max_clients_enforcement(self) -> None:
        """is_at_capacity returns True when max_clients reached."""
        from src.services.tcp_kiss_service import TcpKissService

        service = TcpKissService(port=0, max_clients=2)

        for i in range(2):
            writer = make_mock_tcp_writer()
            service._add_client(f"client{i}:100{i}", asyncio.StreamReader(), writer)

        assert service.is_at_capacity

    @pytest.mark.asyncio
    async def test_client_tracks_bridge_state(self) -> None:
        """Adding a client should add TcpKissConnection to bridge state."""
        from src.models.connection import BLEConnection, ClassicConnection
        from src.models.kiss import KISSParser
        from src.models.state import BridgeState
        from src.services.tcp_kiss_service import TcpKissService

        state = BridgeState(
            ble=BLEConnection(),
            classic=ClassicConnection(target_address="00:11:22:33:44:55"),
            ble_parser=KISSParser(),
            classic_parser=KISSParser(),
        )
        service = TcpKissService(port=0, bridge_state=state)

        writer = make_mock_tcp_writer()
        service._add_client("192.168.1.1:5000", asyncio.StreamReader(), writer)

        assert len(state.tcp_clients) == 1
        assert state.tcp_clients[0].remote_address == "192.168.1.1:5000"


# =============================================================================
# Data sending tests
# =============================================================================


class TestTcpKissServiceDataSending:
    """Tests for sending data to TCP clients."""

    @pytest.mark.asyncio
    async def test_broadcast_sends_to_all(self) -> None:
        """broadcast() sends data to all connected clients."""
        from src.services.tcp_kiss_service import TcpKissService

        service = TcpKissService(port=0)

        writers = []
        for i in range(3):
            writer = make_mock_tcp_writer()
            writers.append(writer)
            service._add_client(f"client{i}:100{i}", asyncio.StreamReader(), writer)

        data = b"\xc0\x00test\xc0"
        await service.broadcast(data)

        for writer in writers:
            writer.write.assert_called_once_with(data)

    @pytest.mark.asyncio
    async def test_send_data_alias(self) -> None:
        """send_data() is an alias for broadcast()."""
        from src.services.tcp_kiss_service import TcpKissService

        service = TcpKissService(port=0)

        writer = make_mock_tcp_writer()
        service._add_client("client:1000", asyncio.StreamReader(), writer)

        data = b"\xc0\x00hello\xc0"
        await service.send_data(data)

        writer.write.assert_called_once_with(data)

    @pytest.mark.asyncio
    async def test_broadcast_to_empty_clients_is_safe(self) -> None:
        """broadcast() with no clients should not raise."""
        from src.services.tcp_kiss_service import TcpKissService

        service = TcpKissService(port=0)
        await service.broadcast(b"\xc0\x00test\xc0")  # Should not raise

    @pytest.mark.asyncio
    async def test_broadcast_skips_closing_writers(self) -> None:
        """broadcast() should skip writers that are closing."""
        from src.services.tcp_kiss_service import TcpKissService

        service = TcpKissService(port=0)

        good_writer = make_mock_tcp_writer()
        closing_writer = make_mock_tcp_writer(is_closing=True)

        service._add_client("good:1000", asyncio.StreamReader(), good_writer)
        service._add_client("closing:2000", asyncio.StreamReader(), closing_writer)

        data = b"\xc0\x00test\xc0"
        await service.broadcast(data)

        good_writer.write.assert_called_once_with(data)
        closing_writer.write.assert_not_called()


# =============================================================================
# Data receiving tests
# =============================================================================


class TestTcpKissServiceDataReceiving:
    """Tests for receiving data from TCP clients."""

    @pytest.mark.asyncio
    async def test_data_callback_called_with_frames(self) -> None:
        """set_data_callback receives parsed KISS frames."""
        from src.services.tcp_kiss_service import TcpKissService

        service = TcpKissService(port=0)
        received_data: list[bytes] = []

        def on_data(data: bytes) -> None:
            received_data.append(data)

        service.set_data_callback(on_data)

        # Register a client first so _handle_client_data finds it
        writer = make_mock_tcp_writer()
        service._add_client("client:1000", asyncio.StreamReader(), writer)

        # Simulate a client sending data
        frame = KISSFrame(port=0, command=KISSCommand.DATA_FRAME, data=b"hello")
        service._handle_client_data("client:1000", frame.encode())

        assert len(received_data) == 1
        # Callback receives re-encoded KISS frame bytes
        parser = KISSParser()
        frames = parser.feed(received_data[0])
        assert len(frames) == 1
        assert frames[0].data == b"hello"

    @pytest.mark.asyncio
    async def test_set_data_callback(self) -> None:
        """set_data_callback stores the callback."""
        from src.services.tcp_kiss_service import TcpKissService

        service = TcpKissService(port=0)
        callback = MagicMock()
        service.set_data_callback(callback)

        # Register a client first
        writer = make_mock_tcp_writer()
        service._add_client("client:1000", asyncio.StreamReader(), writer)

        # Verify callback is stored (indirectly)
        frame = KISSFrame(port=0, command=KISSCommand.DATA_FRAME, data=b"test")
        service._handle_client_data("client:1000", frame.encode())

        assert callback.called


# =============================================================================
# Integration with BridgeState
# =============================================================================


class TestTcpKissServiceBridgeState:
    """Tests for TcpKissService interaction with BridgeState."""

    def test_service_without_bridge_state(self) -> None:
        """Service works without bridge_state (standalone mode)."""
        from src.services.tcp_kiss_service import TcpKissService

        service = TcpKissService(port=0)
        writer = make_mock_tcp_writer()
        service._add_client("client:1000", asyncio.StreamReader(), writer)
        service._remove_client("client:1000")
        # Should not raise

    @pytest.mark.asyncio
    async def test_remove_client_updates_bridge_state(self) -> None:
        """Removing a client should remove TcpKissConnection from bridge state."""
        from src.models.connection import BLEConnection, ClassicConnection
        from src.models.kiss import KISSParser
        from src.models.state import BridgeState
        from src.services.tcp_kiss_service import TcpKissService

        state = BridgeState(
            ble=BLEConnection(),
            classic=ClassicConnection(target_address="00:11:22:33:44:55"),
            ble_parser=KISSParser(),
            classic_parser=KISSParser(),
        )
        service = TcpKissService(port=0, bridge_state=state)

        writer = make_mock_tcp_writer()
        service._add_client("192.168.1.1:5000", asyncio.StreamReader(), writer)
        assert len(state.tcp_clients) == 1

        service._remove_client("192.168.1.1:5000")
        assert len(state.tcp_clients) == 0
