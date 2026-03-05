"""Configuration management for the BT bridge daemon."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Final

# Default configuration path
DEFAULT_CONFIG_PATH: Final[str] = "/etc/bt-bridge/config.json"

# MAC address validation pattern
MAC_PATTERN: Final[re.Pattern[str]] = re.compile(r"^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$")

# Valid log levels
VALID_LOG_LEVELS: Final[frozenset[str]] = frozenset({"DEBUG", "INFO", "WARNING", "ERROR"})


class ConfigurationError(Exception):
    """Raised when configuration is invalid or cannot be loaded."""

    pass


@dataclass
class Configuration:
    """
    Persisted daemon configuration.

    Attributes:
        target_address: BT Classic target MAC address (required).
        target_pin: Pairing PIN if needed.
        rfcomm_channel: RFCOMM channel for SPP connection (use sdptool to find).
        device_name: Advertised BLE device name.
        log_level: Logging verbosity (DEBUG, INFO, WARNING, ERROR).
        log_file: Log file path, None for stdout.
        buffer_size: Queue buffer size in bytes.
        reconnect_max_delay: Maximum reconnect wait in seconds.
        status_socket: Unix socket path for status queries.
        web_enabled: Enable web interface.
        web_port: HTTP port for web interface.
        web_host: Host to bind web interface to.
    """

    target_address: str
    target_pin: str = "0000"
    rfcomm_channel: int = 2  # TH-D74 uses channel 2 for SPP/Serial Port
    device_name: str = "PiBTBridge"
    log_level: str = "INFO"
    log_file: str | None = None
    buffer_size: int = 4096
    reconnect_max_delay: int = 30
    status_socket: str = "/var/run/bt-bridge.sock"
    web_enabled: bool = True
    web_port: int = 8080
    web_host: str = "0.0.0.0"

    def __post_init__(self) -> None:
        """Validate configuration fields."""
        self.validate()

    def validate(self) -> None:
        """
        Validate all configuration fields.

        Raises:
            ConfigurationError: If any field is invalid.
        """
        errors: list[str] = []

        # Validate target_address (required, must be valid MAC)
        if not self.target_address:
            errors.append("target_address is required")
        elif not MAC_PATTERN.match(self.target_address):
            errors.append(
                f"target_address must be valid MAC format (XX:XX:XX:XX:XX:XX), "
                f"got: {self.target_address}"
            )

        # Validate log_level
        if self.log_level.upper() not in VALID_LOG_LEVELS:
            errors.append(
                f"log_level must be one of {sorted(VALID_LOG_LEVELS)}, got: {self.log_level}"
            )

        # Validate buffer_size (1KB - 64KB)
        if not 1024 <= self.buffer_size <= 65536:
            errors.append(f"buffer_size must be 1024-65536, got: {self.buffer_size}")

        # Validate reconnect_max_delay (5s - 300s)
        if not 5 <= self.reconnect_max_delay <= 300:
            errors.append(f"reconnect_max_delay must be 5-300, got: {self.reconnect_max_delay}")

        # Validate rfcomm_channel (1-30)
        if not 1 <= self.rfcomm_channel <= 30:
            errors.append(f"rfcomm_channel must be 1-30, got: {self.rfcomm_channel}")

        # Validate web_port (1024-65535)
        if not 1024 <= self.web_port <= 65535:
            errors.append(f"web_port must be 1024-65535, got: {self.web_port}")

        if errors:
            raise ConfigurationError("; ".join(errors))

    def to_dict(self) -> dict[str, object]:
        """Convert configuration to dictionary for serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> Configuration:
        """
        Create Configuration from dictionary.

        Args:
            data: Dictionary with configuration fields.

        Returns:
            Configuration instance.

        Raises:
            ConfigurationError: If data is invalid.
        """
        try:
            return cls(
                target_address=str(data.get("target_address", "")),
                target_pin=str(data.get("target_pin", "0000")),
                rfcomm_channel=int(data.get("rfcomm_channel", 2)),  # type: ignore[arg-type]
                device_name=str(data.get("device_name", "PiBTBridge")),
                log_level=str(data.get("log_level", "INFO")),
                log_file=data.get("log_file"),  # type: ignore[arg-type]
                buffer_size=int(data.get("buffer_size", 4096)),  # type: ignore[arg-type]
                reconnect_max_delay=int(data.get("reconnect_max_delay", 30)),  # type: ignore[arg-type]
                status_socket=str(data.get("status_socket", "/var/run/bt-bridge.sock")),
                web_enabled=bool(data.get("web_enabled", True)),
                web_port=int(data.get("web_port", 8080)),  # type: ignore[arg-type]
                web_host=str(data.get("web_host", "0.0.0.0")),
            )
        except (TypeError, ValueError) as e:
            raise ConfigurationError(f"Invalid configuration data: {e}") from e


def load_config(path: str | Path = DEFAULT_CONFIG_PATH) -> Configuration:
    """
    Load configuration from JSON file.

    Args:
        path: Path to configuration file.

    Returns:
        Configuration instance.

    Raises:
        ConfigurationError: If file cannot be read or parsed.
    """
    config_path = Path(path)

    if not config_path.exists():
        raise ConfigurationError(f"Configuration file not found: {config_path}")

    try:
        with config_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise ConfigurationError(f"Invalid JSON in {config_path}: {e}") from e
    except OSError as e:
        raise ConfigurationError(f"Cannot read {config_path}: {e}") from e

    if not isinstance(data, dict):
        raise ConfigurationError(f"Configuration must be a JSON object, got: {type(data).__name__}")

    return Configuration.from_dict(data)


def save_config(config: Configuration, path: str | Path = DEFAULT_CONFIG_PATH) -> None:
    """
    Save configuration to JSON file.

    Args:
        config: Configuration to save.
        path: Path to configuration file.

    Raises:
        ConfigurationError: If file cannot be written.
    """
    config_path = Path(path)

    # Ensure parent directory exists
    config_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with config_path.open("w", encoding="utf-8") as f:
            json.dump(config.to_dict(), f, indent=2)
            f.write("\n")  # Trailing newline
    except OSError as e:
        raise ConfigurationError(f"Cannot write {config_path}: {e}") from e
