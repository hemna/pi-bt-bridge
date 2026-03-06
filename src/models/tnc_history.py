"""TNC device history models for tracking paired TNC radios.

Provides TNCDevice and TNCHistory classes for persisting a list of
previously paired TNC devices, enabling quick switching between radios.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any, Final

logger = logging.getLogger("tnc_history")

# Default history file path
DEFAULT_HISTORY_PATH: Final[str] = "/etc/bt-bridge/tnc-history.json"

# Current history file format version
HISTORY_VERSION: Final[int] = 1

# Soft limit on number of history entries
MAX_HISTORY_ENTRIES: Final[int] = 20

# MAC address validation pattern
MAC_PATTERN: Final[re.Pattern[str]] = re.compile(r"^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$")

# Maximum friendly name length
MAX_FRIENDLY_NAME_LENGTH: Final[int] = 50


class TNCProtocol(Enum):
    """Protocol framing used by the TNC over Bluetooth SPP.

    KISS: Standard KISS framing with 0xC0 (FEND) delimiters.
        Used by most TNCs (TH-D74, Mobilinkd, etc.).
    HDLC: AX.25 HDLC-style framing with 0x7E flag delimiters.
        Used by some radios (VGC VR-N7600) that send raw HDLC
        frames rather than KISS-wrapped data.
    AUTO: Auto-detect on first received data from the TNC.
        Looks at the first delimiter byte to determine protocol.
    """

    KISS = "kiss"
    HDLC = "hdlc"
    AUTO = "auto"


@dataclass
class TNCDevice:
    """A known TNC radio device.

    Attributes:
        address: Bluetooth MAC address (primary identifier).
        bluetooth_name: Device name from Bluetooth discovery.
        friendly_name: User-assigned display name (optional).
        rfcomm_channel: RFCOMM channel for SPP connection (1-30).
        protocol: Framing protocol (kiss, hdlc, or auto-detect).
        last_used: Timestamp of last successful connection.
        added_at: Timestamp when first added to history.
    """

    address: str
    bluetooth_name: str
    friendly_name: str | None = None
    rfcomm_channel: int = 2
    protocol: TNCProtocol = TNCProtocol.AUTO
    last_used: datetime | None = None
    added_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        """Validate fields after initialization."""
        self.validate()

    def validate(self) -> None:
        """Validate TNCDevice fields.

        Raises:
            ValueError: If any field is invalid.
        """
        errors: list[str] = []

        # Normalize MAC address to uppercase
        self.address = self.address.upper()

        if not MAC_PATTERN.match(self.address):
            errors.append(
                f"address must be valid MAC format (XX:XX:XX:XX:XX:XX), got: {self.address}"
            )

        if not self.bluetooth_name:
            errors.append("bluetooth_name must not be empty")

        if not 1 <= self.rfcomm_channel <= 30:
            errors.append(f"rfcomm_channel must be 1-30, got: {self.rfcomm_channel}")

        if self.friendly_name is not None and (
            len(self.friendly_name) == 0 or len(self.friendly_name) > MAX_FRIENDLY_NAME_LENGTH
        ):
            errors.append(f"friendly_name must be 1-{MAX_FRIENDLY_NAME_LENGTH} characters")

        if errors:
            raise ValueError("; ".join(errors))

    @property
    def display_name(self) -> str:
        """Get the display name (friendly_name if set, else bluetooth_name)."""
        return self.friendly_name if self.friendly_name else self.bluetooth_name

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization.

        Returns:
            Dictionary with all fields serialized.
        """
        return {
            "address": self.address,
            "bluetooth_name": self.bluetooth_name,
            "friendly_name": self.friendly_name,
            "rfcomm_channel": self.rfcomm_channel,
            "protocol": self.protocol.value,
            "last_used": self.last_used.isoformat() if self.last_used else None,
            "added_at": self.added_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TNCDevice:
        """Create TNCDevice from dictionary.

        Args:
            data: Dictionary with device fields.

        Returns:
            TNCDevice instance.

        Raises:
            ValueError: If data is invalid.
        """
        last_used_str = data.get("last_used")
        added_at_str = data.get("added_at")

        last_used = datetime.fromisoformat(last_used_str) if last_used_str else None
        added_at = datetime.fromisoformat(added_at_str) if added_at_str else datetime.now(UTC)

        # Parse protocol (default to AUTO for backwards compat with old history files)
        protocol_str = data.get("protocol", "auto")
        try:
            protocol = TNCProtocol(protocol_str)
        except ValueError:
            protocol = TNCProtocol.AUTO

        return cls(
            address=str(data.get("address", "")),
            bluetooth_name=str(data.get("bluetooth_name", "")),
            friendly_name=data.get("friendly_name"),
            rfcomm_channel=int(data.get("rfcomm_channel", 2)),
            protocol=protocol,
            last_used=last_used,
            added_at=added_at,
        )


class TNCHistory:
    """Persistent collection of known TNC devices.

    Maintains an in-memory cache of TNC devices with write-through
    persistence to a JSON file.

    Attributes:
        path: File path for persistent storage.
    """

    def __init__(self, path: str | Path = DEFAULT_HISTORY_PATH) -> None:
        """Initialize TNC history.

        Args:
            path: Path to the history JSON file.
        """
        self._path = Path(path)
        self._devices: dict[str, TNCDevice] = {}
        self._load()

    @property
    def path(self) -> Path:
        """Get the history file path."""
        return self._path

    def _load(self) -> None:
        """Load history from JSON file.

        Handles missing files (creates empty history) and corrupted
        files (logs warning, uses empty history).
        """
        if not self._path.exists():
            logger.info("History file not found at %s, starting empty", self._path)
            return

        try:
            with self._path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            logger.warning(
                "Corrupted history file at %s: %s. Starting empty.",
                self._path,
                e,
            )
            return
        except OSError as e:
            logger.warning("Cannot read history file %s: %s", self._path, e)
            return

        if not isinstance(data, dict):
            logger.warning("History file has invalid format, starting empty")
            return

        # Check version for future migrations
        version = data.get("version", 1)
        if version != HISTORY_VERSION:
            logger.warning(
                "History file version %d != expected %d, attempting load anyway",
                version,
                HISTORY_VERSION,
            )

        devices_list = data.get("devices", [])
        if not isinstance(devices_list, list):
            logger.warning("History 'devices' field is not a list, starting empty")
            return

        for device_data in devices_list:
            try:
                device = TNCDevice.from_dict(device_data)
                self._devices[device.address] = device
            except (ValueError, TypeError, KeyError) as e:
                logger.warning("Skipping invalid history entry: %s", e)

        logger.info("Loaded %d TNC devices from history", len(self._devices))

    def _save(self) -> None:
        """Save history to JSON file.

        Creates parent directories if needed.

        Raises:
            OSError: If file cannot be written.
        """
        self._path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "version": HISTORY_VERSION,
            "devices": [device.to_dict() for device in self._devices.values()],
        }

        try:
            with self._path.open("w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
                f.write("\n")
        except OSError as e:
            logger.error("Failed to save history to %s: %s", self._path, e)
            raise

    def add(self, device: TNCDevice) -> None:
        """Add or update a device in history.

        If a device with the same address exists, it is updated.
        Saves to file after modification.

        Args:
            device: TNCDevice to add or update.
        """
        existing = self._devices.get(device.address)
        if existing:
            # Update existing entry, preserve added_at
            device.added_at = existing.added_at
            logger.info("Updating TNC device %s in history", device.address)
        else:
            logger.info("Adding new TNC device %s to history", device.address)

        self._devices[device.address] = device
        self._save()

    def remove(self, address: str) -> bool:
        """Remove a device from history.

        Args:
            address: MAC address of device to remove.

        Returns:
            True if device was removed, False if not found.
        """
        address = address.upper()
        if address in self._devices:
            del self._devices[address]
            self._save()
            logger.info("Removed TNC device %s from history", address)
            return True
        return False

    def get(self, address: str) -> TNCDevice | None:
        """Get a device by MAC address.

        Args:
            address: MAC address to look up.

        Returns:
            TNCDevice if found, None otherwise.
        """
        return self._devices.get(address.upper())

    def list_all(self) -> list[TNCDevice]:
        """Get all devices sorted by last_used (most recent first).

        Devices that have never been used sort to the end.

        Returns:
            List of TNCDevice instances.
        """
        return sorted(
            self._devices.values(),
            key=lambda d: d.last_used or datetime.min.replace(tzinfo=UTC),
            reverse=True,
        )

    def __len__(self) -> int:
        """Get number of devices in history."""
        return len(self._devices)

    def __contains__(self, address: str) -> bool:
        """Check if address is in history."""
        return address.upper() in self._devices
