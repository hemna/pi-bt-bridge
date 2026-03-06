"""Unit tests for HDLC frame parser and KISS<->HDLC translation."""

from __future__ import annotations

from src.models.hdlc import HDLC_FLAG, HDLCFrame, HDLCParser, detect_protocol
from src.models.kiss import FEND, KISSCommand, KISSFrame


class TestHDLCParser:
    """Tests for the HDLCParser state machine."""

    def test_parse_single_frame(self) -> None:
        """Single frame between two 7E flags."""
        parser = HDLCParser()
        data = bytes([HDLC_FLAG, 0x00, 0xAA, 0xBB, HDLC_FLAG])
        frames = parser.feed(data)
        assert len(frames) == 1
        assert frames[0].data == bytes([0x00, 0xAA, 0xBB])

    def test_parse_multiple_frames(self) -> None:
        """Two consecutive frames."""
        parser = HDLCParser()
        data = bytes(
            [
                HDLC_FLAG,
                0x01,
                0x02,
                HDLC_FLAG,
                HDLC_FLAG,
                0x03,
                0x04,
                HDLC_FLAG,
            ]
        )
        frames = parser.feed(data)
        assert len(frames) == 2
        assert frames[0].data == bytes([0x01, 0x02])
        assert frames[1].data == bytes([0x03, 0x04])

    def test_consecutive_flags_ignored(self) -> None:
        """Multiple 7E flags in a row produce no empty frames."""
        parser = HDLCParser()
        data = bytes([HDLC_FLAG, HDLC_FLAG, HDLC_FLAG, 0x42, HDLC_FLAG])
        frames = parser.feed(data)
        assert len(frames) == 1
        assert frames[0].data == bytes([0x42])

    def test_incremental_feed(self) -> None:
        """Frame split across multiple feed() calls."""
        parser = HDLCParser()
        assert parser.feed(bytes([HDLC_FLAG, 0xAA])) == []
        assert parser.feed(bytes([0xBB])) == []
        frames = parser.feed(bytes([0xCC, HDLC_FLAG]))
        assert len(frames) == 1
        assert frames[0].data == bytes([0xAA, 0xBB, 0xCC])

    def test_data_before_first_flag_ignored(self) -> None:
        """Bytes before the first 7E flag are discarded."""
        parser = HDLCParser()
        data = bytes([0xFF, 0xFE, HDLC_FLAG, 0x42, HDLC_FLAG])
        frames = parser.feed(data)
        assert len(frames) == 1
        assert frames[0].data == bytes([0x42])

    def test_empty_frame_ignored(self) -> None:
        """Two flags with nothing in between produce no frame."""
        parser = HDLCParser()
        frames = parser.feed(bytes([HDLC_FLAG, HDLC_FLAG]))
        assert len(frames) == 0

    def test_oversize_frame_discarded(self) -> None:
        """Frame exceeding max buffer size is discarded."""
        parser = HDLCParser(max_buffer_size=8)
        data = bytes([HDLC_FLAG]) + bytes(range(10)) + bytes([HDLC_FLAG])
        frames = parser.feed(data)
        assert len(frames) == 0

    def test_reset_clears_state(self) -> None:
        """reset() discards partial frame."""
        parser = HDLCParser()
        parser.feed(bytes([HDLC_FLAG, 0xAA, 0xBB]))
        assert parser.in_frame
        parser.reset()
        assert not parser.in_frame
        assert parser.buffer_size == 0

    def test_buffer_size_tracking(self) -> None:
        """buffer_size reflects accumulated payload bytes."""
        parser = HDLCParser()
        parser.feed(bytes([HDLC_FLAG, 0x01, 0x02, 0x03]))
        assert parser.buffer_size == 3
        assert parser.in_frame

    def test_frame_has_timestamp(self) -> None:
        """Parsed frames have a timestamp."""
        parser = HDLCParser()
        frames = parser.feed(bytes([HDLC_FLAG, 0x42, HDLC_FLAG]))
        assert frames[0].timestamp is not None

    def test_real_vgc_frame_structure(self) -> None:
        """Parse a frame resembling real VR-N7600 data (7E 00 9C 71 12 ... 7E)."""
        parser = HDLCParser()
        # Simulated VGC frame with the constant 9c7112 header pattern
        payload = bytes([0x00, 0x9C, 0x71, 0x12, 0x22, 0xED, 0xEC, 0xBA])
        data = bytes([HDLC_FLAG]) + payload + bytes([HDLC_FLAG])
        frames = parser.feed(data)
        assert len(frames) == 1
        assert frames[0].data == payload


class TestHDLCFrameEncode:
    """Tests for HDLCFrame.encode()."""

    def test_encode_wraps_in_flags(self) -> None:
        """encode() produces 7E [data] 7E."""
        frame = HDLCFrame(data=bytes([0x00, 0xAA, 0xBB]))
        encoded = frame.encode()
        assert encoded[0] == HDLC_FLAG
        assert encoded[-1] == HDLC_FLAG
        assert encoded[1:-1] == bytes([0x00, 0xAA, 0xBB])

    def test_encode_empty_data(self) -> None:
        """Empty payload encodes as just two flags."""
        frame = HDLCFrame(data=b"")
        assert frame.encode() == bytes([HDLC_FLAG, HDLC_FLAG])


class TestHDLCToKISS:
    """Tests for HDLC -> KISS translation (radio -> phone direction)."""

    def test_to_kiss_frame_port_zero(self) -> None:
        """HDLC frame converts to KISS port 0 DATA_FRAME."""
        hdlc = HDLCFrame(data=bytes([0x00, 0xAA, 0xBB, 0xCC]))
        kiss = hdlc.to_kiss_frame()
        assert kiss.port == 0
        assert kiss.command == KISSCommand.DATA_FRAME
        assert kiss.data == bytes([0x00, 0xAA, 0xBB, 0xCC])

    def test_to_kiss_frame_encode_produces_c0(self) -> None:
        """Converted frame encodes with 0xC0 KISS delimiters."""
        hdlc = HDLCFrame(data=bytes([0x00, 0x42]))
        kiss = hdlc.to_kiss_frame()
        encoded = kiss.encode()
        assert encoded[0] == FEND
        assert encoded[-1] == FEND


class TestKISSToHDLC:
    """Tests for KISS -> HDLC translation (phone -> radio direction)."""

    def test_from_kiss_frame_includes_cmd_byte(self) -> None:
        """KISS frame converts to HDLC with command byte prepended."""
        kiss = KISSFrame(port=0, command=KISSCommand.DATA_FRAME, data=b"\xaa\xbb")
        hdlc = HDLCFrame.from_kiss_frame(kiss)
        # cmd byte = (0 << 4) | 0 = 0x00
        assert hdlc.data == bytes([0x00, 0xAA, 0xBB])

    def test_from_kiss_frame_preserves_port(self) -> None:
        """Non-zero KISS port is encoded in the HDLC command byte."""
        kiss = KISSFrame(port=1, command=KISSCommand.DATA_FRAME, data=b"\x42")
        hdlc = HDLCFrame.from_kiss_frame(kiss)
        # cmd byte = (1 << 4) | 0 = 0x10
        assert hdlc.data[0] == 0x10
        assert hdlc.data[1:] == b"\x42"

    def test_from_kiss_encode_wraps_in_7e(self) -> None:
        """Converted HDLC frame encodes with 0x7E flags."""
        kiss = KISSFrame(port=0, command=KISSCommand.DATA_FRAME, data=b"\x42")
        hdlc = HDLCFrame.from_kiss_frame(kiss)
        encoded = hdlc.encode()
        assert encoded[0] == HDLC_FLAG
        assert encoded[-1] == HDLC_FLAG

    def test_roundtrip_kiss_hdlc_kiss(self) -> None:
        """KISS -> HDLC -> KISS roundtrip preserves the data."""
        original = KISSFrame(port=0, command=KISSCommand.DATA_FRAME, data=b"\xde\xad\xbe\xef")
        hdlc = HDLCFrame.from_kiss_frame(original)
        recovered = hdlc.to_kiss_frame()
        # The recovered KISS frame data includes the command byte from HDLC
        # which is the same as what the original KISS frame would produce
        assert recovered.port == 0
        assert recovered.command == KISSCommand.DATA_FRAME
        # data = [0x00 (cmd byte), 0xDE, 0xAD, 0xBE, 0xEF]
        assert recovered.data == bytes([0x00]) + b"\xde\xad\xbe\xef"


class TestDetectProtocol:
    """Tests for auto-detection of protocol framing."""

    def test_detect_kiss(self) -> None:
        """0xC0 byte detected as KISS."""
        assert detect_protocol(bytes([0xC0, 0x00, 0x42])) == "kiss"

    def test_detect_hdlc(self) -> None:
        """0x7E byte detected as HDLC."""
        assert detect_protocol(bytes([0x7E, 0x00, 0x42])) == "hdlc"

    def test_detect_unknown_empty(self) -> None:
        """Empty data returns unknown."""
        assert detect_protocol(b"") == "unknown"

    def test_detect_unknown_no_delimiter(self) -> None:
        """Data without 0xC0 or 0x7E returns unknown."""
        assert detect_protocol(bytes([0x01, 0x02, 0x03])) == "unknown"

    def test_detect_first_delimiter_wins(self) -> None:
        """First delimiter byte encountered determines protocol."""
        # 0x7E appears before 0xC0
        assert detect_protocol(bytes([0x01, 0x7E, 0xC0])) == "hdlc"
        # 0xC0 appears before 0x7E
        assert detect_protocol(bytes([0x01, 0xC0, 0x7E])) == "kiss"

    def test_detect_with_bytearray(self) -> None:
        """Accepts bytearray input."""
        assert detect_protocol(bytearray([0xC0, 0x00])) == "kiss"


class TestTNCProtocolInTNCDevice:
    """Tests for protocol field in TNCDevice model."""

    def test_default_protocol_is_auto(self) -> None:
        """New TNCDevice defaults to AUTO protocol."""
        from src.models.tnc_history import TNCDevice, TNCProtocol

        device = TNCDevice(address="AA:BB:CC:DD:EE:FF", bluetooth_name="Test")
        assert device.protocol == TNCProtocol.AUTO

    def test_protocol_serialization(self) -> None:
        """Protocol is serialized to/from dict correctly."""
        from src.models.tnc_history import TNCDevice, TNCProtocol

        device = TNCDevice(
            address="AA:BB:CC:DD:EE:FF",
            bluetooth_name="Test",
            protocol=TNCProtocol.HDLC,
        )
        d = device.to_dict()
        assert d["protocol"] == "hdlc"

        restored = TNCDevice.from_dict(d)
        assert restored.protocol == TNCProtocol.HDLC

    def test_protocol_backwards_compat(self) -> None:
        """Missing protocol field in dict defaults to AUTO."""
        from src.models.tnc_history import TNCDevice, TNCProtocol

        d = {
            "address": "AA:BB:CC:DD:EE:FF",
            "bluetooth_name": "OldDevice",
            "rfcomm_channel": 2,
        }
        device = TNCDevice.from_dict(d)
        assert device.protocol == TNCProtocol.AUTO

    def test_invalid_protocol_in_dict_defaults_to_auto(self) -> None:
        """Invalid protocol string in dict defaults to AUTO."""
        from src.models.tnc_history import TNCDevice, TNCProtocol

        d = {
            "address": "AA:BB:CC:DD:EE:FF",
            "bluetooth_name": "Test",
            "protocol": "bogus",
        }
        device = TNCDevice.from_dict(d)
        assert device.protocol == TNCProtocol.AUTO
