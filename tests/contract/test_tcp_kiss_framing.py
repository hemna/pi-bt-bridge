"""Contract tests for KISS-over-TCP frame integrity and reassembly.

Tests CT-001 through CT-006 from specs/004-tcp-kiss-server/contracts/tcp-kiss-protocol.md.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from src.models.kiss import FEND, FESC, TFEND, TFESC, KISSCommand, KISSFrame, KISSParser
from tests.conftest import make_mock_tcp_writer

# =============================================================================
# CT-001: Frame Integrity
# =============================================================================


class TestFrameIntegrity:
    """CT-001: KISS frames must arrive intact through TCP transport."""

    def test_tcp_client_kiss_frame_parsed_identically(self) -> None:
        """A complete KISS frame sent by a TCP client MUST arrive as an identical KISSFrame."""
        parser = KISSParser()

        # Simulate a TCP client sending a KISS data frame: FEND + cmd(port=0, DATA) + payload + FEND
        payload = b"APRS>TEST:hello world"
        frame_bytes = KISSFrame(port=0, command=KISSCommand.DATA_FRAME, data=payload).encode()

        frames = parser.feed(frame_bytes)

        assert len(frames) == 1
        assert frames[0].port == 0
        assert frames[0].command == KISSCommand.DATA_FRAME
        assert frames[0].data == payload

    def test_tnc_kiss_frame_encoded_for_tcp(self) -> None:
        """A KISS frame from the TNC MUST arrive at the TCP client as identical bytes."""
        # Frame from TNC
        original = KISSFrame(port=0, command=KISSCommand.DATA_FRAME, data=b"TNC data")
        encoded = original.encode()

        # TCP client receives encoded bytes and parses
        parser = KISSParser()
        frames = parser.feed(encoded)

        assert len(frames) == 1
        assert frames[0].data == b"TNC data"
        assert frames[0].command == KISSCommand.DATA_FRAME

    def test_round_trip_integrity(self) -> None:
        """Encode -> decode round-trip must preserve all fields."""
        original = KISSFrame(port=3, command=KISSCommand.TX_DELAY, data=bytes([0x1E]))
        encoded = original.encode()

        parser = KISSParser()
        frames = parser.feed(encoded)

        assert len(frames) == 1
        assert frames[0].port == original.port
        assert frames[0].command == original.command
        assert frames[0].data == original.data

    def test_binary_payload_integrity(self) -> None:
        """Binary payloads (all byte values) must survive encode/decode."""
        # All byte values except FEND and FESC (which get escaped)
        payload = bytes(range(256))
        frame = KISSFrame(port=0, command=KISSCommand.DATA_FRAME, data=payload)
        encoded = frame.encode()

        parser = KISSParser()
        frames = parser.feed(encoded)

        assert len(frames) == 1
        assert frames[0].data == payload


# =============================================================================
# CT-002: Frame Reassembly
# =============================================================================


class TestFrameReassembly:
    """CT-002: Frames split across TCP segments must be reassembled correctly."""

    def test_frame_split_across_two_segments(self) -> None:
        """A KISS frame split across two TCP reads MUST be reassembled."""
        parser = KISSParser()
        frame_bytes = bytes([FEND, 0x00, 0x48, 0x45, 0x4C, 0x4C, 0x4F, FEND])

        # Split in the middle
        segment1 = frame_bytes[:4]
        segment2 = frame_bytes[4:]

        frames1 = parser.feed(segment1)
        assert len(frames1) == 0  # Not complete yet

        frames2 = parser.feed(segment2)
        assert len(frames2) == 1
        assert frames2[0].data == b"HELLO"

    def test_frame_split_byte_by_byte(self) -> None:
        """Frame delivered one byte at a time must still be reassembled."""
        parser = KISSParser()
        frame_bytes = bytes([FEND, 0x00, 0x41, 0x42, 0x43, FEND])

        all_frames = []
        for b in frame_bytes:
            all_frames.extend(parser.feed(bytes([b])))

        assert len(all_frames) == 1
        assert all_frames[0].data == b"ABC"

    def test_multiple_frames_in_single_segment(self) -> None:
        """Multiple KISS frames in a single TCP segment MUST be parsed as separate frames."""
        parser = KISSParser()

        frame1 = KISSFrame(port=0, command=KISSCommand.DATA_FRAME, data=b"first").encode()
        frame2 = KISSFrame(port=0, command=KISSCommand.DATA_FRAME, data=b"second").encode()

        # Both frames in one TCP segment
        combined = frame1 + frame2

        frames = parser.feed(combined)

        assert len(frames) == 2
        assert frames[0].data == b"first"
        assert frames[1].data == b"second"

    def test_partial_frame_then_rest_plus_next(self) -> None:
        """Partial frame, then rest + start of next, then rest of next."""
        parser = KISSParser()

        frame1 = bytes([FEND, 0x00, 0x41, 0x42, FEND])
        frame2 = bytes([FEND, 0x00, 0x43, 0x44, FEND])

        # Segment 1: first 3 bytes of frame1
        frames = parser.feed(frame1[:3])
        assert len(frames) == 0

        # Segment 2: rest of frame1 + all of frame2
        frames = parser.feed(frame1[3:] + frame2)
        assert len(frames) == 2
        assert frames[0].data == b"AB"
        assert frames[1].data == b"CD"


# =============================================================================
# CT-003: KISS Escaping
# =============================================================================


class TestKISSEscapingOverTcp:
    """CT-003: KISS escape sequences must work correctly over TCP."""

    def test_fend_in_data_escaped(self) -> None:
        """0xC0 bytes within frame data MUST be escaped as 0xDB 0xDC."""
        frame = KISSFrame(port=0, command=KISSCommand.DATA_FRAME, data=bytes([0xC0]))
        encoded = frame.encode()

        # Check that the encoded bytes contain the escape sequence
        assert bytes([FESC, TFEND]) in encoded

        # Verify round-trip
        parser = KISSParser()
        frames = parser.feed(encoded)
        assert len(frames) == 1
        assert frames[0].data == bytes([0xC0])

    def test_fesc_in_data_escaped(self) -> None:
        """0xDB bytes within frame data MUST be escaped as 0xDB 0xDD."""
        frame = KISSFrame(port=0, command=KISSCommand.DATA_FRAME, data=bytes([0xDB]))
        encoded = frame.encode()

        assert bytes([FESC, TFESC]) in encoded

        parser = KISSParser()
        frames = parser.feed(encoded)
        assert len(frames) == 1
        assert frames[0].data == bytes([0xDB])

    def test_escaped_sequences_unescaped_on_receive(self) -> None:
        """Escaped sequences MUST be unescaped correctly on receive."""
        parser = KISSParser()

        # Manually build: FEND + cmd + A + escaped_FEND + escaped_FESC + B + FEND
        data = bytes([FEND, 0x00, 0x41, FESC, TFEND, FESC, TFESC, 0x42, FEND])
        frames = parser.feed(data)

        assert len(frames) == 1
        assert frames[0].data == bytes([0x41, 0xC0, 0xDB, 0x42])

    def test_multiple_consecutive_escapes(self) -> None:
        """Multiple consecutive escape sequences must be handled."""
        # Data: FEND FEND FESC FESC
        payload = bytes([0xC0, 0xC0, 0xDB, 0xDB])
        frame = KISSFrame(port=0, command=KISSCommand.DATA_FRAME, data=payload)
        encoded = frame.encode()

        parser = KISSParser()
        frames = parser.feed(encoded)

        assert len(frames) == 1
        assert frames[0].data == payload


# =============================================================================
# CT-004: Multi-Client Broadcast
# =============================================================================


class TestMultiClientBroadcast:
    """CT-004: TNC frames must be delivered to ALL connected TCP clients."""

    @pytest.mark.asyncio
    async def test_broadcast_to_all_tcp_clients(self) -> None:
        """A KISS frame from the TNC MUST be delivered to ALL connected TCP clients."""
        from src.services.tcp_kiss_service import TcpKissService

        service = TcpKissService(port=0)  # port=0 for tests

        # Create mock writers for 3 clients
        writers = []
        for _i in range(3):
            writer = make_mock_tcp_writer()
            writers.append(writer)

        # Register clients
        for i, writer in enumerate(writers):
            service._add_client(f"192.168.1.{i}:5000{i}", asyncio.StreamReader(), writer)

        # Broadcast a KISS frame
        frame_data = KISSFrame(port=0, command=KISSCommand.DATA_FRAME, data=b"broadcast").encode()
        await service.broadcast(frame_data)

        # All 3 clients must have received the data
        for writer in writers:
            writer.write.assert_called_once_with(frame_data)

    @pytest.mark.asyncio
    async def test_broadcast_handles_failed_client(self) -> None:
        """A write error on one client MUST NOT affect other clients."""
        from src.services.tcp_kiss_service import TcpKissService

        service = TcpKissService(port=0)

        good_writer = make_mock_tcp_writer()

        bad_writer = make_mock_tcp_writer()
        bad_writer.drain = AsyncMock(side_effect=ConnectionResetError("broken"))

        service._add_client("good:1000", asyncio.StreamReader(), good_writer)
        service._add_client("bad:2000", asyncio.StreamReader(), bad_writer)

        frame_data = KISSFrame(port=0, command=KISSCommand.DATA_FRAME, data=b"test").encode()
        await service.broadcast(frame_data)

        # Good client must still have received data
        good_writer.write.assert_called_once_with(frame_data)


# =============================================================================
# CT-005: Client Isolation
# =============================================================================


class TestClientIsolation:
    """CT-005: Client failures must not affect other clients."""

    @pytest.mark.asyncio
    async def test_disconnect_does_not_affect_others(self) -> None:
        """One client disconnecting MUST NOT affect other clients."""
        from src.services.tcp_kiss_service import TcpKissService

        service = TcpKissService(port=0)

        writer1 = make_mock_tcp_writer()
        writer2 = make_mock_tcp_writer()

        service._add_client("client1:1000", asyncio.StreamReader(), writer1)
        service._add_client("client2:2000", asyncio.StreamReader(), writer2)

        # Remove client1
        service._remove_client("client1:1000")

        assert service.client_count == 1

        # Broadcast should still work for client2
        data = KISSFrame(port=0, command=KISSCommand.DATA_FRAME, data=b"still works").encode()
        await service.broadcast(data)

        writer2.write.assert_called_once_with(data)
        writer1.write.assert_not_called()


# =============================================================================
# CT-006: Connection Limit
# =============================================================================


class TestConnectionLimit:
    """CT-006: Connection limit must be enforced."""

    @pytest.mark.asyncio
    async def test_reject_when_max_clients_reached(self) -> None:
        """When max_clients is reached, new connections MUST be rejected."""
        from src.services.tcp_kiss_service import TcpKissService

        service = TcpKissService(port=0, max_clients=2)

        # Add 2 clients (at limit)
        for i in range(2):
            writer = make_mock_tcp_writer()
            service._add_client(f"client{i}:100{i}", asyncio.StreamReader(), writer)

        assert service.client_count == 2
        assert service.is_at_capacity

    @pytest.mark.asyncio
    async def test_accept_after_disconnect_frees_slot(self) -> None:
        """After a client disconnects, a new client MUST be able to connect."""
        from src.services.tcp_kiss_service import TcpKissService

        service = TcpKissService(port=0, max_clients=1)

        writer1 = make_mock_tcp_writer()
        service._add_client("client1:1000", asyncio.StreamReader(), writer1)

        assert service.is_at_capacity

        # Remove client, freeing a slot
        service._remove_client("client1:1000")

        assert not service.is_at_capacity
        assert service.client_count == 0
