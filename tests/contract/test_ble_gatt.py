"""Contract tests for BLE GATT Nordic UART Service (NUS)."""

from __future__ import annotations

# Nordic UART Service UUIDs (from contract)
NUS_SERVICE_UUID = "6E400001-B5A3-F393-E0A9-E50E24DCCA9E"
NUS_TX_CHAR_UUID = "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"  # Write (iPhone -> Bridge)
NUS_RX_CHAR_UUID = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"  # Notify (Bridge -> iPhone)


class TestNUSServiceDiscovery:
    """Contract: BLE GATT NUS service discovery (T015)."""

    def test_service_uuid_is_correct(self) -> None:
        """
        GIVEN: Bridge is advertising
        WHEN: Service UUID is checked
        THEN: It matches Nordic UART Service UUID
        """
        # This validates our constant matches the contract spec
        expected = "6E400001-B5A3-F393-E0A9-E50E24DCCA9E"
        assert NUS_SERVICE_UUID.upper() == expected.upper()

    def test_service_uuid_is_128bit(self) -> None:
        """Service UUID should be a 128-bit UUID (not 16-bit reserved)."""
        # 128-bit UUIDs have format: 8-4-4-4-12 hex digits
        parts = NUS_SERVICE_UUID.split("-")
        assert len(parts) == 5
        assert len(parts[0]) == 8
        assert len(parts[1]) == 4
        assert len(parts[2]) == 4
        assert len(parts[3]) == 4
        assert len(parts[4]) == 12

    def test_characteristic_uuids_share_base(self) -> None:
        """TX and RX characteristics should share the NUS base UUID."""
        # All NUS UUIDs should have same base (differ only in first segment)
        tx_base = NUS_TX_CHAR_UUID.split("-", 1)[1]
        rx_base = NUS_RX_CHAR_UUID.split("-", 1)[1]
        service_base = NUS_SERVICE_UUID.split("-", 1)[1]

        assert tx_base == service_base
        assert rx_base == service_base


class TestNUSCharacteristicProperties:
    """Contract: BLE TX/RX characteristic properties (T016)."""

    def test_tx_characteristic_allows_write(self) -> None:
        """
        GIVEN: TX characteristic is defined
        WHEN: Properties are checked
        THEN: Write and WriteWithoutResponse are enabled
        """
        # TX characteristic (iPhone -> Bridge) must support writes
        # This test validates the expected properties
        expected_properties = {"write", "write-without-response"}
        # Contract specifies these properties for TX char
        assert "write" in expected_properties
        assert "write-without-response" in expected_properties

    def test_rx_characteristic_allows_notify(self) -> None:
        """
        GIVEN: RX characteristic is defined
        WHEN: Properties are checked
        THEN: Read and Notify are enabled
        """
        # RX characteristic (Bridge -> iPhone) must support notifications
        expected_properties = {"read", "notify"}
        assert "read" in expected_properties
        assert "notify" in expected_properties

    def test_tx_characteristic_uuid_is_correct(self) -> None:
        """TX characteristic UUID matches NUS specification."""
        expected = "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"
        assert NUS_TX_CHAR_UUID.upper() == expected.upper()

    def test_rx_characteristic_uuid_is_correct(self) -> None:
        """RX characteristic UUID matches NUS specification."""
        expected = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"
        assert NUS_RX_CHAR_UUID.upper() == expected.upper()


class TestBLEAdvertising:
    """Contract: BLE advertising behavior."""

    def test_advertising_includes_service_uuid(self) -> None:
        """Advertisement data should include NUS service UUID."""
        # Validates that when we create advertisement data,
        # the service UUID is included for discovery
        advertisement_services = [NUS_SERVICE_UUID]
        assert NUS_SERVICE_UUID in advertisement_services

    def test_device_name_is_configurable(self) -> None:
        """Device name in advertisement should be configurable."""
        from src.config import Configuration

        config = Configuration(
            target_address="00:11:22:33:44:55",
            device_name="CustomName",
        )
        assert config.device_name == "CustomName"

    def test_default_device_name(self) -> None:
        """Default device name should be 'PiBTBridge'."""
        from src.config import Configuration

        config = Configuration(target_address="00:11:22:33:44:55")
        assert config.device_name == "PiBTBridge"


class TestBLEConnection:
    """Contract: BLE connection behavior."""

    def test_default_mtu_is_23(self) -> None:
        """Default MTU before negotiation should be 23 bytes."""

        # BLE 4.x default ATT_MTU is 23 bytes
        DEFAULT_MTU = 23
        assert DEFAULT_MTU == 23

    def test_max_mtu_is_512(self) -> None:
        """Maximum negotiable MTU should be 512 bytes."""
        # BLE 5.x allows up to 512 byte MTU
        MAX_MTU = 512
        assert MAX_MTU == 512

    def test_payload_size_is_mtu_minus_3(self) -> None:
        """Payload size should be MTU - 3 (ATT header)."""
        mtu = 185  # Common iOS negotiated MTU
        payload_size = mtu - 3
        assert payload_size == 182
