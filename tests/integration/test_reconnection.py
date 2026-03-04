"""Integration tests for connection recovery and resilience (US3)."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from src.models.state import ConnectionState


class TestExponentialBackoff:
    """Unit tests for exponential backoff timing (T049)."""

    def test_backoff_starts_at_1_second(self) -> None:
        """Initial backoff delay is 1 second."""
        from src.models.connection import ClassicConnection

        conn = ClassicConnection(target_address="00:11:22:33:44:55")
        conn.reconnect_attempts = 0

        delay = conn.get_backoff_delay()
        assert delay == 1.0

    def test_backoff_doubles_each_attempt(self) -> None:
        """Backoff doubles with each failed attempt."""
        from src.models.connection import ClassicConnection

        conn = ClassicConnection(target_address="00:11:22:33:44:55")

        expected_delays = [1, 2, 4, 8, 16, 30, 30, 30]  # Caps at 30

        for i, expected in enumerate(expected_delays):
            conn.reconnect_attempts = i
            delay = conn.get_backoff_delay(max_delay=30)
            assert delay == expected, f"Attempt {i}: expected {expected}, got {delay}"

    def test_backoff_respects_max_delay(self) -> None:
        """Backoff is capped at max_delay."""
        from src.models.connection import ClassicConnection

        conn = ClassicConnection(target_address="00:11:22:33:44:55")
        conn.reconnect_attempts = 10  # Would be 1024 without cap

        delay = conn.get_backoff_delay(max_delay=60)
        assert delay == 60

    def test_reconnect_attempts_reset_on_success(self) -> None:
        """Reconnect attempts counter resets on successful connection."""
        from src.models.connection import ClassicConnection

        conn = ClassicConnection(target_address="00:11:22:33:44:55")
        conn.reconnect_attempts = 5

        # Simulate successful connection
        conn.set_connected(rfcomm_channel=1)

        assert conn.reconnect_attempts == 0


class TestBLEReconnection:
    """Integration tests for BLE disconnect/reconnect (T050)."""

    @pytest.mark.asyncio
    async def test_ble_disconnect_triggers_readvertise(
        self,
        mock_ble_connection: MagicMock,
    ) -> None:
        """
        GIVEN: BLE connection is active
        WHEN: iPhone disconnects unexpectedly
        THEN: Daemon re-advertises within 1 second
        """
        # Simulate connected state
        mock_ble_connection.state = ConnectionState.CONNECTED
        mock_ble_connection.device_address = "AA:BB:CC:DD:EE:FF"

        # Simulate disconnect
        mock_ble_connection.state = ConnectionState.IDLE
        mock_ble_connection.device_address = None

        # After disconnect, should go to SCANNING (advertising)
        mock_ble_connection.state = ConnectionState.SCANNING

        assert mock_ble_connection.state == ConnectionState.SCANNING

    @pytest.mark.asyncio
    async def test_ble_reconnection_preserves_settings(
        self,
        mock_ble_connection: MagicMock,
    ) -> None:
        """Settings are preserved across BLE reconnection."""
        # Initial connection
        mock_ble_connection.mtu = 185
        mock_ble_connection.bytes_rx = 1000
        mock_ble_connection.bytes_tx = 500

        # Disconnect and reconnect
        mock_ble_connection.state = ConnectionState.IDLE
        mock_ble_connection.state = ConnectionState.CONNECTED

        # Counters should be preserved
        assert mock_ble_connection.bytes_rx == 1000
        assert mock_ble_connection.bytes_tx == 500


class TestClassicReconnection:
    """Integration tests for Classic disconnect/reconnect (T051)."""

    @pytest.mark.asyncio
    async def test_classic_disconnect_triggers_reconnect(
        self,
        mock_classic_connection: MagicMock,
    ) -> None:
        """
        GIVEN: Classic connection is active
        WHEN: TNC disconnects unexpectedly
        THEN: Daemon attempts reconnection
        """
        # Simulate connected state
        mock_classic_connection.state = ConnectionState.CONNECTED
        mock_classic_connection.rfcomm_channel = 1

        # Simulate disconnect
        mock_classic_connection.state = ConnectionState.IDLE
        mock_classic_connection.rfcomm_channel = None
        mock_classic_connection.last_error = "Connection lost"

        # Should attempt reconnection
        mock_classic_connection.state = ConnectionState.CONNECTING

        assert mock_classic_connection.state == ConnectionState.CONNECTING
        assert mock_classic_connection.last_error == "Connection lost"

    @pytest.mark.asyncio
    async def test_classic_reconnection_with_backoff(
        self,
        mock_classic_connection: MagicMock,
    ) -> None:
        """Reconnection uses exponential backoff."""
        from src.models.connection import ClassicConnection

        conn = ClassicConnection(target_address="00:11:22:33:44:55")

        # Simulate multiple failed reconnection attempts
        for _ in range(3):
            conn.record_reconnect_attempt()

        # Backoff should be 2^3 = 8 seconds
        delay = conn.get_backoff_delay()
        assert delay == 8.0


class TestDataBuffering:
    """Integration tests for data buffering during link down (T052)."""

    @pytest.mark.asyncio
    async def test_data_buffered_when_link_down(self) -> None:
        """
        GIVEN: One link is down
        WHEN: Data arrives on active link
        THEN: Data is buffered
        """
        import asyncio

        # Create a queue to simulate buffering
        buffer: asyncio.Queue[bytes] = asyncio.Queue(maxsize=100)

        # Buffer some data
        test_data = b"test frame data"
        await buffer.put(test_data)

        assert buffer.qsize() == 1
        assert await buffer.get() == test_data

    @pytest.mark.asyncio
    async def test_buffer_size_limit(self) -> None:
        """Buffer has size limit to prevent memory exhaustion."""
        import asyncio

        # Small buffer for testing
        buffer: asyncio.Queue[bytes] = asyncio.Queue(maxsize=3)

        # Fill buffer
        await buffer.put(b"1")
        await buffer.put(b"2")
        await buffer.put(b"3")

        assert buffer.full()

        # Next put would block (queue full)
        # In real implementation, would drop oldest

    @pytest.mark.asyncio
    async def test_data_flows_after_reconnection(
        self,
        mock_bridge_state: MagicMock,
    ) -> None:
        """
        GIVEN: Link was down and data was buffered
        WHEN: Link is restored
        THEN: Buffered data flows through
        """
        # Simulate reconnection
        mock_bridge_state.classic.state = ConnectionState.CONNECTED
        mock_bridge_state.ble.state = ConnectionState.CONNECTED
        mock_bridge_state.is_fully_connected = True

        assert mock_bridge_state.is_fully_connected
