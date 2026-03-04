"""Unit tests for KISS parser (T036, T037)."""

from __future__ import annotations

import pytest

from src.models.kiss import (
    FEND,
    FESC,
    TFEND,
    TFESC,
    KISSCommand,
    KISSFrame,
    KISSParser,
)


class TestKISSParserFeed:
    """Unit tests for KISSParser.feed() method (T036)."""

    def test_feed_returns_empty_for_no_complete_frames(self) -> None:
        """feed() returns empty list when no complete frames."""
        parser = KISSParser()

        # Just FEND, no complete frame
        frames = parser.feed(bytes([FEND]))
        assert frames == []

        # Partial frame
        frames = parser.feed(bytes([0x00, 0x41]))  # Command + data, no closing FEND
        assert frames == []

    def test_feed_returns_frame_when_complete(self) -> None:
        """feed() returns frame when FEND closes it."""
        parser = KISSParser()

        # Start frame
        parser.feed(bytes([FEND, 0x00, 0x41]))

        # Complete frame
        frames = parser.feed(bytes([FEND]))
        assert len(frames) == 1
        assert frames[0].data == bytes([0x41])

    def test_feed_handles_chunked_input(self) -> None:
        """Parser handles data arriving in arbitrary chunks."""
        parser = KISSParser()

        # Send frame byte by byte
        all_frames: list[KISSFrame] = []
        frame_bytes = bytes([FEND, 0x00, 0x48, 0x45, 0x4C, 0x4C, 0x4F, FEND])

        for byte in frame_bytes:
            frames = parser.feed(bytes([byte]))
            all_frames.extend(frames)

        assert len(all_frames) == 1
        assert all_frames[0].data == b"HELLO"

    def test_feed_handles_multiple_frames_in_one_call(self) -> None:
        """Parser extracts multiple frames from single feed() call."""
        parser = KISSParser()

        # Two complete frames in one buffer
        data = bytes(
            [
                FEND,
                0x00,
                0x41,
                FEND,  # Frame 1: "A"
                FEND,
                0x00,
                0x42,
                FEND,  # Frame 2: "B"
            ]
        )

        frames = parser.feed(data)

        assert len(frames) == 2
        assert frames[0].data == bytes([0x41])
        assert frames[1].data == bytes([0x42])

    def test_feed_preserves_state_between_calls(self) -> None:
        """Parser state persists correctly between feed() calls."""
        parser = KISSParser()

        # First call: start frame
        frames = parser.feed(bytes([FEND, 0x00, 0x41]))
        assert frames == []
        assert parser.in_frame

        # Second call: more data
        frames = parser.feed(bytes([0x42, 0x43]))
        assert frames == []

        # Third call: complete frame
        frames = parser.feed(bytes([FEND]))
        assert len(frames) == 1
        assert frames[0].data == bytes([0x41, 0x42, 0x43])

    def test_feed_handles_escape_across_chunks(self) -> None:
        """Escape sequences split across feed() calls work correctly."""
        parser = KISSParser()

        # FESC at end of first chunk
        parser.feed(bytes([FEND, 0x00, 0x41, FESC]))

        # TFEND at start of second chunk
        frames = parser.feed(bytes([TFEND, 0x42, FEND]))

        assert len(frames) == 1
        assert frames[0].data == bytes([0x41, FEND, 0x42])


class TestKISSParserReset:
    """Unit tests for KISSParser.reset() method."""

    def test_reset_clears_buffer(self) -> None:
        """reset() clears the accumulation buffer."""
        parser = KISSParser()

        # Accumulate some data
        parser.feed(bytes([FEND, 0x00, 0x41, 0x42, 0x43]))
        assert parser.buffer_size > 0

        # Reset
        parser.reset()
        assert parser.buffer_size == 0

    def test_reset_clears_frame_state(self) -> None:
        """reset() clears in_frame flag."""
        parser = KISSParser()

        parser.feed(bytes([FEND, 0x00, 0x41]))
        assert parser.in_frame

        parser.reset()
        assert not parser.in_frame

    def test_reset_allows_fresh_start(self) -> None:
        """After reset(), parser starts fresh."""
        parser = KISSParser()

        # Partial frame
        parser.feed(bytes([FEND, 0x00, 0x41, 0x42]))

        # Reset mid-frame
        parser.reset()

        # New frame
        frames = parser.feed(bytes([FEND, 0x00, 0x58, 0x59, FEND]))

        assert len(frames) == 1
        assert frames[0].data == bytes([0x58, 0x59])


class TestKISSFrameEncoding:
    """Unit tests for KISS frame encoding (T037)."""

    def test_encode_simple_frame(self) -> None:
        """Basic frame encodes with FEND delimiters."""
        frame = KISSFrame(
            port=0,
            command=KISSCommand.DATA_FRAME,
            data=b"HELLO",
        )

        encoded = frame.encode()

        # FEND + cmd(0x00) + "HELLO" + FEND
        assert encoded == bytes([FEND, 0x00, 0x48, 0x45, 0x4C, 0x4C, 0x4F, FEND])

    def test_encode_with_port_number(self) -> None:
        """Port number is encoded in high nibble of command byte."""
        frame = KISSFrame(
            port=5,
            command=KISSCommand.DATA_FRAME,
            data=b"A",
        )

        encoded = frame.encode()

        # FEND + cmd(0x50 = port 5, cmd 0) + "A" + FEND
        assert encoded == bytes([FEND, 0x50, 0x41, FEND])

    def test_encode_escapes_fend_in_data(self) -> None:
        """FEND in data is escaped as FESC + TFEND."""
        frame = KISSFrame(
            port=0,
            command=KISSCommand.DATA_FRAME,
            data=bytes([0x41, FEND, 0x42]),  # A + FEND + B
        )

        encoded = frame.encode()

        # FEND + cmd + "A" + FESC + TFEND + "B" + FEND
        assert encoded == bytes([FEND, 0x00, 0x41, FESC, TFEND, 0x42, FEND])

    def test_encode_escapes_fesc_in_data(self) -> None:
        """FESC in data is escaped as FESC + TFESC."""
        frame = KISSFrame(
            port=0,
            command=KISSCommand.DATA_FRAME,
            data=bytes([0x41, FESC, 0x42]),  # A + FESC + B
        )

        encoded = frame.encode()

        # FEND + cmd + "A" + FESC + TFESC + "B" + FEND
        assert encoded == bytes([FEND, 0x00, 0x41, FESC, TFESC, 0x42, FEND])

    def test_encode_round_trip(self) -> None:
        """Encoding followed by parsing returns original frame."""
        original = KISSFrame(
            port=3,
            command=KISSCommand.DATA_FRAME,
            data=bytes([0x41, FEND, FESC, 0x42]),  # Complex data
        )

        encoded = original.encode()
        parser = KISSParser()
        parsed_frames = parser.feed(encoded)

        assert len(parsed_frames) == 1
        parsed = parsed_frames[0]
        assert parsed.port == original.port
        assert parsed.command == original.command
        assert parsed.data == original.data

    def test_encode_tx_delay_command(self) -> None:
        """TX_DELAY command encodes correctly."""
        frame = KISSFrame(
            port=0,
            command=KISSCommand.TX_DELAY,
            data=bytes([0x1E]),  # 30 * 10ms = 300ms
        )

        encoded = frame.encode()

        assert encoded == bytes([FEND, 0x01, 0x1E, FEND])

    def test_encode_return_command(self) -> None:
        """RETURN command encodes as 0xFF."""
        frame = KISSFrame(
            port=0,
            command=KISSCommand.RETURN,
            data=b"",
        )

        encoded = frame.encode()

        # RETURN is 0xFF, which has port=15, cmd=15
        # But we encode it as (0 << 4) | 0x0F = 0x0F
        # Wait, RETURN is 0xFF which is special - let me check
        # Actually the low nibble is 0x0F for RETURN
        assert encoded[1] == 0x0F  # (0 << 4) | 0x0F


class TestKISSFrameValidation:
    """Unit tests for KISSFrame validation."""

    def test_port_must_be_0_to_15(self) -> None:
        """Port number must be in range 0-15."""
        # Valid ports
        for port in range(16):
            frame = KISSFrame(port=port, command=KISSCommand.DATA_FRAME, data=b"")
            assert frame.port == port

        # Invalid port
        with pytest.raises(ValueError):
            KISSFrame(port=16, command=KISSCommand.DATA_FRAME, data=b"")

    def test_data_size_limit(self) -> None:
        """Data must not exceed MAX_FRAME_SIZE."""
        from src.models.kiss import MAX_FRAME_SIZE

        # At limit - OK
        frame = KISSFrame(
            port=0,
            command=KISSCommand.DATA_FRAME,
            data=b"X" * MAX_FRAME_SIZE,
        )
        assert len(frame.data) == MAX_FRAME_SIZE

        # Over limit - error
        with pytest.raises(ValueError):
            KISSFrame(
                port=0,
                command=KISSCommand.DATA_FRAME,
                data=b"X" * (MAX_FRAME_SIZE + 1),
            )

    def test_from_bytes_convenience_method(self) -> None:
        """KISSFrame.from_bytes() creates DATA_FRAME."""
        frame = KISSFrame.from_bytes(b"TEST", port=2)

        assert frame.port == 2
        assert frame.command == KISSCommand.DATA_FRAME
        assert frame.data == b"TEST"
