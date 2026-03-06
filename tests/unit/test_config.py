"""Unit tests for configuration (T060)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.config import (
    Configuration,
    ConfigurationError,
    load_config,
    save_config,
)


class TestConfigurationValidation:
    """Unit tests for Configuration validation."""

    def test_valid_configuration(self) -> None:
        """Valid configuration creates successfully."""
        config = Configuration(
            target_address="00:11:22:33:44:55",
            target_pin="1234",
            device_name="TestBridge",
            log_level="DEBUG",
            buffer_size=8192,
            reconnect_max_delay=60,
        )

        assert config.target_address == "00:11:22:33:44:55"
        assert config.target_pin == "1234"
        assert config.device_name == "TestBridge"

    def test_invalid_mac_address_fails(self) -> None:
        """Invalid MAC address raises ConfigurationError."""
        with pytest.raises(ConfigurationError) as exc:
            Configuration(target_address="invalid")

        assert "target_address" in str(exc.value)

    def test_missing_mac_address_fails(self) -> None:
        """Missing MAC address raises ConfigurationError."""
        with pytest.raises(ConfigurationError) as exc:
            Configuration(target_address="")

        assert "target_address" in str(exc.value)

    def test_invalid_log_level_fails(self) -> None:
        """Invalid log level raises ConfigurationError."""
        with pytest.raises(ConfigurationError) as exc:
            Configuration(
                target_address="00:11:22:33:44:55",
                log_level="INVALID",
            )

        assert "log_level" in str(exc.value)

    def test_buffer_size_too_small_fails(self) -> None:
        """Buffer size below minimum raises ConfigurationError."""
        with pytest.raises(ConfigurationError) as exc:
            Configuration(
                target_address="00:11:22:33:44:55",
                buffer_size=512,  # Min is 1024
            )

        assert "buffer_size" in str(exc.value)

    def test_buffer_size_too_large_fails(self) -> None:
        """Buffer size above maximum raises ConfigurationError."""
        with pytest.raises(ConfigurationError) as exc:
            Configuration(
                target_address="00:11:22:33:44:55",
                buffer_size=100000,  # Max is 65536
            )

        assert "buffer_size" in str(exc.value)


class TestStatusJSONSerialization:
    """Unit tests for status JSON serialization (T060)."""

    def test_configuration_to_dict(self) -> None:
        """Configuration serializes to dictionary."""
        config = Configuration(
            target_address="00:11:22:33:44:55",
            device_name="TestBridge",
        )

        data = config.to_dict()

        assert data["target_address"] == "00:11:22:33:44:55"
        assert data["device_name"] == "TestBridge"
        assert "target_pin" in data
        assert "log_level" in data

    def test_configuration_from_dict(self) -> None:
        """Configuration deserializes from dictionary."""
        data = {
            "target_address": "AA:BB:CC:DD:EE:FF",
            "device_name": "FromDict",
            "log_level": "WARNING",
        }

        config = Configuration.from_dict(data)

        assert config.target_address == "AA:BB:CC:DD:EE:FF"
        assert config.device_name == "FromDict"
        assert config.log_level == "WARNING"

    def test_configuration_round_trip(self) -> None:
        """Configuration survives dict round-trip."""
        original = Configuration(
            target_address="00:11:22:33:44:55",
            target_pin="9999",
            device_name="RoundTrip",
            log_level="ERROR",
            buffer_size=2048,
            reconnect_max_delay=45,
        )

        data = original.to_dict()
        restored = Configuration.from_dict(data)

        assert restored.target_address == original.target_address
        assert restored.target_pin == original.target_pin
        assert restored.device_name == original.device_name
        assert restored.log_level == original.log_level
        assert restored.buffer_size == original.buffer_size
        assert restored.reconnect_max_delay == original.reconnect_max_delay


class TestConfigurationPersistence:
    """Unit tests for configuration file I/O."""

    def test_save_and_load_config(self, tmp_path: Path) -> None:
        """Configuration can be saved and loaded."""
        config_file = tmp_path / "config.json"

        original = Configuration(
            target_address="00:11:22:33:44:55",
            device_name="SaveLoadTest",
        )

        save_config(original, config_file)
        loaded = load_config(config_file)

        assert loaded.target_address == original.target_address
        assert loaded.device_name == original.device_name

    def test_load_missing_file_fails(self, tmp_path: Path) -> None:
        """Loading missing file raises ConfigurationError."""
        config_file = tmp_path / "nonexistent.json"

        with pytest.raises(ConfigurationError) as exc:
            load_config(config_file)

        assert "not found" in str(exc.value)

    def test_load_invalid_json_fails(self, tmp_path: Path) -> None:
        """Loading invalid JSON raises ConfigurationError."""
        config_file = tmp_path / "invalid.json"
        config_file.write_text("{ invalid json }")

        with pytest.raises(ConfigurationError) as exc:
            load_config(config_file)

        assert "Invalid JSON" in str(exc.value)

    def test_saved_file_is_valid_json(self, tmp_path: Path) -> None:
        """Saved configuration file is valid JSON."""
        config_file = tmp_path / "config.json"

        config = Configuration(target_address="00:11:22:33:44:55")
        save_config(config, config_file)

        # Should parse as valid JSON
        with config_file.open() as f:
            data = json.load(f)

        assert isinstance(data, dict)
        assert data["target_address"] == "00:11:22:33:44:55"


class TestTcpKissConfiguration:
    """Unit tests for TCP KISS configuration (T062)."""

    def test_tcp_kiss_defaults(self) -> None:
        """TCP KISS has sensible defaults."""
        config = Configuration(target_address="00:11:22:33:44:55")

        assert config.tcp_kiss_enabled is True
        assert config.tcp_kiss_port == 8001
        assert config.tcp_kiss_host == "0.0.0.0"
        assert config.tcp_kiss_max_clients == 5

    def test_tcp_kiss_custom_values(self) -> None:
        """TCP KISS accepts custom configuration."""
        config = Configuration(
            target_address="00:11:22:33:44:55",
            tcp_kiss_enabled=True,
            tcp_kiss_port=9001,
            tcp_kiss_host="127.0.0.1",
            tcp_kiss_max_clients=10,
        )

        assert config.tcp_kiss_enabled is True
        assert config.tcp_kiss_port == 9001
        assert config.tcp_kiss_host == "127.0.0.1"
        assert config.tcp_kiss_max_clients == 10

    def test_tcp_kiss_disabled(self) -> None:
        """TCP KISS can be disabled."""
        config = Configuration(
            target_address="00:11:22:33:44:55",
            tcp_kiss_enabled=False,
        )

        assert config.tcp_kiss_enabled is False

    def test_invalid_tcp_kiss_port_low(self) -> None:
        """TCP KISS port below 1024 raises ConfigurationError."""
        with pytest.raises(ConfigurationError) as exc:
            Configuration(
                target_address="00:11:22:33:44:55",
                tcp_kiss_port=80,
            )

        assert "tcp_kiss_port" in str(exc.value)

    def test_invalid_tcp_kiss_port_high(self) -> None:
        """TCP KISS port above 65535 raises ConfigurationError."""
        with pytest.raises(ConfigurationError) as exc:
            Configuration(
                target_address="00:11:22:33:44:55",
                tcp_kiss_port=70000,
            )

        assert "tcp_kiss_port" in str(exc.value)

    def test_invalid_max_clients_low(self) -> None:
        """TCP KISS max_clients below 1 raises ConfigurationError."""
        with pytest.raises(ConfigurationError) as exc:
            Configuration(
                target_address="00:11:22:33:44:55",
                tcp_kiss_max_clients=0,
            )

        assert "tcp_kiss_max_clients" in str(exc.value)

    def test_invalid_max_clients_high(self) -> None:
        """TCP KISS max_clients above 20 raises ConfigurationError."""
        with pytest.raises(ConfigurationError) as exc:
            Configuration(
                target_address="00:11:22:33:44:55",
                tcp_kiss_max_clients=50,
            )

        assert "tcp_kiss_max_clients" in str(exc.value)

    def test_tcp_kiss_round_trip(self) -> None:
        """TCP KISS config survives dict round-trip."""
        original = Configuration(
            target_address="00:11:22:33:44:55",
            tcp_kiss_enabled=True,
            tcp_kiss_port=9001,
            tcp_kiss_host="192.168.1.1",
            tcp_kiss_max_clients=3,
        )

        data = original.to_dict()
        restored = Configuration.from_dict(data)

        assert restored.tcp_kiss_enabled == original.tcp_kiss_enabled
        assert restored.tcp_kiss_port == original.tcp_kiss_port
        assert restored.tcp_kiss_host == original.tcp_kiss_host
        assert restored.tcp_kiss_max_clients == original.tcp_kiss_max_clients
