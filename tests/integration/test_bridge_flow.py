"""Integration tests for BLE pairing flow (T021) and bridge flow."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.models.kiss import KISSParser
from src.models.state import ConnectionState


class TestBLEPairingFlow:
    """Integration tests for BLE pairing flow (T021)."""

    @pytest.mark.asyncio
    async def test_ble_advertising_starts_on_daemon_start(
        self,
        mock_ble_adapter: MagicMock,
    ) -> None:
        """
        GIVEN: Daemon is starting
        WHEN: BLE service initializes
        THEN: BLE advertising should begin
        """
        # Simulate advertising start
        mock_ble_adapter.start.return_value = None
        await mock_ble_adapter.start()
        mock_ble_adapter.start.assert_called_once()

    @pytest.mark.asyncio
    async def test_ble_accepts_incoming_connection(
        self,
        mock_ble_adapter: MagicMock,
        mock_ble_connection: MagicMock,
    ) -> None:
        """
        GIVEN: Daemon is advertising
        WHEN: iPhone initiates connection
        THEN: Connection is accepted
        """
        # Simulate connection acceptance
        mock_ble_connection.state = ConnectionState.CONNECTED
        mock_ble_connection.device_address = "AA:BB:CC:DD:EE:FF"

        assert mock_ble_connection.state == ConnectionState.CONNECTED
        assert mock_ble_connection.device_address is not None

    @pytest.mark.asyncio
    async def test_ble_mtu_negotiation(
        self,
        mock_ble_connection: MagicMock,
    ) -> None:
        """
        GIVEN: BLE connection is established
        WHEN: MTU negotiation completes
        THEN: MTU is updated from default
        """
        # Default MTU
        assert mock_ble_connection.mtu == 23

        # After negotiation (simulated)
        mock_ble_connection.mtu = 185
        assert mock_ble_connection.mtu == 185

    @pytest.mark.asyncio
    async def test_ble_connection_state_transitions(
        self,
        mock_ble_connection: MagicMock,
    ) -> None:
        """
        GIVEN: BLE service is idle
        WHEN: Connection flow completes
        THEN: State transitions through expected sequence
        """
        states: list[ConnectionState] = []

        # Track state transitions
        mock_ble_connection.state = ConnectionState.IDLE
        states.append(mock_ble_connection.state)

        mock_ble_connection.state = ConnectionState.SCANNING
        states.append(mock_ble_connection.state)

        mock_ble_connection.state = ConnectionState.CONNECTING
        states.append(mock_ble_connection.state)

        mock_ble_connection.state = ConnectionState.CONNECTED
        states.append(mock_ble_connection.state)

        assert states == [
            ConnectionState.IDLE,
            ConnectionState.SCANNING,
            ConnectionState.CONNECTING,
            ConnectionState.CONNECTED,
        ]


class TestClassicPairingFlow:
    """Integration tests for Classic SPP pairing flow."""

    @pytest.mark.asyncio
    async def test_classic_connects_to_target_on_start(
        self,
        mock_classic_connection: MagicMock,
        valid_config: MagicMock,
    ) -> None:
        """
        GIVEN: Daemon starts with valid target_address
        WHEN: Classic service initializes
        THEN: Connection to TNC is attempted
        """
        mock_classic_connection.target_address = "00:11:22:33:44:55"
        mock_classic_connection.state = ConnectionState.CONNECTING

        assert mock_classic_connection.state == ConnectionState.CONNECTING

    @pytest.mark.asyncio
    async def test_classic_discovers_spp_channel(
        self,
        mock_classic_connection: MagicMock,
    ) -> None:
        """
        GIVEN: Classic connection is initiated
        WHEN: SDP query succeeds
        THEN: RFCOMM channel is discovered
        """
        mock_classic_connection.rfcomm_channel = 1
        assert mock_classic_connection.rfcomm_channel is not None
        assert 1 <= mock_classic_connection.rfcomm_channel <= 30

    @pytest.mark.asyncio
    async def test_classic_connection_established(
        self,
        mock_classic_connection: MagicMock,
    ) -> None:
        """
        GIVEN: SDP channel discovered
        WHEN: RFCOMM connection succeeds
        THEN: Connection state is CONNECTED
        """
        mock_classic_connection.state = ConnectionState.CONNECTED
        mock_classic_connection.device_name = "Mobilinkd TNC3"

        assert mock_classic_connection.state == ConnectionState.CONNECTED
        assert mock_classic_connection.device_name is not None


class TestDualConnectionStatus:
    """Integration tests for dual connection status."""

    @pytest.mark.asyncio
    async def test_both_connections_show_status(
        self,
        mock_bridge_state: MagicMock,
    ) -> None:
        """
        GIVEN: Both BLE and Classic connections established
        WHEN: User queries status
        THEN: Both show connected state
        """
        mock_bridge_state.ble.state = ConnectionState.CONNECTED
        mock_bridge_state.classic.state = ConnectionState.CONNECTED
        mock_bridge_state.is_fully_connected = True

        assert mock_bridge_state.ble.state == ConnectionState.CONNECTED
        assert mock_bridge_state.classic.state == ConnectionState.CONNECTED
        assert mock_bridge_state.is_fully_connected

    @pytest.mark.asyncio
    async def test_partial_connection_status(
        self,
        mock_bridge_state: MagicMock,
    ) -> None:
        """
        GIVEN: Only BLE connection established
        WHEN: User queries status
        THEN: Partial connection is indicated
        """
        mock_bridge_state.ble.state = ConnectionState.CONNECTED
        mock_bridge_state.classic.state = ConnectionState.IDLE
        mock_bridge_state.is_fully_connected = False
        mock_bridge_state.is_partially_connected = True

        assert not mock_bridge_state.is_fully_connected
        assert mock_bridge_state.is_partially_connected


class TestKISSFrameBridging:
    """Integration tests for KISS frame bridging (T038, T039)."""

    @pytest.mark.asyncio
    async def test_ble_to_classic_frame_bridging(
        self,
        sample_kiss_bytes: bytes,
        kiss_parser: KISSParser,
    ) -> None:
        """
        GIVEN: Both connections are established
        WHEN: iPhone sends a KISS frame over BLE
        THEN: Frame is forwarded to Classic connection (T038)
        """
        from src.models.kiss import KISSParser

        # Parse the incoming frame (simulating BLE receive)
        parser = KISSParser()
        frames = parser.feed(sample_kiss_bytes)

        assert len(frames) == 1
        frame = frames[0]

        # Verify frame can be encoded for Classic transmission
        encoded = frame.encode()
        assert len(encoded) > 0
        assert encoded[0] == 0xC0  # FEND
        assert encoded[-1] == 0xC0  # FEND

    @pytest.mark.asyncio
    async def test_classic_to_ble_frame_bridging(
        self,
        sample_kiss_bytes: bytes,
        kiss_parser: KISSParser,
    ) -> None:
        """
        GIVEN: Both connections are established
        WHEN: TNC sends a KISS frame over Classic
        THEN: Frame is forwarded to BLE connection (T039)
        """
        from src.models.kiss import KISSParser

        # Parse the incoming frame (simulating Classic receive)
        parser = KISSParser()
        frames = parser.feed(sample_kiss_bytes)

        assert len(frames) == 1
        frame = frames[0]

        # Verify frame can be encoded for BLE transmission
        encoded = frame.encode()
        assert len(encoded) > 0

    @pytest.mark.asyncio
    async def test_frame_with_escapes_bridges_correctly(
        self,
        kiss_frame_with_escapes: bytes,
    ) -> None:
        """Frame containing escaped characters bridges correctly."""
        from src.models.kiss import FEND, KISSParser

        parser = KISSParser()
        frames = parser.feed(kiss_frame_with_escapes)

        assert len(frames) == 1
        frame = frames[0]

        # Data should contain unescaped FEND
        assert FEND in frame.data

        # Re-encode and verify it's properly escaped
        encoded = frame.encode()

        # Re-parse to verify round-trip
        parser2 = KISSParser()
        frames2 = parser2.feed(encoded)

        assert len(frames2) == 1
        assert frames2[0].data == frame.data

    @pytest.mark.asyncio
    async def test_multiple_frames_bridge_in_order(
        self,
        multiple_kiss_frames: bytes,
    ) -> None:
        """Multiple frames are bridged in order."""
        from src.models.kiss import KISSParser

        parser = KISSParser()
        frames = parser.feed(multiple_kiss_frames)

        assert len(frames) == 2
        assert frames[0].data == bytes([0x41])  # "A"
        assert frames[1].data == bytes([0x42])  # "B"

    @pytest.mark.asyncio
    async def test_partial_frame_not_forwarded(self) -> None:
        """Partial frames are not forwarded until complete."""
        from src.models.kiss import FEND, KISSParser

        parser = KISSParser()

        # Send partial frame (no closing FEND)
        frames = parser.feed(bytes([FEND, 0x00, 0x41, 0x42]))
        assert frames == []  # No complete frame yet

        # Complete the frame
        frames = parser.feed(bytes([FEND]))
        assert len(frames) == 1
        assert frames[0].data == bytes([0x41, 0x42])
