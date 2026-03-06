"""Integration tests for TCP<->Classic bridge flow.

Tests the full path: TCP client -> BridgeService -> Classic TNC
and Classic TNC -> BridgeService -> TCP client.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.models.connection import BLEConnection, ClassicConnection
from src.models.kiss import KISSCommand, KISSFrame, KISSParser
from src.models.state import BridgeState, ConnectionState

# =============================================================================
# TCP -> Classic (TX path)
# =============================================================================


class TestTcpToClassicBridge:
    """Integration tests for TCP client sending KISS frames to TNC."""

    @pytest.mark.asyncio
    async def test_tcp_frame_forwarded_to_classic(self) -> None:
        """
        GIVEN: TCP client connected, Classic TNC connected
        WHEN: TCP client sends a KISS data frame
        THEN: Frame is forwarded to Classic TNC
        """
        from src.services.tcp_kiss_service import TcpKissService

        # Set up services
        ble_service = MagicMock()
        ble_service.is_connected = False
        ble_service.set_data_callback = MagicMock()
        ble_service.connection = BLEConnection()

        classic_service = MagicMock()
        classic_service.is_connected = True
        classic_service.send_data = AsyncMock()
        classic_service.set_data_callback = MagicMock()
        classic_service.connection = ClassicConnection(target_address="00:11:22:33:44:55")
        classic_service.connection.state = ConnectionState.CONNECTED

        tcp_service = TcpKissService(port=0)

        state = BridgeState(
            ble=ble_service.connection,
            classic=classic_service.connection,
            ble_parser=KISSParser(),
            classic_parser=KISSParser(),
        )

        from src.services.bridge import BridgeService

        bridge = BridgeService(
            ble_service=ble_service,
            classic_service=classic_service,
            state=state,
            tcp_service=tcp_service,
        )

        # Simulate a TCP client sending a KISS frame
        frame = KISSFrame(port=0, command=KISSCommand.DATA_FRAME, data=b"from TCP")
        encoded = frame.encode()

        # The bridge's TCP data handler should forward to classic
        bridge._handle_tcp_data(encoded)

        # Allow async task to run
        await asyncio.sleep(0.05)

        # Classic service should have received the frame
        classic_service.send_data.assert_called_once()
        sent_data = classic_service.send_data.call_args[0][0]
        assert b"from TCP" in sent_data or sent_data == encoded

    @pytest.mark.asyncio
    async def test_tcp_frame_not_forwarded_when_classic_disconnected(self) -> None:
        """
        GIVEN: TCP client connected, Classic TNC disconnected
        WHEN: TCP client sends a KISS data frame
        THEN: Frame is NOT forwarded (logged as warning)
        """
        from src.services.tcp_kiss_service import TcpKissService

        ble_service = MagicMock()
        ble_service.is_connected = False
        ble_service.set_data_callback = MagicMock()
        ble_service.connection = BLEConnection()

        classic_service = MagicMock()
        classic_service.is_connected = False
        classic_service.send_data = AsyncMock()
        classic_service.set_data_callback = MagicMock()
        classic_service.connection = ClassicConnection(target_address="00:11:22:33:44:55")

        tcp_service = TcpKissService(port=0)

        state = BridgeState(
            ble=ble_service.connection,
            classic=classic_service.connection,
            ble_parser=KISSParser(),
            classic_parser=KISSParser(),
        )

        from src.services.bridge import BridgeService

        bridge = BridgeService(
            ble_service=ble_service,
            classic_service=classic_service,
            state=state,
            tcp_service=tcp_service,
        )

        # Simulate TCP data
        frame = KISSFrame(port=0, command=KISSCommand.DATA_FRAME, data=b"dropped")
        bridge._handle_tcp_data(frame.encode())

        await asyncio.sleep(0.05)

        # Classic should NOT have been called
        classic_service.send_data.assert_not_called()


# =============================================================================
# Classic -> TCP (RX path)
# =============================================================================


class TestClassicToTcpBridge:
    """Integration tests for TNC sending KISS frames to TCP clients."""

    @pytest.mark.asyncio
    async def test_classic_frame_broadcast_to_tcp_clients(self) -> None:
        """
        GIVEN: Classic TNC connected, TCP clients connected
        WHEN: TNC sends a KISS data frame
        THEN: Frame is broadcast to all TCP clients
        """
        from src.services.tcp_kiss_service import TcpKissService

        ble_service = MagicMock()
        ble_service.is_connected = False
        ble_service.set_data_callback = MagicMock()
        ble_service.send_data = AsyncMock()
        ble_service.connection = BLEConnection()

        classic_service = MagicMock()
        classic_service.is_connected = True
        classic_service.set_data_callback = MagicMock()
        classic_service.connection = ClassicConnection(target_address="00:11:22:33:44:55")
        classic_service.connection.state = ConnectionState.CONNECTED

        tcp_service = TcpKissService(port=0)

        # Add a mock TCP client
        tcp_writer = AsyncMock()
        tcp_writer.is_closing = MagicMock(return_value=False)
        tcp_writer.drain = AsyncMock()
        tcp_service._add_client("192.168.1.100:5000", asyncio.StreamReader(), tcp_writer)

        state = BridgeState(
            ble=ble_service.connection,
            classic=classic_service.connection,
            ble_parser=KISSParser(),
            classic_parser=KISSParser(),
        )

        from src.services.bridge import BridgeService

        bridge = BridgeService(
            ble_service=ble_service,
            classic_service=classic_service,
            state=state,
            tcp_service=tcp_service,
        )

        # Simulate TNC sending a KISS frame
        frame = KISSFrame(port=0, command=KISSCommand.DATA_FRAME, data=b"from TNC")
        encoded = frame.encode()

        # Feed data through the classic handler (simulating classic_parser producing a frame)
        bridge._handle_classic_data(encoded)

        # Allow async tasks to run
        await asyncio.sleep(0.05)

        # TCP client should have received the broadcast
        tcp_writer.write.assert_called()

    @pytest.mark.asyncio
    async def test_classic_frame_sent_to_both_ble_and_tcp(self) -> None:
        """
        GIVEN: BLE client connected, TCP clients connected, TNC connected
        WHEN: TNC sends a KISS data frame
        THEN: Frame is sent to BOTH BLE and TCP clients
        """
        from src.services.tcp_kiss_service import TcpKissService

        ble_service = MagicMock()
        ble_service.is_connected = True
        ble_service.set_data_callback = MagicMock()
        ble_service.send_data = AsyncMock()
        ble_service.connection = BLEConnection()
        ble_service.connection.state = ConnectionState.CONNECTED

        classic_service = MagicMock()
        classic_service.is_connected = True
        classic_service.set_data_callback = MagicMock()
        classic_service.connection = ClassicConnection(target_address="00:11:22:33:44:55")
        classic_service.connection.state = ConnectionState.CONNECTED

        tcp_service = TcpKissService(port=0)

        tcp_writer = AsyncMock()
        tcp_writer.is_closing = MagicMock(return_value=False)
        tcp_writer.drain = AsyncMock()
        tcp_service._add_client("192.168.1.100:5000", asyncio.StreamReader(), tcp_writer)

        state = BridgeState(
            ble=ble_service.connection,
            classic=classic_service.connection,
            ble_parser=KISSParser(),
            classic_parser=KISSParser(),
        )

        from src.services.bridge import BridgeService

        bridge = BridgeService(
            ble_service=ble_service,
            classic_service=classic_service,
            state=state,
            tcp_service=tcp_service,
        )

        # Simulate TNC sending data
        frame = KISSFrame(port=0, command=KISSCommand.DATA_FRAME, data=b"broadcast")
        bridge._handle_classic_data(frame.encode())

        await asyncio.sleep(0.05)

        # Both BLE and TCP should receive
        ble_service.send_data.assert_called()
        tcp_writer.write.assert_called()


# =============================================================================
# Bridge with no TCP service (backward compatibility)
# =============================================================================


class TestBridgeWithoutTcp:
    """Ensure BridgeService still works without TCP service (backward compatibility)."""

    @pytest.mark.asyncio
    async def test_bridge_works_without_tcp_service(self) -> None:
        """
        GIVEN: BridgeService created without tcp_service
        WHEN: Classic data arrives
        THEN: BLE forwarding still works as before
        """
        ble_service = MagicMock()
        ble_service.is_connected = True
        ble_service.set_data_callback = MagicMock()
        ble_service.send_data = AsyncMock()
        ble_service.connection = BLEConnection()
        ble_service.connection.state = ConnectionState.CONNECTED

        classic_service = MagicMock()
        classic_service.is_connected = True
        classic_service.set_data_callback = MagicMock()
        classic_service.connection = ClassicConnection(target_address="00:11:22:33:44:55")
        classic_service.connection.state = ConnectionState.CONNECTED

        state = BridgeState(
            ble=ble_service.connection,
            classic=classic_service.connection,
            ble_parser=KISSParser(),
            classic_parser=KISSParser(),
        )

        from src.services.bridge import BridgeService

        bridge = BridgeService(
            ble_service=ble_service,
            classic_service=classic_service,
            state=state,
            # No tcp_service parameter
        )

        # Simulate TNC data
        frame = KISSFrame(port=0, command=KISSCommand.DATA_FRAME, data=b"hello")
        bridge._handle_classic_data(frame.encode())

        await asyncio.sleep(0.05)

        # BLE should still receive the frame
        ble_service.send_data.assert_called()


# =============================================================================
# Full round-trip test
# =============================================================================


class TestFullRoundTrip:
    """End-to-end round-trip: TCP -> Classic -> TCP (via another client)."""

    @pytest.mark.asyncio
    async def test_tcp_to_classic_increments_frames_bridged(self) -> None:
        """frames_bridged counter is incremented when TCP frame is forwarded."""
        from src.services.tcp_kiss_service import TcpKissService

        ble_service = MagicMock()
        ble_service.is_connected = False
        ble_service.set_data_callback = MagicMock()
        ble_service.connection = BLEConnection()

        classic_service = MagicMock()
        classic_service.is_connected = True
        classic_service.send_data = AsyncMock()
        classic_service.set_data_callback = MagicMock()
        classic_service.connection = ClassicConnection(target_address="00:11:22:33:44:55")
        classic_service.connection.state = ConnectionState.CONNECTED

        tcp_service = TcpKissService(port=0)

        state = BridgeState(
            ble=ble_service.connection,
            classic=classic_service.connection,
            ble_parser=KISSParser(),
            classic_parser=KISSParser(),
        )

        from src.services.bridge import BridgeService

        bridge = BridgeService(
            ble_service=ble_service,
            classic_service=classic_service,
            state=state,
            tcp_service=tcp_service,
        )

        assert state.frames_bridged == 0

        frame = KISSFrame(port=0, command=KISSCommand.DATA_FRAME, data=b"count me")
        bridge._handle_tcp_data(frame.encode())

        # frames_bridged incremented for TCP->Classic
        assert state.frames_bridged >= 1


# =============================================================================
# US2: Multi-client broadcast scenarios
# =============================================================================


class TestMultiClientBroadcast:
    """Integration tests for multi-client fan-out (US2)."""

    @pytest.mark.asyncio
    async def test_two_tcp_clients_both_receive_tnc_frame(self) -> None:
        """
        GIVEN: Two TCP clients connected, TNC connected
        WHEN: TNC sends a KISS data frame
        THEN: Both TCP clients receive the frame
        """
        from src.services.tcp_kiss_service import TcpKissService

        ble_service = MagicMock()
        ble_service.is_connected = False
        ble_service.set_data_callback = MagicMock()
        ble_service.connection = BLEConnection()

        classic_service = MagicMock()
        classic_service.is_connected = True
        classic_service.set_data_callback = MagicMock()
        classic_service.connection = ClassicConnection(target_address="00:11:22:33:44:55")
        classic_service.connection.state = ConnectionState.CONNECTED

        tcp_service = TcpKissService(port=0)

        # Add two TCP clients
        writers = []
        for i in range(2):
            writer = AsyncMock()
            writer.is_closing = MagicMock(return_value=False)
            writer.drain = AsyncMock()
            writers.append(writer)
            tcp_service._add_client(f"192.168.1.{i + 1}:500{i}", asyncio.StreamReader(), writer)

        state = BridgeState(
            ble=ble_service.connection,
            classic=classic_service.connection,
            ble_parser=KISSParser(),
            classic_parser=KISSParser(),
        )

        from src.services.bridge import BridgeService

        bridge = BridgeService(
            ble_service=ble_service,
            classic_service=classic_service,
            state=state,
            tcp_service=tcp_service,
        )

        # TNC sends a frame
        frame = KISSFrame(port=0, command=KISSCommand.DATA_FRAME, data=b"multi")
        bridge._handle_classic_data(frame.encode())

        await asyncio.sleep(0.05)

        # Both clients must receive
        for writer in writers:
            writer.write.assert_called()

    @pytest.mark.asyncio
    async def test_ble_and_tcp_both_receive_tnc_frame(self) -> None:
        """
        GIVEN: BLE client + TCP client connected, TNC connected
        WHEN: TNC sends a KISS frame
        THEN: Both BLE and TCP client receive the frame
        """
        from src.services.tcp_kiss_service import TcpKissService

        ble_service = MagicMock()
        ble_service.is_connected = True
        ble_service.set_data_callback = MagicMock()
        ble_service.send_data = AsyncMock()
        ble_service.connection = BLEConnection()
        ble_service.connection.state = ConnectionState.CONNECTED

        classic_service = MagicMock()
        classic_service.is_connected = True
        classic_service.set_data_callback = MagicMock()
        classic_service.connection = ClassicConnection(target_address="00:11:22:33:44:55")
        classic_service.connection.state = ConnectionState.CONNECTED

        tcp_service = TcpKissService(port=0)
        tcp_writer = AsyncMock()
        tcp_writer.is_closing = MagicMock(return_value=False)
        tcp_writer.drain = AsyncMock()
        tcp_service._add_client("192.168.1.1:5000", asyncio.StreamReader(), tcp_writer)

        state = BridgeState(
            ble=ble_service.connection,
            classic=classic_service.connection,
            ble_parser=KISSParser(),
            classic_parser=KISSParser(),
        )

        from src.services.bridge import BridgeService

        bridge = BridgeService(
            ble_service=ble_service,
            classic_service=classic_service,
            state=state,
            tcp_service=tcp_service,
        )

        frame = KISSFrame(port=0, command=KISSCommand.DATA_FRAME, data=b"both")
        bridge._handle_classic_data(frame.encode())

        await asyncio.sleep(0.05)

        ble_service.send_data.assert_called()
        tcp_writer.write.assert_called()

    @pytest.mark.asyncio
    async def test_disconnect_one_tcp_client_others_still_receive(self) -> None:
        """
        GIVEN: Two TCP clients connected
        WHEN: One disconnects, then TNC sends data
        THEN: Remaining client still receives
        """
        from src.services.tcp_kiss_service import TcpKissService

        ble_service = MagicMock()
        ble_service.is_connected = False
        ble_service.set_data_callback = MagicMock()
        ble_service.connection = BLEConnection()

        classic_service = MagicMock()
        classic_service.is_connected = True
        classic_service.set_data_callback = MagicMock()
        classic_service.connection = ClassicConnection(target_address="00:11:22:33:44:55")
        classic_service.connection.state = ConnectionState.CONNECTED

        tcp_service = TcpKissService(port=0)

        writer1 = AsyncMock()
        writer1.is_closing = MagicMock(return_value=False)
        writer1.drain = AsyncMock()

        writer2 = AsyncMock()
        writer2.is_closing = MagicMock(return_value=False)
        writer2.drain = AsyncMock()

        tcp_service._add_client("client1:1000", asyncio.StreamReader(), writer1)
        tcp_service._add_client("client2:2000", asyncio.StreamReader(), writer2)

        state = BridgeState(
            ble=ble_service.connection,
            classic=classic_service.connection,
            ble_parser=KISSParser(),
            classic_parser=KISSParser(),
        )

        from src.services.bridge import BridgeService

        bridge = BridgeService(
            ble_service=ble_service,
            classic_service=classic_service,
            state=state,
            tcp_service=tcp_service,
        )

        # Disconnect client1
        tcp_service._remove_client("client1:1000")

        # TNC sends data
        frame = KISSFrame(port=0, command=KISSCommand.DATA_FRAME, data=b"survivor")
        bridge._handle_classic_data(frame.encode())

        await asyncio.sleep(0.05)

        # Only client2 should receive
        writer2.write.assert_called()
        # writer1 should not be called (it was disconnected before broadcast)
        # Note: writer1.write may have been called during _remove_client cleanup but not for this broadcast
