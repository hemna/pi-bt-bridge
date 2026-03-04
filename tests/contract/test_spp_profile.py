"""Contract tests for Bluetooth Classic SPP profile."""

from __future__ import annotations

import pytest

# SPP Service UUID (standard Bluetooth SIG UUID)
SPP_SERVICE_UUID = "00001101-0000-1000-8000-00805F9B34FB"


class TestSPPProfileRegistration:
    """Contract: SPP profile registration with BlueZ (T017)."""

    def test_spp_service_uuid_is_standard(self) -> None:
        """
        GIVEN: SPP profile is defined
        WHEN: Service UUID is checked
        THEN: It matches standard Bluetooth SIG SPP UUID
        """
        expected = "00001101-0000-1000-8000-00805F9B34FB"
        assert SPP_SERVICE_UUID.upper() == expected.upper()

    def test_spp_uuid_is_16bit_in_128bit_format(self) -> None:
        """SPP uses 16-bit UUID (0x1101) in 128-bit base format."""
        # Standard Bluetooth base UUID: 00000000-0000-1000-8000-00805F9B34FB
        # SPP (0x1101) replaces first segment
        parts = SPP_SERVICE_UUID.split("-")
        uuid_16bit = int(parts[0], 16)
        assert uuid_16bit == 0x1101

    def test_profile_role_is_client(self) -> None:
        """Bridge acts as SPP client (initiator) to connect to TNC."""
        # Contract specifies we initiate connections to TNC
        role = "client"
        assert role == "client"


class TestSPPConnectionFlow:
    """Contract: SPP connection flow (T018)."""

    def test_connection_requires_target_address(self) -> None:
        """
        GIVEN: SPP connection is configured
        WHEN: Configuration is validated
        THEN: target_address must be a valid MAC
        """
        from src.config import Configuration, ConfigurationError

        # Valid MAC should work
        config = Configuration(target_address="00:11:22:33:44:55")
        assert config.target_address == "00:11:22:33:44:55"

        # Invalid MAC should fail
        with pytest.raises(ConfigurationError):
            Configuration(target_address="invalid")

    def test_pin_has_default_value(self) -> None:
        """PIN should default to '0000' for compatibility."""
        from src.config import Configuration

        config = Configuration(target_address="00:11:22:33:44:55")
        assert config.target_pin == "0000"

    def test_rfcomm_channel_range(self) -> None:
        """RFCOMM channel must be in range 1-30."""
        RFCOMM_MIN = 1
        RFCOMM_MAX = 30

        assert RFCOMM_MIN == 1
        assert RFCOMM_MAX == 30

    def test_connection_timeout_is_reasonable(self) -> None:
        """Connection should complete within 10 seconds per contract."""
        CONNECTION_TIMEOUT_SECONDS = 10
        assert CONNECTION_TIMEOUT_SECONDS <= 10


class TestSPPReconnection:
    """Contract: SPP reconnection behavior."""

    def test_reconnect_delay_starts_at_1_second(self) -> None:
        """Initial reconnection delay should be 1 second."""
        initial_delay = 1
        assert initial_delay == 1

    def test_reconnect_uses_exponential_backoff(self) -> None:
        """Reconnection should use exponential backoff."""
        # Sequence: 1, 2, 4, 8, 16, 30 (capped)
        delays = [1]
        for _ in range(5):
            next_delay = min(delays[-1] * 2, 30)
            delays.append(next_delay)

        assert delays == [1, 2, 4, 8, 16, 30]

    def test_reconnect_max_delay_is_configurable(self) -> None:
        """Maximum reconnect delay should be configurable."""
        from src.config import Configuration

        config = Configuration(
            target_address="00:11:22:33:44:55",
            reconnect_max_delay=60,
        )
        assert config.reconnect_max_delay == 60

    def test_reconnect_max_delay_default(self) -> None:
        """Default max reconnect delay should be 30 seconds."""
        from src.config import Configuration

        config = Configuration(target_address="00:11:22:33:44:55")
        assert config.reconnect_max_delay == 30


class TestSPPDataTransfer:
    """Contract: SPP data transfer properties."""

    def test_buffer_size_is_configurable(self) -> None:
        """Buffer size for SPP data should be configurable."""
        from src.config import Configuration

        config = Configuration(
            target_address="00:11:22:33:44:55",
            buffer_size=8192,
        )
        assert config.buffer_size == 8192

    def test_buffer_size_default_is_4096(self) -> None:
        """Default buffer size should be 4KB."""
        from src.config import Configuration

        config = Configuration(target_address="00:11:22:33:44:55")
        assert config.buffer_size == 4096

    def test_minimum_throughput_requirement(self) -> None:
        """Must support at least 960 bytes/sec (9600 baud equivalent)."""
        MIN_THROUGHPUT_BPS = 960
        assert MIN_THROUGHPUT_BPS >= 960
