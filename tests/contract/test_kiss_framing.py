"""Contract tests for KISS TNC protocol framing."""

from __future__ import annotations

from src.models.kiss import (
    FEND,
    FESC,
    MAX_FRAME_SIZE,
    MAX_PORT,
    TFEND,
    TFESC,
    KISSCommand,
    KISSParser,
)


class TestKISSSimpleFrame:
    """Contract: KISS frame parsing (simple frame) (T032)."""

    def test_simple_data_frame(self) -> None:
        """
        INPUT:  0xC0 0x00 0x48 0x45 0x4C 0x4C 0x4F 0xC0
        EXPECT: Frame with port=0, cmd=DATA_FRAME, data="HELLO"
        """
        parser = KISSParser()
        data = bytes([0xC0, 0x00, 0x48, 0x45, 0x4C, 0x4C, 0x4F, 0xC0])

        frames = parser.feed(data)

        assert len(frames) == 1
        frame = frames[0]
        assert frame.port == 0
        assert frame.command == KISSCommand.DATA_FRAME
        assert frame.data == b"HELLO"

    def test_empty_data_frame(self) -> None:
        """Frame with no payload (just command byte)."""
        parser = KISSParser()
        data = bytes([0xC0, 0x00, 0xC0])  # FEND + DATA_FRAME + FEND

        frames = parser.feed(data)

        assert len(frames) == 1
        assert frames[0].data == b""

    def test_tx_delay_command(self) -> None:
        """
        INPUT:  0xC0 0x01 0x1E 0xC0
        EXPECT: Frame with cmd=TX_DELAY, data=[0x1E] (300ms)
        """
        parser = KISSParser()
        data = bytes([0xC0, 0x01, 0x1E, 0xC0])

        frames = parser.feed(data)

        assert len(frames) == 1
        frame = frames[0]
        assert frame.port == 0
        assert frame.command == KISSCommand.TX_DELAY
        assert frame.data == bytes([0x1E])


class TestKISSEscapeSequences:
    """Contract: KISS escape sequences (T033)."""

    def test_escaped_fend_in_data(self) -> None:
        """
        INPUT:  0xC0 0x00 0x41 0xDB 0xDC 0x42 0xC0
        EXPECT: Frame with data = [0x41, 0xC0, 0x42] ("A" + FEND + "B")
        """
        parser = KISSParser()
        data = bytes([0xC0, 0x00, 0x41, 0xDB, 0xDC, 0x42, 0xC0])

        frames = parser.feed(data)

        assert len(frames) == 1
        frame = frames[0]
        assert frame.data == bytes([0x41, 0xC0, 0x42])

    def test_escaped_fesc_in_data(self) -> None:
        """
        INPUT:  0xC0 0x00 0xDB 0xDD 0xC0
        EXPECT: Frame with data = [0xDB]
        """
        parser = KISSParser()
        data = bytes([0xC0, 0x00, 0xDB, 0xDD, 0xC0])

        frames = parser.feed(data)

        assert len(frames) == 1
        assert frames[0].data == bytes([0xDB])

    def test_both_escapes_in_data(self) -> None:
        """Frame containing both FEND and FESC in data."""
        parser = KISSParser()
        # Data: FEND + FESC (0xC0 + 0xDB)
        data = bytes([0xC0, 0x00, 0xDB, 0xDC, 0xDB, 0xDD, 0xC0])

        frames = parser.feed(data)

        assert len(frames) == 1
        assert frames[0].data == bytes([0xC0, 0xDB])

    def test_invalid_escape_is_ignored(self) -> None:
        """
        INPUT:  0xC0 0x00 0x41 0xDB 0x42 0x43 0xC0
        EXPECT: Invalid escape byte (0x42) is discarded
        """
        parser = KISSParser()
        data = bytes([0xC0, 0x00, 0x41, 0xDB, 0x42, 0x43, 0xC0])

        frames = parser.feed(data)

        assert len(frames) == 1
        # 0x42 after FESC is invalid, should be discarded
        # Result: "A" + "C" (0x41 + 0x43)
        assert frames[0].data == bytes([0x41, 0x43])


class TestKISSMultipleFENDs:
    """Contract: KISS multiple FENDs and back-to-back frames (T034)."""

    def test_multiple_fends_as_sync(self) -> None:
        """
        INPUT:  0xC0 0xC0 0xC0 0x00 0x41 0xC0
        EXPECT: Single frame with data = [0x41] ("A")
        """
        parser = KISSParser()
        data = bytes([0xC0, 0xC0, 0xC0, 0x00, 0x41, 0xC0])

        frames = parser.feed(data)

        assert len(frames) == 1
        assert frames[0].data == bytes([0x41])

    def test_back_to_back_frames(self) -> None:
        """
        INPUT:  0xC0 0x00 0x41 0xC0 0xC0 0x00 0x42 0xC0
        EXPECT: Two frames: "A" and "B"
        """
        parser = KISSParser()
        data = bytes([0xC0, 0x00, 0x41, 0xC0, 0xC0, 0x00, 0x42, 0xC0])

        frames = parser.feed(data)

        assert len(frames) == 2
        assert frames[0].data == bytes([0x41])
        assert frames[1].data == bytes([0x42])

    def test_leading_garbage_is_discarded(self) -> None:
        """Garbage before first FEND should be discarded."""
        parser = KISSParser()
        # Garbage bytes before first FEND
        data = bytes([0x99, 0x88, 0x77, 0xC0, 0x00, 0x41, 0xC0])

        frames = parser.feed(data)

        assert len(frames) == 1
        assert frames[0].data == bytes([0x41])


class TestKISSPortExtraction:
    """Contract: KISS port number extraction (T035)."""

    def test_port_number_in_high_nibble(self) -> None:
        """
        INPUT:  0xC0 0x50 0x44 0x41 0x54 0x41 0xC0
        EXPECT: Frame with port=5, cmd=DATA_FRAME, data="DATA"
        """
        parser = KISSParser()
        data = bytes([0xC0, 0x50, 0x44, 0x41, 0x54, 0x41, 0xC0])

        frames = parser.feed(data)

        assert len(frames) == 1
        frame = frames[0]
        assert frame.port == 5
        assert frame.command == KISSCommand.DATA_FRAME
        assert frame.data == b"DATA"

    def test_port_0_is_default(self) -> None:
        """Port 0 is the default for single-port TNCs."""
        parser = KISSParser()
        data = bytes([0xC0, 0x00, 0x41, 0xC0])

        frames = parser.feed(data)

        assert frames[0].port == 0

    def test_port_15_is_maximum(self) -> None:
        """Port 15 (0xF0) is the maximum port number."""
        parser = KISSParser()
        data = bytes([0xC0, 0xF0, 0x41, 0xC0])

        frames = parser.feed(data)

        assert frames[0].port == 15

    def test_return_command_special_case(self) -> None:
        """
        INPUT:  0xC0 0xFF 0xC0
        EXPECT: Frame with cmd=RETURN
        """
        parser = KISSParser()
        data = bytes([0xC0, 0xFF, 0xC0])

        frames = parser.feed(data)

        assert len(frames) == 1
        assert frames[0].command == KISSCommand.RETURN


class TestKISSConstants:
    """Verify KISS protocol constants match specification."""

    def test_fend_value(self) -> None:
        """FEND must be 0xC0."""
        assert FEND == 0xC0

    def test_fesc_value(self) -> None:
        """FESC must be 0xDB."""
        assert FESC == 0xDB

    def test_tfend_value(self) -> None:
        """TFEND must be 0xDC."""
        assert TFEND == 0xDC

    def test_tfesc_value(self) -> None:
        """TFESC must be 0xDD."""
        assert TFESC == 0xDD

    def test_max_frame_size(self) -> None:
        """Max frame size should be 4096 bytes."""
        assert MAX_FRAME_SIZE == 4096

    def test_max_port(self) -> None:
        """Max port should be 15 (4-bit value)."""
        assert MAX_PORT == 15
